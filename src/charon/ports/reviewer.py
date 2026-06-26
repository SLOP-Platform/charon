"""The consensus port (ADR-0003 §6). Port only in Tier 1.

A reviewer judges an executed unit against its acceptance. Tier 1 ships a no-op
pass-through (no consensus gate yet); Tier 3 wires a real cross-model reviewer
behind the same interface. The harness owns the gate predicate + circuit
breaker, not the reviewer itself (ADR-0001 §2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..types import Outcome, WorkUnit


class ReviewerError(RuntimeError):
    """A reviewer failed to produce a verdict (timeout/unavailable/crash/open circuit)."""


@dataclass
class Findings:
    blocking: list[str] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        return not self.blocking


@runtime_checkable
class Reviewer(Protocol):
    def review(self, unit: WorkUnit, outcome: Outcome) -> Findings:
        ...
