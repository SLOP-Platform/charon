repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: money-path
branch: feat/balance-canary
owns: fleet/balance-canary.sh, fleet/tests/balance-canary.test.sh
real-dep: PLANE-CANARY-REGISTRY seeds this plane's registry row at the exact
  fleet/balance-canary.sh / fleet/tests/balance-canary.test.sh paths this ticket owns, and
  creates fleet/plane-canary.sh's shared runner/reconciliation-leg contract this canary must
  satisfy to go GREEN — a genuine build prereq, not a merge-order preference.
depends_on: PLANE-CANARY-REGISTRY
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 3 "P3 money/balance" spec +
  "PROPOSED TICKET LIST" row 7.
work_class_note: money-path — asserts BalanceTracker ledger-decrement PERSISTENCE and the
  funding-class park lifecycle, the literal #167 inert-meter class this ticket extends coverage
  of. [[e2e-dogfood-norm-for-money-code]]
note: |
  PARTIAL plane (design doc Phase 3, #3) — fleet/flow-canary.sh STAGE 2
  (fleet/flow-canary.sh:286-324) already covers the served-count+cost DELTA (the #167 inert-meter
  guard) but NOT ledger PERSISTENCE (does the decrement survive a status re-read, not just an
  in-memory counter bump) or the funding-class PARK LIFECYCLE (drain -> parked=true -> excluded
  -> re-admit persists across restarts). This ticket EXTENDS flow-canary's STAGE 2 into a
  standalone dedicated canary for those two persistence properties — it does not duplicate the
  delta assertion flow-canary already proves. [[charon-meter-inert]]
accept: |
  - fleet/balance-canary.sh: (a) ledger-decrement persistence — send a real request, read
    /charon/status, record the balance; re-read /charon/status again (a second, independent read,
    not a cached response) and assert the decrement is STILL there (proves persistence, not an
    in-memory-only counter that would reset on re-read); (b) funding-class park lifecycle — drain
    a leg, assert parked=true persists across a re-read, assert it is EXCLUDED from the served
    path (reuse flow-canary.sh STAGE 3's #188 park-exclusion assertion pattern, do not
    reimplement), re-admit it, assert it is served again. Reuses BalanceTracker's live
    /charon/status surface exactly as flow-canary.sh does (token from opencode.json, state from
    /charon/status) — never re-implements the meter.
  - Fault seeds (RED->GREEN, one pair per class): decrement-no-op (persisted value doesn't
    change across the two reads despite a served request) -> RED; park-not-persisted (parked flag
    resets on re-read) -> RED; re-admit-no-op (a re-admitted leg still excluded from serving) ->
    RED. Each seed reverts to GREEN once the underlying persistence is correct.
  - fail-on-revert test (fleet/tests/balance-canary.test.sh): seed each of the three fault
    classes above against a hermetic fake /charon/status backend (mirror
    fleet/tests/flow-canary.test.sh's scenario.json-rewrite pattern) -> assert RED; revert each
    seed -> GREEN; a revert-proof re-run confirms green-is-not-a-fluke (mirror
    flow-canary.test.sh:300-305).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — money-path canary; a false
    GREEN here means a silent ledger-decrement no-op or a park-lifecycle regression could ship
    undetected. Manager gates; PR does NOT merge on the builder's self-report.
scope: |
  Ledger-persistence + park-lifecycle canary only. Does not modify BalanceTracker itself or
  src/charon/gateway.py's meter code — read-only assertion against the live /charon/status
  surface, extending flow-canary's STAGE 2 coverage, not replacing it.
ds: |
  ## Dependencies & sequence
  depends_on PLANE-CANARY-REGISTRY only (registry row already seeded at this exact path).
  Disjoint owns from every other gap-canary ticket in this wave — parallelizable with
  FAILOVER-CANARY, EGRESS-KEY-CANARY, REVIEW-DISPENSATION-CANARY, TICKET-LIFECYCLE-CANARY,
  CONFIG-SSOT-CANARY-REGISTER, LANDING-GATE-REGISTER.
