# STUCK-TICKET-LOUD-VISIBILITY -- Review Log

## Ticket
STUCK-TICKET-LOUD-VISIBILITY: stuck/quarantined tickets must be LOUD, never silent.

## RCA
2026-07-23 deadlock: a P0 keystone ticket was loop-guard-quarantined
("repeated zero-commit re-claims") and NOTHING was loud about it -- the pool
went dry and the rig deadlocked. Quarantined tickets were a silent state marker;
no status.sh/report.sh/preflight emitted them, so a structural wedge looked
exactly like "pool drained, nothing to do."

## Decision: four-category stuck detector
- **quarantined**: loop-guard marker exists, ticket has board file, not done/submitted.
  The core fix -- these were the silent killer.
- **parked**: explicit operator hold (parked: field). Already in status.sh but
  surfaced in the unified stuck dashboard.
- **dep-dissolved**: depends_on references a ticket with no board/archive/done.
  This ticket can NEVER unblock.
- **orphan-marker**: state marker exists for an id with no board file. Residue
  from a deleted ticket.

## Decision: quarantine narrowing documented, not enforced here
loop-guard.sh may quarantine ONLY for genuine MODEL-ATTRIBUTABLE failure. A
structurally-wedged ticket surfaces as STUCK, not silently quarantined. The
narrowing is DOCUMENTED in stuck-ticket-loud.sh as the prevention half; the
detector surfaces ALL quarantines loudly regardless of cause (fail-safe: a
mis-quarantine being loud is strictly better than a real quarantine being silent).

## Decision: quarantine marker validation
Files in state/loop-guard/ are validated as real quarantine markers by checking
for the "droid=" header (matching loop-guard.sh::record output). Other state
files in that directory (GRACEFUL-DEGRADE, ROUTER-LEDGER-DECAY, etc.) are
ignored.

## Test results
- 37/37 tests pass (hermetic, offline)
- validate_board.sh GREEN
- fail-on-revert: neutered quarantine scan flips RED->GREEN

## Open questions
- Wire into preflight.sh::cmd_detect (follow-up ticket; not in owns for this ticket)
- Wire into status.sh board scan (follow-up ticket; not in owns)
- The stale loop-guard run counters under state/loop-guard/runs/ are not
  cleaned by this check (scope: read-only; those are fleet-droid.sh's job)
