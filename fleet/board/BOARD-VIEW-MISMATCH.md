repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: fix/board-view-mismatch
depends_on:
owns: fleet/status.sh, fleet/tests/board-view-parity.test.sh, docs/review-log/BOARD-VIEW-MISMATCH.md
serial_justified: |
  One eligibility definition shared by two readers. Splitting it ships two more views of the
  same board, which is the defect.
substrate: N/A
substrate-novel: |
  Nothing adopted. Both readers exist; the novel slice is making them agree and making exclusion
  auditable.
accept: |
  MEASURED 2026-08-02: status.sh reports a ticket `ready` while claim.sh silently skips it. Five
  filters live ONLY in claim.sh and none surfaces a reason — the droid just prints
  "no <tier>-eligible work":
    1. loop-guard quarantine set (state/loop-guard/<id>)
    2. `note ~ /PARKED/` — a SUBSTRING match against free-form prose. Currently excludes 3 live
       tickets that have NO parked: field: BENCH-OOB-GRADING, GATEWAY-GRADE-ORDER-MVP,
       PRICE-REFRESHER
    3. tier-rank (`trank > drank`)
    4. own/other tier pass
    5. claimed/submitted/done sets
  WORSE: `--only <ID>` is applied BEFORE these, so a hard pin is silently overridden. Two
  targeted tabs produced nothing today with no diagnostic whatsoever.
  Done contract:
  1. ONE shared eligibility function used by BOTH status.sh and claim.sh. Divergence is the bug.
  2. status.sh must show the REAL state — `guarded`, `excluded(reason)` — never `ready` for a
     ticket claim.sh will skip.
  3. `--only` naming a ticket that a filter drops must FAIL LOUD, naming the filter. A silently
     overridden hard pin is the false-green class.
  4. Replace the /PARKED/ prose grep with the structured `parked:` field only (is_parked_value in
     _lib.sh already exists and is asserted by parked-semantics.test.sh).
  5. Fail-on-revert: a guarded ticket must not read `ready`; an --only drop must not be silent.

## Dependencies & Sequence

P0. No inbound deps. Blocks nothing structurally but makes every other lane's progress
observable — today it hid P0 tool tickets from their own tabs.
