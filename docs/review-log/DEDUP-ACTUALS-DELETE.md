# DEDUP-ACTUALS-DELETE review

Confirmed inert: `check_inert_code.py` listed `ActualsLedger`/`ActualRow` as stale after deletion
(deleted symbols can no longer be flagged as dead).

## Changes

1. **DELETED** `src/charon/capability/actuals.py` — entire `ActualsLedger`/`ActualRow` dead module.
2. **EDITED** `src/charon/decompose_sizing.py:54` — removed the `capability.actuals.ActualsLedger`
   reference from the calibration TODO comment.
3. **DELETED** `tests/test_actuals_ledger.py` — removed dead-module tests.
4. **PORTED** ScorecardStore tests from `test_actuals_ledger.py` into
   `tests/test_capability_matrix.py` (ScorecardStore is LIVE code exercised by these tests).
5. **FILED** a follow-up build-rig ticket (TSV-APPEND-UNIFY) for
   TOOL-AUDIT-REDUNDANCY finding 6 (dual TSV appenders, rig-side).

## Accept verification

- `grep -rn "ActualsLedger\|ActualRow" src/ tests/` → zero hits.
- `PYTHONPATH=src python3 tools/check_inert_code.py` → no longer flags them.
- `PYTHONPATH=src python3 -m pytest -q` → 1827 passed, full suite green.
- the TSV-APPEND-UNIFY follow-up ticket exists in the build rig, referencing TOOL-AUDIT-REDUNDANCY.
