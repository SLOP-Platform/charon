"""Retry budgeting — mirrors Charon's gateway/budget.py shape.

RetryBudget caps how many upstream retries a single request may spend. It is
defined here but NOT yet consulted by the dispatch path (see gateway/proxy.py).
"""
from dataclasses import dataclass


@dataclass
class RetryBudget:
    """A per-request retry allowance."""

    max_retries: int
    spent: int = 0

    def exhausted(self) -> bool:
        """True once no further retry may be spent."""
        return self.spent >= self.max_retries

    def spend(self) -> None:
        """Record that one retry was consumed."""
        self.spent += 1
