# WORKTREE-ADD-FORCE review note

## Decision
`add_worktree` now prunes stale `.git/worktrees` entries before every add, then
force-removes any leftover `dest` directory from a prior interrupted run. A
git-locked worktree resists the single `--force` remove, so the subsequent add
surfaces the real error rather than silently replacing it.

## Approach considered
- `git worktree add -f` alone: would skip prune, stale registration without a
  present dir still causes exit 128 on some git versions.
- prune-only: doesn't handle the case where the dir *and* registration both
  survived (partial interrupted run).
- prune + force-remove (chosen): covers both stale-registration and
  leftover-dir cases; "live locked" path still errors cleanly.

## Test coverage
6 tests in `tests/test_gitutil_worktree.py`: clean add, stale-registration
recovery, leftover-dir recovery, idempotent repeated calls, locked-worktree
raises, remove-worktree best-effort. All pass; full suite 615 passed.
