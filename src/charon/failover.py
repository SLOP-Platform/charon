"""Failover glue — connects the observing proxy to the pool router (ADR-0004).

The proxy (proxy.py) observes the gateway and knows which *models* are exhausted
or silently-downgraded. The router (pools.py) chooses among *(agent, model)*
profiles and excludes by entry key. This module is the small translation between
them, so cross-model failover (H6) is automatic: a 429 / pseudo-success on the
current model marks it excluded, and the next route for that role picks the next
cheapest live profile.

Kept separate from the coordinator so the selection logic is unit-provable with
no live agent.
"""
from __future__ import annotations

from collections.abc import Callable

from .pools import PoolEntry
from .proxy import GatewayProxy
from .router import StaticRouter


def proxy_excluded_keys(pool: list[PoolEntry], proxy: GatewayProxy) -> set[str]:
    """Pool-entry keys to exclude because their model exhausted/downgraded at the
    gateway. The proxy keys by model id; the router excludes by ``agent:model``,
    so this maps one to the other against the role's pool."""
    exhausted = proxy.exhausted_models()
    return {e.key for e in pool if e.model in exhausted}


def next_entry(
    router: StaticRouter,
    role: str,
    proxy: GatewayProxy,
    *,
    also_exclude: set[str] | None = None,
    code_safe_only: bool = False,
) -> PoolEntry:
    """Pick the next live profile for ``role``: free-first/cheapest-first, skipping
    any model the proxy has flagged exhausted (plus any caller-supplied keys).
    Raises (clean ``exhausted`` stop) when the pool is dry."""
    pool = router.pools.get(role, [])
    exclude = proxy_excluded_keys(pool, proxy) | (also_exclude or set())
    return router.route_pool(role, exclude=exclude, code_safe_only=code_safe_only)


def select_live_entry(
    router: StaticRouter,
    role: str,
    proxy: GatewayProxy,
    probe: Callable[[PoolEntry], None],
    *,
    code_safe_only: bool = False,
) -> PoolEntry | None:
    """Pick the first *actually-available* model for ``role`` — the cost-first
    failover (#6). Walk the pool, run ``probe(entry)`` on each (the probe drives a
    cheap request through the proxy so the observer sees a 429/404/downgrade), and
    return the first entry the proxy did NOT flag. Returns None when the pool is
    dry — a clean exhausted stop, never a launch onto a dead model.

    This is the pre-flight that avoids OpenCode's hang-on-429: a model is verified
    live *before* the heavy agent is committed to it."""
    while True:
        try:
            entry = next_entry(router, role, proxy, code_safe_only=code_safe_only)
        except RuntimeError:
            return None  # pool exhausted
        probe(entry)
        if not proxy.is_exhausted(entry.model):
            return entry
