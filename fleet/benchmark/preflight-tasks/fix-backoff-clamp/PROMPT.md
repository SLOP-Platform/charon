# Ticket: backoff delay is not clamped to the ceiling

`tests/test_backoff.py` is failing. It asserts that `clamp_delay` never returns
a delay above `MAX_DELAY_S` (retry backoff must not exceed the ceiling), but
`gateway/backoff.py::clamp_delay` currently lets large delays through unclamped.

Fix the product so the failing test passes. **Do not modify, skip, xfail, or
delete `tests/test_backoff.py`** — it encodes the required behavior. The fix
belongs in `gateway/backoff.py`.
