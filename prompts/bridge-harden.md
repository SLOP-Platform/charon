# BRIDGE-HARDEN — Session-bridge improvements from mediastack droid patterns

## Why

PR #78 merge collision (2026-07-01): session `yoda` lost uncommitted `--all` import work when an
operator checkout/merge happened on the same branch without bridge visibility. Root cause: the
Charon session-bridge has binary auto-purge (delete after 600s TTL) with no graduated response,
no progress detection, no collision warning, and no end-session gate.

The mediastack droid management system (`~/.code/mediastack/.claude/mailbox/`) has five patterns
that are strictly better and transferrable to the Charon bridge. This ticket implements all five.

## Reference

Full analysis: `/home/stack/charon-private/fleet/BRIDGE-IMPROVEMENT-PLAN.md`

## 1. Background operations (process change, no bridge code)

**Mediastack pattern:** Droids dispatch long subagents and reviews via `run_in_background`, NOT
foreground. Background ends the turn immediately → heartbeat stamps → no false reap. Foreground
blocking during a subagent call is the #1 cause of false reaps (killed bb-8 twice).

**What to do:**
- Update AGENTS.md heartbeat-before-dispatch section to require background subagent dispatch for
  any operation exceeding 120s.
- Document the pattern: "Before starting long work → heartbeat. Then dispatch in background.
  Background ends your turn → heartbeat stamps → no reap. Do NOT foreground-block on subagents."

## 2. Graduated response (NUDGE → ESCALATE → REAP)

**Mediastack pattern:** Stale droid → NUDGE → if no response, NUDGE again → if still nothing,
ESCALATE (alert operator) → 600s grace → THEN auto-reap. A live droid clears the stall counter
by responding to one nudge. Binary purge (just delete) never triggers without escalation.

**What to do:**
- Add `expires_in_seconds` field to `board()` response entries: time remaining before purge.
- Add `advisories` list to `board()` and `update()` responses: warnings for sessions approaching
  TTL (>80% elapsed = "expiring_soon").
- Add `nudge` tool: send a directed wake-up to a session (returns a message the session sees
  on next `board()` call). Sessions that respond (any `update()` call) clear their nudge counter.
- In `_purge_stale()`: before deleting, check if the session was nudged. If nudged < 2 times,
  send a nudge instead of purging. Only purge after 2 unanswered nudges + grace TTL.

## 3. Session PID verification on claim

**Mediastack pattern:** The proposed `heartbeat.sh` records `spid=<claude PID>` so `claim_role.sh`
can verify "is this session's process still alive?" via `kill -0` before claiming its slot.
Prevents the "sidecar race" where a slot reads claimable but its process is still running.

**What to do:**
- In `claim()`: before returning a conflict because the ticket is already claimed, check if
  the claiming session's PID is still alive via `os.kill(pid, 0)`. If the PID is dead, auto-release
  the claim and grant it to the new session. Return a `released_stale: true` flag.
- This is the INVERSE of the PID-liveness-in-purge already implemented (which checks "is this
  session dead before purging"). This checks "is the claim holder dead before denying."

## 4. Progress detection (stall check)

**Mediastack pattern:** `check_progress.sh` hashes 4 physics signals (git HEAD, uncommitted diff,
mailbox posts, heartbeat item). If the hash is unchanged for 300s while status = WORKING, flag
STALL — alive but frozen. The response is a NUDGE, not a kill.

**What to do:**
- Add `last_status_change` timestamp to the sessions table (updated whenever `status` or
  `blockers` change in `update()`).
- In `_board_result()`: compute `stall_seconds = now - last_status_change`. If
  `stall_seconds > 300` and status is `in-progress`, mark the session as `stalled: true`
  in the board response with `stall_seconds`.
- Stalled sessions trigger a nudge (pattern #2 above), not auto-purge.
- Schema migration: add `last_status_change TEXT` column.

## 5. End session gate (no bare `unregister`)

**Mediastack pattern:** `end_session.sh` REFUSES bare shutdown while the pool is non-empty. Must
provide `winddown` (budget exhausted, role file updated, fires respawn) or `drained <proof>`
(nothing safe to work, proof-of-search required).

**What to do:**
- Add optional `reason` field to `unregister()`: `"done"` (ticket completed), `"winddown"`
  (session ending normally), `"drained"` (no work remaining), or null (bare exit).
- If `reason` is null and the session has an active `ticket` claim, return a warning:
  `"active_ticket": "<id>", "hint": "Session has an active ticket — release it first or pass reason='done'/'winddown'."`
- This is advisory, not blocking — the session can still unregister. But the warning surfaces
  to the operator.
- On `unregister()`, auto-release any tickets the session held.

## Hard constraints

- **Bridge server is stdlib-only** (already is — sqlite3 + json + os). No new dependencies.
- **Backwards compatible**: all new fields optional with defaults. Existing sessions that don't
  use the new features continue to work.
- **Schema migration**: add columns with `ALTER TABLE ... ADD COLUMN` (safe — SQLite adds with
  default NULL). The `_migrate()` function already handles this pattern.
- **AGENTS.md is gitignored** — changes are local-only but should be documented in the charon
  fleet notes.

## Implementation order

| Step | What | Files |
|---|---|---|
| 1 | Background ops AGENTS.md update | AGENTS.md |
| 2 | Schema migration: `last_status_change` column | server.py |
| 3 | Nudge tool + graduated purge | server.py |
| 4 | PID claim verification | server.py |
| 5 | Stall detection in board | server.py |
| 6 | unregister reason + auto-release | server.py |
| 7 | Update opencode.json bridge tools schema | opencode.json |

## Acceptance

- Bridge server starts and processes all tools without error.
- `board()` returns `expires_in_seconds` and `stalled` fields.
- `board()` returns `advisories` when sessions are expiring.
- `update()` updates `last_status_change` on status/blockers change.
- `nudge()` sends a directed message, cleared by any `update()`.
- `purge_stale()` uses escalated response: nudge → nudge → escalate → purge.
- `claim()` auto-releases stale claims when PID is dead.
- `unregister()` warns on active ticket without reason; auto-releases tickets.
- Backward compatible: sessions that don't use new fields are unaffected.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
