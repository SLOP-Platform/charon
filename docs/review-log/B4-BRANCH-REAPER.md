# B4-BRANCH-REAPER review note

Shipped `fleet/branch-reaper.sh` — a NEW, self-contained hygiene reaper for the
~92-branch / stale-worktree accretion (gap-register B4 / QUICKWINS-LEVERAGE #7,
`[[investigate-and-backup-before-data-loss]]`).

## Design decisions

1. **DRY-RUN is the default** — `--apply` is the only destructive mode. The delete
   blast radius (branches + worktrees) mandates a print-first default so an operator
   can audit the candidate list before anything is removed. Idempotent in both modes.

2. **Two hard data-loss guards** (each is the FAIL-ON-REVERT axis in the self-test):
   - **MERGED-ONLY branch filter**: candidate branches come ONLY from
     `git branch --merged <base>`, minus base/current/protected. An unmerged branch
     is never a candidate and is never deleted. Deletion uses `git branch -D`; the
     `--merged` filter IS the guard. Reverting it to a bare `git branch` makes the
     self-test go RED on (c1) — the unmerged `live-unmerged` branch is wrongly deleted.
   - **LIVE-CLAIM worktree guard**: a fleet worktree dir is removed ONLY if NEITHER
     `state/claims/<id>` (active droid) NOR `state/needs-push/<id>`
     (committed-but-unlanded work) exists. Either marker protects it unconditionally.
     Mirrors `safe_worktree_remove` in `fleet/leak-guard.sh` (the #3 hazard).

3. **What it reaps, in order**:
   (0) `git worktree prune` — clean admin metadata for already-gone dirs.
   (1) stale fleet worktree dirs (glob `<repo-dir>/<repo-base>-fleet-*`) with no
       live claim marker for the ticket id derived from the dir name.
   (2) local branches merged into `<base>` (excluding base / current / protected).

4. **Env hooks for testability** (`REAPER_REPO`, `REAPER_BASE`, `REAPER_FLEET_DIR`,
   `REAPER_WT_GLOB`, `REAPER_PROTECTED`) so the self-test drives an isolated temp
   git repo fixture (never the live fleet or `/home/stack/code/charon`). Same pattern
   as the `RECONCILE_*` / `VERIFY_MERGED_*` hooks in `reconcile-merged.sh` / `_lib.sh`.

5. **Branch-name trimming**: `git branch` indents non-current branches with 2 spaces.
   The reaper strips ALL leading/trailing whitespace from each candidate line
   (`${branch#"${branch%%[![:space:]]*}"}`) so `case` matching against the protected
   list is exact — a bare `${line# }` (single-space strip) left a leading space and
   silently failed to match the protected set.

## GREEN-IS-NOT-PROOF coverage

Exit 0 alone does not prove correct reaping. The self-test asserts SURVIVAL of the
two things a too-broad reaper would destroy:
- (c1) the UNMERGED branch (`live-unmerged`) is still present after `--apply`.
- (d3) a CLAIMED worktree (live `state/claims/CL1`) is still present after `--apply`.
- (e2) a NEEDS-PUSH worktree (live `state/needs-push/NP1`) survives `--apply`.

And the positive side:
- (b2) a MERGED branch (`throwaway-merged`) IS deleted under `--apply`.
- (f3) a STALE worktree (no live claim) IS reaped under `--apply`.

## FAIL-ON-REVERT validation (run during development)

Reverting the `--merged` filter to a bare `git branch` was tested by sed-substituting
the command, running the self-test, and observing RED:
```
FAIL: c1 unmerged branch was DELETED under --apply (guard reverted — DATA LOSS)
```
then restoring. The `--merged` guard is what protects (c1).

## Overlap with F15

F15 owns a DIFFERENT part of worktree-cleanup per the gap-register; today F15 is not a
live board ticket owning `branch-reaper.sh`, so this ships with zero owns-collision.
If F15 later claims the same script, serialize (the DS note flags this).

## Scope

`owns:` is exactly `fleet/branch-reaper.sh`. The self-test
`fleet/tests/branch-reaper.test.sh` and this fragment
`docs/review-log/B4-BRANCH-REAPER.md` are the lone exceptions per the droid rules
(per-ticket review-log fragment + its self-test).
