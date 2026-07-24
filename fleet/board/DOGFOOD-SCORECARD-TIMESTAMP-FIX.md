repo: charon-private
tier: economy
difficulty: 1
priority: 1
work_class: rig-meta
branch: fix/dogfood-scorecard-timestamp-collision
owns: fleet/benchmark/dogfood-to-scorecard.sh, fleet/tests/dogfood-to-scorecard.test.sh
depends_on:
source: scratchpad WORKTREE-DISPOSITION-DONE.md (disposition sub, 2026-07-23) — same-second run collision
note: |
  dogfood-to-scorecard.sh names its generated output file by a second-resolution timestamp
  (scorecard-append-pathc-<ts>.sh). Two runs within the SAME second produce the SAME filename, and the
  second run SILENTLY CLOBBERS the first run's output — losing a batch's scorecard rows with no error.
  Observed live during the archive of 6 dogfood batches this session.
accept: |
  - Output filenames are collision-proof within a second (add a monotonic suffix / PID / content hash,
    or refuse-and-error rather than overwrite an existing target). Two runs in the same second BOTH
    persist; neither is silently lost.
  - fail-on-revert test (fleet/tests/dogfood-to-scorecard.test.sh): two invocations forced to the same
    timestamp both produce distinct non-empty outputs. Revert the collision-guard => the test detects the
    clobber (one output lost) => RED.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
scope: |
  Output-naming collision fix in dogfood-to-scorecard.sh only. Sibling to RFL-3-CAPTURE-FIX (the other
  dogfood-tool data-loss flag): capture misses untracked files; this one clobbers same-second outputs.
ds: |
  ## Dependencies & sequence
  Small, no build prereq. Disjoint owns from RFL-3-CAPTURE-FIX (different file). Parallelizable.
