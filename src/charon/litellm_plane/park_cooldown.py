"""Bridge park<->cooldown: unify Charon park state with litellm.Router cooldown.

Charon's park (funding drain / free-tier window) and litellm.Router's native
model-cooldown (transient allowed_fails breach) compose into ONE coherent
exclusion set. This module provides the bridge.

The two kinds of exclusion answer the never-strand question DIFFERENTLY
(D-018): a chain excluded ONLY by transient cooldown is restored so a blip
never strands a request, while a chain with any parked leg is NOT restored —
park is an operator decision that stops spend, so a fully-parked chain
returns EMPTY and the caller answers with the D-012 503 (same shape, same
``no_provider_reason == "all_legs_parked"`` discriminator as ``forwarder.py``).

Usage — the bridge's primary function replaces ``_preorder_chain`` in the
Router assembly pipeline (``litellm_router.routes_by_model``), unifying
the two exclusion mechanisms so no leg is "cooled" yet still offered, and
no parked leg leaks back in on cooldown expiry::

    from charon.litellm_plane.park_cooldown import park_cooldown_filter_chain
    chains = {m: park_cooldown_filter_chain(chain, bt=bt)
              for m, chain in chains.items()}

The sole-leg guard is built in and park-aware: a cooldown-only chain is never
parked/cooled into a no-workers-left state, but a chain with a parked leg is
NOT restored into a servable state.
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


def _parked_and_cooled(
    bt: Any,
    router: Any = None,
) -> tuple[set[str], set[str]]:
    """Return ``(parked, cooled)`` provider-id sets SEPARATELY.

    The split is the point (D-018): park and cooldown are different kinds
    of exclusion and must be answerable independently — park is an operator
    decision that stops spend (stronger signal), cooldown is a transient
    upstream failure (never-strand applies).
    """
    parked = parked_providers(bt)
    cooled: set[str] = set()
    if router is not None:
        _maybe_add_cooled(router, cooled)
    return parked, cooled


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

    Union only: the two kinds of exclusion are deliberately merged for
    "is this provider excluded at all" questions. Callers that need to
    tell them apart use ``park_cooldown_filter_chain``, which treats park
    as the stronger signal (D-018).
    """
    parked, cooled = _parked_and_cooled(bt, router)
    return parked | cooled


def _maybe_add_cooled(router: Any, excluded: set[str]) -> None:
    """Read *router*'s ``cooldown_cache`` and add cooled deployment
    provider IDs into *excluded*.

    ``litellm.Router`` tracks cooldowns in its ``cooldown_cache`` (a
    ``CooldownCache``). Deployments that have been cooled (too many recent
    failures) are stored with a TTL equal to their cooldown time. This
    function reads the active cooldowns from the cache and maps them back
    to Charon provider IDs via the ``model_list`` entries' ``model_info``.

    When the Router does not expose ``get_model_ids`` or ``cooldown_cache``
    (different litellm version), the function silently returns — cooldown
    filtering falls back to park-only, which is strictly safer (over-excludes
    rather than under-excludes).
    """
    try:
        model_ids: list[str] = router.get_model_ids()
        cc = router.cooldown_cache
        cooled: list[tuple[str, Any]] = cc.get_active_cooldowns(
            model_ids=model_ids, parent_otel_span=None,
        )
    except Exception:  # noqa: BLE001
        return

    if not cooled:
        return

    cooled_ids: set[str] = {cv[0] for cv in cooled}
    model_list: list[dict] = getattr(router, "model_list", []) or []
    for entry in model_list:
        dep_id = _deployment_id(entry)
        if dep_id and dep_id in cooled_ids:
            prov = _provider_from_entry(entry)
            if prov:
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


def sole_leg_guard(
    live: list[Any],
    original: list[Any],
) -> list[Any]:
    """Return *live* if non-empty, otherwise *original* (never strand).

    This is the COOLDOWN-ONLY sole-leg guard (D-018): when every leg is
    excluded purely by transient Router cooldown and none is parked, the
    last leg is kept so a request can still route — a transient upstream
    blip never strands a request.

    It is deliberately NOT applied when a leg is parked: restoring a parked
    leg is a money leak (D-012). ``park_cooldown_filter_chain`` decides that
    split before calling this.

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
    """Filter *chain* to exclude parked/cooled providers (D-018 split).

    Charon park state (``bt.is_parked``) and litellm.Router cooldown are
    TWO different kinds of exclusion and get TWO different never-strand
    answers (D-018):

    * **Cooldown-only, no leg parked** — the never-strand guard is KEPT:
      if every leg is excluded purely by transient Router cooldown, the
      ORIGINAL chain is returned unchanged, so a transient upstream blip
      never strands a request.
    * **Any parked leg** — park is the STRONGER signal. A parked leg is an
      operator/config decision that stops SPEND; restoring it to satisfy a
      cooldown-shaped guard is a money leak (D-012). When no leg survives
      and at least one is parked, the result is EMPTY and the caller
      answers with the D-012 503 (``no_provider_reason == "all_legs_parked"``),
      exactly like ``forwarder.py``.
    * **Mixed park + cooldown, none live** — the park rule wins: parked legs
      are NOT restored, so the result is EMPTY. The precedence is stated here
      so it cannot silently drift back to the merged guard.

    When *bt* is ``None``, no park-based exclusion is applied. When
    *router* is ``None``, no cooldown-based exclusion is applied —
    the function gracefully degrades to park-only or no-op.

    Works with any route-like object that has ``.provider`` or
    ``.label`` attributes (``UpstreamRoute``, duck-typed fakes in
    tests).
    """
    parked, cooled = _parked_and_cooled(bt, router)
    excluded = parked | cooled

    if not excluded:
        return list(chain)

    live = [r for r in chain if _provider_id(r) not in excluded]
    if live:
        return live

    if any(_provider_id(r) in parked for r in chain):
        return []

    return sole_leg_guard(live, chain)


def count_viable_legs(
    chain: list[Any],
    *,
    bt: Any,
    router: Any = None,
) -> int:
    """Number of legs the filter leaves dispatchable after the D-018 rule.

    Delegates to ``park_cooldown_filter_chain`` so callers can never
    disagree with the dispatcher about whether a pool is servable: a
    cooldown-only chain the filter restores counts as viable (the
    dispatcher WILL try it), a chain with a parked leg that yields empty
    counts as 0.
    """
    return len(park_cooldown_filter_chain(chain, bt=bt, router=router))
