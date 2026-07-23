repo: charon-private
tier: strong
difficulty: 2
priority: 1
work_class: rig-meta
branch: fix/rfl3-dogfood-capture
owns: fleet/benchmark/dogfood-eval.sh, fleet/tests/dogfood-eval-capture.test.sh
depends_on:
source: scratchpad WORKTREE-TRIAGE-34.md finding #2 (D1 triage, 2026-07-23) — SILENT DATA LOSS in dogfood-eval capture
note: |
  dogfood-eval.sh captures a candidate's work via `git diff` (tracked changes only) and scores it as
  real-diff(files=N). For the RFL-3 eval, every candidate wrote a genuinely NEW UNTRACKED file
  (tests/test_image_routing.py) — created, never `git add`ed. Both the git-diff capture AND the scorer
  MISS untracked files entirely: the output exists ONLY in the live worktree, is invisible to capture/
  score, and a raw worktree reap DESTROYS it permanently. This silently under-credits candidates and
  loses real eval output. [[eval-system-under-repair]]
accept: |
  - dogfood-eval.sh capture includes UNTRACKED files the candidate created (e.g. `git add -A -n` /
    `git status --porcelain` covering `??` entries, or `git add -N` before diff), so new untracked
    files appear in both the captured artifact AND the real-diff file count/score.
  - No candidate output can exist only in the worktree and be missed by capture — verify with a
    candidate that ONLY creates a new untracked file (files=1 must be captured+scored, not 0).
  - fail-on-revert test (fleet/tests/dogfood-eval-capture.test.sh): a fixture candidate that writes a
    single new untracked file → capture records it and score = real-diff(files>=1). Revert the
    untracked-inclusion → test goes RED (file lost, score 0).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — silent-data-loss + eval-integrity;
    manager gates, PR does NOT merge on the builder's self-report. Fix root cause, not symptoms.
scope: |
  Capture/score correctness in dogfood-eval.sh only. INTERIM (separate, manual): before archiving the
  6 RFL-3 dogfood worktrees, copy out their tests/test_image_routing.py first (handled by the archive/
  reap disposition pass) — this ticket fixes the ROOT so future evals don't lose untracked output.
ds: |
  ## Dependencies & sequence
  Wave-1, no build prereq. Disjoint owns. Unblocks trustworthy archiving of untracked-output evals.
