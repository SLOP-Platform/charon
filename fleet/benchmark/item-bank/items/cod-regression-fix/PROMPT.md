# Task: fix a regression in `backoff.clamp` WITHOUT touching the test

`backoff.py`'s `clamp(delay, max_delay)` is supposed to cap the delay to
`max_delay`. Today, the function returns `min(delay, max_delay)` but
the test expects `max_delay` to be applied AFTER adding a jitter — so
delays in the 1.5×–2× range bleed past the cap.

The seeded RED test in `tests/test_backoff.py` is the spec. Do NOT
modify the test. Fix `backoff.py` to make it pass.

Hint: the test asserts the cap is enforced after a +50% jitter offset.
So `clamp(delay, max_delay, *, jitter=0.5)` should return
`min(delay + delay*jitter, max_delay)`.

Hard constraints:
- Do NOT modify `tests/test_backoff.py` (the test is the spec; modifying
  it would defeat the purpose of the seeded regression).
- The default behavior (no jitter) must match the previous contract
  for callers that don't pass jitter.
