"""dispatch.py — minimal dispatch loop the model must wire RetryBudget to."""


class DispatchError(Exception):
    pass


def _do_request(url, payload):
    """Stub: pretend we POST to upstream. Returns the response body or
    raises DispatchError. Replace with a mock in tests."""
    raise NotImplementedError


def dispatch(request, budget):
    """Dispatch a request with a retry budget. MUST consult the budget
    before each retry and stop once it is exhausted. Currently this
    loops without consulting the budget (the bug)."""
    url = request["url"]
    payload = request["payload"]
    last_err = None
    while True:
        try:
            return _do_request(url, payload)
        except DispatchError as exc:
            last_err = exc
            # BUG: should consult budget.can_retry() here and break
            # when the budget is exhausted. Currently re-raises
            # unconditionally when some other condition holds (none).
            raise last_err
