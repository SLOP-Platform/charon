"""test_dispatch.py — verifies the dispatch path consults the budget."""
import pytest

import dispatch as dispatch_mod
from budget import RetryBudget
from dispatch import DispatchError, dispatch


def test_budget_respected(monkeypatch):
    """If the upstream fails 5 times and the budget allows only 2 retries,
    dispatch must return/raise after 2 retries — NOT loop forever."""
    calls = {"n": 0}

    def _failing_request(url, payload):
        calls["n"] += 1
        raise DispatchError(f"fail #{calls['n']}")

    monkeypatch.setattr(dispatch_mod, "_do_request", _failing_request)

    budget = RetryBudget(max_retries=2)
    request = {"url": "https://x", "payload": {}}

    with pytest.raises(DispatchError):
        dispatch(request, budget)
    # Initial call + 2 retries = 3 invocations. The bug (no budget check)
    # would either raise on the very first call (no retries) OR loop
    # forever. 3 is the post-fix contract: respect the budget.
    assert calls["n"] == 3, (
        f"dispatch must stop after exhausting the budget (expected 3 calls: "
        f"1 initial + 2 retries; got {calls['n']})"
    )


def test_within_budget_succeeds(monkeypatch):
    """If the upstream fails 1 time and the budget allows 3 retries,
    the second attempt must succeed (dispatch is the same happy path
    as before, just now budget-aware)."""
    calls = {"n": 0}

    def _flaky_request(url, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise DispatchError("first attempt fails")
        return {"ok": True, "attempt": calls["n"]}

    monkeypatch.setattr(dispatch_mod, "_do_request", _flaky_request)

    budget = RetryBudget(max_retries=3)
    request = {"url": "https://x", "payload": {}}
    result = dispatch(request, budget)
    assert result == {"ok": True, "attempt": 2}
    assert calls["n"] == 2
