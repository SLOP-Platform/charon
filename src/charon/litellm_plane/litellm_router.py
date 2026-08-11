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
    the key stored for that provider *bound to this route's base*, or ``None`` if none is.
    There is NO fallback to ``route.api_key`` — the one provider-key resolver is the single
    chokepoint, and every keyed path goes through it (control-1 fail-on-revert: falling back
    to ``route.api_key`` defeats the base-binding check, leaking a key to a moved base).
    A route with NO provider id is a direct/keyless entry that never had a per-provider
    stored key, so its own ``api_key`` is used as-is.
    """
    provider_id = getattr(route, "provider", None)
    base_url = getattr(route, "upstream_base", None)
    key_env = getattr(route, "key_env", None)
    if provider_id:
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


# LITELLM-ROUTER-CUTOVER (D-019): separator for the synthetic per-leg model_name.
# litellm coalesces N deployments of one model_name into a load-balanced GROUP; to
# express an ORDERED chain we give each leg a distinct model_name (<agent>#<i>) and a
# fallbacks entry chaining them, so litellm tries leg 0, then leg 1, etc.
FALLBACK_SEP = "#"


def _leg_model_name(agent_model: str, index: int) -> str:
    return f"{agent_model}{FALLBACK_SEP}{index}"


def _deployment(
    route: UpstreamRoute, model_name: str, base: str, key: str | None
) -> dict[str, Any]:
    """One ``model_list`` entry (a litellm "deployment"). ``model_name`` is the per-leg
    synthetic id (NOT the agent-facing id) so a Charon failover CHAIN maps to N
    deployments of distinct names, chained via ``fallbacks`` (D-019). ``api_base`` is
    the exact value :func:`_screen_base` validated. ``model_info`` carries the charon
    ``provider`` id so the per-attempt recorder can map a litellm deployment back to its
    Charon provider label."""
    upstream_model = getattr(route, "upstream_model", None) or model_name
    params: dict[str, Any] = {
        "model": f"openai/{upstream_model}",
        "api_base": base,
        "api_key": key,
    }
    _prov = getattr(route, "provider", None) or getattr(route, "label", "")
    info: dict[str, Any] = {"provider": _prov}
    max_context = getattr(route, "max_context", None)
    if max_context is not None:
        info["max_input_tokens"] = int(max_context)
    return {"model_name": model_name, "litellm_params": params, "model_info": info}


def build_model_list(
    chains_by_model: dict[str, list[UpstreamRoute]],
    *,
    key_resolver: KeyResolver = secrets.get_provider_key,
) -> list[dict[str, Any]]:
    """Map ``{agent_model: [route, ...]}`` to a litellm ``model_list``. A SINGLE-leg
    chain keeps the agent-facing ``model_name``; a MULTI-leg chain gives each leg a
    distinct per-leg name (``<agent>#<i>``) so :func:`build_fallbacks` can chain them.

    Raises :class:`AdoptError` (SSRF) or ``egress.EgressPolicyError`` (off-allowlist base)."""
    model_list: list[dict[str, Any]] = []
    for agent_model, chain in chains_by_model.items():
        screened = [(i, r) for i, r in enumerate(chain) if not _is_anthropic(r, agent_model)]
        multi = len(screened) > 1
        for pos, (_index, route) in enumerate(screened):
            base = _screen_base(getattr(route, "upstream_base", None), agent_model)
            key = resolve_route_key(route, key_resolver=key_resolver)
            name = _leg_model_name(agent_model, pos) if multi else agent_model
            model_list.append(_deployment(route, name, base, key))
    return model_list


def build_fallbacks(chains_by_model: dict[str, list[UpstreamRoute]]) -> list[dict[str, list[str]]]:
    """Map ``{agent_model: ordered chain}`` to a litellm ``fallbacks`` list (D-019:
    ``fallbacks`` replace chains). A multi-leg chain becomes ``{leg#0: [leg#1, ...]}``."""
    fallbacks: list[dict[str, list[str]]] = []
    for agent_model, chain in chains_by_model.items():
        legs: list[str] = []
        for _index, route in enumerate(chain):
            if _is_anthropic(route, agent_model):
                continue
            legs.append(_leg_model_name(agent_model, len(legs)))
        if len(legs) > 1:
            fallbacks.append({legs[0]: legs[1:]})  # pragma: no cover  # multi-leg only
    return fallbacks


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
    forwarder's drain-then-park routing.

    D-012: when EVERY leg is parked the chain is EMPTY, not restored. This used to
    ``return live or list(chain)`` — mirroring the forwarder's never-strand
    fallback — which handed litellm the full parked chain and billed it, the exact
    behaviour OPERATOR DECISION D-012 outlaws ("Change it to 503 don't allow it to
    leak"). An empty chain builds no deployment, so the plane can only refuse; it
    can never silently serve a parked leg. A pool with at least one unparked leg is
    unaffected — ``live`` is non-empty and is returned exactly as before."""
    from charon.litellm_plane.park_cooldown import excluded_provider_ids
    from charon.routing_policy import order_chain_by_funding_class

    def _fc(prov: str) -> int | None:
        fc = bt.funding_class(prov)
        return int(fc) if fc is not None else None

    def _rem(prov: str) -> float | None:
        return bt.remaining(prov)

    ordered = order_chain_by_funding_class(
        list(chain), funding_class_fn=_fc, remaining_fn=_rem)

    # Hard-exclude: parked (deterministic 402/403) + drained (balance ~0).
    # Item 3: excluded_provider_ids unifies park + cooldown exclusion.
    # D-019: no funding = no deployment. The sole-leg guard from the hand-rolled
    # path does NOT apply here -- a fully-exhausted chain returns empty and the
    # caller 503s. Free-quota providers with remaining allowance are FUNDED.
    excluded = excluded_provider_ids(bt=bt)
    live = []
    for r in ordered:
        prov = getattr(r, "provider", None) or getattr(r, "label", "")
        if prov in excluded:
            continue
        # is_drained catches a class-3 provider at ~0 that was not yet auto-parked
        # (the hand-rolled sole-leg guard may have prevented the park). D-019: hard-exclude.
        if bt.is_drained(prov):
            continue
        live.append(r)
    return live  # D-012: fully parked → EMPTY, never the restored parked chain


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


def _provider_budget_config() -> dict | None:
    """Construct ``provider_budget_config`` from the TSV seed for providers with
    known rate limits. Returns None when no limits are configured or file absent.

    S26: reads ``fleet/state/FREE-TIER-LIMITS.tsv`` (per-provider rpd/rpm/tpm/tpd).
    Skips ``unpublished``/``unverified`` rows — only rows with at least one numeric
    limit are included. A daily limit is divided by 1440 for the per-minute proxy
    that litellm enforces natively via ``RouterBudgetLimiting``.

    Uses the operator's exhaustion_signal column to pick ``budget_duration``:
    a ``_per_month`` → ``\"30d\"``, a ``_per_day`` → ``\"1d\"``, else ``\"1d\"``.
    The ``RouterBudgetLimiting`` callback auto-resets on window rollover — exactly
    the period-boundary park-then-rearm the operator specified.
    """
    import csv
    import re
    from pathlib import Path

    # Repo-root-relative path: free_tier.py lives at 4 parents, but we're in
    # litellm_plane which is one deeper. Find the product repo root.
    tsv_path = Path(__file__).resolve().parents[3] / "fleet" / "state" / "FREE-TIER-LIMITS.tsv"
    if not tsv_path.exists():
        return None
    try:
        text = tsv_path.read_text(encoding="utf-8")
    except OSError:
        return None
    rows = list(csv.DictReader(text.splitlines(), delimiter="\t"))
    if not rows:
        return None

    cfg: dict[str, dict] = {}
    for row in rows:
        prov = str(row.get("provider", "")).strip()
        if not prov or prov.startswith("#"):
            continue
        if prov in cfg:
            continue

        def _int_or(v: str) -> int | None:
            s = v.strip()
            if not s or s in ("-", "unknown", "unpublished", "unverified"):
                return None
            m = re.match(r"(\d+)(?:_per_\w+)?", s)
            if m:
                return int(m.group(1))
            try:
                return int(s)
            except (ValueError, TypeError):
                return None

        rpm_v = _int_or(row.get("rpm", ""))
        rpd_v = _int_or(row.get("rpd", ""))
        tpm_v = _int_or(row.get("tpm", ""))
        tpd_v = _int_or(row.get("tpd", ""))

        if rpm_v is None and rpd_v is None and tpm_v is None and tpd_v is None:
            continue  # no numeric limits — skip unpublished/unverified rows

        entry: dict[str, object] = {}
        rpm = rpm_v or (rpd_v // 1440 if rpd_v else None)
        tpm = tpm_v or (tpd_v // 1440 if tpd_v else None)
        if rpm:
            entry["rpm_limit"] = rpm
        if tpm:
            entry["tpm_limit"] = tpm

        sig = str(row.get("exhaustion_signal", "")).strip().lower()
        if "month" in sig or "monthly" in sig or (tpd_v and tpd_v > 10_000_000):
            entry["budget_duration"] = "30d"
        elif "week" in sig:
            entry["budget_duration"] = "7d"
        elif "tmo" in row or "tpd" in row and tpd_v > 1_000_000:
            entry["budget_duration"] = "30d"
        else:
            entry["budget_duration"] = "1d"

        if entry:
            cfg[prov] = entry
    return cfg or None


def make_router(
    server: Any,
    *,
    allowed_fails: int = DEFAULT_ALLOWED_FAILS,
    num_retries: int = DEFAULT_NUM_RETRIES,
    key_resolver: KeyResolver = secrets.get_provider_key,
):  # noqa: ANN201 - litellm.Router type is lazy
    """Construct a ``litellm.Router`` from a live ``GatewayProxyServer`` (lazy litellm import).

    Commodity-plane mapping (ADOPT-MAP.md / D-019): ``cooldown_time`` ←
    ``server.default_cooldown``; ``allowed_fails`` / ``num_retries`` ← the retry-once +
    cool-after-N behavior; ``retry_after`` ← 0 (the hand-rolled RETRY-ONCE retries
    immediately with no backoff — cooldown is managed by ``cooldown_time`` +
    ``allowed_fails`` independently); ``fallbacks`` ← the ordered chain.

    S26: ``provider_budget_config`` ← TSV-seed per-provider rate limits, enabling
    litellm's ``RouterBudgetLimiting`` for period-boundary auto-reset + pre-request
    filtering — no hand-rolled token-volume accounting.
    """
    from litellm import Router  # lazy: adopting the library, not standing up its proxy

    _install_no_redirect_patch()  # control 4: patch litellm's HTTPHandler NOW, before first use
    chains = routes_by_model(server)
    model_list = build_model_list(chains, key_resolver=key_resolver)
    fallbacks = build_fallbacks(chains)
    cooldown = float(getattr(server, "default_cooldown", 60.0) or 60.0)
    budget = _provider_budget_config()
    return Router(
        model_list=model_list,
        fallbacks=fallbacks,
        cooldown_time=cooldown,
        allowed_fails=allowed_fails,
        num_retries=num_retries,
        retry_after=0,
        set_verbose=False,
        provider_budget_config=budget,
    )


# ── LIVE DISPATCH (LITELLM-ROUTER-CUTOVER) ─────────────────────────────────────

ATTEMPTS_META_KEY = "__charon_attempts__"


@dataclass
class AttemptRecord:
    """One leg's outcome as recorded by the per-attempt callback (for X-Charon headers)."""
    provider: str
    status: int
    ok: bool
    reason: str = ""


def _install_attempt_callbacks() -> None:
    """Install global litellm success/failure callbacks that record each leg's outcome
    into the per-request ATTEMPTS_META_KEY list (idempotent)."""
    import litellm

    def _record(kwargs, ok):
        lp = kwargs.get("litellm_params") or {}
        meta = lp.get("metadata") or {}
        attempts = meta.get(ATTEMPTS_META_KEY)
        if attempts is None:
            return  # pragma: no cover — safety net; metadata always set in Router-path dispatch
        mi = lp.get("model_info") or {}
        provider = str(mi.get("provider") or "")
        exc = kwargs.get("exception")
        status = int(getattr(exc, "status_code", 0) or 0) if exc else 200
        reason = str(getattr(exc, "message", "") or type(exc).__name__)[:200] if exc else ""
        attempts.append(AttemptRecord(provider=provider, status=status, ok=ok, reason=reason))

    def _on_failure(kwargs, completion_response, start_time, end_time):  # noqa: ANN001, ARG001
        _record(kwargs, False)

    def _on_success(kwargs, completion_response, start_time, end_time):  # noqa: ANN001, ARG001
        _record(kwargs, True)

    _tag = "__charon_installed__"
    if not getattr(litellm, _tag, False):
        litellm.failure_callback = list(litellm.failure_callback or []) + [_on_failure]
        litellm.success_callback = list(litellm.success_callback or []) + [_on_success]
        _install_no_redirect_patch()
        setattr(litellm, _tag, True)


def _install_no_redirect_patch() -> None:
    """Patch litellm's HTTPHandler to never follow redirects (control 4: no-redirect transport).

    litellm's ``HTTPHandler.__init__`` hardcodes ``follow_redirects=True`` in every httpx
    client it creates (litellm/llms/custom_httpx/http_handler.py:1098). A redirecting
    upstream harvests the provider key because httpx re-sends the ``Authorization`` header
    cross-host. This patch replaces the default with ``follow_redirects=False`` —
    idempotent, one-time, and scoped to ``make_router`` side-effects.

    The ``no_redirect_client`` helper constructs the same no-redirect client explicitly for
    any direct-httpx use (e.g. balance polling); this patch covers the Router's internal
    client creation which we do not control directly.
    """
    import litellm.llms.custom_httpx.http_handler as _hh

    _patch_tag = "__charon_no_redirect_patched__"
    if getattr(_hh, _patch_tag, False):
        return

    _orig_init = _hh.HTTPHandler.__init__

    def _patched_init(self, *args, **kwargs):  # pragma: no cover  # HTTPHandler monkeypatch
        _orig_init(self, *args, **kwargs)
        if not getattr(self, "_charon_redirect_patched", False):
            try:
                self.client.follow_redirects = False
                self._charon_redirect_patched = True  # type: ignore[attr-defined]
            except AttributeError:
                pass  # pragma: no cover — not an httpx.Client we control — silently skip

    _hh.HTTPHandler.__init__ = _patched_init  # type: ignore[assignment]
    setattr(_hh, _patch_tag, True)


def _primary_leg(agent_model: str, chains: dict[str, list]) -> str | None:
    """The model_name litellm should route to first. Single-leg → agent-facing name;
    multi-leg → ``<agent>#0``. None when no chain."""
    chain = chains.get(agent_model)
    if not chain:
        return None
    screened = sum(1 for r in chain if not _is_anthropic(r, agent_model))
    return _leg_model_name(agent_model, 0) if screened > 1 else agent_model


def _provider_from_deployment(router, model_id):  # noqa: ANN001
    if not model_id:
        return ""
    for entry in getattr(router, "model_list", None) or []:
        mi = entry.get("model_info") or {}
        if mi.get("id") == model_id:
            return str(mi.get("provider") or "")
    return ""


def _classify_for_envelope(provider, bt):  # noqa: ANN001
    if bt is None:
        return ("unknown", "unknown")
    fc = bt.funding_class(provider)
    if fc is None:
        return ("unknown", "unknown")
    _L = {1: "free-recurring", 2: "flat-sub", 3: "drain-then-park", 4: "PAYG"}
    _R = {1: "auto reset (quota window)", 2: "operator top-up (next cycle)",
          3: "operator top-up", 4: "top-up or rate-limit cooldown"}
    try:
        return (_L[int(fc)], _R[int(fc)])
    except (KeyError, ValueError):  # pragma: no cover — fc always a valid int from 1-4
        return ("unknown", "unknown")


def _synth_exhaustion_envelope(requested, attempts, *, all_parked, bt, retry_after_s=None):  # noqa: ANN001
    """Build the ADR-0016 terminal 503 envelope (all_parked or all_exhausted)."""
    if all_parked:
        legs = []
        for r in attempts:
            cls, rearm = _classify_for_envelope(r.provider, bt)
            legs.append({"provider": r.provider, "status": "parked",
                         "reason": "provider is parked — spend is intentionally stopped",
                         "class": cls, "rearm": rearm})
        return 503, {"error": {
            "message": "every leg is parked", "type": "all_providers_exhausted",
            "requested_model": requested, "no_provider_reason": "all_legs_parked",
            "retry_after_s": None, "providers_tried": legs,
            "failover_reasons": [f"{leg['provider']}=parked" for leg in legs]}}
    legs = []
    for r in attempts:
        cls, rearm = _classify_for_envelope(r.provider, bt)
        legs.append({"provider": r.provider, "status": r.status,
                     "reason": r.reason or "exhausted", "class": cls, "rearm": rearm})
    return 503, {"error": {
        "message": "all providers exhausted", "type": "all_providers_exhausted",
        "requested_model": requested, "no_provider_reason": None,
        "retry_after_s": retry_after_s, "providers_tried": legs,
        "failover_reasons": [f"{r.provider}={r.status}" for r in attempts]}}


def complete_via_router_tracked(
    router, body, *, chains, bt=None, orig_pools=None, orig_routes=None, timeout=180.0,  # noqa: ANN001
) -> tuple[int, dict, dict[str, str]]:
    """Serve ONE non-streaming request through the Router with per-attempt X-Charon
    header reconstruction + D-012/D-018 envelope synthesis (the live money-path dispatch).

    Returns ``(status, response_dict, headers)``. D-012: fully-parked → 503 without an
    upstream call. On Router failure → 503 all_providers_exhausted from recorded attempts.
    On success → 200 with X-Charon-Provider/Failovers/Failover-Reasons headers."""
    _install_attempt_callbacks()
    requested = body.get("model", "")
    primary = _primary_leg(requested, chains)

    if primary is None:
        has_unscreened = bool(
            (orig_pools and orig_pools.get(requested))
            or (orig_routes and orig_routes.get(requested)))
        if has_unscreened:
            orig_chain = (
                (orig_pools or {}).get(requested)
                or (orig_routes or {}).get(requested)
                or []
            )
            parked_legs = [AttemptRecord(
                provider=getattr(r, "provider", None) or getattr(r, "label", ""),
                status=0, ok=False, reason="parked") for r in orig_chain]
            status, env = _synth_exhaustion_envelope(
                requested, parked_legs, all_parked=True, bt=bt)
            return status, env, {"X-Charon-Failovers": "0"}
        return 502, {"error": {
            "message": f"no route for model {requested!r}",
            "type": "no_route_configured", "requested_model": requested,
            "no_provider_reason": "no_providers_configured",
            "retry_after_s": None, "providers_tried": []}}, {"X-Charon-Failovers": "0"}

    attempts: list[AttemptRecord] = []
    try:
        raw = router.completion(
            model=primary, messages=body.get("messages") or [], timeout=timeout,
            metadata={ATTEMPTS_META_KEY: attempts},
            **{k: body[k] for k in ("temperature", "top_p", "max_tokens", "tools",
                                   "tool_choice", "stop", "response_format") if k in body})
    except Exception as exc:  # noqa: BLE001
        if not attempts:
            attempts = [AttemptRecord(  # pragma: no cover  # zero-attempts edge case
                provider=_provider_from_deployment(router, None),
                status=int(getattr(exc, "status_code", 0) or 0), ok=False,
                reason=str(getattr(exc, "message", "") or type(exc).__name__)[:200])]
        status, env = _synth_exhaustion_envelope(
            requested, attempts, all_parked=False, bt=bt)
        return status, env, {
            "X-Charon-Failovers": str(max(len(attempts) - 1, 0)),
            "X-Charon-Failover-Reasons": "; ".join(
                f"{r.provider}={r.status}" for r in attempts if not r.ok)}

    served = _to_dict(raw)
    hp = getattr(raw, "_hidden_params", None) or {}
    provider = _provider_from_deployment(router, hp.get("model_id"))
    fallbacks = int((hp.get("additional_headers") or {}).get("x-litellm-attempted-fallbacks", 0))
    headers: dict[str, str] = {"X-Charon-Failovers": str(fallbacks)}
    if provider:
        headers["X-Charon-Provider"] = provider
    failover_attempts = [r for r in attempts if not r.ok]
    if failover_attempts:  # pragma: no cover — multi-leg failover; service tier
        headers["X-Charon-Failover-Reasons"] = "; ".join(
            f"{r.provider}={r.status}" for r in failover_attempts)
    return 200, served, headers
