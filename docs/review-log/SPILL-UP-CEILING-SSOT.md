# Review: SPILL-UP-CEILING-SSOT
**Ticket:** fleet/board/SPILL-UP-CEILING-SSOT.md
**Date:** 2026-08-02
**Branch:** fix/spill-up-ceiling-ssot

## Verdict
APPROVE

## Change
Added `SPILL_UP_COST_CEILING = strong` to `fleet/state/TIER-CANON.md` (the cost-band SSOT),
between the threshold rationale and the price-input section. The awk extraction at
`fleet/fleet-droid.sh:276` now returns `strong` instead of empty, so the cost-driven
spill-up guardrail activates across all fleet-droid tabs.

## Verification
- `awk` extraction confirms `strong` is returned (verified via the exact awk expression the
  dispatcher uses).
- `fleet/tests/spill-up.test.sh`: 55/55 pass, including cost-cap cases (d)(g)(h)(i)(j)(k)(l)(m)(n)
  that exercise the REAL SSOT ceiling.
- `grep -c SPILL_UP_COST_CEILING fleet/state/TIER-CANON.md` returns 1 (was 0 before this change).

## Fail-on-revert
Removing the key from TIER-CANON.md reverts spill-up to FAIL CLOSED: the awk returns empty,
`spill_ceiling_tier()` echoes nothing, and the launcher emits `COST-CAP: no usable
SPILL_UP_COST_CEILING` and disables spill-up fleet-wide. The spill-up test's canon-no-key
cases (i1-i4) explicitly assert this revert behavior — they PASS now and would PASS after
a revert, confirming the fail-closed invariant holds in both directions.

## Known residual
The ceiling value (`strong`) is a policy choice: it prevents economy→strong→frontier
cascading but permits economy→strong escalation. The operator may raise it to `frontier`
by editing this file; no code change is required.
