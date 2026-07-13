# Ticket: honor the retry budget on the request path

`gateway/budget.py` already defines a `RetryBudget` (a per-request cap on how
many upstream retries we are willing to spend). It is currently dead code — the
dispatch path in `gateway/proxy.py` never consults it, so a request can retry
without limit.

Wire it up: `dispatch(request, budget)` must consult the `RetryBudget` and
**stop retrying once the budget is exhausted**, returning the last error result
instead of retrying again. A request whose retries fit inside the budget should
still succeed exactly as it does today.

Keep the change on the real dispatch path (do not add a parallel/unused helper).
Add a test that exercises `dispatch` end-to-end and would fail if the budget
were ignored.
