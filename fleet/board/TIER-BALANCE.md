repo: charon-private
tier: strong
difficulty: 3
priority: 3
work_class: rig-meta
branch: feat/tier-classifier
commit: f1f162c
worktree: /home/stack/charon-private-wt/TIER-BALANCE
owns: fleet/capability/tier_classify.py, fleet/capability/effort.py, fleet/capability/tests/test_tier_classify.py, fleet/tests/tier-drift.test.sh, fleet/state/tier-drift-red.txt, fleet/validate_board.sh, fleet/checks/rig-ci-scope.sh, .gitignore
commit-note: fleet/capability/effort.py added to owns: 2026-07-24 — a NEW file created by c8c1f13
  (the decompose_effort adoption) that was missing from the declared surface. An owned-but-undeclared
  file is invisible to the collision check, which is how two writers meet on it [[harmless-cruft-bites]].
design-rationale: |
  ### RECORDED 2026-07-24 so a future session does not "simplify" these into defects.

  (R1) THE EFFORT SCORER IS PORTED, NOT IMPORTED — AND THAT IS DELIBERATE.
  `fleet/tests/tier-drift.test.sh` runs in the RIG's GitHub CI on a charon-private-ONLY checkout,
  where `/home/stack/code/charon` DOES NOT EXIST. Importing the product module there would make a
  MERGE-BLOCKING preflight unrunnable — the gate would fail for absence-of-repo, not for drift. The
  obvious "fix", an import-with-fallback, is WORSE: it would derive DIFFERENT TIERS ON DIFFERENT
  HOSTS (product tree present -> imported scorer; absent -> fallback), i.e. a gate whose verdict
  depends on which box ran it. That is a silent-divergence defect, not a convenience.
  HOW DRIFT IS PINNED INSTEAD: assert the 5 constants LITERALLY, plus a cross-repo diff WHEN the
  product tree resolves. The literal assertions run everywhere; the diff adds real coupling wherever
  it can. DO NOT replace this with an import [[fix-root-cause-never-workaround]].

  (R2) THE PROMOTION BAND IS THE PRODUCT'S **HARD 16.0**, NOT THE ADVISORY **SOFT 10.0**.
  SOFT would promote 65 of 104 tickets — reproducing the very over-promotion this ticket exists to
  end, just with a new proxy in place of the old breadth heuristic. A threshold that promotes ~63% of
  the board is not a threshold.

  (R3) F5'S FLOOR IS STRUCTURAL: `EFFORT_DIFFICULTY_FLOOR=3`. Breadth ALONE can therefore NEVER
  promote a ticket — which is exactly the F5 defect that `FT-CATALOG-SEED` exhibited (difficulty 2,
  effort 7.45, promoted on breadth only). The floor is the fix; do not soften it to make a specific
  ticket pass.
serial_justified: ALREADY BUILT as one commit (feat/tier-classifier @ f1f162c) — the classifier, its drift gate in validate_board.sh, its runner registration in rig-ci-scope.sh and its red-list are ONE contract: splitting them ships a gate with no classifier (or a classifier no runner executes), which is the exact non-enforcement the first review rejected. Remaining work is re-review + land, not a build that could fan out.
promotions-applied: |
  ### 2026-07-24 — OPERATOR-APPROVED: 7 of the 9 outstanding drift REDs APPLIED to the LIVE board.
  Re-derived FIRST with `tier_classify.py deltas --board <live>` from the branch's own HEAD (c8c1f13,
  the effort-scorer adoption) — NOT taken from the quoted list below, which was written against
  f1f162c. The re-derivation returned the SAME 9 hard-fail ids, 35 deltas over 120 declared tiers.
  Each applied line flips `tier:` ONLY, byte-identical to the branch's own edit, so the merge
  resolves without conflict.
    BOUNCE-1                  strong -> frontier  security surface: real-SUT egress/header exfil canary; SEC_RE ratchet, capability never traded down
    FIX-PROVIDER-KEY-EXFIL    strong -> frontier  security surface: provider-key exfil path; SEC_RE ratchet, capability never traded down
    FT-WIRE-QUOTA             strong -> frontier  money-path: live-forwarding quota wiring, d4, measured effort 12.6
    GATEWAY-GRADE-ORDER-MVP   strong -> frontier  money-path: routing/grade-order, d5, measured effort 13.6
    GW-CUTOVER-LIVE-WIRE      strong -> frontier  money-path: live cutover wiring, livefwd=1 d5, measured effort 13.6
    ORDER-A-COST-PRIMARY-LAND strong -> frontier  money-path: cost-primary ordering, livefwd=1 d3, measured effort 10.75
    WIRE-GRADING-PRIOR-LIVE   strong -> frontier  money-path: live grading prior, livefwd=1 d3, measured effort 10.3
  APPROVAL EXTENDED same day to the remaining two (money floor, not frontier) — also APPLIED:
    FT-LIMITS-GROQ-RECONCILE  economy -> strong   money floor: quota/limits reconcile, d2, measured effort 7.3
    ROUTER-LEDGER-DECAY       economy -> strong   money floor: router spend-ledger decay, d3, measured effort 10.3
  Both were independently re-derived from the same `deltas` run, not from the quoted list. Applying
  them was also FORCED-CHOICE rather than optional: the branch's OWN board files already set both to
  `strong`, so landing applies them regardless — the only alternatives were approve or hold the land.
  ALL 9 outstanding drift REDs are now dispositioned; `tier_classify.py drift` against the live
  board exits 0 with ZERO REDs, so gate 2f survives this branch landing.
land-blocked: |
  ### 2026-07-24 — LAND ATTEMPTED AND REFUSED, rc=4 GATE RED. The blocker is NOT the tier decisions.
  `bash fleet/land.sh feat/tier-classifier /home/stack/charon-private-wt/TIER-BALANCE` -> rc=4:
      RED tier-drift: FT-CATALOG-SEED  declared=frontier derived=strong   (money floor d2 effort7.45)
      RED tier-drift: PRICE-REFRESHER  declared=strong   derived=frontier (money+ livefwd=0 d3 effort40.3)
  MECHANISM — worth knowing before anyone repeats this: `fleet/land.sh:298-299` builds its gate as
  `bash $REPO/fleet/validate_board.sh $REPO/fleet` where $REPO is the WORKTREE. The gate therefore
  grades the BRANCH'S OWN COPY of fleet/board/, not the live board on master. Proving drift clean
  against the live board (which this pass did, rc=0 / zero REDs) does NOT predict the land gate.
  ROOT CAUSE: feat/tier-classifier is **41 commits behind master** with ~85 fleet/board/*.md files
  diverged. FT-CATALOG-SEED and PRICE-REFRESHER are exactly the two the ticket records as "fixed on
  master that day" — the branch still carries their pre-fix tiers, so its stale board self-fails 2f.
  BLOCKING PRECONDITION IS NOW SATISFIABLE: depends_on REPO-FIELD-REQUIRED HAS landed — master's
  fleet/validate_board.sh:100 carries its `repo:` check. The accept: clause "Rebased onto landed
  REPO-FIELD-REQUIRED before land" can now actually be done, and is the remaining work.
  NEXT STEP (deliberately NOT done here — 41 commits x ~85 diverged board files is a reconcile, not
  a board write, and near-certain to conflict on the 36 tier: lines this branch owns):
    1. rebase/merge feat/tier-classifier onto master in /home/stack/charon-private-wt/TIER-BALANCE
    2. re-run `tier_classify.py board-retier` so applied tiers match the post-rebase board
       (owns_data: records this as the sanctioned re-apply path)
    3. re-run land.sh — the 9 promotions above are already on master, so 2f should then be clean
  Also note the MAIN checkout was dirty during this attempt (another lane's board-archive WIP:
  4 deleted fleet/board/*.md + 4 untracked fleet/board/archive/*.md). That did not cause this rc=4,
  but it is the documented cause of land.sh rc=8 and should be settled before the retry.
outstanding-reds: |
  ### 9 HARD-FAIL DRIFTS REMAIN ON THE LIVE BOARD — UNRESOLVED, AND THIS TICKET CANNOT LAND OVER THEM.
  Ran `tier_classify.py drift` (from c8c1f13) against the LIVE board 2026-07-24. FOUR were fixed on
  master that day — FT-CATALOG-SEED (economy->strong), PRICE-REFRESHER (strong->frontier), and the
  two F11 work_class corrections (FINAL-E2E-REVIEW, MODEL-PREFLIGHT -> design-review). NINE remain
  RED, and `drift` exits 3 while any do:
      BOUNCE-1                  strong  -> frontier  security-critical path (ratchet)
      FIX-PROVIDER-KEY-EXFIL    strong  -> frontier  security-critical path (ratchet)
      FT-LIMITS-GROQ-RECONCILE  economy -> strong    money floor (d2 effort 7.3)
      FT-WIRE-QUOTA             strong  -> frontier  money+ (livefwd=1 d4 effort 12.6)
      GATEWAY-GRADE-ORDER-MVP   strong  -> frontier  money+ (livefwd=0 d5 effort 13.6)
      GW-CUTOVER-LIVE-WIRE      strong  -> frontier  money+ (livefwd=1 d5 effort 13.6)
      ORDER-A-COST-PRIMARY-LAND strong  -> frontier  money+ (livefwd=1 d3 effort 10.75)
      ROUTER-LEDGER-DECAY       economy -> strong    money floor (d3 effort 10.3)
      WIRE-GRADING-PRIOR-LIVE   strong  -> frontier  money+ (livefwd=1 d3 effort 10.3)
  DELIBERATELY NOT APPLIED HERE. Every one is a PROMOTION, seven of them to frontier — the most
  expensive tier — on money-path and security-critical tickets. That is a real recurring SPEND
  decision, not board hygiene, and it belongs to the operator [[no-workhorse-finalized]]
  [[adversarial-review-must-not-silently-override-operator]]. Applying nine tier promotions to make a
  gate green would be the gate driving the spend rather than the reverse.
  SEQUENCING CONSEQUENCE — read this before landing: gate 2f is NOT on master today (master's
  validate_board.sh has no tier check at all, and validate_board is GREEN, rc=0). It arrives WITH this
  branch. So these nine block NOTHING right now, and nothing is currently blocked on them — but the
  moment this branch lands, `validate_board.sh` (which land.sh runs as the rig's merge gate) goes RED
  and rig landing stops for everyone. DISPOSITION THE NINE FIRST — re-tier, or add a recorded
  exemption — and only then land.
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
