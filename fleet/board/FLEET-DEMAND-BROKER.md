repo: charon-private
tier: frontier
difficulty: 4
priority: 2
work_class: money-path
branch: feat/FLEET-DEMAND-DRIVEN-ROUTING-avail-cap
commit: 2ab0518
worktree: /home/stack/charon-private-wt/FLEET-DEMAND-BROKER
owns: fleet/capability/availability.py, fleet/capability/assign.py, fleet/capability/tests/test_availability_capped.py, fleet/tests/spill-up.test.sh, fleet/tests/assign-dispatch.test.sh, fleet/tests/test_detention.sh, fleet/fleet-droid.sh, fleet/state/TIER-CANON.md
serial_justified: ALREADY BUILT as one commit (feat/FLEET-DEMAND-DRIVEN-ROUTING-avail-cap @ 2ab0518) — capped-model exclusion, cost-band spill-up and the SPILL_UP_COST_CEILING cap are one money-path decision point across availability.py/assign.py/fleet-droid.sh; landing spill-up without its cost cap is an open spend path, so the pieces cannot land independently. Remaining work is adversarial review + land, not a build that could fan out.
depends_on: ASSIGN-DISPATCH-PICK-FIX, DROID-LIFECYCLE-REAP
real-dep: ASSIGN-DISPATCH-PICK-FIX shares fleet/capability/assign.py — it is SUBMITTED (built, PR
  open) and edits the same pick path this branch extends with capped-model exclusion. Land it first,
  rebase this on top; a parallel edit clobbers one of the two.
real-dep: DROID-LIFECYCLE-REAP shares fleet/fleet-droid.sh — SUBMITTED, edits the launcher's
  stand-down/cleanup path; this branch adds 242 lines to the same launcher. Merge-order only in
  file terms, but a genuine edit-collision.
priority_justification: P:2 (PRIORITY-LADDER "standalone, biggest blast-radius") — this is the MONEY
  path: cost-band spill-up without the SPILL_UP_COST_CEILING cap is an unbounded live spend path
  that every droid launch traverses. Biggest blast radius of the four repaired tickets, and it is
  already built. Not P:0/P:1 — it is not operator-escalated and not attached to active CG work.
work_class_note: money-path — the change decides which PRICED model a tier's work is dispatched to
  and adds the cost ceiling that bounds spill-up. A defect here spends real money.
state: BUILT + VERIFIED, NOT LANDED. Branch feat/FLEET-DEMAND-DRIVEN-ROUTING-avail-cap @ 2ab0518 is
  checked out in /home/stack/charon-private-wt/FLEET-DEMAND-BROKER, which already holds this
  ticket's live claim (fleet/state/claims/FLEET-DEMAND-BROKER).
predecessor: FLEET-DEMAND-DRIVEN-ROUTING (DONE) — that ticket replaced the static per-tier model
  CHAINS with a live demand query. It is CLOSED, so it cannot carry this branch: a done ticket is
  not claimable and no tab could pick this work up from it. This is the FOLLOW-ON slice, not a
  duplicate; scope is disjoint (that one built the demand query, this one bounds it).
note: |
  Broker hardening on top of the landed demand-driven switchboard. Three changes:
    1. CAPPED-MODEL EXCLUSION — a model that has hit its cap is excluded from the candidate set
       instead of being selected and failing at dispatch.
    2. COST-BAND SPILL-UP — when no candidate in the requested band is available, the broker spills
       UP a cost band rather than starving the tier.
    3. SPILL_UP_COST_CEILING — a fail-closed cost cap on (2): spill-up DETAINS on cap rather than
       climbing without bound. This is the money-path guard; without it (2) is an open spend path.
  Proof surfaces on the branch: fleet/capability/tests/test_availability_capped.py (161 lines),
  fleet/tests/spill-up.test.sh (219 lines), fleet/tests/test_detention.sh (detain-on-cap).
accept: |
  - Adversarial review (reviewer != builder) — money path + fail-closed cap; does NOT merge on the
    builder's self-report.
  - Fail-on-revert proof for the cost ceiling: with SPILL_UP_COST_CEILING set, a spill-up that would
    cross the ceiling DETAINS (not selects); revert the ceiling check → the test goes RED.
  - Capped-model exclusion proven by test: a model marked capped is absent from the candidate set.
  - Rebased onto landed ASSIGN-DISPATCH-PICK-FIX and DROID-LIFECYCLE-REAP before land.
  - bash fleet/validate_board.sh GREEN.
ds: |
  ## Dependencies & sequence
  depends_on ASSIGN-DISPATCH-PICK-FIX (SUBMITTED, shares fleet/capability/assign.py) and
  DROID-LIFECYCLE-REAP (SUBMITTED, shares fleet/fleet-droid.sh) — both are built and ahead in the
  merge queue; this branch rebases onto their landed versions.
  THIS ticket is the predecessor for LAUNCHER-CRASH-PARTIAL-DETECT, which now carries
  `depends_on: FLEET-DEMAND-BROKER` — it edits the same fleet/fleet-droid.sh stand-down path and
  was already sequenced behind DROID-LIFECYCLE-REAP, so the extra edge costs it no schedule time.
  Wave order on fleet/fleet-droid.sh: DROID-LIFECYCLE-REAP → FLEET-DEMAND-BROKER →
  LAUNCHER-CRASH-PARTIAL-DETECT.
  Concurrency safety: work this ticket from /home/stack/charon-private-wt/FLEET-DEMAND-BROKER —
  the branch is checked out there and that worktree already holds the claim.
