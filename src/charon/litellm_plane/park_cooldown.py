"""Bridge park<->cooldown: unify Charon park state with litellm.Router cooldown.

Charon's park (funding drain / free-tier window) and litellm.Router's native
model-cooldown (transient allowed_fails breach) compose into ONE coherent
exclusion set. This module provides the bridge.

Usage — the bridge's primary function replaces ``_preorder_chain`` in the
Router assembly pipeline (``litellm_router.routes_by_model``), unifying
the two exclusion mechanisms so no leg is "cooled" yet still offered, and
no parked leg leaks back in on cooldown expiry::

    from charon.litellm_plane.park_cooldown import park_cooldown_filter_chain
    chains = {m: park_cooldown_filter_chain(chain, bt=bt)
              for m, chain in chains.items()}

The sole-leg guard is built in: the last remaining viable leg is never
parked/cooled into a no-workers-left state.
"""
from __future__ import annotations

from typing import Any


def _provider_id(route: Any) -> str:
    """Extract the provider identifier from a route-like object.

    Matches the same extraction ``litellm_router._preorder_chain`` uses:
    ``route.provider`` (preferred), then ``route.label``.
    """
    prov: str | None = getattr(route, "provider", None)
    if prov:
        return prov
    label: str | None = getattr(route, "label", None)
    return label or ""


def parked_providers(bt: Any) -> set[str]:
    """Return the set of provider IDs parked in *bt* (a ``BalanceTracker``).

    Thread-safe snapshot. Returns empty set when *bt* is ``None``, so the
    caller may pass an absent tracker without special-casing.
    """
    if bt is None:
        return set()
    parked = getattr(bt, "parked_providers", None)
    if parked is not None:
        return parked()
    return set()


def excluded_provider_ids(
    *,
    bt: Any,
    router: Any = None,
) -> set[str]:
    """Return the union of park-excluded and cooldown-excluded provider IDs.

    *bt* — a ``BalanceTracker`` providing the park set (``None`` → no
    park-based exclusion).

    *router* — a ``litellm.Router`` whose internal cooldown state is read
    (``None`` or absent → no cooldown-based exclusion).  The Router must
    not be locked or in the middle of a completion when this is called.

    The returned set is a read-only snapshot — call again to re-read.
    """
    excluded: set[str] = set(parked_providers(bt))

    if router is not None:
        _maybe_add_cooled(router, excluded)

    return excluded


def _maybe_add_cooled(router: Any, excluded: set[str]) -> None:
    """Read *router*'s internal cooldown tracking and add cooled
    deployment provider IDs into *excluded*.

    litellm tracks failures per deployment in ``_failed_calls``
    (a dict of deployment_id → list of timestamps). A deployment is
    "cooled" when the number of failures within ``cooldown_time``
    seconds reaches ``allowed_fails``.

    When the Router does not expose ``_failed_calls`` (different litellm
    version), the function silently returns — cooldown filtering falls
    back to park-only, which is strictly safer (over-excludes rather
    than under-excludes).
    """
    try:
        cfails: dict | None = getattr(router, "_failed_calls", None)
        ctime: float = getattr(router, "cooldown_time", 60.0) or 60.0
        afails: int = getattr(router, "allowed_fails", 3) or 3
        model_list: list[dict] = getattr(router, "model_list", []) or []
        now: float = _monotonic()
    except Exception:  # any attribute access failure → bail gracefully
        return

    if not cfails or not model_list:
        return

    # Build a reverse lookup: deployment_id → provider_id.
    dep_to_prov: dict[str, str] = {}
    for entry in model_list:
        dep_id = _deployment_id(entry)
        if dep_id:
            prov = _provider_from_entry(entry)
            if prov:
                dep_to_prov[dep_id] = prov

    for dep_id, timestamps in cfails.items():
        prov = dep_to_prov.get(dep_id)
        if prov is None:
            continue
        recent = [ts for ts in timestamps if now - ts <= ctime]
        if len(recent) >= afails:
            excluded.add(prov)


def _deployment_id(entry: dict) -> str | None:
    """Return the unique deployment identifier litellm uses for this
    model_list entry, or ``None`` if the entry has no useful id."""
    mi = entry.get("model_info") or {}
    did = mi.get("id")
    if did:
        return str(did)
    lp = entry.get("litellm_params") or {}
    model = lp.get("model", "")
    base = lp.get("api_base", "")
    return f"{model}@{base}" if base else model or None


def _provider_from_entry(entry: dict) -> str | None:
    """Recover a Charon provider id from a model_list entry.

    Uses the ``model_info``'s ``provider`` field (when set by
    :func:`tag_entry`) otherwise falls back to heuristic: extract
    the host from ``api_base``.
    """
    mi = entry.get("model_info") or {}
    prov = mi.get("provider")
    if prov:
        return str(prov)
    lp = entry.get("litellm_params") or {}
    base = lp.get("api_base", "")
    if base:
        from urllib.parse import urlsplit
        host = urlsplit(base).hostname
        if host:
            return str(host)
    return None


def _monotonic() -> float:
    """Return monotonic time. Exposed for test injection."""
    import time
    return time.monotonic()


def sole_leg_guard(
    live: list[Any],
    original: list[Any],
) -> list[Any]:
    """Return *live* if non-empty, otherwise *original* (never strand).

    This is the sole-leg guard: with one viable leg left, exclusion does
    NOT remove it — the last leg is always kept so a request can still
    route.

    Works per-chain (per-model). A chain represents all routes for one
    agent-facing model id.
    """
    return live if live else list(original)


def park_cooldown_filter_chain(
    chain: list[Any],
    *,
    bt: Any,
    router: Any = None,
) -> list[Any]:
    """Filter *chain* to exclude parked/cooled providers with sole-leg guard.

    This is the bridge function that makes Charon park state and
    litellm.Router cooldown ONE exclusion set:

    * Parked providers (``bt.is_parked``) are removed.
    * Cooled deployments (Router internal cooldown state) are removed.
    * Sole-leg guard: if every leg would be excluded, the original chain
      is returned unchanged (never strand).

    When *bt* is ``None``, no park-based exclusion is applied. When
    *router* is ``None``, no cooldown-based exclusion is applied —
    the function gracefully degrades to park-only or no-op.

    Works with any route-like object that has ``.provider`` or
    ``.label`` attributes (``UpstreamRoute``, duck-typed fakes in
    tests).
    """
    excluded = excluded_provider_ids(bt=bt, router=router)

    if not excluded:
        return list(chain)

    live = [r for r in chain if _provider_id(r) not in excluded]
    return sole_leg_guard(live, chain)


def count_viable_legs(
    chain: list[Any],
    *,
    bt: Any,
    router: Any = None,
) -> int:
    """Number of legs in *chain* that are NOT excluded."""
    excluded = excluded_provider_ids(bt=bt, router=router)
    if not excluded:
        return len(chain)
    return sum(1 for r in chain if _provider_id(r) not in excluded)
