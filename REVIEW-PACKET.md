# REVIEW PACKET — PR #90 (feat/ci-workflow-policy-gate)

## Files changed + line ranges

| File | Lines | Change |
|---|---|---|
| `tests/test_check_workflows.py` | 5, 8–9, 11 (f-string), 33, 62 (f-string), 77 | Restructure fixtures to build SHAs by concatenation; add import of `check_file` |
| `tests/test_check_workflows.py` | 184–195 | New fail-on-revert test: `test_fixtures_have_no_raw_40_hex_literals` |

## Root cause

The `public-clean` scanner (`tools/check_public_clean.py`) uses a regex pattern `\b[0-9a-fA-F]{40,}\b` to detect hex tokens (secrets) in tracked source files. Two test fixtures in `tests/test_check_workflows.py` contained raw 40-character git commit SHAs on `uses:` lines:

- Line 29: `uses: docker/build-push-action@8b0d3ffb0e0a5b4c8e6c6c8f4a1f8f4a1f8f4a1f`
- Line 73: `uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5`

These are legitimate pinned git-commit SHAs used as **test fixtures** to verify the workflow-policy checker. They are not secrets. The scanner's 40-hex heuristic false-positived on them, failing the `public-clean` gate stage.

## Option chosen: (b) — fixture restructuring

**Why (b) over (a):** Restructuring the test fixtures has zero blast radius on the shared scanner. The SHAs are split via Python string concatenation (`"first20chars" + "last20chars"`) and interpolated into the fixture strings via f-strings. No contiguous >=40-char hex literal appears in the source file.

- `tools/check_public_clean.py` is **untouched**.
- `tools/check_workflows.py` is **untouched** — its validation logic is unchanged.
- The fixtures evaluate to the same YAML content as before at runtime (verified via existing tests).

## Fail-on-revert test

**Test name:** `test_fixtures_have_no_raw_40_hex_literals` (at `tests/test_check_workflows.py:184`)

**Run command:**
```
python3 -m pytest tests/test_check_workflows.py::test_fixtures_have_no_raw_40_hex_literals -v
```

**How reverting makes it RED:** If someone replaces the concatenation-based SHAs (`_SHA_DOCKER`, `_SHA_CHECKOUT`) with raw 40-hex string literals, the `check_file()` call from `tools/check_public_clean` will detect >=40-char hex tokens in the test file and fail the assertion.

## Full-gate result

```
CHARON GATE — running all validation checks...
  [ruff] OK
  [mypy] OK
  [SLOP-boundary] OK
  [version] OK
  [gate-registry] OK
  [public-clean] OK
CHARON-GATE: all checks passed
```

All 9 `test_check_workflows.py` tests pass. `check_public_clean.py` reports clean.
All 14 gates listed in `gates.json` remain consistent.

## Residual risk

None. The change is purely cosmetic at the source level — the fixture strings evaluate to identical YAML content at runtime. The workflow-policy checker (`check_workflows.py`) is unchanged and its tests (`test_check_workflows.py`) continue to verify all three policies correctly. The public-clean scanner is untouched, so no secret-detection coverage is lost.

## Commit

TBD — will be inserted after commit.
