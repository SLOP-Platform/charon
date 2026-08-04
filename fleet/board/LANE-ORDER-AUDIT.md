repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: design-review
branch: docs/lane-order-audit
owns: docs/review-log/LANE-ORDER-AUDIT.md
depends_on:
dep-kind:
work_class_note: design-review — re-sequences the programme by blast radius and real dependency.
  Read-only analysis; it moves no code and changes no lane content, only order.
note: |
  ⛔ OPERATOR, 2026-08-04: *"should we audit the A B C and maybe logically/blast radius move some
  elements around in the sequence? have the next session adversarial review it?"* — YES to both.
  **This ticket REQUIRES an adversarial review of its own conclusion before the order changes.**

  ## WHY NOW — the ordering has drifted from its own justification
  D-010 approved: Lane A first (turn on what we own — it makes every later verdict measurable),
  Lane C in parallel (read-only, cannot collide), Lane B last and as a cutover-with-deletion.
  That was sound when written. What has changed since:
  - **Lane A is largely DONE** (tool-enablement ratchet, shellcheck, status board, three scanners now
    REQUIRED). Its remaining named items are diff-cover (built, INCOMPLETE) and hypothesis (0 refs).
  - **Lane C is stalled at 2/3 and never resumed** — AXIS 2 candidates were NAMED, never EXECUTED
    (~50 tools, ~10 re-test rows). It was supposed to run "in parallel" and did not, across multiple
    sessions. An ordering that is repeatedly not followed is evidence about the ordering.
  - **Several items now cut ACROSS lanes.** The durable-queue question is simultaneously Lane C's
    top unexecuted trial, Lane B's ~6,000-LOC deletion target, and the D-008a blocker on the Go
    supervisor — which in turn blocks TAB-RELIABILITY, which the operator has set HIGH priority.
    A single question gating three lanes is a sequencing smell.
  - **New p0 work exists that predates no lane at all:** LIFECYCLE-ENFORCEMENT, DEPLOY-MECHANIZE,
    FINDING-CAPTURE-MECHANIZE, TAB-RELIABILITY.

  ## THE QUESTION TO ANSWER — order by BLAST RADIUS and REAL DEPENDENCY, not by lane letter
  For every open programme item, state: what breaks if it is wrong; what it BLOCKS; what blocks it;
  and whether it is reversible. Then propose an order and NAME WHAT MOVES AND WHY.
  Specific hypotheses to test, not to assume:
  1. **Does enforcement now outrank Lane A's remainder?** Every recurring failure here is "nothing
     BLOCKS on an unfinished commitment" (D-003). Turning on more linting does not fix that.
  2. **Should the durable-queue trial be pulled OUT of Lane C and run first as its own item**, since
     three separate things wait on it?
  3. **Is "Lane B last" still right?** It was justified as a cutover-with-deletion, but the rig is
     2.4x the product and is what breaks. Does deferring it keep paying interest?
  4. **Does DEPLOY-MECHANIZE outrank most of it?** A fix that never reaches production has zero
     value regardless of which lane produced it — measured 2026-08-04: D-012 leaked for a full day
     after it merged.
  5. Which items are genuinely parallel-safe (disjoint `owns:`) versus merely believed to be?

  ## ⛔ MANDATORY ADVERSARIAL REVIEW — operator-requested ⛔
  The proposed order MUST be adversarially reviewed before adoption, by a reviewer briefed to REFUTE
  it. The reviewer must specifically attack: reordering that is really just preference; any claimed
  dependency that is merely a merge-order convenience (the board gate already distinguishes these —
  a disjoint-owns dep needs `real-dep:`); any item promoted without a blast-radius argument; and
  whether the proposal quietly drops work rather than sequencing it.
  ⚠️ **A re-sequence that is not adversarially reviewed does not get adopted.** D-010 is an ACTIVE
  operator decision — per the ledger no session may act contrary to it, so this ticket may only
  PROPOSE a replacement for operator ruling. It must not silently reorder the programme.

  ACCEPTANCE: (a) every open programme item classified by blast radius, blocks, blocked-by and
  reversibility; (b) an explicit proposed order naming exactly what MOVES and why; (c) an adversarial
  review attached, with its objections either answered or accepted; (d) a single clear question put
  to the operator, since only they can supersede D-010.
