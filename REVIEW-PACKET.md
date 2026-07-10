# REVIEW PACKET — ACTUALS-LEDGER-WAVE1

## Files Changed + Line Ranges

| File | Lines | Change |
|---|---|---|
| `src/charon/capability/__init__.py` | 1–14 | New package init |
| `src/charon/capability/actuals.py` | 1–122 | Actuals ledger — append-only JSONL keyed by (model, work_class) |
| `src/charon/capability/scorecard.py` | 1–204 | Freeze-ring scorecard with latest + LKG fallback reader |
| `tests/test_actuals_ledger.py` | 1–208 | 12 tests including FAIL-ON-REVERT |

## Root Cause / Approach

**What:** Scaffold the real-outcomes ranker subsystem for deterministic byproduct recording.

**Approach:**
- `ActualsLedger` — append-only JSONL store, one row per headless sub-session. Crash-safe: torn trailing line skipped on read. Keyed by (model, work_class). Stores run_result, packet_parses, fail_on_revert_pass, gate_pass, failover_hops, tokens, wall_clock_ms. D2 manager_accept column kept separate and optional (never dominates).
- `ScorecardStore` — freeze-ring reader with versioned artifacts (`scorecard.{seq}.json`). Red-team fix #2: `read_latest()` returns the latest frozen artifact, falling back to LKG, then scanning backward through older artifacts if both latest and LKG artifacts are corrupt. Must NOT import rig grader — no references to `fleet` or `benchmark`.

## FAIL-ON-REVERT Test

**Name:** `test_fail_on_revert_corrupt_latest_falls_back_to_lkg`

**Run command:**
```
PYTHONPATH=src python3 -m pytest tests/test_actuals_ledger.py::test_fail_on_revert_corrupt_latest_falls_back_to_lkg -v
```

**What it does:**
1. Freezes two scorecard artifacts (seq=1, seq=2)
2. Corrupts the latest artifact file (seq=2) with invalid JSON
3. Asserts `read_latest()` returns seq=1 (LKG) instead of None
4. **Goes RED** if the LKG fallback is removed from `ScorecardStore.read_latest()`

## Self-Run Full Gate Result

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

## Residual Risk + Blast Radius

| Risk | Severity | Mitigation |
|---|---|---|
| `capability` sub-package has no `__all__` | Low | Package is a standalone leaf; nothing imports from it yet |
| Manager_accept stored in-band with deterministic data | Low | Optional field, never read for score derivation |
| LKG scan is O(n) backward walk | Low | Only invoked when the primary fallback artifact is also unreadable (rare edge case) |
| No integration with CLI or gate command yet | None | Wave 1 is pure scaffold; CLI wiring deferred to Wave 2 |

**Blast radius:** Entirely contained within `src/charon/capability/` and `tests/test_actuals_ledger.py`. Zero changes to existing modules. Existing tests: 1379 passed, 0 failed.

## Commit SHA

```
32899d6 ACTUALS-LEDGER-WAVE1: scaffold real-outcomes ranker with freeze-ring LKG
```
