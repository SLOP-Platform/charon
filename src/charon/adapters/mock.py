"""MockBackend — the deterministic Tier-1 proof and demo vehicle.

It drives the full coordinator loop with no live agent. Crucially it also has
**adversarial modes** (reconciliation BR-6): it can try to escape the worktree,
report exhaustion, or *claim* progress it did not make. Tests assert the
coordinator/ledger REJECT these — so the invariants are proven, not merely
asserted against a well-behaved mock.
"""
from __future__ import annotations

import enum
import re
from pathlib import Path

from .. import gitutil
from ..types import Budget, CapSet, Health, Outcome, OutcomeStatus, Tier, WorkUnit

_TEST_FILE_RE = re.compile(r"test\s+-[ef]\s+(\S+)")


class MockMode(enum.Enum):
    SATISFY = "satisfy"  # well-behaved: creates files to satisfy acceptance
    EXHAUST = "exhaust"  # reports health exhausted (handoff signal)
    BLOCKED = "blocked"  # makes no progress
    ESCAPE = "escape"  # writes OUTSIDE the worktree (must be rejected)
    LIE = "lie"  # claims PROGRESSED + a commit but satisfies nothing


class MockBackend:
    """A deterministic backend.

    ``creates`` is a flat list of files (relative to the worktree) to create,
    one per dispatch, in order — letting a test simulate multi-checkpoint work.
    If ``creates`` is None and mode is SATISFY, the backend infers files from
    ``test -f``/``test -e`` acceptance commands embedded in the unit goal.
    """

    def __init__(
        self,
        name: str = "mock",
        *,
        mode: MockMode = MockMode.SATISFY,
        creates: list[str] | None = None,
        escape_path: Path | None = None,
        health: Health | None = None,
        exhaust_after: int | None = None,
    ) -> None:
        self.name = name
        self.mode = mode
        self._creates = list(creates) if creates else None
        self._escape_path = escape_path
        self._health = health or Health()
        # After this many dispatches the backend self-reports exhausted (H4): the
        # handoff signal a real backend raises on rate-limit / context pressure /
        # budget cap. Lets a test choreograph "vendor A does some work, then
        # exhausts; vendor B must pick up from the ledger".
        self._exhaust_after = exhaust_after
        self._dispatches = 0
        self._killed = False

    @classmethod
    def satisfying(cls, checks, name: str = "mock") -> MockBackend:
        """Build a SATISFY mock that creates the files named by ``test -f/-e``
        acceptance checks — the demo path so ``charon run --backend mock`` is a
        believable end-to-end."""
        creates: list[str] = []
        for c in checks:
            creates.extend(_TEST_FILE_RE.findall(c.cmd))
        return cls(name=name, mode=MockMode.SATISFY, creates=creates or None)

    # -------------------------------------------------------- port methods
    def dispatch(
        self,
        unit: WorkUnit,
        tier: Tier,
        budget: Budget,
        worktree: Path,
        env: dict[str, str],
    ) -> Outcome:
        self._dispatches += 1
        idx = self._dispatches - 1

        if self.mode is MockMode.EXHAUST:
            return Outcome(OutcomeStatus.EXHAUSTED, self.name, note="mock exhausted")

        if self.mode is MockMode.BLOCKED:
            return Outcome(OutcomeStatus.BLOCKED, self.name, note="mock blocked")

        if self.mode is MockMode.ESCAPE:
            target = self._escape_path or (worktree.parent / "charon-escape.txt")
            target.write_text("escaped\n")
            commit = gitutil.commit_all(worktree, f"{self.name}: dispatch {idx}")
            return Outcome(OutcomeStatus.PROGRESSED, self.name, commit=commit,
                           note=f"wrote outside worktree: {target}")

        if self.mode is MockMode.LIE:
            # Claim success, write a harmless file that satisfies NO acceptance.
            (worktree / f".mock-noise-{idx}").write_text("noise\n")
            commit = gitutil.commit_all(worktree, f"{self.name}: bogus {idx}")
            return Outcome(OutcomeStatus.PROGRESSED, self.name, commit=commit,
                           note="claims done but satisfies nothing")

        # SATISFY
        files = self._files_to_create(unit, idx)
        for rel in files:
            dest = worktree / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f"created by {self.name}\n")
        commit = gitutil.commit_all(worktree, f"{self.name}: dispatch {idx}")
        return Outcome(OutcomeStatus.PROGRESSED, self.name, commit=commit,
                       note=f"created {files}")

    def health(self) -> Health:
        if self._exhaust_after is not None and self._dispatches >= self._exhaust_after:
            return Health(budget_remaining=False)
        return self._health

    def capabilities(self) -> CapSet:
        return CapSet(frozenset())  # competent at everything (mock)

    def kill(self) -> None:
        self._killed = True

    # --------------------------------------------------------------- helpers
    def _files_to_create(self, unit: WorkUnit, idx: int) -> list[str]:
        if self._creates is not None:
            return [self._creates[idx]] if idx < len(self._creates) else []
        # infer from "test -f X" patterns in the goal text
        return _TEST_FILE_RE.findall(unit.goal)
