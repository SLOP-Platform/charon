tier: strong
difficulty: 2
work_class: ci-infra
branch: fix/land-sh-safe-sync
repo: charon-private
depends_on:
owns: fleet/land.sh, fleet/tests/test_land_safe_sync.sh
accept: |
  DATA-LOSS FIX (HIGH). land.sh's step-7 "sync local base to origin" HARD-RESET the main checkout and
  DESTROYED uncommitted working-tree changes (a whole session's board bookkeeping wiped, 2026-07-13). It must
  NEVER destroy uncommitted work.
  DO: before the sync, detect a DIRTY working tree (`git status --porcelain` non-empty in the target repo).
  If dirty: REFUSE to hard-reset — either (a) auto-`git stash` (with a clear stash label) then FF then
  `stash pop`, or (b) skip the sync and print a loud warning with the exact manual command. NEVER `reset --hard`
  / `clean -fd` over uncommitted or untracked files. Fast-forward only; abort loudly on divergence.
  FAIL-ON-REVERT (fleet/tests/test_land_safe_sync.sh): stage a dirty fixture repo (uncommitted tracked edit +
  an untracked file), run the sync path, assert BOTH survive. Revert the guard -> the dirty edit/untracked file
  is gone -> RED.
  ALSO note (2nd land.sh defect, separate follow-up ok): its gate is weaker than CI (missed arch-lint on F29) —
  fold "land.sh product gate == full CI" here or a sibling ticket.
scope: Rig safety fix — the sanctioned merge tool must honor back-up-before-data-loss. [[investigate-and-backup-before-data-loss]] [[mechanized-handoff-gate]]
ds: |
  depends_on: none. concurrency: sole owner of land.sh. HIGH — land.sh is used every merge; the bug recurs.
note: HIGH — filed after land.sh wiped session board state 2026-07-13 (2nd land.sh problem). Manager or a strong droid; adversarial review (money/rig-path).
