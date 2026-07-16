repo: charon-private
tier: strong
difficulty: 4
work_class: design-review
parked: operator-led DEEP-DIVE next session — the operator will personally investigate/design this before it is built (2026-07-16). Do NOT route to an SG droid; unpark only after the operator's design deep-dive lands. It also gates BENCH-OOB-GRADING (#26) which stays parked until this resolves.
branch: feat/bench-provisional-scoring
serial_justified: One cohesive stage-plumbing design + rewire across the shared scorecard call sites; splitting fractures the provisional→active contract.
owns: fleet/state/BENCH-PROVISIONAL-SCORING-DESIGN.md
depends_on:
dep-kind:
work_class_note: money/trust-adjacent — scores drive budget + routing; a wrong promotion rule makes untrusted scores steer real spend.
note: |
  #20. WHAT IT IS (grounded from code 2026-07-16): the scorecard STAGE mechanism. Every row a
  tool emits defaults `stage=provisional`; it is only PROMOTED to `stage=active` by a trusted
  live grade. Consumers trust ONLY active: `budget-derive.py:29` ("a provisional MERGE is not
  yet trustworthy"), routing/grades read active. Path-C dogfood probes are COLLECTED as
  provisional, never auto-promoted. Toggle: `CHARON_SCORECARD_STAGE=provisional|active`
  (dogfood-to-scorecard.sh:16-116). It REWIRES the shared call sites — benchmark/bench.sh +
  grade_state.record + the scorecard append — for stage plumbing; BENCH-OOB-GRADING (#26)
  is file-sequenced AFTER it (must rebase onto #20, never co-write) and stays parked until it lands.
  OPERATOR (2026-07-16): "bench-provisional-scoring was supposed to be something I would have next
  session do a deep dive." So this ticket is that deep-dive: investigate + DESIGN first, then build.
accept: |
  - DEEP-DIVE DESIGN (operator-led) first, written to fleet/state/BENCH-PROVISIONAL-SCORING-DESIGN.md:
    the provisional→active state machine — who/what may PROMOTE a row to active (must be a trusted
    OOB/live grade, never a self-reported or dogfood probe), where the promotion is enforced (which
    call site), fail-closed default (unknown/unpaired → provisional, never active), and how it
    composes with the OOB grader (#26) that verifies scores.
  - Only AFTER the design is reviewed: the rewire of grade_state.record + scorecard append + bench.sh
    to carry stage, with a fail-on-revert test — a provisional row NEVER influences budget/routing;
    only a trusted-grade promotion flips it to active.
  - Decision recorded so BENCH-OOB-GRADING (#26) can rebase onto the landed stage plumbing.
scope: |
  DESIGN-FIRST integrity ticket (money/trust-adjacent). Blast radius: every score that steers budget
  + routing. Operator-led deep-dive; adversarial review before any build lands. Resolves the dangling
  `build-after: BENCH-PROVISIONAL-SCORING` reference on BENCH-OOB-GRADING (now a real ticket).
ds: Next session, OPERATOR-LED. Gates BENCH-OOB-GRADING. Parked until the deep-dive design lands.
