repo: charon-private
tier: economy
difficulty: 2
priority: 0
work_class: rig-meta
branch: feat/review-dispensation-canary
owns: fleet/tests/review-dispensation-canary.test.sh
real-dep: RECONCILE-REVIEW-GATE owns fleet/checks/reconcile-review-gate.sh (the check this
  ticket's canary drives) and already ships its own fault-seed test
  (fleet/tests/reconcile-review-gate.test.sh, R-J/R-K/R-L classes). This ticket does NOT rebuild
  that check — it REUSES it and adds the composite/#200-specific fault classes the design doc
  calls out (builder==reviewer explicitly) as a plane-canary dogfood, registered under the
  "review" plane.
real-dep: PLANE-CANARY-REGISTRY seeds this plane's registry row at the exact
  fleet/tests/review-dispensation-canary.test.sh path this ticket owns — a genuine build prereq.
depends_on: PLANE-CANARY-REGISTRY, RECONCILE-REVIEW-GATE
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 3 "P5 review/dispensation" spec +
  "PROPOSED TICKET LIST" row 5.
note: |
  GAP plane (design doc Phase 3, #5) — the #200 no-op-review class. FOLDS INTO
  fleet/board/RECONCILE-REVIEW-GATE.md per the design doc explicitly ("folds into
  RECONCILE-REVIEW-GATE") — do NOT fork a second review-gate checker. RECONCILE-REVIEW-GATE's own
  fail-on-revert test already covers R-J (no marker), R-K (stale reviewed_sha), and the fail-closed
  unknown-path default; this ticket's dogfood ADDS the one class not yet exercised there:
  builder==reviewer (the reviewer field equals the author_model field on the SAME reviewed
  marker) -> must BLOCK, the literal #200 self-review incident shape. Hermetic per the design
  doc's spec: throwaway docs/review-log/<id>.md + fleet/state/reviewed/<id> fixture markers, no
  live board/PR state touched. [[adversarial-review-default-for-droid-prs]]
  [[reviews-use-our-own-tools]]
accept: |
  - fleet/tests/review-dispensation-canary.test.sh: drives fleet/checks/reconcile-review-gate.sh
    (unmodified, reused as-is) against three seeded fixtures: (a) reviewer == author_model on the
    same reviewed/<id> marker -> BLOCK; (b) reviewed_sha != merge sha (already covered by
    RECONCILE-REVIEW-GATE's own test — re-assert here as a composite smoke, not a duplicate
    unit); (c) a hot-path merge with no review fragment at all -> BLOCK. Correct marker (distinct
    reviewer, matching sha, fragment present) -> GREEN for all three.
  - This IS the fault-seed dogfood registered as the "review" plane's dogfood_test in
    fleet/plane-canary-registry.tsv (row already seeded by PLANE-CANARY-REGISTRY at this exact
    path) — no separate registration edit needed in this ticket.
  - fail-on-revert test: revert the builder==reviewer seed (make the fixture pass a
    distinct-reviewer marker while still labeled "self-review test") -> the (a) assertion goes
    RED, proving it isn't a tautology.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — this is the fault-seed proof
    for the review/dispensation gate itself (the literal builder==reviewer #200 class); a false
    GREEN here would mean the gate meant to catch self-review can't be trusted. Manager gates,
    PR does NOT merge on the builder's self-report.
scope: |
  Fault-seed dogfood + plane registration only. Does not modify
  fleet/checks/reconcile-review-gate.sh (RECONCILE-REVIEW-GATE owns it) and does not build
  BLAST-TIER substrate (parked, out of scope per RECONCILE-REVIEW-GATE's own note).
ds: |
  ## Dependencies & sequence
  depends_on PLANE-CANARY-REGISTRY (registry row) and RECONCILE-REVIEW-GATE (the check reused —
  real build prereq, marked above). Disjoint owns from every other gap-canary ticket in this
  wave — parallelizable with FAILOVER-CANARY, EGRESS-KEY-CANARY, TICKET-LIFECYCLE-CANARY,
  BALANCE-CANARY, CONFIG-SSOT-CANARY-REGISTER, LANDING-GATE-REGISTER.
