tier: economy
difficulty: 2
work_class: rig-meta
branch: chore/b4-branch-worktree-reaper
depends_on:
owns: /home/stack/charon-private/fleet/branch-reaper.sh
accept: |
  ~92 branches (~20 merged-but-undeleted) + stale git worktrees accrete forever. Ship a NEW self-contained
  `fleet/branch-reaper.sh` that: (1) deletes local branches already merged into master (`git branch --merged master`
  minus master/current/protected), and (2) runs `git worktree prune` + removes leaked/stale fleet worktrees
  (`/home/stack/code/charon-fleet-*` with no live claim). Idempotent; DRY-RUN by default with an explicit `--apply`
  to actually delete; print exactly what it would reap. NEVER delete an unmerged branch or a worktree with a live
  state/claims/* marker — hard guard both.
  FAIL-ON-REVERT: create a merged throwaway branch + an unmerged one → `branch-reaper.sh --apply` → merged one gone,
  unmerged one KEPT; revert the `--merged` guard → the unmerged branch is wrongly deleted (test RED). Add a rig
  self-test under fleet/tests/ (operate on a temp git repo fixture) asserting both, and that a worktree with a live
  claim marker is never reaped.
  GREEN-IS-NOT-PROOF: exit 0 does NOT prove correct reaping — the self-test MUST assert the unmerged branch and the
  claimed worktree SURVIVE (guards against an over-broad reaper that eats live work — the exact data-loss risk here).
scope: |
  GAP-REGISTER B4 (overlaps F15 worktree-cleanup — coordinate, do not duplicate F15's part). Hygiene debt stops
  growing. Source: QUICKWINS-LEVERAGE.md #7. [[investigate-and-backup-before-data-loss]] — default DRY-RUN is
  mandatory given the delete blast radius. Owns a NEW script → disjoint from B3.
ds: FLEET Wave G / FOUNDATION hygiene. depends_on EMPTY — launch NOW. Owns ONE new script → zero owns-collision; runs
  fully concurrently with B3 and the rest of the wave. (F15 owns a DIFFERENT part of worktree-cleanup; if F15 becomes
  a live board ticket owning branch-reaper.sh, serialize — today it does not.)
