repo: charon-private
tier: strong
difficulty: 2
work_class: design-review
priority: 1
branch: review/workloop-attempt3
depends_on:
owns: fleet/state/REVIEW-WORKLOOP-ATTEMPT3.md
work_class_note: |
  INDEPENDENT adversarial review of WORKLOOP attempt-3 (PR #179, branch feat/workloop-stack-spike-run).
  You are NOT the author. Attempt-2 was BOUNCED for ranking hand-roll #1 (ao §1.3, Archon §4.3). Attempt-3
  claims to fix ONLY that by executing the demoted adopts (adnanh/webhook + pydantic/cerberus) on 4-LOM and
  re-ranking adopt-first. Verify that claim is REAL, not prose. [[document-model-self-report-lies]]
  [[no-rig-as-product-adopt-dont-handroll]] [[gates-must-actually-run]]
accept: |
  DELIVERABLE = fleet/state/REVIEW-WORKLOOP-ATTEMPT3.md — a NARROW adversarial verdict on PR #179.
  Read: `gh pr diff 179 --repo Nnyan/charon-private`. The scope is NARROW — attempt-2's four trials
  (ao/Omnigent/Windmill/Archon) were already verified real; do NOT re-litigate them. Check ONLY the
  three bounce-fix items, ground-truthing on 4-LOM (ssh -i ~/.ssh/4lom stack@10.0.1.60):
    1. **adnanh/webhook trial REAL?** The doc claims webhook 2.8.3 built on 4-LOM (~12.9MB) + a wired
       CI-fail→re-trigger hook, transcript in §1.4. Ground-truth: do the artifacts exist on 4-LOM
       (/tmp/wltrial/{transcript,hooks*.json,ci-gate.sh,receiver/server.py})? Does the transcript show a
       real run (host + commands + observed output), not a source citation? Is the ao §1.3 seam now ranked
       adnanh/webhook (or Windmill) #1 with the hand-roll ONLY as after-adopt-disproven fallback?
    2. **pydantic/cerberus trial REAL?** Doc claims pydantic 2.13.4 (§4.4, 5 fixtures, tri-state matrix) +
       cerberus 1.3.8, validating a DoD spec AND rejecting a malformed one. Ground-truth the artifacts
       (/tmp/wltrial/pydtrial/{dod_schema.py,fx_*.yaml}). Is Archon §4.3 now pydantic #1 (EXECUTED), hand-
       roll only after-disproven?
    3. **EVAL-REGISTRY provenance**: are the ao-seam and Archon-seam adopt rows in SEPARATE commits
       (claimed 89320e6, d89a0ef)? Confirm via `git log --oneline` on the branch.
  If any trial artifact is ABSENT on 4-LOM, or a hand-roll is still ranked #1 anywhere, or the rows are
  not in separate commits → BOUNCE with the specific gap. Otherwise APPROVE-FOR-OPERATOR. Silence is never
  a pass. Review only — do not modify the deliverable.
scope: |
  Narrow independent review of WORKLOOP attempt-3 (PR #179): ground-truth the two new adopt trials
  (adnanh/webhook, pydantic/cerberus) on 4-LOM + confirm the adopt-first re-ranking and separate-commit
  provenance actually fix the attempt-2 bounce. Verdict for operator, before merge.
ds: |
  ## Dependencies & sequence
  - depends_on: (none for launch) — reviews PR #179 which exists. Owns its own verdict doc; no collision
    with the spike deliverable.
  - reviewer independence: did NOT author #179. Ground-truth on 4-LOM, do not trust the doc's prose.
