repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 1
branch: fix/grade-provenance-divergence
depends_on: SW-PHASE0-GRADE-READ
real-dep: SW-PHASE0-GRADE-READ — build prereq and shared single-owner of fleet/capability/grades.py.
  This ticket refines the very predicate that one introduces; co-writing would clobber it.
dep-kind: build
owns: fleet/capability/grades.py, fleet/capability/tests/test_grade_provenance.py
serial_justified: |
  ONE predicate and the flag it must propagate. Setting a flag nothing reads is the defect being fixed.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample. Own worktree.
  Acquire the work-lease FROM INSIDE the worktree — it binds to the acquiring worktree.
source: |
  Adversarial review of SW-PHASE0-GRADE-READ by session ganner-rhysode, 2026-07-26:
  fleet/handoff-notes/ADVREVIEW-SW-PHASE0-GRADE-READ.md (verdict MERGE, 0 BLOCKING).
note: |
  ## THE DIVERGENCE
  SW-PHASE0-GRADE-READ correctly unblocked the read path — `assign.py` went from REFUSING every
  ticket to grading (`minimax-m3-free` at n=21 / score=69.07 instead of `None`). That fix stands.
  BUT: `fallback_admit` is SET in the panel and then **never consumed** by `_rows_for()` or `Grade`.
  The PRODUCT copy flags fallback-admitted rows as **provisional**; the RIG copy cannot distinguish
  them from controlled grades.
  **All 64 live scorecard rows are currently uncontrolled — and look identical to controlled admits.**

  ## WHY THIS IS MORE THAN COSMETIC
  Promote/demote (`model-detention.sh`, `assign.py`) will treat a grade derived from ZERO controls
  exactly like a rigorously-controlled one. The entire point of the grading plane is that routing
  decisions rest on evidence; a grade that cannot state the strength of its own evidence is the same
  silent-failure class as the inert meter and the dead read — it looks healthy and is not
  distinguishable. A flag that is set and never read is indistinguishable from no flag at all.
  It is NOT release-blocking: grades-with-unknown-provenance beat no grades. Sequence, do not rush.

  ## SCOPE
  Propagate `fallback_admit` through `_rows_for()` into `Grade` so a consumer can tell controlled from
  fallback-admitted, and MIRROR the product's provisional semantics rather than inventing new ones.
  Read `/home/stack/code/charon/src/charon/capability/grades.py` first — if the rig genuinely needs
  DIFFERENT semantics from the product, STOP and report: a second divergence is worse than this one.
accept: |
  DONE-CONTRACT:
  - A consumer can distinguish a controlled grade from a fallback-admitted one. Show it on real data:
    all 64 current rows must report as fallback-admitted/provisional, not as controlled.
  - The rig's semantics MATCH the product's. State how you verified the match.
  - RED-PROOF BY EXECUTION: strip the propagation -> the test goes RED naming the indistinguishable
    case. Report BOTH exit codes.
  - NON-VACUOUS: a test over zero rows is RED, never a silent pass.
  - `assign.py` still returns candidates (no regression of the Phase-0 unblock) — paste the output.
  - No change to `fleet/model-scorecard.tsv` (bench-grader-owned, anti-gaming).
  - `bash fleet/validate_board.sh` GREEN, run from the MAIN checkout.
## Dependencies & sequence
- **Depends on: SW-PHASE0-GRADE-READ** (build prereq, same file). Land that first.
- **Blocks:** trustworthy promote/demote. Until this lands, treat every grade as provenance-unknown.
- **Wave:** phase 0 follow-up, P1.
