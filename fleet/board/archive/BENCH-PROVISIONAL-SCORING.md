repo: charon-private
tier: strong
difficulty: 4
work_class: design-review
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
  CORRECTED (2026-07-16, operator): "that directive is WRONG it's for YOU to investigate not the
  operator." The deep-dive is CLAUDE's to run, not the operator's. This ticket is therefore
  CLAUDE-RESERVED — the MANAGER investigates it via its own background Claude sub-session (see
  [[claude-reserved-tickets-manager-builds]]); it is NOT operator-led and NOT starved waiting on a
  human. The old `parked:` line asserting operator-led / "do NOT route to an SG droid" is REMOVED.
  NO `claude_reserved:` FIELD IS SET HERE ON PURPOSE. A first draft added one; nothing in the rig
  reads it (grep: zero consumers), so it would have been DECORATION that LOOKS like a guard and
  isn't — the same failure mode as the prose park above, which also looked like a guard and let an
  SG droid through. The gap is real (no mechanism means "not for SG droids, but DO work it via
  Claude" — parked means nobody works it, which this ticket must never be), so it is ticketed as
  CLAUDE-RESERVED-ROUTING rather than faked with an inert field.
  UN-PARK NOTE: that park never actually held. It was written as PROSE, and every consumer tested
  `parked == "true"` literally, so claim.sh read it as UNPARKED — an SG droid claimed this ticket
  anyway and produced the 425-line design in PR #107. The park was fiction; the predicate is fixed
  on master (fa07ca0), so a future park here would really bite. Do not re-add one casually.
  STATE (2026-07-16): PR #107 carries a REAL 425-line fleet/state/BENCH-PROVISIONAL-SCORING-DESIGN.md
  + review log; its final "launcher auto-commit" commit (bc15076) is CRASH DEBRIS that swept in an
  unrelated fleet/board/REVIEWER-DOGFOOD-REDS.md (owns violation — split it out). The deep-dive is
  therefore a CLAUDE ADVERSARIAL REVIEW of that existing design, not a from-scratch design.
  It gates BENCH-OOB-GRADING (#26), which gates MODEL-PREFLIGHT + GRADER-SECFIX-RECONCILE — the
  single highest-leverage blocker on the board (3 tickets).
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
