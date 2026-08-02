# PYLINT-UNUSED-ARGS — pylint W0613 red-proof tests

## Summary
Created `tests/test_pylint_unused_args.py` — red-proof tests for pylint W0613
(unused-argument) detection, the ONLY tool in our stack that signals unused
arguments (ruff F841 is variable-only; deadcode classifies args as DC01 without
an argument-specific signal).

## What was done
- Added `tests/test_pylint_unused_args.py` with three test groups:
  - **TestPylintW0613Detector** (10 tests): validates that pylint flags unused
    args on functions, methods, and directories; passes when all args used;
    respects `_` dummy-var convention; handles `self`/`cls` exemption correctly.
  - **TestAntiOverBlock** (2 tests): proves ruff F841 behaviour is unchanged.
  - **TestBaselineCountSanity** (1 test): asserts the real product tree has
    W0613 findings (baseline ~46).

## Key observations
- pylint 4.0.6 defaults `ignored-argument-names` to `_.*|^ignored_|^unused_`,
  so test argument names must avoid those prefixes (used `spare`, `extra_arg`,
  `cfg`).
- `self`/`cls` are exempt; `@classmethod` other args are NOT exempt.
- The 46-product baseline from DEADCODE-TOOL-REDERIVE was confirmed in this
  worktree (`pylint --disable=all --enable=W0613 src` reports 46 findings).
  The 3-ksf portion lives in the separate keystone_framework checkout, which
  is not present here, so it could not be re-verified from this ticket.

## Files owned
- `tests/test_pylint_unused_args.py`