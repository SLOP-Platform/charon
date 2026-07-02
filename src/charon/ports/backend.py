"""The execution port (ADR-0001 §2 / ADR-0003 §3).

Any coding-agent backend is swappable behind this one interface. Adapters
translate a WorkUnit into a CLI invocation in an isolated worktree, capture the
trajectory, and report an Outcome to the Ledger. Adapters never own progress
truth — they report it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..types import Budget, CapSet, Health, Outcome, Tier, WorkUnit


@runtime_checkable
class AgentBackend(Protocol):
    """Stable execution port. dispatch → observe → report."""

    name: str

    def dispatch(
        self,
        unit: WorkUnit,
        tier: Tier,
        budget: Budget,
        worktree: Path,
        env: dict[str, str],
        state_dir: Path | None = None,
    ) -> Outcome:
        """Run the unit in ``worktree`` using the hardened ``env``. Make
        progress toward the unit's acceptance and return an Outcome. Must be
        safe to kill at a checkpoint boundary with no progress loss (INV-5).

        ``state_dir``, when not None, is the durable ledger root's parent
        directory — the adapter MAY persist per-unit agent output at
        ``<state_dir>/<task_id>/agent.log``."""
        ...

    def health(self) -> Health:
        """Self-report budget / rate-limit / context-pressure (feeds H4)."""
        ...

    def capabilities(self) -> CapSet:
        """Task-classes this backend is competent at."""
        ...

    def kill(self) -> None:
        """Terminate at the nearest checkpoint boundary; no data loss."""
        ...
