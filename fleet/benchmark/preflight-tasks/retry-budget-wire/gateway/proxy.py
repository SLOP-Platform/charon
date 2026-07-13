"""Request dispatch — mirrors Charon's gateway/proxy.py shape.

`dispatch` sends a request to an upstream and retries on a retryable error. The
retry loop currently has NO budget: it keeps retrying as long as the upstream
keeps returning a retryable error. gateway/budget.py::RetryBudget exists to cap
this, but dispatch does not consult it yet.
"""


class Upstream:
    """A tiny stand-in upstream. `attempt(request)` returns a result dict with
    a `status`. A status in RETRYABLE means dispatch should retry."""

    RETRYABLE = {429, 503}

    def __init__(self, statuses):
        # statuses: the sequence of statuses this upstream will return, one per
        # attempt. The last one repeats if attempts exceed the list.
        self._statuses = list(statuses)
        self.attempts = 0

    def attempt(self, request):
        idx = min(self.attempts, len(self._statuses) - 1)
        self.attempts += 1
        return {"status": self._statuses[idx], "request": request}


def dispatch(request, budget=None):
    """Send `request` to its upstream, retrying on a retryable status.

    `budget` is a RetryBudget. TODO: it is accepted but ignored — the loop
    retries without limit. Wire the budget in so dispatch stops retrying once
    the budget is exhausted and returns the last result.
    """
    upstream = request["upstream"]
    result = upstream.attempt(request)
    while result["status"] in Upstream.RETRYABLE:
        # BUG: no budget check here — retries forever while status is retryable.
        result = upstream.attempt(request)
    return result
