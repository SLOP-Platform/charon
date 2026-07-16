"""Routing plane — predictive, task-level (ADR-0001 §3 / ADR-0003 §5).

Tier 1 is a **static policy** loaded from disk (reconciliation BR-3: NO network
gateway enters the privileged loop). The policy is *data, not code*, so it tunes
without a redeploy. Per-turn gateway routing and success-rate feedback are
Tier 2+.

GRACEFUL-DEGRADE: the router accepts a ``parked_keys`` set so the shared park/
degrade state machine (balance.py / failover.py / router.py) can exclude parked
pool entries at routing time.  The forwarder wires it from the balance tracker's
``parked_providers()``, mapping provider labels → pool entry keys.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .pools import PoolEntry, choose_from_pool, load_pools
from .types import Budget, Tier

# Stable default so the system is useful before any tuning (ADR-0003 §5).
_DEFAULT_POLICY = {
    "diagnosis": "high",
    "review": "high",
    "refactor": "med",
    "test-authoring": "med",
    "codegen": "med",
    "_default": "med",
}


@dataclass
class Route:
    tier: Tier
    backend: str
    budget: Budget


class StaticRouter:
    def __init__(self, policy: dict[str, str] | None = None,
                 backends: list[str] | None = None,
                 pools: dict[str, list[PoolEntry]] | None = None) -> None:
        self.policy = policy or dict(_DEFAULT_POLICY)
        self.backends = backends or []
        self.pools = pools or {}
        # GRACEFUL-DEGRADE: provider → pool-entry-key mapping for parked
        # providers.  Set by the forwarder from the balance tracker; the
        # router merges these into the per-call ``exclude`` set.
        self.parked_keys: set[str] = set()

    @classmethod
    def from_file(cls, path: Path, backends: list[str]) -> StaticRouter:
        if path.exists():
            data = json.loads(path.read_text())
            return cls(policy=data.get("policy", _DEFAULT_POLICY),
                       backends=backends)
        return cls(backends=backends)

    @classmethod
    def from_charon_dir(cls, state_dir: Path,
                        policy: dict[str, str] | None = None,
                        metered_costs: dict[tuple[str, str], float] | None = None,
                        ) -> StaticRouter:
        """Build a pool-aware router from ``.charon/models.json`` + ``pools.json``
        (ADR-0004 R2). ``backends`` is derived from the agents named in the pools."""
        pools = load_pools(Path(state_dir), metered_costs=metered_costs)
        backends = sorted({e.agent for entries in pools.values() for e in entries})
        return cls(policy=policy, backends=backends, pools=pools)

    def route_pool(self, role: str, *, exclude: set[str] | None = None,
                   code_safe_only: bool = False) -> PoolEntry:
        """Pick the next (agent, model) profile for ``role`` — free-first,
        cheapest-first, skipping exhausted AND parked entries (H6 + GRACEFUL-
        DEGRADE). Cross-model failover is just re-running this with the
        exhausted entry's key excluded."""
        pool = self.pools.get(role)
        if not pool:
            raise RuntimeError(f"no pool configured for role {role!r}")
        merged_exclude = (exclude or set()) | self.parked_keys
        return choose_from_pool(pool, exclude=merged_exclude, code_safe_only=code_safe_only)

    def tier_for(self, task_class: str) -> Tier:
        """The capability tier ``task_class`` maps to under the static policy. Pure
        policy lookup — no backend needed — so callers (api's warm-map builder) can
        enumerate the tiers a decompose run will span before any backend exists."""
        tier_name = self.policy.get(task_class, self.policy.get("_default", "med"))
        return Tier(tier_name)

    def route(self, task_class: str, *, exclude: set[str] | None = None) -> Route:
        """Choose (tier, backend, budget) for a unit before generation.

        Backend selection is **by tier** (ADR-0014 D6): when a backend is keyed by
        the dispatch's tier vid — the warm-agent-per-tier map api builds for a
        multi-tier decompose run — route to it, so each stage reaches its own tier's
        model. A single-backend run (the Phase-A / non-decompose case) has no
        tier-keyed backend, so it falls through to the sole candidate unchanged.

        H6: handoff re-runs this with the exhausted provider excluded — so
        handoff order is a routing decision, not a static fallback list. An excluded
        tier backend drops out of ``candidates`` and the fallback takes over."""
        exclude = exclude or set()
        tier = self.tier_for(task_class)
        candidates = [b for b in self.backends if b not in exclude]
        if not candidates:
            raise RuntimeError(
                f"no backend available for task_class={task_class!r} "
                f"(excluded={sorted(exclude)})"
            )
        backend = tier.value if tier.value in candidates else candidates[0]
        return Route(tier=tier, backend=backend, budget=Budget())
