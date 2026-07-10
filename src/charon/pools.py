"""Role → model-pool routing data (ADR-0004 D4/R2).

A *pool* is an ordered list of candidate (agent, model) profiles a role may run
on; the coordinator walks it, excluding exhausted entries (H6), so cross-model
failover is a routing decision — not a hardcoded fallback. The data lives on disk
(``.charon/models.json`` + ``.charon/pools.json``), so the operator tunes pools
without a redeploy and never edits code (INV-P0).

The pool is sorted **free-first, then cheapest-first** (`(not free, cost_rank)`,
a *stable* sort so hand-authored order breaks ties) — this is the operator's
"minimize cost, keep working" policy expressed as data. ``code_safe`` lets a
role refuse providers that train on / leak proprietary code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .routing_policy.cost_rank import derived_cost_rank


class PoolConfigError(RuntimeError):
    """Raised when models.json / pools.json is malformed or inconsistent. Loud."""


@dataclass(frozen=True)
class PoolEntry:
    """One candidate profile in a role's pool: an ACP agent pinned to a model."""

    agent: str  # ACP backend that executes (e.g. "opencode", "codex")
    model: str  # provider/model id the agent is pinned to (e.g. "openrouter/qwen3-coder")
    cost_tier: str  # free | flat | ptk | premium (display/grouping)
    cost_rank: int  # lower = cheaper; the cost-first sort key
    code_safe: bool  # defensible for proprietary code (no-train + jurisdiction)
    free: bool  # genuinely $0 (free-first sort key)
    upstream_base: str | None = None  # OpenAI-compat base the observing proxy forwards to
    key_env: str | None = None  # env var holding the upstream key (proxy injects it)
    upstream_model: str | None = None  # real model id at the upstream, if it differs

    @property
    def key(self) -> str:
        """Stable identity for exclusion across a handoff (one per agent+model)."""
        return f"{self.agent}:{self.model}"


def _entry_from_registry(model_id: str, spec: dict) -> PoolEntry:
    try:
        return PoolEntry(
            agent=str(spec["agent"]),
            model=model_id,
            cost_tier=str(spec.get("cost_tier", "ptk")),
            cost_rank=derived_cost_rank(spec),
            code_safe=bool(spec.get("code_safe", False)),
            free=bool(spec.get("free", False)),
            upstream_base=spec.get("upstream_base"),
            key_env=spec.get("key_env"),
            upstream_model=spec.get("upstream_model"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PoolConfigError(f"model {model_id!r} in models.json is malformed: {exc}") from exc



def load_pools(state_dir: Path) -> dict[str, list[PoolEntry]]:
    """Build ``role -> [PoolEntry]`` from ``models.json`` + ``pools.json``.

    Each role's list is sorted free-first then cost_rank (stable). A pool that
    names a model absent from the registry is a LOUD config error, never a silent
    drop."""
    state_dir = Path(state_dir)
    models_path = state_dir / "models.json"
    pools_path = state_dir / "pools.json"
    if not models_path.exists() or not pools_path.exists():
        return {}
    try:
        registry = json.loads(models_path.read_text())
        pools_raw = json.loads(pools_path.read_text())
    except json.JSONDecodeError as exc:
        raise PoolConfigError(f"pool config is not valid JSON: {exc}") from exc

    pools: dict[str, list[PoolEntry]] = {}
    for role, model_ids in pools_raw.items():
        if not isinstance(model_ids, list):
            raise PoolConfigError(f"pool {role!r} must be a list of model ids")
        entries: list[PoolEntry] = []
        for mid in model_ids:
            if mid not in registry:
                raise PoolConfigError(
                    f"pool {role!r} names model {mid!r} not in models.json"
                )
            entries.append(_entry_from_registry(mid, registry[mid]))
        # free-first, then cheapest-first; stable → hand order breaks ties.
        entries.sort(key=lambda e: (not e.free, e.cost_rank))
        pools[role] = entries
    return pools


def choose_from_pool(
    pool: list[PoolEntry], *, exclude: set[str] | None = None, code_safe_only: bool = False
) -> PoolEntry:
    """Return the first non-excluded (and, if required, code-safe) pool entry.

    Raising (rather than degrading) when the pool is dry is deliberate: the
    coordinator turns it into a clean ``exhausted`` stop, never a silent wrong
    choice."""
    exclude = exclude or set()
    for entry in pool:
        if entry.key in exclude:
            continue
        if code_safe_only and not entry.code_safe:
            continue
        return entry
    raise RuntimeError(
        f"pool exhausted (excluded={sorted(exclude)}, code_safe_only={code_safe_only})"
    )
