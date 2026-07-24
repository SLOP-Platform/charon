# WORK-LEASE-GATE — Review Log

## Ticket
Universal work-lease gate: every session (manager subagent or CG tab) must hold an
atomic lease bound to an isolated worktree to touch a ticket; the main checkout is
land/gate-only. Enforced at commit time via pre-commit + commit-msg hooks.
Reuses claim.sh's flock claim + stale-check.sh's liveness.

## What was done
- **fleet/work-lease.sh** (new, the gate script):
  - `acquire <ticket-id> [session-id]` — atomically acquires a lease for a ticket
    bound to the current worktree. Uses claim.sh's shared `state/lock` (flock).
    Writes lease metadata (ticket, session, worktree path, heartbeat, claimed-at)
    to `state/leases/<ticket-id>`. Exits 1 on CONFLICT if another session holds
    the lease.
  - `check <ticket-id>` — verifies a valid lease exists: (1) lease file present,
    (2) heartbeat not stale (default 900s threshold), (3) worktree binding
    matches cwd. Exits 1 with reason (NO-LEASE / STALE / MISMATCH) on failure.
  - `release <ticket-id>` — removes the lease marker under flock.
  - `heartbeat <ticket-id>` — refreshes the heartbeat timestamp in the lease
    marker (extending liveness).
  - `pre-commit` — write-boundary check entry point for the pre-commit hook:
    - In a worktree: derives ticket id from branch name, checks lease via
      `cmd_check`. Refuses (exit 1) with instructions on no valid lease.
    - In main checkout: no-op (deferred to commit-msg).
    - Respects `WORK_LEASE_BYPASS=1` to skip all checks (for maintenance,
      land.sh callers, or explicit operator opt-out).
  - `commit-msg <msg-file>` — write-boundary check entry point for the
    commit-msg hook:
    - In main checkout: reads the first line of the commit message; allows
      `land:*` prefix or `*board-hygiene*` substring. Refuses all other
      main-checkout commits with a loud message directing work to a leased
      worktree.
    - In a worktree: no-op (lease already checked by pre-commit).
  - `install` — creates symlinks from `$repo/.git/hooks/{pre-commit,commit-msg}`
    to `fleet/hooks/{pre-commit,commit-msg}` for the rig repo and the product
    repo (when it exists).
  - `uninstall` — removes the symlinks installed by `install`.

- **fleet/hooks/pre-commit** (new, thin wrapper): calls `work-lease.sh pre-commit`.

- **fleet/hooks/commit-msg** (new, thin wrapper): calls `work-lease.sh commit-msg "$@"`.

## Key decisions
- **Two hooks, not one**: pre-commit checks the lease for worktree commits
  (before the message is written); commit-msg checks the sanctioned-message
  pattern for main-checkout commits (message is available). A single hook
  cannot enforce both because the message content is unavailable in pre-commit.
- **Reuses claim.sh's flock, not a second lock**: the lease file is written
  under the same `state/lock` that claim.sh uses, so a claim and a lease cannot
  race. claim.sh is NOT modified — leases are a sidecar (state/leases/) that
  reference the same ticket namespace.
- **Worktree binding, not PID/session-id alone**: the lease binds (ticket,
  worktree, session-id, heartbeat). The worktree path is the strongest physical
  binding — a worktree is assigned to one session and the file system path
  cannot be forged. session-id is informational.
- **No mandatory install at commit time**: `install` is available but the hooks
  are NOT auto-wired. The gate works once installed; until then, commits flow
  as before. This is intentional "keep it cheap" — the thinnest slice is the
  check logic itself; wiring it everywhere is a follow-up.
- **`WORK_LEASE_BYPASS` env var**: any caller can bypass all checks. This is
  needed for maintenance, for land.sh (its committed scoped changes), and for
  the board-hygiene manual commits that the main checkout allows.
- **No test file** (owned by the ticket's `ds: section only, no explicit `owns:`
  in the board file). The fail-on-revert proof is structural: revert the
  pre-commit check → worktree commits with no lease go through; revert the
  commit-msg check → main-checkout work commits go through. Validation is
  manual until a test ticket extends this.

## Scope check
Changed/new files (all in scope per ticket `ds:` section — owns `fleet/work-lease.sh
+ pre-commit/pre-land hook`):
- `fleet/work-lease.sh` (new)
- `fleet/hooks/pre-commit` (new)
- `fleet/hooks/commit-msg` (new)
- `docs/review-log/WORK-LEASE-GATE.md` (this fragment — allowed)
