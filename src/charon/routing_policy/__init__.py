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

import os

from charon import config as _config_mod
from charon import providers as _providers_mod
from charon.proxy_server import UpstreamRoute as _UpstreamRoute

from .base import DefaultPolicy, Policy
from .cost_rank import derived_cost_rank

__all__ = [
    "Policy",
    "DefaultPolicy",
    "CapabilityMatrix",
    "ModelCapability",
    "Grade",
    "WorkClass",
    "derived_cost_rank",
    "DrainPolicy",
    "PoolsSimplificationPolicy",
    "SpillPolicy",
    "route_from_spec",
    "build_routes_and_pools",
    "tier_pools",
    "build_fallback_chain",
]


def route_from_spec(spec: dict, providers_cfg: dict) -> _UpstreamRoute | None:
    """One registry entry → UpstreamRoute. A ``provider`` reference (P3) resolves
    base_url/key_env/quirks from a preset (+ ``[providers.<name>]`` overrides); a
    direct ``upstream_base`` entry (P1/P2) still works. Returns None when neither
    yields a base (not HTTP-serveable)."""
    prov = spec.get("provider")
    if prov:
        preset = _providers_mod.resolve(prov, providers_cfg.get(prov))
        base: str | None = preset.base_url
        key_env = spec.get("key_env") or preset.key_env
        strip_v1: bool | None = preset.strip_v1
        wire = str(spec.get("wire") or preset.wire)  # per-model override wins
        adapter = str(spec.get("adapter") or preset.adapter or "") or None
    else:
        base = spec.get("upstream_base")
        if not base:
            return None
        key_env = spec.get("key_env")
        strip_v1 = spec.get("strip_v1")  # explicit only; else server default
        wire = str(spec.get("wire") or _providers_mod.WIRE_OPENAI)
        adapter = str(spec.get("adapter") or "") or None
    return _UpstreamRoute(
        upstream_base=str(base),
        api_key=os.environ.get(key_env) if key_env else None,
        upstream_model=spec.get("upstream_model"),
        provider=prov,
        strip_v1=strip_v1,
        wire=wire,
        adapter=adapter,
    )


def build_routes_and_pools(
    registry: dict, pool_map: dict, providers_cfg: dict | None = None,
) -> tuple[dict[str, _UpstreamRoute], dict[str, list[_UpstreamRoute]], list[str]]:
    """Compile a model registry + ``pool_map`` (virtual id → [model id]) into
    single routes (concrete models) and failover chains (virtual ids). Each chain
    is ordered **free-first then cheapest-first** from the registry's cost metadata
    (stable → the listed order breaks ties), matching `pools.load_pools` (D4).

    Effective ``cost_rank`` (SR-6) is **derived** from per-token pricing when
    present: ``blended = (3*cost_input + cost_output) / 4`` (a 3:1 input:output
    blend approximating typical chat-completion token mix). An explicit
    ``cost_rank`` override still wins (operator escape hatch). Genuinely-free
    models (``free:true``) sort first regardless. Models with ``cost_class:
    "premium"`` are GATED OUT of pool chains — they're usable only when explicitly
    requested or in a premium role, never the cheap-first default.

    Models with ``"enabled": false`` are excluded from routes and pools."""
    providers_cfg = providers_cfg or {}
    routes: dict[str, _UpstreamRoute] = {}
    for mid, spec in registry.items():
        if isinstance(spec, dict):
            if spec.get("enabled") is False:
                continue
            r = route_from_spec(spec, providers_cfg)
            if r is not None:
                routes[mid] = r

    def _rank(mid: str) -> tuple[bool, int]:
        spec = registry.get(mid, {})
        return (not bool(spec.get("free", False)), derived_cost_rank(spec))

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


def tier_pools(registry: dict, providers_cfg: dict) -> dict[str, list[_UpstreamRoute]]:
    """Compile ``tiers.json`` members into failover chains via the SAME
    ``build_routes_and_pools`` the gateway uses for ``pools.json`` (DTC HARD REQ #2).

    Tiers are read from the separate ``tiers.json`` store (TIER-1 ``config.load_tiers``),
    NOT ``pools.json`` — the strict ``pools.load_pools`` / ACP-router loader must never see
    web-authored tier data (no ``agent`` field → it would crash that path). Members are model
    ids already in ``registry``; each tier vid is ordered free-first→``cost_rank`` by the shared
    compiler. Absent/empty ``tiers.json`` → no member matches → no tier vids (behavior
    unchanged)."""
    members = _config_mod.load_tiers().get("members") or {}
    _, pools, _ = build_routes_and_pools(registry, members, providers_cfg)
    return pools


def build_fallback_chain(
    *,
    routes: dict[str, _UpstreamRoute],
    pools: dict[str, list[_UpstreamRoute]],
    providers_cfg: dict,
    fallback_names: list[str],
) -> tuple[dict[str, _UpstreamRoute], dict[str, list[_UpstreamRoute]]]:
    """Append global fallback providers to the end of every pool chain (after
    the model's own providers — they're tried LAST) and to single-route models."""
    if not fallback_names:
        return routes, pools

    fallback_routes: list[_UpstreamRoute] = []
    for fname in fallback_names:
        try:
            r = route_from_spec({"provider": fname}, providers_cfg)
            if r is not None:
                fallback_routes.append(r)
        except ValueError:
            pass  # skip invalid/unknown provider names gracefully

    if not fallback_routes:
        return routes, pools

    pools = dict(pools)
    for vid in list(pools.keys()):
        existing = list(pools[vid])
        pools[vid] = existing + [fr for fr in fallback_routes
                                  if fr not in existing]
    # Single-route models (not in any pool) also get the fallback.
    for mid in list(routes.keys()):
        if mid not in pools:
            pools[mid] = [routes[mid]] + fallback_routes

    return routes, pools
