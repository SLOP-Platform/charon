"""budget.py — RetryBudget primitive the dispatch path must consult."""


class RetryBudget:
    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries
        self.used = 0

    def can_retry(self) -> bool:
        return self.used < self.max_retries

    def spend(self) -> None:
        self.used += 1

    @property
    def remaining(self) -> int:
        return max(0, self.max_retries - self.used)
