# RECONCILE-REVIEW-GATE — Review Log

## Ticket
RECONCILE-REVIEW-GATE: Folded review-gate axis (§2.1) + fail-closed taxonomy (§2.2) from UNIFIED-RECONCILIATION-GATE-DESIGN.md.

## What was done
- **fleet/checks/reconcile-review-gate.sh**: Implements the review-gate check with:
  - R-J detection: ≥hot-path change with no review-log fragment AND no reviewed/<id> marker
  - R-K detection: reviewed_sha != expected merge sha (stale review)
  - R-L detection: verdict=FIXES with no follow-up CONFIRMED-CLEAN (doom-loop via ReviewerCircuitBreaker pattern)
  - Fail-closed taxonomy: unknown `src/charon/*` path → hot-path; unknown `work_class` → hot-path; unknown `docs/*`/`fleet/*` → tier 0
  - `check` subcommand (hard gate, exit 1 on BLOCK) and `scan` subcommand (advisory, always exit 0)
  - Env-var overrides for test isolation (BOARD, STATE, REVIEW_LOG, REVIEWED, MERGE_SHA)

- **fleet/tests/reconcile-review-gate.test.sh**: 15 fail-on-revert tests covering:
  - (a) R-J: no evidence → RED; add matching marker → GREEN
  - (b) R-K: stale sha → RED
  - (c) fail-closed: unknown src/charon path → classified hot-path → review required
  - (d) economy/docs → GREEN (below hot-path threshold)
  - (e) R-L: verdict=FIXES → RED; CONFIRMED-CLEAN → GREEN
  - (f) self-review → RED
  - (g) operator-reviewed → GREEN
  - (h) unknown work_class → fail-closed hot-path
  - (i) standard docs → GREEN
  - (j) fail-on-revert: removing fail-closed taxonomy lets unknown src/charon path pass silently

## Key decisions
- **Reuses ReviewerCircuitBreaker pattern** from `src/charon/failover.py:73-142` for R-L doom-loop detection (as specified in design). Implemented as a bash pattern matching the Python circuit-breaker's state machine for the FIXES-without-follow-up case.
- **Path-pattern fallback** marked as `REMOVE WHEN BLAST-TIER SUBSTRATE LANDS` — once `src/charon/blast_tier.py` ships, the hardcoded path patterns in `classify_ticket()` should be replaced by calling the substrate.
- **Env-override test seam** follows the established pattern from `rule-sync.sh` and `reconcile-merged.sh`.
- **Isolated fixture per test** — each test section creates its own `mktemp -d` fixture so previous RED assertions don't cascade into later GREEN assertions.

## Scope check
Changed files: `fleet/checks/reconcile-review-gate.sh`, `fleet/tests/reconcile-review-gate.test.sh`, `docs/review-log/RECONCILE-REVIEW-GATE.md`

## Self-test results
```
15 passed, 0 failed
ALL RECONCILE-REVIEW-GATE TESTS PASS
```

## FAIL-ON-REVERT proof
- Reverting the fail-closed default (`src/charon/* → hot-path`) in `classify_ticket()` makes test (j) go GREEN (it expects RED for an unknown src/charon path with economy tier and no review evidence). Proving the fail-closed posture is what enforces review for unknown paths.
- Reverting the R-K check (stale sha comparison) in `check_ticket()` makes test (b) go GREEN (it expects RED for a marker with stale sha).
- Reverting the R-L check (verdict=FIXES → doom loop) in `check_ticket()` makes test (e) go GREEN (it expects RED for FIXES without follow-up).
- Reverting the self-review check makes test (f) go GREEN.
