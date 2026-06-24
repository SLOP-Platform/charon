"""Core value types shared across the harness.

These are deliberately small and JSON-serializable: the Work Ledger persists
them, and three public surfaces (CLI / Python API / HTTP service) exchange them.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Tier(enum.Enum):
    """Capability tier a unit is routed to. Maps to model strength."""

    LOW = "low"
    MED = "med"
    HIGH = "high"


class Autonomy(enum.IntEnum):
    """Operator-set autonomy ladder (ADR-0001 §6 / ADR-0003 §7).

    Ordered so that ``level >= required`` is a valid gate test.
    """

    L0 = 0  # propose-only: diffs produced, nothing applied
    L1 = 1  # apply reversible: commit in worktree, lkg rollback; no delete/deploy
    L2 = 2  # apply with consensus
    L3 = 3  # full-auto within fence


class PrivilegedOp(enum.Enum):
    """The privileged actions that must cross the control-plane fence."""

    PROPOSE = "propose"
    APPLY_REVERSIBLE = "apply_reversible"
    DELETE = "delete"
    DEPLOY = "deploy"


@dataclass(frozen=True)
class Budget:
    """Bounds a run so 'always working' cannot mean 'unbounded cost'."""

    max_checkpoints: int = 8
    max_seconds: int | None = None


@dataclass(frozen=True)
class Health:
    """A backend's self-reported state, used for exhaustion detection (H4)."""

    budget_remaining: bool = True
    rate_limited: bool = False
    context_pressure: bool = False

    @property
    def exhausted(self) -> bool:
        return (not self.budget_remaining) or self.rate_limited or self.context_pressure


@dataclass(frozen=True)
class CapSet:
    """Task-classes a backend declares competence at."""

    classes: frozenset[str] = field(default_factory=frozenset)

    def covers(self, task_class: str) -> bool:
        return not self.classes or task_class in self.classes


@dataclass(frozen=True)
class WorkUnit:
    """One dispatchable unit of work."""

    task_id: str
    goal: str
    task_class: str = "codegen"


class OutcomeStatus(enum.Enum):
    PROGRESSED = "progressed"  # made changes toward acceptance
    BLOCKED = "blocked"  # could not progress
    EXHAUSTED = "exhausted"  # backend ran out (handoff signal)


@dataclass
class Outcome:
    """What a single dispatch produced. Adapters report this to the Ledger;
    they never own progress truth (ADR-0003 §3)."""

    status: OutcomeStatus
    provider: str
    # commit SHA in the target repo produced by this dispatch, if any.
    commit: str | None = None
    note: str = ""
