"""Routing policy engine — the gateway's provider-selection layer.

This package extracts the routing / provider-selection logic from the
gateway into a separately versioned package so Wave-2 policy
implementations (cost-rank-auto, drain, pools-simplification, spill) can
be developed in parallel.

Public API
----------
Policy                  — abstract base (Wave-2 authors implement this)
DefaultPolicy           — passthrough (the backward-compatible default)
route_from_spec         — registry entry → UpstreamRoute
build_routes_and_pools  — compile routes + failover chains from registry
tier_pools              — compile tier-based pool chains
build_fallback_chain    — append global fallback providers to pools/routes
CapabilityMatrix        — (model × work_class) → grade schema (Wave 2)
derived_cost_rank       — SR-6 cost-rank derivation from per-token pricing
"""
from __future__ import annotations

from collections.abc import Callable

from charon import config as _config_mod
from charon import providers as _providers_mod
from charon.proxy_server import UpstreamRoute as _UpstreamRoute

from .base import DefaultPolicy, Policy
from .cost_rank import cost_class_priority, derived_cost_rank
from .drain import DrainPolicy
from .matrix import CapabilityMatrix, Grade, ModelCapability, WorkClass
from .pools import PoolsSimplificationPolicy
from .spill import SpillPolicy

__all__ = [
    "Policy",
    "DefaultPolicy",
    "CapabilityMatrix",
    "ModelCapability",
    "Grade",
    "WorkClass",
    "derived_cost_rank",
    "cost_class_priority",
    "DrainPolicy",
    "PoolsSimplificationPolicy",
    "SpillPolicy",
    "route_from_spec",
    "build_routes_and_pools",
    "tier_pools",
    "build_fallback_chain",
    "order_pool_by_live_cost",
    "order_chain_by_funding_class",
]


def _int_or_none(v: object) -> int | None:
    return int(v) if isinstance(v, int) and v > 0 else None


def route_from_spec(spec: dict, providers_cfg: dict,
                     *, model_id: str | None = None,
                     enforce_preset_allowlist: bool = False) -> _UpstreamRoute | None:
    """One registry entry → UpstreamRoute. A ``provider`` reference (P3) resolves
    base_url/key_env/quirks from a preset (+ ``[providers.<name>]`` overrides); a
    direct ``upstream_base`` entry (P1/P2) still works. Returns None when neither
    yields a base (not HTTP-serveable).

    ``enforce_preset_allowlist`` (Phase-1 key-exfil control): when True — set only
    for the ATTACKER-WRITABLE ``providers.json`` runtime store — a BUILT-IN preset
    provider whose effective base was overridden off the git-tracked preset hosts
    has its route dropped (see the check below). It is False for the trusted,
    operator-managed ``--config charon.toml`` file, where overriding a preset's
    base is a first-class documented feature."""
    prov = spec.get("provider")
    if prov:
        preset = _providers_mod.resolve(prov, providers_cfg.get(prov))
        base: str | None = preset.base_url
        key_env = spec.get("key_env") or preset.key_env
        strip_v1: bool | None = preset.strip_v1
        wire = str(spec.get("wire") or preset.wire)  # per-model override wins
        adapter = str(spec.get("adapter") or preset.adapter or "") or None
        max_context = _int_or_none(spec.get("context_window") or spec.get("max_context"))
        if max_context is None:
            max_context = preset.max_context
        max_concurrency = _int_or_none(spec.get("max_concurrency"))
        if max_concurrency is None:
            max_concurrency = preset.max_concurrency
    else:
        base = spec.get("upstream_base")
        if not base:
            return None
        key_env = spec.get("key_env")
        strip_v1 = spec.get("strip_v1")  # explicit only; else server default
        wire = str(spec.get("wire") or _providers_mod.WIRE_OPENAI)
        adapter = str(spec.get("adapter") or "") or None
        max_context = _int_or_none(spec.get("context_window") or spec.get("max_context"))
        max_concurrency = _int_or_none(spec.get("max_concurrency"))
    from charon import egress as _egress
    from charon import secrets as _secrets

    # KEY-EXFIL FIX (Phase-1 app layer): a BUILT-IN preset provider's base is
    # NON-OVERRIDABLE off the git-tracked preset hosts. The effective base here is
    # preset ⊕ [providers.<name>] override — and providers.json is attacker-writable
    # via the token-gated add_provider handler (blast-radius §6-B: a poisoned entry
    # leaks on EVERY completion with no further attacker action). A built-in preset's
    # OWN base is always allowlisted, so a preset provider whose EFFECTIVE base is
    # not allowlisted was necessarily repointed off-preset by such an override —
    # drop it, fail CLOSED, rather than route a key there. This is checked on the
    # resolved value (the LiteLLM CVE-2024-6587 lesson: validate the effective
    # config, not a request's top-level shape). Deliberately scoped to preset
    # providers: operator-authored direct ``upstream_base`` entries (the shipped
    # P1/P2 feature) and locally-configured non-preset providers are trusted config,
    # not request-supplied — their arbitrary-host SSRF surface is round-6 MEDIUM-4,
    # constrained by the network-layer egress denial (Smokescreen), not here.
    if (enforce_preset_allowlist and prov and prov in _providers_mod.PRESETS
            and not _egress.is_allowed_base(base)):
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "dropping route for model %r: built-in preset provider %r was overridden "
            "in the runtime provider store to base %r, whose host is not a git-tracked "
            "preset — refusing to route a key to an off-preset override "
            "(charon.egress allowlist). Add new egress destinations by editing the "
            "presets, not via the runtime store.",
            model_id, prov, base)
        return None

    return _UpstreamRoute(
        upstream_base=str(base),
        # KEY-EXFIL FIX: the forward path resolves through the ONE provider-key
        # resolver, not `os.environ[key_env]`. This is the sink that fires on
        # EVERY proxied completion, so a mis-bound key here leaks with no
        # attacker action at all once a bad entry is persisted.
        api_key=_secrets.get_provider_key(prov, key_env=key_env, base_url=base),
        upstream_model=spec.get("upstream_model"),
        provider=prov,
        strip_v1=strip_v1,
        wire=wire,
        adapter=adapter,
        model_id=model_id,
        max_context=max_context,
        max_concurrency=max_concurrency,
    )


def build_routes_and_pools(
    registry: dict, pool_map: dict, providers_cfg: dict | None = None,
    *, metered_costs: dict[tuple[str, str], float] | None = None,
    enforce_preset_allowlist: bool = False,
) -> tuple[dict[str, _UpstreamRoute], dict[str, list[_UpstreamRoute]], list[str]]:
    """Compile a model registry + ``pool_map`` (virtual id → [model id]) into
    single routes (concrete models) and failover chains (virtual ids). Each chain
    is ordered **free-first, then by cost-class priority, then cheapest-first**
    from the registry's cost metadata (stable → the listed order breaks ties),
    matching `pools.load_pools` (D4).

    Effective ``cost_rank`` (SR-6 + R5) is **derived** from per-token pricing when
    present, or from live metered per-(model,provider) cost when available.
    DELETE-STATIC-RANK (ADR-0016 step #6): a hand-typed ``cost_rank`` override is
    no longer honored — ordering is always derived from price.  An external
    config that still stamps ``cost_rank`` emits a ``DeprecationWarning`` and the
    integer is silently dropped from ordering.
    Genuinely-free models (``free:true``) sort first regardless. Models with
    ``cost_class: "premium"`` are GATED OUT of pool chains — they're usable only
    when explicitly requested or in a premium role, never the cheap-first default.

    Models with ``"enabled": false`` are excluded from routes and pools."""
    providers_cfg = providers_cfg or {}
    metered_costs = metered_costs or {}
    routes: dict[str, _UpstreamRoute] = {}
    for mid, spec in registry.items():
        if isinstance(spec, dict):
            if spec.get("enabled") is False:
                continue
            r = route_from_spec(spec, providers_cfg, model_id=mid,
                                enforce_preset_allowlist=enforce_preset_allowlist)
            if r is not None:
                routes[mid] = r

    def _rank(mid: str) -> tuple[bool, int, int]:
        spec = registry.get(mid, {})
        provider = spec.get("provider") or ""
        metered = metered_costs.get((mid, provider))
        return (
            not bool(spec.get("free", False)),
            cost_class_priority(spec),
            derived_cost_rank(spec, metered_cost=metered),
        )

    def _is_premium(mid: str) -> bool:
        return registry.get(mid, {}).get("cost_class") == "premium"

    pools: dict[str, list[_UpstreamRoute]] = {}
    for vid, members in pool_map.items():
        if not isinstance(members, list):
            continue
        # SR-6: premium models are excluded from default-primary pool chains.
        # They remain in `routes` (explicitly requestable) but never appear in a
        # cheap-first failover chain unless the operator opts in by listing the
        # premium model's own id as the pool vid (a premium-only role).
        eligible = [m for m in members if m in routes and not _is_premium(m)]
        # If every member is premium, keep them — an explicit premium-only pool
        # is the operator's opt-in to a premium role (don't silently empty it).
        if not eligible and members:
            eligible = [m for m in members if m in routes]
        ordered = sorted(eligible, key=_rank)
        if ordered:
            pools[vid] = [routes[m] for m in ordered]

    return routes, pools, sorted(set(routes) | set(pools))


def tier_pools(registry: dict, providers_cfg: dict,
               *, enforce_preset_allowlist: bool = False) -> dict[str, list[_UpstreamRoute]]:
    """Compile ``tiers.json`` members into failover chains via the SAME
    ``build_routes_and_pools`` the gateway uses for ``pools.json`` (DTC HARD REQ #2).

    Tiers are read from the separate ``tiers.json`` store (``config.load_tiers``),
    NOT ``pools.json`` — the strict ``pools.load_pools`` / ACP-router loader must never see
    web-authored tier data (no ``agent`` field → it would crash that path). Members are model
    ids already in ``registry``; each tier vid is ordered free-first→``cost_rank`` by the shared
    compiler. Absent/empty ``tiers.json`` → no member matches → no tier vids (behavior
    unchanged)."""
    members = _config_mod.load_tiers().get("members") or {}
    _, pools, _ = build_routes_and_pools(
        registry, members, providers_cfg,
        enforce_preset_allowlist=enforce_preset_allowlist)
    return pools


def build_fallback_chain(
    *,
    routes: dict[str, _UpstreamRoute],
    pools: dict[str, list[_UpstreamRoute]],
    providers_cfg: dict,
    fallback_names: list[str],
    enforce_preset_allowlist: bool = False,
) -> tuple[dict[str, _UpstreamRoute], dict[str, list[_UpstreamRoute]]]:
    """Append global fallback providers to the end of every pool chain (after
    the model's own providers — they're tried LAST) and to single-route models."""
    if not fallback_names:
        return routes, pools

    fallback_routes: list[_UpstreamRoute] = []
    for fname in fallback_names:
        try:
            r = route_from_spec({"provider": fname}, providers_cfg,
                                enforce_preset_allowlist=enforce_preset_allowlist)
            if r is not None:
                fallback_routes.append(r)
        except ValueError:
            pass  # skip invalid/unknown provider names gracefully

    if not fallback_routes:
        return routes, pools

    def _same_endpoint(a, b) -> bool:
        return a.upstream_base == b.upstream_base and a.provider == b.provider

    pools = dict(pools)
    for vid in list(pools.keys()):
        existing = list(pools[vid])
        pools[vid] = existing + [fr for fr in fallback_routes
                                  if not any(_same_endpoint(fr, e)
                                             for e in existing)]
    # Single-route models (not in any pool) also get the fallback.
    for mid in list(routes.keys()):
        if mid not in pools:
            pools[mid] = [routes[mid]] + fallback_routes

    return routes, pools


def _live_rank_key(
    route: _UpstreamRoute,
    registry: dict,
    metered_costs: dict[tuple[str, str], float],
) -> tuple[bool, int, int]:
    """Tuple to sort routes cheapest-first using LIVE metered cost.

    Falls back to the registry's configured ``cost_input``/``cost_output`` when
    the meter has no data for this (model, provider).  None-safe: missing
    registry entries sort last (``not free`` True, cost_class_priority 4,
    cost_rank 1000).

    DELETE-STATIC-RANK (ADR-0016 step #6): a hand-typed ``cost_rank`` in the
    registry is NEVER honored here — the field is derived, not read."""
    mid = route.model_id or route.pool_id or ""
    spec = registry.get(mid, {}) if isinstance(registry.get(mid), dict) else {}
    provider = route.provider or ""
    metered = metered_costs.get((mid, provider))
    return (
        not bool(spec.get("free", False)),
        cost_class_priority(spec),
        derived_cost_rank(spec, metered_cost=metered),
    )


def order_pool_by_live_cost(
    chain: list[_UpstreamRoute],
    *,
    registry: dict,
    metered_costs: dict[tuple[str, str], float] | None = None,
) -> list[_UpstreamRoute]:
    """Return ``chain`` reordered cheapest-first using LIVE metered cost.

    If ``metered_costs`` is empty/None, the order is **unchanged** — this
    preserves the existing static-config behaviour until traffic has created
    data in the meter.  Premium models are NOT filtered here (that is the
    caller's responsibility in ``build_routes_and_pools``; we only reorder).

    The sort key composes (not free, cost_class_priority, cost_rank) exactly
    as ``build_routes_and_pools`` and ``pools.load_pools`` do, but with the
    **live** ``metered_cost`` overriding the configured ``cost_input`` /
    ``cost_output`` when present.  Stable sort keeps relative order for ties."""
    if not chain:
        return []
    if not metered_costs:
        return list(chain)
    return sorted(chain, key=lambda r: _live_rank_key(r, registry, metered_costs))


# Funding-class priority for drain routing (operator decision #2 free-first-then-drain).
# Lower = preferred.  Class 1 (free-daily) first, then class 3 (drain-then-park prepaid),
# then class 2 (flat-sub), then class 4 (PAYG).  Unknown / None → 5 (sort last).
_FUNDING_CLASS_ORDER: dict[int | None, int] = {
    1: 0,   # free-recurring (try first — never blocks draining)
    3: 1,   # drain-then-park prepaid (drain finite credit before flat/PAYG)
    2: 2,   # flat-sub
    4: 3,   # PAYG
    None: 5,  # unconfigured
}


def funding_class_order(fc: int | None) -> int:
    return _FUNDING_CLASS_ORDER.get(fc, 5)


def order_chain_by_funding_class(
    chain: list[_UpstreamRoute],
    *,
    funding_class_fn: Callable[[str], int | None],
    remaining_fn: Callable[[str], float | None] | None = None,
) -> list[_UpstreamRoute]:
    """Return ``chain`` reordered by funding-class priority (free-first-then-drain).

    Within class 3 (drain-then-park), providers with positive remaining balance
    sort first (drain priority); exhausted ones sort last.  This is the sort
    ONLY — exclusion (skip-at-0) and the sole-leg guard happen in the caller.

    ``funding_class_fn(provider)`` must return the funding_class int or None.
    ``remaining_fn(provider)`` must return remaining USD or None (used only for
    breaking ties within class 3).
    """
    if not chain:
        return []

    def _sort_key(route: _UpstreamRoute) -> tuple[int, int]:
        prov = route.provider or route.label
        fc = funding_class_fn(prov)
        fc_order = funding_class_order(fc)
        # Within class 3: positive balance → preferred (0), exhausted → deprioritised (1)
        drain_prio = 0
        if fc == 3 and remaining_fn is not None:
            rem = remaining_fn(prov)
            if rem is not None and rem <= 0.0:
                drain_prio = 1  # at ~0 → sort after those with balance
        return (fc_order, drain_prio)

    return sorted(chain, key=_sort_key)

