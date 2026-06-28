# WORKTREE-ADD-FORCE — make add_worktree resilient to stale registrations

## Why (surfaced by the 2026-06-27 live certification)
A `charon work` re-run crashed at `_integrate` with `git worktree add --detach … exit 128` because
a stale-but-registered worktree path lingered in `.git/worktrees`. `charon/gitutil.add_worktree`
uses `git worktree add --detach` **without `-f` and without pruning**, so any stale registration
(common after an interrupted run) aborts the whole run instead of recovering.

## What to build
Make `gitutil.add_worktree` re-run-resilient: prune stale registrations and/or pass `-f` so a
lingering registration for the same path does not abort. Prefer `git worktree prune` (+ remove the
target dir if present) before the add, falling back to `-f`; keep behavior identical on the
clean-first-run path. Don't mask a genuine "path in use by a LIVE worktree" error — only recover
from STALE registrations.

## Acceptance
- Test: `add_worktree` succeeds when a stale registration exists for the target path (simulate a
  leftover `.git/worktrees/<name>` with a missing/old dir); still errors clearly if the path is held
  by a live worktree. Existing gitutil tests stay GREEN.

## CONSTRAINTS
Own ONLY: `src/charon/gitutil.py`, `tests/test_gitutil.py` (or a new `tests/test_gitutil_worktree.py`
if `test_gitutil.py` is absent — finalize at activation). Stdlib core; no secrets; gate GREEN every
commit. Conventional commits; review note → `docs/review-log/WORKTREE-ADD-FORCE.md`. Draft PR,
`submit.sh`, STOP. BACKLOG — tackle after the priority cluster if budget remains.
