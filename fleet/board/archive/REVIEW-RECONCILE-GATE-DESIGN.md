repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 0
branch: review/reconcile-gate-design
depends_on:
owns: fleet/state/REVIEW-RECONCILE-GATE-DESIGN.md
work_class_note: |
  INDEPENDENT adversarial review of the RANK-0 LEAD design (PR #178, branch design/unified-reconciliation-
  gate, deliverable fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md). Two-owner firewall: you are NOT the
  author — ground-truth every claim against the ACTUAL repo, do NOT trust the doc's prose.
  [[document-model-self-report-lies]] [[gates-must-actually-run]] [[no-rig-as-product-adopt-dont-handroll]]
accept: |
  DELIVERABLE = fleet/state/REVIEW-RECONCILE-GATE-DESIGN.md — an adversarial verdict on PR #178's design.
  Read the design at: `git show origin/design/unified-reconciliation-gate:fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md`
  (or `gh pr diff 178 --repo Nnyan/charon-private`). GROUND-TRUTH each of these against the live repo — cite
  file:line evidence, do NOT accept the doc's assertions at face value:
    1. **Are the 3 v1 reconcilers actually buildable as designed?** For board↔PR↔done: does the proposed
       disambiguation (branch-name↔ticket, PR-title/id, merged-sha) actually resolve the LIVE AMBIGUOUS case
       where a merged branch's file is owned by N tickets? Reproduce one AMBIGUOUS case (see `reconcile-merged`
       output from `fleet/preflight.sh` or the reds) and check the design's logic would deterministically
       close it. For owns-tracked: confirm `fleet/state/*` really is blanket-gitignored (the root it claims).
       For gate-wired: does a real firing layer exist to check against (preflight/CI/hooks)?
    2. **Fail-closed taxonomy**: verify the design's taxonomy actually fails CLOSED (unknown path ⇒ needs-
       review), not open — the BLAST-TIER F2 blocker it claims to fix. Find any residual fail-open path.
    3. **Adopt-first honesty**: the design sanctions a hand-rolled reconciliation LOGIC as "implement-as-
       pattern (validated by WORKLOOP spike)". Is that justification REAL (no external tool reconciles
       Charon's own state) or is it AP-5/AP-7 drift? Name any adopt candidate it skipped.
    4. **Deferred/parked correctness**: is parking the grading consumer (grades.py 0 real-outcome grades)
       and deferring R44 e2e-observable-effects to v2 sound, or does v1 secretly depend on them?
    5. **Enforcement gaps**: the git -C land.sh bypass is FLAGGED not closed — confirm it's flagged (not
       fake-closed) and that the rig preflight+timer enforcement is actually wireable today.
    6. **Blast radius / completeness**: does the design's BUILD BACKLOG decompose cleanly into one-lens
       tickets? Any missing reconciler class the operator escalated? Any internal contradiction?
  VERDICT per item: CONFIRMED-SOUND / NEEDS-REVISION (with the specific fix) / BLOCKER. End with an overall
  APPROVE-FOR-OPERATOR / BOUNCE recommendation. Silence is NEVER a pass — if you cannot ground-truth a
  claim, say so and mark it unverified. Do NOT modify the design or any code — review only.
scope: |
  Independent adversarial review of the unified-reconciliation-gate LEAD design (PR #178) — ground-truth the
  3 reconcilers' buildability, fail-closed taxonomy, adopt-first honesty, parked/deferred correctness, and
  enforcement wireability against the live repo. Verdict doc for operator, before merge.
ds: |
  ## Dependencies & sequence
  - depends_on: (none for launch) — but REVIEWS the design/unified-reconciliation-gate deliverable; run
    AFTER that PR (#178) exists (it does). Owns its own verdict doc — no owns-collision with the design.
  - reviewer independence: you did NOT author PR #178. Ground-truth, do not trust prose.
