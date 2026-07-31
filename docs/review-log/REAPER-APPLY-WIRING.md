# REAPER-APPLY-WIRING review note

OPEN-PR GUARD added to `fleet/branch-reaper.sh` -- the worktree-reap guard
now consults GitHub PR state via `gh` so a branch with an open PR is NEVER
reaped even when clean + fully pushed + unclaimed.

## What changed

**`fleet/branch-reaper.sh`** (OPEN-PR guard in `_rp_keep_reason`):
- After `_lg_wt_target_ok` passes (no dirty files, no unpushed commits), before
  the LOW-2 remote-freshness check, the new guard reads the worktree's current
  branch (`git rev-parse --abbrev-ref HEAD`) and queries `gh pr list --state open
  --head <branch>`.
- If the query returns >0 open PRs, the worktree is KEPT.
- Fail-closed: if `gh` is unavailable or the query errors, the tree is treated as
  "has open PR" (KEEP).
- Configurable via `REAPER_GH_CMD` env var (default: `gh`).

**`fleet/tests/branch-reaper.test.sh`** (test v, fail-on-revert):
- Fixture: clean + fully pushed + unclaimed worktree on a branch.
- Mock `gh` reports 1 open PR for the branch.
- `--apply` run asserts the worktree is KEPT with reason mentioning open PR.
- Reverting the open-PR guard makes this RED (worktree wrongly reaped).

## Root cause

The existing guard checked push-reachability (`rev-list --count HEAD --not
--remotes`) but not open-PR state. A branch with an open PR that is fully pushed
reads as "clean + pushed + unclaimed" and was listed for REAP -- would destroy a
worktree with live PR `feat/work-lease-gate` (#204).

## Gate results

- 119/119 branch-reaper tests pass (all existing + new test v)
- `validate_board.sh` GREEN
- Shell syntax OK, no new shellcheck issues
- Only owned files changed: `fleet/branch-reaper.sh`, `fleet/tests/branch-reaper.test.sh`
