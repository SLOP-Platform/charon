"""Routing plane — predictive, task-level (ADR-0001 §3 / ADR-0003 §5).

Tier 1 is a **static policy** loaded from disk (reconciliation BR-3: NO network
gateway enters the privileged loop). The policy is *data, not code*, so it tunes
without a redeploy. Per-turn gateway routing and success-rate feedback are
Tier 2+.
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

    @classmethod
    def from_file(cls, path: Path, backends: list[str]) -> StaticRouter:
        if path.exists():
            data = json.loads(path.read_text())
            return cls(policy=data.get("policy", _DEFAULT_POLICY),
                       backends=backends)
        return cls(backends=backends)

    @classmethod
    def from_charon_dir(cls, state_dir: Path,
                        policy: dict[str, str] | None = None) -> StaticRouter:
        """Build a pool-aware router from ``.charon/models.json`` + ``pools.json``
        (ADR-0004 R2). ``backends`` is derived from the agents named in the pools."""
        pools = load_pools(Path(state_dir))
        backends = sorted({e.agent for entries in pools.values() for e in entries})
        return cls(policy=policy, backends=backends, pools=pools)

    def route_pool(self, role: str, *, exclude: set[str] | None = None,
                   code_safe_only: bool = False) -> PoolEntry:
        """Pick the next (agent, model) profile for ``role`` — free-first,
        cheapest-first, skipping exhausted entries (H6). Cross-model failover is
        just re-running this with the exhausted entry's key excluded."""
        pool = self.pools.get(role)
        if not pool:
            raise RuntimeError(f"no pool configured for role {role!r}")
        return choose_from_pool(pool, exclude=exclude, code_safe_only=code_safe_only)

    def route(self, task_class: str, *, exclude: set[str] | None = None) -> Route:
        """Choose (tier, backend, budget) for a unit before generation.

        H6: handoff re-runs this with the exhausted provider excluded — so
        handoff order is a routing decision, not a static fallback list."""
        exclude = exclude or set()
        tier_name = self.policy.get(task_class, self.policy.get("_default", "med"))
        tier = Tier(tier_name)
        candidates = [b for b in self.backends if b not in exclude]
        if not candidates:
            raise RuntimeError(
                f"no backend available for task_class={task_class!r} "
                f"(excluded={sorted(exclude)})"
            )
        return Route(tier=tier, backend=candidates[0], budget=Budget())
