# DROID-LIFECYCLE-REAP — Review Log

## Ticket
DROID-LIFECYCLE-REAP: Reap dead-PID claims + orphaned worktrees; preserve committed work.
P0: worktree-create must not force-recreate a branch that already has unmerged commits.

## Symptoms (from manager observation 2026-07-16)
1. A frontier tab was Ctrl-C'd / terminal-closed. Claim record persisted. Worktree persisted.
2. With one hot ticket + many idle tabs, every re-claim fails the existing worktree path ->
   claim-release churn.
3. A SIGKILL-orphaned claim blocks the ticket forever (no in-process trap can release it).
4. **P0**: `git worktree add -B <branch> origin/master` (reflog "Created from origin/master")
   SILENTLY DISCARDS the existing branch's unmerged commits. Observed twice on
   FLEET-DEMAND-DRIVEN-ROUTING this session; recovered by SHA both times. No human
   error needed — a routine re-claim destroys unmerged work.

## Root causes
- `cleanup()` in fleet-droid.sh runs on the bash EXIT trap; SIGKILL / terminal close
  bypasses it entirely. The claim + worktree outlive the droid.
- `leak_worktree_setup()` does `git worktree add -B <branch> $base_ref` which ALWAYS
  creates the branch from base, silently overwriting any existing branch with the same
  name. There is no `if branch exists with unmerged commits: reuse it` path.
- There is no out-of-band mechanism to detect a dead-PID claim and recover it.

## Design

### 1. `leak_worktree_setup` (P0 #4 fix) — REUSE pre-existing branches with unique commits
The launcher is the ONE place that creates the worktree, so fixing it here fixes the
bug everywhere. New contract:

  if branch `refs/heads/<branch>` exists AND has commits not in `<base_ref>`:
    if the worktree dir already exists:       -> REUSE (cd into it; do nothing else)
    else (worktree dir gone, branch survives): `git worktree add <wt> <branch>`
  else:
    normal create path: `git worktree add <wt> -b <branch> <base_ref>`

Crucially: `git branch -D <branch>` is REMOVED. The pre-fix code dropped the branch
on every retry, which is exactly the data-loss path. If the branch exists with NO
unique commits, the launcher can still safely `git branch -D` to recreate from base
(unmerged branches are NOT deleted by this path).

A new helper `branch_unique_commits <repo> <branch> <base_ref>` returns the count of
commits in `<branch>` not reachable from `<base_ref>`. The launcher uses it to decide
reuse vs. recreate.

### 2. `cleanup()` in fleet-droid.sh — soft-land work, never drop a branch with commits
On stand-down (EXIT trap), if the droid is mid-claim (`$current` set) and the worktree
exists:
  - snapshot uncommitted changes
  - `git add -A && git commit` (with a flagging message) so NOTHING is lost in the
    worktree, OR stash them if the user requested no-commit (not implemented yet;
    the default is auto-commit because committed work is still on the branch and
    safe; uncommitted work would die with `git worktree remove --force`).
  - `git worktree remove` (NOT --force; if dirty, we already committed, so this
    should be clean. If `git worktree remove` still fails, fall back to `rm -rf`).
  - DO NOT `git branch -D`. The branch persists in the repo regardless; the worktree
    removal does NOT delete branches.
  - The claim is still released (so the ticket re-claimable by the next live droid).

A branch with `origin/master..HEAD` commits is NEVER deleted by cleanup.

### 3. `fleet/reap-orphans.sh` (new) — out-of-band dead-PID claim sweeper
Inputs: `state/claims/*` (one per active claim) + the board's `repo:` + `branch:` fields.
For each claim:
  1. Parse `<droid-id>` (format: `<tier>-<pid>`) and extract PID.
  2. `kill -0 <pid>`. If succeeds: skip (live droid).
  3. If dead:
     a. Resolve ticket's repo/worktree/branch via `repo-registry.sh`.
     b. Compute `unique=$(git -C <repo> log --oneline <base_ref>..<branch> | wc -l)`.
     c. If `unique > 0`: PRESERVE the work — flag `state/orphans/<id>` with a note
        that the branch has unmerged commits and call `submit.sh` (which verifies a
        real PR exists, or — if there isn't one — opens one via the same logic as
        land-needs-push.sh, then marks submitted). The orphaned worktree is then
        safely removed (the branch persists).
     d. If `unique == 0` (dead droid, no work): remove the orphaned worktree via
        `safe_worktree_remove` and release the claim. The branch is empty (== base),
        so `git branch -D` is safe AND `git worktree add -B` from base produces the
        same result, so there is no data loss either way.

The reaper is DRY-RUN by default (so the first run can be audited). `--apply` performs
deletions. Idempotent: a second run sees no dead-PID claims and exits 0 with 0 actions.

### 4. Wiring into foreman
- At foreman.sh start, after the tier-depth probe: invoke `reap-orphans.sh` (DRY-RUN) so
  the manager sees the orphaned-claim count in the regular foreman output.
- A new section "ORPHANED CLAIMS (dead PID)" prints the count + the offending
  `<droid> <ts>` for each dead claim.
- `foreman.sh --fix` also invokes the reaper with `--apply` (provably-safe: only touches
  dead-PID claims, never live ones; preserves branches with unique commits).

### 5. SessionStart + post-stand-down triggers
The droid's EXIT trap ALREADY calls `cleanup()`. The reaper covers the cases cleanup
cannot (SIGKILL, terminal close, OOM). A `SessionStart`-equivalent in the launcher
or harness setup is the right cadence hook. Wiring strategy: `foreman.sh` is already
on the regular session cadence (manager runs it on every board-feed); that cadence
becomes the reaper cadence. The reaper is INVOKED from foreman, not from each tab.

## Files
- `fleet/fleet-droid.sh` — harden cleanup(), do not pass through `git branch -D`
- `fleet/leak-guard.sh` — fix `leak_worktree_setup` to REUSE branches with unmerged commits
  (P0 #4)
- `fleet/reap-orphans.sh` — new out-of-band dead-PID claim sweeper
- `fleet/foreman.sh` — invoke reaper (DRY-RUN in report mode, --apply with --fix)
- `fleet/tests/test_droid_reap.sh` — fail-on-revert test for the new behavior

## Test plan
1. P0 #4 — pre-seed a ticket branch with a commit; run `leak_worktree_setup` again;
   assert the commit SURVIVES (NOT recreated from origin/master).
2. Dead-PID + branch with commit -> reaper releases claim, removes worktree, branch
   survives, ticket ends up submitted (or `state/orphans/<id>` flagged for manager
   land if no PR can be opened).
3. Dead-PID + branch with no commit -> reaper releases claim, removes worktree, no
   branch left behind.
4. Live-PID claim is left UNTOUCHED.
5. cleanup() on a dirty worktree -> uncommitted changes are auto-committed, then
   worktree removed; branch is preserved.
6. Idempotency: re-running the reaper finds nothing to do.
7. fail-on-revert: removing the dead-PID check, the unique-commits preservation, or
   the live-PID skip ALL flip a test to RED.

## Risk surface
- Reaper touches claim markers + worktrees + branches. Live droid interference is
  guarded by `kill -0` (the live droid can never accidentally lose its claim).
- The auto-submit path inside the reaper (case 3c) is the riskiest — it opens a PR
  for a dead droid's branch. That is INTENDED: the alternative is silent data loss
  in a `state/orphans/<id>` nobody ever visits. But it is loud (logs) and the PR
  stays DRAFT.
- P0 #4 fix is a behaviour change for `leak_worktree_setup`. The old behaviour is
  "always recreate" which was the bug; the new behaviour is "reuse if has unique
  commits". This is the data-safety fix.
