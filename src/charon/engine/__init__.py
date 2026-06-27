"""Charon's native work-engine substrate (ADR-0010, wave 1).

COORDINATION STATE ONLY — a durable, Charon-owned work backlog (`board`) and an
atomic claim with an epoch fencing token (`claim`). No worker management, no
process spawning: Charon's workers are warm-poolable **ACP agents**, driven by
the existing `AgentBackend`/`coordinator.run`. This package is a thin layer over
the existing PERF-4 primitives (`ledger`'s PID-liveness lock, `land`'s owned-path
scoping), never a second subsystem.
"""
from __future__ import annotations

from .board import (
    BLOCKED,
    CLAIMED,
    DONE,
    READY,
    STATES,
    Board,
    BoardError,
    Unit,
)
from .claim import (
    Claim,
    ClaimContended,
    StaleReclaim,
    claim,
    current,
    is_held,
    release,
)

__all__ = [
    "Board",
    "BoardError",
    "Unit",
    "STATES",
    "READY",
    "CLAIMED",
    "DONE",
    "BLOCKED",
    "Claim",
    "ClaimContended",
    "StaleReclaim",
    "claim",
    "release",
    "current",
    "is_held",
]
