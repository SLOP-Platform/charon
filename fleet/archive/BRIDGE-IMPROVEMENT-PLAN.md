> ARCHIVED 2026-07-08 — superseded by BRIDGE-HARDEN (done) + the durable-bridge redesign (DURABLE-BRIDGE-DESIGN-v3.md)

# Bridge Improvement Plan — Charon Session-Bridge

**Date:** 2026-07-02
**Trigger:** PR #78 merge collision — `yoda` lost uncommitted `--all` import work when
operator checkout/merge happened on the same branch without bridge visibility.

## Root cause

The Charon session-bridge (`~/.config/opencode/session-bridge/server.py`) is a simple
register/update/purge MCP server. It auto-purges sessions after `SESSION_TTL_S = 600s`
of inactivity. When the operator merged PR #78 and checked out a different branch:

1. No session knew the merge was happening (bridge has no merge/checkout signal)
2. Sessions on the same branch had no collision warning (bridge has no `branch` field)
3. Uncommitted work was silently wiped (bridge has no file-ownership tracking)
4. The auto-purge is binary (delete after TTL) — no graduated response

## Mediastack droid system — reference model

The mediastack system (`~/.code/mediastack/.claude/mailbox/`) uses a filesystem-based
droid management system with these key design patterns:

### Multi-layer defense against false reaps
- **NUDGE** (300s stall) → **NUDGE again** → **ESCALATION** (operator alert) →
  **GRACE period** (600s) → **AUTO-REAP** — graduated, not binary
- **Two independent detection legs**: heartbeat staleness (600s mtime) AND progress
  stall (300s hash-unchanged) — either can flag a droid, same escalation chain
- **Background operations**: long subagents dispatch in `run_in_background`, freeing
  main loop to continue heartbeating
- **PID liveness**: `kill -0` check verifies process exists before claiming a slot
- **Proof requirements**: BLOCKED requires existing proof-of-search file; session
  end refuses bare shutdown while pool non-empty

### Key timing constants
| Parameter | Value | Purpose |
|---|---|---|
| Heartbeat staleness | 600s | Session mtime > this = presumed dead |
| Progress stall | 300s | Hash unchanged while WORKING = STALL |
| Warden interval | 300s | Election/watcher cycle |
| Nudge max | 2 | Unanswered nudges before escalation |
| Reap grace | 600s | Operator window after escalation |
| Reap cooldown | 1800s | Reaped name pulled from pool |

## What to implement

### Phase 1: Fix immediate docs bug (0 risk, immediate benefit)

AGENTS.md says 300s TTL in 3 places — reality is 600s. Fix all instances.

### Phase 2: Env-var-configurable TTL + PID liveness (prevents false reaps)

**File:** `~/.config/opencode/session-bridge/server.py`

1. Change line 24 from:
   ```python
   SESSION_TTL_S = 600
   ```
   to:
   ```python
   SESSION_TTL_S = int(os.environ.get("SESSION_BRIDGE_TTL", "600"))
   ```

2. Add PID liveness check in `_purge_stale()`: before deleting a session, call
   `os.kill(pid, 0)` to verify the process is actually dead. Skip purge if the
   process is still alive. This prevents the most common false-reap scenario
   (session running a long subagent, heartbeat missed).

3. Pass the env var from the MCP config in `~/.config/opencode/opencode.json`:
   ```json
   "mcp": {
     "session-bridge": {
       "type": "local",
       "command": ["python3", "/home/stack/.config/opencode/session-bridge/server.py"],
       "enabled": true,
       "env": { "SESSION_BRIDGE_TTL": "600" }
     }
   }
   ```

### Phase 3: Graduated response (warn before purge)

Add to `_board_result()`: sessions approaching TTL get an `"expires_in_seconds"` field
in the board response. Sessions see their own expiry approaching and can heartbeat
before being purged. The board marks sessions > 80% of TTL as `"expiring_soon": true`.

### Phase 4: Branch + files tracking (collision prevention)

Add optional fields to `register()` and `update()`:

| Field | Type | Purpose |
|---|---|---|
| `branch` | string | Git branch the session is on |
| `files` | list[string] | Files being edited (from ticket's `owns`) |
| `busy` | string or null | State-changing operation flag (`"committing"`, `"merging"`, null) |

On `board()`, return an `advisories` field listing active operations that affect the
caller's branch/files. This is advisory, not blocking — the bridge can't prevent
git operations, only warn about them.

### Phase 5: Claim atomically on register

Make `ticket` and `claim()` the primary coordination signal. Sessions SHOULD claim
a ticket on register. The board highlights `ticket: null` sessions.

## What we are NOT doing (from mediastack but out of scope)

- Filesystem-based heartbeat files (Charon uses MCP, not scripts)
- Warden election cycle (single session context, no team)
- Proof-of-search requirements (no blocked/search concept in Charon)
- Budget / wind-down tracking (not relevant to gateway config work)
- Per-tab droid relauncher (operator manages sessions manually)

## Collision example: PR #78 with the improved bridge

If Phase 4 were active during the PR #78 merge:

1. `yoda` registers with `branch="feat/global-fallback-provider"`, `files=["src/charon/cli.py"]`
2. `luke-skywalker` registers awaiting merge on same branch
3. `board()` shows both sessions on the same branch — advisory visible
4. Operator checkout to `feat/prod-install` — no bridge signal (can't prevent shell commands)
5. After phase 4, `yoda` calls `update(busy="committing")` before committing
6. Advisories in `board()` show `yoda` has uncommitted changes on this branch
7. Operator sees advisory and waits or coordinates before checkout

The bridge CANNOT block shell commands. But it CAN warn. The real prevention is:
(a) sessions commit frequently, (b) operator checks board before branch operations.

## Files to modify

| File | Change |
|---|---|
| `/home/stack/code/charon/AGENTS.md` | Fix 300s→600s (3 instances) |
| `~/.config/opencode/session-bridge/server.py` | Env-var TTL + PID liveness |
| `~/.config/opencode/opencode.json` | Pass TTL env var to MCP server (optional) |
| `~/.config/opencode/session-bridge/SESSION.md` | Document graduated response |
| `/home/stack/charon-private/fleet/BRIDGE-IMPROVEMENT-PLAN.md` | This document |
