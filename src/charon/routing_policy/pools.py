"""POOLS-SIMPLIFICATION policy (Wave 2).

Stub — the full implementation lands in Wave 2. Pool simplification
collapses redundant or near-identical pool chains, deduplicates members,
and prunes exhausted / unreachable entries so the routing table stays
compact and operators reason about fewer candidates.
"""
from __future__ import annotations

from .base import Policy


class PoolsSimplificationPolicy(Policy):
    """Stub — returns empty list (not yet implemented)."""

    name = "pools_simplification"

    def select(self, **kwargs):
        return []
