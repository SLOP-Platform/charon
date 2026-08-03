# RIG-CI-GATE-REPAIR — review-log fragment

## What this ticket ships
- `fleet/state/tier-drift-red.txt` — the HARD-FAIL set for validate_board.sh check 2f (TIER-DRIFT).
  Committed with `!fleet/state/tier-drift-red.txt` in `.gitignore`. Non-vacuous (12 ids).
- `fleet/state/service-registry.tsv` — the declarative SSOT of every supervised service.
  Committed with `!fleet/state/service-registry.tsv` in `.gitignore`. Round-trips through generate-monit-config.sh --check.
- `fleet/tests/tier-drift.test.sh` — hermetic suite with synthetic fixtures; no live board coupling.
  CHARON_TIER_RANKS_CMD pinned for CI hermeticity. 44 assertions, all pass.
- `fleet/tests/board-file-ratchet.test.sh` — fork-bomb guard re-entrancy fix (env -u RIG_CI_TESTS_ACTIVE for probe).
  8 assertions, all pass.
- `fleet/watchdog/monit.d/canary-service.conf` — generated from service-registry.tsv.

## Scope-clean check
All owned files (5 paths) identical to origin/master after reset-to-master. Zero off-scope diffs.

## Pre-existing gate failures (NOT owned by this ticket)
- `test_live_board_drift_is_exactly_the_pending_retiers` in `fleet/capability/tests/test_tier_classify.py:142` — FAILING on master.
  Cause: the test asserts the pending-retiers set matches a hardcoded corpus that is stale.
  The pytest suite that rig-ci runs does not include this test (it's not in the allowlist).
- Ruff E701 errors in `fleet/benchmark/grader-daemon.py` — pre-existing, not owned by this ticket.
- Mypy errors in `fleet/capability/tests/test_tier_classify.py` — pre-existing import issues, not owned.

## Verification
- `bash fleet/tests/tier-drift.test.sh` → 44 passed, 0 failed
- `bash fleet/tests/board-file-ratchet.test.sh` → 8 passed, 0 failed
- `.gitignore` negations for both state files present and correct

## Decision
This ticket was landed by a prior run (commit 8d6147d on master). The branch `fix/rig-ci-gate-repair` carries no additional diff. No new commit needed.
