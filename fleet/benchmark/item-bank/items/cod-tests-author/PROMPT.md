# Task: add a regression test for a known bug

`calc.py` has a known bug: `percent(part, whole)` divides by zero when
`whole == 0` and silently returns 0 (a footgun — a missing-data
condition is indistinguishable from a genuine 0% result).

Add a regression test in `tests/test_calc.py` that exercises this case
AND fixes the implementation in `calc.py` so the test passes.

Hard constraints:
- The test MUST check the documented post-fix behavior: `percent(5, 0)`
  raises `ZeroDivisionError` (do NOT silently return 0).
- The test MUST be added to `tests/test_calc.py`; the existing happy
  path tests for non-zero wholes must continue to pass.
- Do not change the function's signature or return type for the
  non-zero case.
