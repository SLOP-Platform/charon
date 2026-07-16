# STALE-CHECK-SH — stale-check.sh + hermetic test file

**Tier:** strong / difficulty 2 / ci-infra

## Change

- `fleet/stale-check.sh` — standalone stall + quarantine detector. Reads two ground-truth
  sources: `state/claims/<id>` mtimes (same "held-by / age" signal `status.sh` renders)
  and `state/loop-guard/<id>` quarantine markers. Exits nonzero if any session is past the
  stall threshold (default 900s) or quarantined. NOT wired into preflight.sh (owned elsewhere);
  output notes that preflight should call it.
- `fleet/tests/stale-check.test.sh` — dedicated FAIL-ON-REVERT hermetic test. Covers stale
  flagging, fresh non-flagging, quarantine detection, and clean-exit scenario. Exit code
  assertions guard against revert (removing the check → always-silent → always-exit-0 →
  test fails).

## Design decisions

1. **Reads state/claims/ directly** rather than shelling out to status.sh or the session-bridge
   API, because the claim-marker mtime is the canonical ground truth and bypassing the extra
   layer keeps the script hermetically testable via `STALE_CLAIMS_DIR`.
2. **Reads state/loop-guard/ directly** rather than calling `loop-guard.sh list`, because
   loop-guard.sh hardcodes its state dir from its script path with no env-override hook
   (and is owned elsewhere, so not edited here). Direct file parsing uses the same
   `droid=/count=/quarantined=/reason=` convention loop-guard.sh's own `list` subcommand uses.
3. **Split test file** from LAUNCH-PLAN-GATE's combined `launch-plan.test.sh` so stale-check
   and launch-plan don't share a test-file surface (incompatible with disjoint ownership).

## Scope check

`git diff --name-only master...HEAD`:
- fleet/stale-check.sh ✓ (owned)
- fleet/tests/stale-check.test.sh ✓ (owned)
- docs/review-log/STALE-CHECK-SH.md ✓ (review fragment, per-ticket)
