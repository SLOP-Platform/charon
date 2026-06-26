"""MockReviewer — the deterministic Tier-4 consensus proof vehicle.

Mirrors MockBackend: it drives the consensus gate with no live reviewer, and has
adversarial modes so the gate's *cross-cutting* properties are proven, not just
asserted — a BLOCK must leave lkg unadvanced; an ERROR must fail **closed**.

A real cross-model reviewer is integrated behind the same ``Reviewer`` port
(ADR-0001 §2); it needs model access via the gated gateway (see adapters/review.py).
"""
from __future__ import annotations

import enum

from ..ports.reviewer import Findings, ReviewerError
from ..types import Outcome, WorkUnit

# Re-export so existing test imports don't break.
__all__ = ["MockReviewer", "ReviewMode", "ReviewerError"]


class ReviewMode(enum.Enum):
    PASS = "pass"  # empty findings → gate passes
    BLOCK = "block"  # blocking findings → gate refuses
    ERROR = "error"  # raises → gate must fail CLOSED
    FLAKY = "flaky"  # errors `k` times then passes (breaker / recovery)


class MockReviewer:
    def __init__(
        self,
        mode: ReviewMode = ReviewMode.PASS,
        *,
        blocking: list[str] | None = None,
        flaky_k: int = 1,
    ) -> None:
        self.mode = mode
        self._blocking = blocking or ["mock blocking finding"]
        self._flaky_k = flaky_k
        self.calls = 0  # so a test can assert the breaker bounded the call count

    def review(self, unit: WorkUnit, outcome: Outcome) -> Findings:
        self.calls += 1
        if self.mode is ReviewMode.PASS:
            return Findings(blocking=[])
        if self.mode is ReviewMode.BLOCK:
            return Findings(blocking=list(self._blocking))
        if self.mode is ReviewMode.ERROR:
            raise ReviewerError("mock reviewer unavailable")
        # FLAKY: error for the first k calls, then pass.
        if self.calls <= self._flaky_k:
            raise ReviewerError(f"mock reviewer flaky ({self.calls}/{self._flaky_k})")
        return Findings(blocking=[])
