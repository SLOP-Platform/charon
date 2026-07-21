"""Build a ``litellm.Router`` from the gateway's existing config — the ADR-0017 adopt.

``litellm.Router`` (imported as a LIBRARY, never its proxy-server/FastAPI/Prisma stack)
provides the commodity plane Charon hand-rolls: provider failover, cooldown/``allowed_fails``,
retry, mechanical ordering and a cost callback. This module maps Charon's live routing config
onto a ``Router`` while PRESERVING the money-path's security + policy controls at build time.

The ``litellm_plane`` outbound path is a NEW way for the product to reach providers, so it
MUST enforce the SAME egress controls the live money-path enforces at
``routing_policy.route_from_spec`` — otherwise it would be a bypass of the allowlist. It does:

  1. **base-bound provider key** (`secrets.get_provider_key`, #181) — each route's key is
     resolved bound to ``route.upstream_base`` and attached ONLY to that route's own
     ``api_base``; a route whose base was moved resolves NO key. litellm sends ``api_key`` to
     ``api_base`` 1:1, so the binding survives.
  2. **SSRF / non-routable refusal** (`netutil.validate_base_url`) — link-local / cloud-metadata
     / non-http bases raise before entering the ``model_list``.
  3. **preset-derived egress allowlist** (`egress.assert_base_allowed`, fail-CLOSED) — the
     EFFECTIVE base (the exact value written into the nested ``litellm_params['api_base']``,
     which is what litellm actually dials — the LiteLLM CVE-2024-6587 lesson) must be a
     git-tracked preset external host or a local host, else the route is REFUSED. A preset
     repointed off-preset or an attacker base is dropped exactly as the live path drops it.
  4. **no-redirect** — ``httpx`` (litellm's transport) does not follow redirects by default;
     :func:`no_redirect_client` pins ``follow_redirects=False`` for explicit wiring.
  5. **SG-never-Anthropic** (`providers.is_anthropic_route`) — any Anthropic
     model/provider/base is dropped from the ``model_list`` and can never be selected.
  6. **drain-then-park + funding-class order** — preserved as a PRE-ordering of each chain
     (`routing_policy.order_chain_by_funding_class` + parked exclusion) before assembly.

``litellm`` is imported lazily (inside :func:`make_router` / :func:`no_redirect_client`) so
this module imports cleanly with or without litellm installed — the pure-Python builder and
its security screening (controls 1, 2, 3, 5, 6) run and are testable regardless.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from charon import egress, netutil, providers, secrets

if TYPE_CHECKING:  # annotation-only; avoids importing the proxy_server graph at runtime
    from charon.proxy import ProxyObservation
    from charon.proxy_server import UpstreamRoute

# The response header the hand-rolled serve path emits on a GENUINE silent downgrade
# (proxy_server.py:365). The Router serve path has no HTTP shell of its own yet, so the
# guard surfaces the SAME marker for a future serve shell to emit verbatim — one marker
# contract shared with the money path.
DOWNGRADE_HEADER = "X-Charon-Downgrade"
_DOWNGRADE_HEADER_VALUE = "served a different model than requested"

# The money-path retries a transient upstream error once (forwarder.py); mirror it.
DEFAULT_NUM_RETRIES = 1
# Failures before a deployment is cooled — the commodity analogue of set_cooldown().
DEFAULT_ALLOWED_FAILS = 3

# Provider-key resolver signature: (provider_id, *, key_env, base_url) -> key|None.
KeyResolver = Callable[..., "str | None"]


class AdoptError(ValueError):
    """A route could not be mapped onto litellm without breaking a preserved control."""


def resolve_route_key(
    route: UpstreamRoute,
    *,
    key_resolver: KeyResolver = secrets.get_provider_key,
) -> str | None:
    """The key to send for *route*, BASE-BOUND to ``route.upstream_base`` (control 1).

    When the route names a provider, the resolver is AUTHORITATIVE and base-bound: it returns
    the key stored for that provider *bound to this route's base*, or ``None`` if none is —
    there is deliberately no fall-back to a possibly-stale ``route.api_key``, because a
    populated ``api_key`` riding to a moved ``upstream_base`` is exactly the exfil the binding
    exists to stop. A route with NO provider id is a direct/keyless entry that never had a
    per-provider stored key, so its own ``api_key`` (resolved for its own base upstream) is
    used as-is.
    """
    provider_id = getattr(route, "provider", None)
    base_url = getattr(route, "upstream_base", None)
    key_env = getattr(route, "key_env", None)
    if provider_id:
        # Authoritative, base-bound. None => send no key rather than the wrong one.
        return key_resolver(provider_id, key_env=key_env, base_url=base_url)
    return getattr(route, "api_key", None)


def _is_anthropic(route: UpstreamRoute, agent_model: str) -> bool:
    """True if this candidate is an Anthropic/Claude route on ANY of its identifiers
    (control 5). Screens the agent-facing id, the upstream model id, the provider label
    and the base — the same fields ``providers.is_anthropic_route`` covers."""
    return providers.is_anthropic_route(
        model_id=agent_model,
        provider=getattr(route, "provider", None),
        base_url=getattr(route, "upstream_base", None),
    ) or providers.is_anthropic_route(
        model_id=getattr(route, "upstream_model", None),
    )


def _screen_base(base: str | None, agent_model: str) -> str:
    """Apply the two destination gates the live path applies, and return the validated base.

    (2) ``netutil.validate_base_url`` — SSRF / link-local / metadata / scheme; wrapped as
    :class:`AdoptError` so an unsafe base never silently enters the Router.
    (3) ``egress.assert_base_allowed`` — the fail-CLOSED preset-derived allowlist; a non-preset
    external host raises :class:`egress.EgressPolicyError` (a ``ValueError`` → HTTP 400). The
    value screened here is the EXACT string written into ``litellm_params['api_base']`` (the
    nested, effective value litellm dials — CVE-2024-6587), not a request's top-level shape."""
    try:
        netutil.validate_base_url(base or "")
    except ValueError as exc:
        raise AdoptError(
            f"refusing to add route for {agent_model!r}: {exc}") from exc
    # Fail-closed egress allowlist (propagates EgressPolicyError unchanged, so a reviewer/
    # caller sees the SAME rejection the live route_from_spec path raises).
    return egress.assert_base_allowed(base)


def _deployment(
    route: UpstreamRoute, agent_model: str, base: str, key: str | None
) -> dict[str, Any]:
    """One ``model_list`` entry (a litellm "deployment"). ``model_name`` is the agent-facing
    id — several deployments sharing one ``model_name`` are what gives litellm intra-model
    failover/load-balancing, so a Charon failover CHAIN maps to N deployments of one name.

    ``api_base`` is set to *base* — the exact value :func:`_screen_base` validated — so the
    guarded value and the dialed value are the same object (the CVE-2024-6587 lesson made
    structural)."""
    upstream_model = getattr(route, "upstream_model", None) or agent_model
    params: dict[str, Any] = {
        # openai/ prefix => litellm speaks the OpenAI-compatible wire to api_base.
        "model": f"openai/{upstream_model}",
        "api_base": base,
        "api_key": key,
    }
    max_context = getattr(route, "max_context", None)
    entry: dict[str, Any] = {"model_name": agent_model, "litellm_params": params}
    if max_context is not None:
        entry["model_info"] = {"max_input_tokens": int(max_context)}
    return entry


def build_model_list(
    chains_by_model: dict[str, list[UpstreamRoute]],
    *,
    key_resolver: KeyResolver = secrets.get_provider_key,
) -> list[dict[str, Any]]:
    """Map ``{agent_model: [route, ...]}`` to a litellm ``model_list``, enforcing the
    build-time controls. Route ORDER is preserved (cold-start / static-fallback equivalence:
    with no grades and no live signal, the litellm candidate order equals today's chain order).

    Raises :class:`AdoptError` (SSRF) or ``egress.EgressPolicyError`` (off-allowlist base)
    before an unsafe/off-preset base can enter the Router.
    """
    model_list: list[dict[str, Any]] = []
    for agent_model, chain in chains_by_model.items():
        for route in chain:
            # Controls 2 + 3: SSRF refusal, then the fail-closed preset egress allowlist.
            base = _screen_base(getattr(route, "upstream_base", None), agent_model)
            # Control 5: SG-never-Anthropic. Drop (never select) an Anthropic route.
            if _is_anthropic(route, agent_model):
                continue
            # Control 1: base-bound key.
            key = resolve_route_key(route, key_resolver=key_resolver)
            model_list.append(_deployment(route, agent_model, base, key))
    return model_list


def routes_by_model(server: Any) -> dict[str, list[UpstreamRoute]]:
    """Assemble ``{agent_model: ordered chain}`` from a live ``GatewayProxyServer``.

    Mirrors ``GatewayProxyServer.chain_for``: a configured pool is a multi-provider chain; a
    plain route is a chain of one. Pools win over a same-named single route (same precedence
    as ``chain_for``). Optionally PRE-orders each chain by funding class and drops parked
    providers (control 6) when a ``balance_tracker`` is present — preserving the drain-then-park
    order the forwarder applies.
    """
    chains: dict[str, list[UpstreamRoute]] = {}
    pools: dict[str, list] = getattr(server, "pools", {}) or {}
    routes: dict[str, Any] = getattr(server, "routes", {}) or {}
    for model_id, chain in pools.items():
        chains[model_id] = list(chain)
    for model_id, route in routes.items():
        chains.setdefault(model_id, [route])

    bt = getattr(server, "balance_tracker", None)
    if bt is not None:
        chains = {m: _preorder_chain(chain, bt) for m, chain in chains.items()}
    return chains


def _preorder_chain(chain: list[UpstreamRoute], bt: Any) -> list[UpstreamRoute]:
    """Funding-class pre-order + parked-provider exclusion (control 6), matching the
    forwarder's drain-then-park routing. Never strands: if every leg is parked, the
    original chain is returned unchanged (the forwarder's never-strand fallback)."""
    from charon.routing_policy import order_chain_by_funding_class

    def _fc(prov: str) -> int | None:
        fc = bt.funding_class(prov)
        return int(fc) if fc is not None else None

    def _rem(prov: str) -> float | None:
        return bt.remaining(prov)

    ordered = order_chain_by_funding_class(
        list(chain), funding_class_fn=_fc, remaining_fn=_rem)
    live = [r for r in ordered
            if not bt.is_parked(getattr(r, "provider", None) or getattr(r, "label", ""))]
    return live or list(chain)


def no_redirect_client(*, timeout: float = 180.0):  # noqa: ANN201 - httpx type is lazy
    """An ``httpx.Client`` pinned to ``follow_redirects=False`` (control 4).

    A key-bearing request must never chase a 30x cross-host. httpx already defaults to not
    following redirects, but pinning it explicitly makes the guarantee a property of THIS
    plane rather than of a library default that could change. Wire the returned client into a
    litellm deployment's ``litellm_params['client']`` when serving."""
    import httpx  # lazy: only needed when actually constructing the transport

    return httpx.Client(follow_redirects=False, timeout=timeout)


def _raw_completion(router: Any, body: dict, *, timeout: float = 180.0) -> Any:
    """Issue ONE ``Router.completion`` and return litellm's raw ``ModelResponse`` (which still
    carries ``_hidden_params`` — the selected deployment's ``model_id`` / ``litellm_model_name``
    the downgrade guard needs). Raises whatever litellm raises when no deployment can serve."""
    model = body.get("model")
    messages = body.get("messages") or []
    passthrough = {
        k: body[k] for k in ("temperature", "top_p", "max_tokens", "tools", "tool_choice",
                             "stop", "response_format")
        if k in body
    }
    return router.completion(model=model, messages=messages, timeout=timeout, **passthrough)


def _to_dict(resp: Any) -> dict:
    """Normalize litellm's pydantic ``ModelResponse`` to a plain dict for the caller."""
    for attr in ("model_dump", "dict"):
        fn = getattr(resp, attr, None)
        if callable(fn):
            return fn()
    return dict(resp)  # last resort (already a mapping)


def complete_via_router(router: Any, body: dict, *, timeout: float = 180.0) -> dict:
    """Serve ONE OpenAI chat-completions request through the adopted ``litellm.Router``
    (non-streaming slice) and return the response as a plain dict.

    This is the live serve entry the e2e/dogfood exercise: gateway config → :func:`make_router`
    (controls applied to the model_list) → ``Router.completion`` → httpx send to the selected
    deployment's ``api_base`` carrying its base-bound key. Raises whatever litellm raises when
    no deployment can serve the requested model (e.g. an all-Anthropic model whose only legs
    were dropped by control 5).

    Downgrade-unaware: see :func:`complete_via_router_guarded` for the SR-1/SR-2 silent-downgrade
    guard the future cutover needs."""
    return _to_dict(_raw_completion(router, body, timeout=timeout))


def _selected_upstream_model(router: Any, resp: Any, fallback: str | None) -> str | None:
    """The NATIVE upstream model litellm actually SENT for this response — the ``expected``
    the SR-1 compare needs (forwarder.py uses ``route.upstream_model``; here the Router chose
    the deployment, so we recover ITS model). Primary: ``_hidden_params['litellm_model_name']``
    (e.g. ``'openai/ma'``); fallback: match ``_hidden_params['model_id']`` to a
    ``model_list`` entry's ``model_info.id``.

    On failure returns *fallback* = the RETURNED model id, so the caller compares a value
    against itself and flags NO downgrade. This is the D025-safe default: never fabricate a
    mismatch we cannot substantiate, because a false downgrade is exactly the false-positive
    that drove the SR-1 double-bill — better to under-flag than to re-bill an honest 200."""
    hp = getattr(resp, "_hidden_params", None) or {}
    name = hp.get("litellm_model_name")
    if name:
        return name
    dep_id = hp.get("model_id")
    if dep_id:
        for entry in (getattr(router, "model_list", None) or []):
            if (entry.get("model_info") or {}).get("id") == dep_id:
                return (entry.get("litellm_params") or {}).get("model")
    return fallback


@dataclass(frozen=True)
class GuardedResponse:
    """A Router-served response plus the SR-1/SR-2 downgrade verdict and the header a future
    serve shell emits. ``response`` is the already-billed 200 served AS-IS (never re-fetched,
    never re-billed — D025). ``downgrade`` is the canonical :meth:`GatewayProxy.classify`
    verdict; when True, ``headers`` carries ``X-Charon-Downgrade``."""

    response: dict
    downgrade: bool
    headers: dict[str, str] = field(default_factory=dict)
    observation: ProxyObservation | None = None


def complete_via_router_guarded(
    router: Any, body: dict, *, observer: Any = None, timeout: float = 180.0,
) -> GuardedResponse:
    """Serve ONE request through the Router **with the SR-1/SR-2 silent-downgrade guard** the
    future money-path cutover requires — the Router-path analogue of the hand-rolled
    forwarder's post-200 downgrade handling (forwarder.py:785-834).

    Exactly ONE upstream completion is issued and its already-billed 200 is served AS-IS. If the
    returned model's final ``/``-segment differs from the model litellm actually SENT (the
    canonical namespace/quant-tolerant compare — REUSED from ``proxy.GatewayProxy.classify`` /
    ``_normalize_model_id``, the SAME source of truth forwarder.py calls, NOT a second
    implementation), the response is marked a genuine downgrade: ``headers`` gains
    ``X-Charon-Downgrade`` and the completion is served unchanged. It is **never** discarded and
    re-fetched from the next deployment (that discard-and-rebill was the 2026-07-03 SR-1/SR-2
    double-bill). This guard only CLASSIFIES (pure) — it never calls ``record``/``observe``, so
    it can add no fresh billable spend (D025: an already-billed 200 is served as-is with the
    marker).

    ``observer`` — an optional live ``proxy.GatewayProxy`` to classify with (shares its
    pricing/normalization); a throwaway one is used when omitted. It is used PURELY for its
    canonical ``classify`` compare; no state is mutated on it.
    """
    from charon.proxy import GatewayProxy  # canonical SR-1/SR-2 downgrade classifier

    requested = body.get("model")
    raw = _raw_completion(router, body, timeout=timeout)
    served = _to_dict(raw)

    obs = (observer or GatewayProxy()).classify(
        requested_model=requested,
        status=200,
        headers=None,
        body=served,  # carries the RETURNED model id (body["model"])
        # the NATIVE model litellm SENT — the SR-1 ``expected`` (forwarder: route.upstream_model)
        expected_model=_selected_upstream_model(router, raw, fallback=served.get("model")),
    )
    headers: dict[str, str] = {}
    if obs.pseudo_success:
        headers[DOWNGRADE_HEADER] = _DOWNGRADE_HEADER_VALUE
    return GuardedResponse(
        response=served, downgrade=obs.pseudo_success, headers=headers, observation=obs)


def make_router(
    server: Any,
    *,
    allowed_fails: int = DEFAULT_ALLOWED_FAILS,
    num_retries: int = DEFAULT_NUM_RETRIES,
    key_resolver: KeyResolver = secrets.get_provider_key,
):  # noqa: ANN201 - litellm.Router type is lazy
    """Construct a ``litellm.Router`` from a live ``GatewayProxyServer`` (lazy litellm import).

    Commodity-plane mapping (ADOPT-MAP.md): ``cooldown_time`` ← ``server.default_cooldown``;
    ``allowed_fails`` / ``num_retries`` ← the retry-once + cool-after-N behavior;
    ``retry_after`` ← the default cooldown. All preserved controls are enforced by
    :func:`build_model_list` / :func:`routes_by_model` before the Router is built.
    """
    from litellm import Router  # lazy: adopting the library, not standing up its proxy

    chains = routes_by_model(server)
    model_list = build_model_list(chains, key_resolver=key_resolver)
    cooldown = float(getattr(server, "default_cooldown", 60.0) or 60.0)
    return Router(
        model_list=model_list,
        cooldown_time=cooldown,
        allowed_fails=allowed_fails,
        num_retries=num_retries,
        retry_after=int(cooldown),
        set_verbose=False,
    )
