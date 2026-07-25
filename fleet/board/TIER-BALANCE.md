repo: charon-private
tier: strong
difficulty: 3
priority: 3
work_class: rig-meta
branch: feat/tier-classifier
commit: f1f162c
worktree: /home/stack/charon-private-wt/TIER-BALANCE
owns: fleet/capability/tier_classify.py, fleet/capability/tests/test_tier_classify.py, fleet/tests/tier-drift.test.sh, fleet/state/tier-drift-red.txt, fleet/validate_board.sh, fleet/checks/rig-ci-scope.sh, .gitignore
serial_justified: ALREADY BUILT as one commit (feat/tier-classifier @ f1f162c) — the classifier, its drift gate in validate_board.sh, its runner registration in rig-ci-scope.sh and its red-list are ONE contract: splitting them ships a gate with no classifier (or a classifier no runner executes), which is the exact non-enforcement the first review rejected. Remaining work is re-review + land, not a build that could fan out.
owns_data: fleet/board/*.md — the branch also rewrites the `tier:` FIELD ONLY on 36 board tickets
  (data edit, no logic). Declared here rather than in owns: so it does not register as a code-surface
  collision against every other live ticket; a rebase re-applies it with `tier_classify.py board-retier`.
depends_on: REPO-FIELD-REQUIRED
real-dep: REPO-FIELD-REQUIRED shares fleet/validate_board.sh and is already SUBMITTED (built, PR
  open) — its repo:-field check lands first and this branch's "2f" tier-drift block must be added on
  top of that version, not in parallel with it. Merge-order + real edit-collision on the same file.
priority_justification: P:3 (PRIORITY-LADDER band "standalone") — standalone board-tiering work with
  no live spend path of its own; it is BUILT and REVIEWED so it drains fast, but it is gated behind
  REPO-FIELD-REQUIRED landing anyway, so promoting it above the money-path/guardrail tickets would
  only reorder a blocked item. It unblocks REPO-MAP-CONVERGE and HANDOFF-GATE-NONBYPASSABLE
  (both sequenced after it on shared files).
work_class_note: rig-meta — mechanizes the rig's own work→tier classification and adds a preflight
  gate over the board's tier: fields. No product code.
state: BUILT + REVIEWED + FIXED, NOT LANDED. Branch feat/tier-classifier @ f1f162c is checked out in
  /home/stack/charon-private-wt/TIER-BALANCE. Remaining work = re-review of the fixes, then land.
review: fleet/state/reviews/TIER-CLASSIFIER-REVIEW-agen-kolar.md (verdict DO-NOT-LAND @ 0a759a8).
note: |
  Mechanizes work→tier classification (fleet/capability/tier_classify.py) and adds a tier-DRIFT gate
  to validate_board.sh (labelled "2f") so a ticket whose declared tier: disagrees with the derived
  tier fails preflight. Applied 36 board re-tiers: frontier 3→14, strong 89→74, economy 12→16.

  REVIEW HISTORY — the first review (agen-kolar, @ 0a759a8) returned DO-NOT-LAND on four
  independent non-enforcement defects: (F1) the drift check could never go RED because the
  hard-fail id list fleet/state/tier-drift-red.txt did not exist; (F2) it went GREEN if the
  classifier file was missing/renamed; (F7) its 15 tests were executed by no gate, no CI job and no
  land path; and an over-broad SEC_RE substring rule routing d1 docs work to frontier. Commit
  f1f162c is the fix pass: the gate can now go RED, fails closed on a missing classifier, and is
  reachable from a real runner (fleet/tests/tier-drift.test.sh + fleet/checks/rig-ci-scope.sh).
  Those four are FIXED — re-review verifies the fixes; do NOT re-derive them from scratch.

  DO NOT re-litigate: cost/blast consequence of the frontier promotions (F4) is a known, accepted
  consequence of the change, not a defect.
decisions: |
  OQ-2 / review F11 — ANSWERED 2026-07-24 by the OPERATOR: **REJECTED.** The two capability
  DOWNGRADES on review-class work are NOT accepted. Review-class work KEEPS its capability tier;
  tier_classify.py must not demote it. Whoever claims this ticket implements that — the rule's
  design-review branch must cover review-class work so FINAL-E2E-REVIEW and MODEL-PREFLIGHT stay
  frontier — and re-runs `board-retier` so the applied re-tiers match.

  RATIONALE (recorded so this is not re-litigated from scratch next session): adversarial reviews
  are currently THE load-bearing quality mechanism in this rig. On 2026-07-24 alone they caught
  three separate fake-greens, a repo-wide unbounded-recursion hazard (the gate<->pytest re-entrancy
  class), and a design fork — NONE of which any gate caught. Downgrading review capability to save
  money cuts the one mechanism that is demonstrably working. Cost is the wrong axis to optimize on
  the review path. [[adversarial-review-default-for-droid-prs]] [[gates-must-actually-run]]
  DO NOT re-open this question without a fresh operator call.
open_questions: |
  ONE review finding remains DELIBERATELY deferred to an OPERATOR CALL. It is NOT fixed, NOT
  dismissed, and must NOT be silently dropped by whoever claims this ticket. It does not block the
  land, but it must be answered and written back here before this ticket is marked done.
  (The second, OQ-2 / F11, was ANSWERED 2026-07-24 — see decisions: above.)

  OQ-1 (review F5 — MAJOR) — `nsurf >= 3` ALONE promotes to frontier.
    fleet/capability/tier_classify.py:53 and :73-74:
      if money and (d >= 4 or (livefwd and d >= 3) or nsurf >= 3): return "frontier"
    `nsurf` is just the count of non-.md owned paths, so a difficulty-2 ticket that touches three
    small files is priced at the top tier. Live example: FT-CATALOG-SEED (economy → frontier,
    work_class=greenfield-feature, d=2) owns exactly the repo's OWN normal decomposition shape
    (module + policy module + test) — the better-decomposed a money-path ticket is, the more
    expensive the rule makes it. Reviewer's suggested options: require `nsurf>=3 AND d>=3`, or
    count distinct top-level PACKAGES rather than files.
    OPERATOR DECISION REQUIRED: keep as-is / add the d>=3 conjunct / count packages.
    STATUS 2026-07-24 — STILL OPEN, PENDING RESEARCH. The operator approved the INTERIM rule
    (`nsurf>=3` AND a difficulty floor, i.e. breadth alone no longer promotes) **only pending review
    of alternatives**. A research pass is running now on EXISTING formulas / algorithms / tools for
    difficulty estimation and cheapest-capable routing — RouteLLM, FrugalGPT, model cascades, and
    code-complexity metrics — before this rule is fixed in place
    [[adopt-substrate-build-only-novel-slice]] [[research-posture-solution-seeking]].
    CONSEQUENCE: TIER-BALANCE CANNOT be marked done until that research lands and F5 is answered
    here. The interim rule may be implemented and landed; the QUESTION stays open.

  OQ-2 (review F11 — MODERATE) — two capability DOWNGRADES on review-class work.
      FINAL-E2E-REVIEW  frontier → strong  (work_class=ci-infra, d=3)
      MODEL-PREFLIGHT   frontier → strong  (work_class=ci-infra, d=4)
    Both were hand-set to frontier by an author and own a single fleet/state/*.md. The rule demotes
    them only because work_class: ci-infra is not in the design-review branch. FINAL-E2E-REVIEW is
    the end-to-end PRODUCT review — running it on a cheaper model is the direction that produces a
    worse review while still looking green.
    OPERATOR DECISION REQUIRED: accept the demotion / pin these two back to frontier / add
    review-class work_classes to the design-review branch of the rule.
accept: |
  - Re-review of the f1f162c fix pass (reviewer != builder), specifically re-verifying by EXECUTION
    that: the drift gate can go RED on a seeded mismatch; it fails CLOSED when
    fleet/capability/tier_classify.py is absent/renamed; and fleet/tests/tier-drift.test.sh is
    actually reached by a runner (fleet/checks/rig-ci-scope.sh CI_SUITES).
  - BOTH deferred review findings resolved and written back into this ticket:
      * OQ-2 / F11 — ANSWERED 2026-07-24 (REJECTED; see decisions:). IMPLEMENT it: review-class work
        keeps its capability tier in fleet/capability/tier_classify.py, FINAL-E2E-REVIEW and
        MODEL-PREFLIGHT stay frontier, and `board-retier` is re-run so the applied tiers agree.
        A land that still demotes review-class work does NOT satisfy this.
      * OQ-1 / F5 — STILL OPEN, pending the difficulty-estimation / cheapest-capable-routing
        research pass. The interim rule (`nsurf>=3` AND a difficulty floor) may be implemented, but
        THIS TICKET IS NOT DONE until F5 is answered and the answer is recorded here.
    A land with F5 still unanswered is NOT done.
  - bash fleet/validate_board.sh GREEN with the 2f block active (modulo pre-existing board state).
  - Rebased onto landed REPO-FIELD-REQUIRED before land (shared fleet/validate_board.sh).
ds: |
  ## Dependencies & sequence
  depends_on REPO-FIELD-REQUIRED (SUBMITTED) — real edit-collision on fleet/validate_board.sh;
  that branch lands first, this one rebases on top. THIS ticket is then the predecessor for two
  live tickets that share its files, both of which now carry `depends_on: TIER-BALANCE`:
    - REPO-MAP-CONVERGE          (shares fleet/validate_board.sh)
    - HANDOFF-GATE-NONBYPASSABLE (shares fleet/checks/rig-ci-scope.sh)
  MARKER-PROOF-MECHANIZE shares .gitignore and is transitively sequenced after this ticket via
  REPO-MAP-CONVERGE — no direct edge needed.
  Concurrency safety: the branch is already built and checked out in
  /home/stack/charon-private-wt/TIER-BALANCE — claim this ticket from THAT worktree; git will
  refuse to check feat/tier-classifier out anywhere else (one checkout, one agent).
