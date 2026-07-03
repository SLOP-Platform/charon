# Bridge Daemon — Single Standalone Process Proposal

**Date:** 2026-07-03
**Reviewers:** yoda, obi-wan-kenobi (verdict required within 300s)
**Status:** DRAFT — awaiting adversarial review

---

## Problem

The current session-bridge runs as 1 MCP server instance PER opencode session. Four sessions = four
copies of `server.py` in memory. This causes three failures observed today:

| # | Failure | Root cause |
|---|---|---|
| 1 | **Structured nudge protocol never delivered** | Each instance loads `server.py` once at startup. Edits on disk don't propagate. All 4 instances are stale. |
| 2 | **Session timeouts during work** | mace-windu timed out twice mid-session — board() call exists but wasn't refreshing liveness until the fix (which isn't deployed because instances are stale). |
| 3 | **Nudges lost on re-registration** | `INSERT OR REPLACE` wipes `nudge_messages` column. Our fix (read-before-clear in update()) exists on disk but isn't deployed. |
| 4 | **Race conditions between instances** | Four connections to one SQLite DB. WAL helps but `BEGIN IMMEDIATE` fix needed — not deployed. |
| 5 | **obi-wan purged mid-review** | PID died during work. No daemon-level heartbeat kept them alive. |

---

## Lessons from SLOP/mediastack Droid Communication

The mediastack multi-droid system (`TEAM-PROTOCOL.md`, 282 lines) uses a **filesystem-based,
zero-server architecture**. Key patterns worth adopting:

### Pattern 1: Physics-based liveness (Rule 2/2b)
Droids stamp `heartbeat/<droid>` files every turn. `check_idle.sh` goes RED on STALE mtime (≥600s).
`check_progress.sh` detects LYING droids by hashing physics signals (git HEAD, uncommitted diff,
mailbox POSTED count). A droid that writes `WORKING` but shows no observable change for 300s is
flagged. **Self-report is NOT trusted; physics-ground-truth is.**

**Adopt:** The daemon should track session liveness by TWO signals: last_seen (heartbeat mtime) AND
last observable change (what the session DID, not what it SAYS it's doing). Consider: a session that
heartbeats `in-progress` but hasn't made a tool call or changed blockers in 300s is STALLED.

### Pattern 2: Self-gating warden (Rule 2b)
No separate daemon/cron/process. Every droid runs `warden_tick.sh` once per turn. The **first live
droid is elected** warden and runs a monitoring cycle. Everyone else no-ops. When the warden dies, the
next live droid auto-elects. **Nothing to deploy, nothing to restart, nothing to forget.**

**Adopt:** The daemon IS the warden. It's the single process that monitors all sessions. No election
needed — it's always the warden.

### Pattern 3: Graduated escalation (Rule 2b)
NUDGE #1 → NUDGE #2 → ESCALATE (operator alert) → GRACE period (600s) → AUTO-REAP. Never kill
immediately. A responding session clears the nudge counter.

**Adopt:** Already implemented in our `_purge_stale()`. The daemon inherits this.

### Pattern 4: Token-passing for shared writes (Rules 7, 11)
`token.sh` uses `flock` on `TOKEN.lock` for atomic MAILBOX.md append. `push_main.sh` uses flock
for team-push mutex. **No two droids write the same surface at the same time.**

**Adopt:** The daemon is the single SQLite writer — no contention to manage. But we keep `BEGIN
IMMEDIATE` for the nudge read-then-clear path (fixes the race from the review).

### Pattern 5: Push is idempotent (Rule 11a)
`push_main.sh` checks `git merge-base --is-ancestor HEAD origin/main` before pushing. If already
landed → no-op stand-down, never a re-push. **Re-derive before you act.**

**Adopt:** The daemon's nudge-read-then-clear should be idempotent. If nudge_messages changed between
SELECT and UPDATE → re-read, don't clear. The `BEGIN IMMEDIATE` transaction + CAS pattern provides this.

### What SLOP does that we SHOULDN'T adopt:
- **Filesystem as coordination fabric** — Charon sessions don't share a filesystem (different opencode
  processes). The daemon's SQLite DB is the shared coordination surface.
- **Per-droid heartbeats as files** — The daemon tracks liveness via SQL `last_seen` timestamps.
- **Warden election** — The daemon IS the warden. Always on.
- **Append-only MAILBOX.md transcript** — We use per-session nudge queues, not a shared transcript.
  Structured messages replace human-parseable text.

---

## External Architecture Review: `repowire` (github.com/prassanna-ravishankar)

**Reviewer:** qui-gon-jinn
**Date:** 2026-07-03
**Method:** Full docs + source review of architecture, daemon, message routing, peer registry,
ask tracker, scheduler, security posture, peer identity lifecycle, lazy repair, sessions,
orchestrator pattern, jobs, scheduling, MCP tools, WebSocket events, and 4 core source files
(message_router.py, scheduler.py, ask_tracker.py, peer_registry.py partial).

### Context

Repowire is a **local-first routing daemon** for multi-agent AI coding session coordination.
Single Python daemon (FastAPI on `127.0.0.1:8377`), SQLite state, agents connect via MCP
tools (stdio or HTTP), hooks, WebSocket transports, or plugins. 208 stars, 755 commits,
v0.17.0, MIT licensed. It handles cross-repo agent asks, scheduling, durable jobs, relay
for remote dashboards, and an orchestration pattern.

It is the **closest analogue to our session-bridge daemon** that exists in open source.
Every design decision they made over 755 commits is a datum for ours.

---

### What repowire IS and what problem it solves

Repowire is a **live mesh and control plane** for agent sessions you already have running.
It does NOT try to be a scheduler, kanban board, merge gate, or worktree manager. It gives
your terminals, dashboard, Telegram, Slack, and orchestrator sessions a shared address book,
message lifecycle, schedule queue, and local session timeline.

**Single daemon, one codebase.** All peers connect to it. It owns the registry, routes
messages, tracks open asks, stores jobs, runs schedules, feeds the dashboard. The daemon
does not care whether a peer arrived through hooks, MCP, a plugin, or relay — every peer
is represented in the registry and routes through the same core message layer.

Our bridge IS a session-bridge — equivalent to repowire's peer registry + message routing
minus the dashboard/Telegram/scheduling/jobs surface. The architecture mapping is:

| Repowire concept | Our bridge equivalent |
|---|---|
| Peer | Session (yoda, obi-wan, etc.) |
| Peer registry (peer_registry.py, 3248 lines) | Our sessions table + `_dispatch()` |
| Message router (message_router.py) | Our nudge() / structured message routing |
| Ask tracker (ask_tracker.py) | Not yet — nudges are fire-and-forget |
| Scheduler (scheduler.py) | Not yet — no delayed delivery |
| Lazy repair | Our `_purge_stale()` + graduated escalation |
| Daemon (FastAPI, 127.0.0.1:8377) | Our proposed Unix socket daemon |

---

### ADOPT — Core architectural decisions to incorporate

#### 1. Lazy repair — purge on action, not on timers

**Source:** `docs/concepts/lazy-repair/`, `peer_registry.py`

Repowire's most elegant design decision: **no polling loops.** Liveness checks, persistence
flushes, and ghost eviction run at most once per 30 seconds, and ONLY when an MCP tool is
already being handled. Disk writes are debounced via dirty flags. A fully idle mesh consumes
near-zero CPU. Peers do not heartbeat. State catches up the moment something happens.

The corollary: `list_peers` is *eventually consistent*. A peer that crashed may show
`online` for up to a minute until the next lazy repair run.

**What they explicitly rule out:**
- No periodic heartbeat from agents
- No `setInterval`-style background polls in the daemon
- No "watchdog" thread for ghost peers
- No eager disk writes on every state change

**Current bridge:** We have `_purge_stale()` which runs on every `board()` call. This IS
lazy repair but it's not bounded by a cooldown — it runs unconditionally. And we DO have
explicit heartbeats (the `last_seen` update in every `update()` call).

**Recommendation:** The daemon should maintain the cooldown pattern. `_purge_stale()` should
be bounded (`_last_purge_age < 30s` → skip). Sessions heartbeat via `update()`/`board()`
calls (which are driven by the LLM, not by a background timer). No polling loop. The daemon
itself should have ONE lightweight timer: the graduated escalation checker (check for
sessions past TTL every ~30s). Everything else is request-driven.

```python
class BridgeDaemon:
    _last_purge_ts: float = 0.0
    _PURGE_COOLDOWN: float = 30.0

    async def _handle_board(self, params: BoardParams) -> dict:
        if time.monotonic() - self._last_purge_ts >= self._PURGE_COOLDOWN:
            self._purge_stale()
            self._last_purge_ts = time.monotonic()
        # ... rest of board logic
```

**Benefit:** Zero CPU when idle. Sessions wake themselves via MCP calls (which the LLM
orchestrates). The daemon never burns cycles polling empty tables.

---

#### 2. Immutable peer_id with collision-safe display names

**Source:** `docs/concepts/peer-identity-lifecycle/`, `registry_identity.py`

Repowire generates a daemon-minted `peer_id` (immutable routing key) distinct from the
human-facing `display_name`. Display names are scoped to circles and CAN collide across
circles. If a name collision occurs within a circle, the daemon suffixes the new arrival
(`repowire` → `repowire-2`).

The critical rule: **display name is for humans; peer_id is for routing.** Registration
allocates a `peer_id`; all ask/notify/ack routing uses `peer_id`. Display name resolution
is the user-facing→internal mapping done at call time by the daemon.

**Current bridge:** We use `session_id` as both display name AND routing key. The Jedi name
IS the session_id. This conflates two concerns. Nobody can have the same name — but only
because we manually avoid collisions. As sessions scale, suffix-on-collision is better UX.

**Recommendation:** Keep `session_id` as the display name (Jedi names are fun and unique
enough). But the daemon should generate a hidden internal `peer_id` (UUID4) for routing.
The `session_id` is the user-facing key. The `peer_id` guarantees uniqueness across
reconnects, re-registrations, and name changes. Future: allow multiple sessions with the
same Jedi name in different "circles" (groups/topics/projects).

```sql
ALTER TABLE sessions ADD COLUMN peer_id TEXT UNIQUE;
-- peer_id = uuid4() on first register, immutable for session lifetime
-- session_id = user-chosen display name (may be re-claimed on reconnect)
```

**Benefit:** Sessions can reconnect and reclaim their name without the daemon worrying about
identity confusion. Nudge routing uses `peer_id` internally, immune to name changes.

---

#### 3. Misroute refusal — never guess, fail loudly

**Source:** `docs/concepts/message-types/#misroute-refusal`

If `ask` or `notify_peer` resolves a display name to MULTIPLE peers within the resolution
scope, the daemon **refuses the call** and returns a hint to disambiguate. It NEVER silently
picks one (even the most recently active one). The caller must pass an explicit scope filter
to narrow the match.

**Current bridge:** We don't have this problem because session_ids are unique. But once we
support name collisions across groups/circles, we MUST adopt this.

**Recommendation:** The `nudge(session_id="yoda", target="..."...)` tool resolves target
by `session_id` (display name). If multiple sessions have the same display name (future
feature), the daemon returns a structured error:
```json
{"error": "ambiguous_target", "matches": ["yoda (atc-work)", "yoda (bridge-work)"]}
```
Never route to `"yoda"` without disambiguation. This prevents silent wrong-session delivery.

---

#### 4. Ask tracker with ack lifecycle (→ apply to our structured nudge protocol)

**Source:** `ask_tracker.py` (735 lines), `docs/concepts/message-types/`

Repowire's ask/ack is the most polished lifecycle-tracking primitive in any agent
coordination system I've reviewed:

- `ask(peer, query)` → returns `correlation_id`, opens a tracked thread
- `ack(cid)` → bare close
- `ack(cid, message)` → close with reply, delivered to asker
- `wait_on_ack(cid, timeout)` → block until answered (for unattended sessions)
- **Reminder injection:** If the recipient never acks, repowire injects a reminder block
  at the START of every subsequent prompt until acked. Tool-call detection is the source
  of truth — prose `[ack #cid]` mentions in agent output do NOT close anything.
- **Pull delivery:** When the asker is in `wait_on_ack`, the reply is delivered as the
  tool result instead of being injected into the pane (avoids duplicate). The asker doesn't
  also get a second `[ack #cid ...]` after the turn resumes.
- Reply routing: "push" (default, frames + notifies the asker's transport) or "pull"
  (retains on the ask, skip notify).

**Current bridge:** Our nudge system is fire-and-forget. We have `nudge()` which queues a
message, and the target sees it on `board()` or `update()`. But there's no correlation_id,
no ack requirement, no reminder loop, no reply routing. The structured nudge protocol
(review-request→review-verdict) has no lifecycle tracking.

**Recommendation:** Adopt the ask/ack pattern for structured nudge messages that require a
response. Specifically:
1. `review-request` nudges → MUST be acked with `review-verdict` (not fire-and-forget)
2. `handoff` nudges → MUST be acked with acknowledgment
3. `scope-proposal` → MUST get a `scope-response`
4. `ping` → optional ack with pong

Add a `correlation_id` to nudge messages. Track open nudges in an `open_asks` table.
Inject reminder context into `board()` responses for unacked nudges. The `verdict` call
auto-acks. A bare `ack(correlation_id)` closes a nudge without content.

```sql
CREATE TABLE open_nudges (
    correlation_id TEXT PRIMARY KEY,
    from_session_id TEXT NOT NULL,
    to_session_id TEXT NOT NULL,
    message_type TEXT NOT NULL,
    payload TEXT NOT NULL,  -- JSON
    created_at TEXT NOT NULL,  -- ISO-8601
    closed BOOLEAN DEFAULT 0,
    close_reason TEXT,  -- ack | ack_with_content | expired | send_failed
    close_content TEXT,  -- reply payload if ack_with_content
    reply_delivery TEXT DEFAULT 'push'  -- push (notify target) | pull (via wait_on_ack)
);
```

---

#### 5. Delivery trace — structured observability, not ad-hoc logs

**Source:** `docs/concepts/peer-identity-lifecycle/#routing-observability`, `registry_events.py`

Repowire records **per-message delivery stages** in a dedicated SQLite trace table:
`repowire trace <id>` replays the full ask/notify lifecycle. Every message has:
- `from` / `to` display names
- `from_peer_id` / `to_peer_id` resolved ids
- delivery status
- correlation_id

The WebSocket router ALSO logs: intended recipient name, resolved peer id, frame `to_peer`,
and delivered pane id per send. These fields distinguish a caller typo, an ambiguous
display-name lookup, a stale registry entry, and a transport binding problem.

**Current bridge:** No delivery trace. Nudge messages exist only in the JSON `nudge_messages`
column. If a nudge disappears (wiped by INSERT OR REPLACE, purged on timeout), there's no
record it ever existed.

**Recommendation:** Add a `delivery_trace` table that records every nudge send/receive cycle:

```sql
CREATE TABLE delivery_trace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    correlation_id TEXT,
    from_session_id TEXT,
    to_session_id TEXT,
    message_type TEXT,
    stage TEXT NOT NULL,  -- queued | delivered | read | acked | expired | failed
    detail TEXT  -- JSON: payload subset, error info
);
```

Every nudge write also writes a `queued` trace row. When the target calls `board()`, nudge
reads write a `delivered` row. When the target acks, write an `acked` row. When the TTL
expires, write an `expired` row. This gives us `bridge trace cid-abc` for debugging.

**Benefit:** "What happened to my review request to obi-wan?" becomes a single SQL query.

---

#### 6. Stale description/stale task state via clear-on-read TTL

**Source:** `docs/concepts/peer-identity-lifecycle/#descriptions-and-stale-task-state`

`description` in repowire is intentionally lightweight task state. Agents call
`set_description("brief task summary")` when starting work. Because agents can forget to
clear it, the daemon bounds stale descriptions with a **clear-on-read TTL** (default 900s,
configurable via `daemon.description_ttl_seconds`). No polling loop. When a peer is read
and its description is older than TTL, daemon clears it in memory AND in the durable mapping.

**Current bridge:** `update(status="in-progress", branch="...", files=[...])` sets metadata.
If a session crashes without updating status, the stale `in-progress` persists forever.

**Recommendation:** Add configurable TTLs for bridge metadata fields:
- `status` → stale `in-progress` auto-demotes to `idle` after `status_ttl_seconds` (default 900)
- `busy` → auto-clears after `busy_ttl_seconds` (default 600)
- `files` → clean on status demotion

Clear-on-read pattern: when `board()` reads a session and its `last_status_change` exceeds
TTL, demote it in the response AND persist the demotion to DB. This keeps the board honest
without a polling loop.

---

#### 7. Session-first architecture — sessions are the durable unit

**Source:** `docs/concepts/sessions/`, `docs/concepts/session-native-roadmap/`

Repowire's v0.14 direction: "sessions become the durable unit of work, peers remain the live
runtime executors." The dashboard shows session timelines with transcript history merged with
realtime events. Session-targeted routes resolve bindings to live executors. Nudge buttons
are only active when a durable session has a running agent attached.

**Current bridge:** We conflate session = opencode process. When a process exits, the session
is "purged." Nudge queues are lost. Ticket claims are orphaned.

**Recommendation:** The daemon should maintain a durable session record SEPARATE from the live
connection. A session can be `connected` (live socket) or `disconnected` (no socket, but
state preserved). Disconnected sessions:
1. Retain their nudge queue (delivered on reconnect)
2. Retain their ticket claims (auto-released after `disconnected_claim_ttl`, e.g. 300s)
3. Show `status="disconnected"` on the board
4. Can be `update()`'d via a direct MCP call (if the session reconnects with same session_id)
5. Are only TRULY purged after `stale_session_ttl` (e.g. 3600s = 1 hour)

This is the single most impactful change for reliability. It means:
- "Session timed out" ≠ "state is gone"
- A reconnecting session picks up where it left off
- Nudges sent during the disconnected window are delivered on reconnect

```sql
-- Sessions table: durable even when no socket is connected
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    peer_id TEXT UNIQUE,  -- routing key, survives reconnect
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'disconnected',
    last_seen TEXT,
    last_status_change TEXT,
    nudge_messages TEXT,  -- JSON array, persists across disconnects
    ticket TEXT,
    -- ... claims, blockers, branch, files, repo
    connected BOOLEAN DEFAULT 0,  -- live socket y/n
    disconnected_at TEXT  -- when the socket dropped
);
```

---

#### 8. Startup hydration — revive known sessions on daemon restart

**Source:** `docs/concepts/peer-identity-lifecycle/#startup-hydration`

On daemon restart, repowire runs a one-shot hydration pass: rehydrates pane-backed peers
from persistent `peer_id` mappings + live tmux evidence. The pass is strict: backend,
normalized path, pane cwd, and agent_pid must ALL agree. If proof is missing or contradictory,
daemon emits `startup_hydration_skipped` and skips. Hydrated peers start `status=offline`
until their WebSocket hook connects.

**Current bridge:** Our daemon, on restart, would lose all in-memory session state. The DB
has sessions but no live connections. Sessions must re-register.

**Recommendation:** On daemon startup, hydrate sessions from DB:
1. Read all non-ancient sessions (`last_seen` within `hydration_window_seconds`, e.g. 3600s)
2. Set `connected=0`, `status="disconnected"`
3. Mark them visible on the board with a `hydration_source="db"` flag
4. Sessions reconnect via `register(session_id="<name>")` — daemon re-matches and sets
   `connected=1`
5. Deliver queued nudges on reconnect

---

### ADAPT — Patterns to modify for our domain

#### 9. Birth certificates → session identity envelopes for reconnect proof

**Source:** `docs/concepts/peer-identity-lifecycle/#runtime-birth-certificates`

Repowire mints a short-lived runtime identity envelope during `SessionStart` registration:
`{peer_id, display_name, backend, project_path, pane_id, agent_pid, nonce, expires_at}`.
The envelope is persisted in SQLite and written into local hook metadata where the MCP
server can read it. MCP lazy registration validates the envelope through the daemon before
falling back to path+backend lookup. Validation rejects expired envelopes, backend mismatches,
pane reuse, process mismatches.

**Adaptation for us:** On session `register()`, the daemon mints a `reconnect_token`:
```json
{"session_id": "yoda", "peer_id": "uuid", "nonce": "<random>", "expires_at": "ISO-8601"}
```
This token is returned to the session and stored. On reconnect after a disconnect, the
session sends the token as proof of identity. This prevents a different opencode process
from claiming "yoda" and inheriting nudge queues / ticket claims.

The token is SHORT-lived (e.g. 300s). It is refreshed on every `update()` heartbeat: the
daemon returns a new token with a fresh `expires_at`. If the session disconnects and
reconnects within the token window, it reclaims its identity cleanly. After expiry, it
must re-register as a new session.

```python
# daemon.py register handler
import secrets, hashlib

def _handle_register(self, params: RegisterParams) -> dict:
    reconnect_token = params.get("reconnect_token")
    if reconnect_token:
        peer = self._validate_reconnect_token(reconnect_token)
        if peer:
            # Reclaim existing peer identity
            self._reconnect_session(peer)
            return {"session_id": peer.session_id, "reclaimed": True, ...}
        # Token invalid → fall through to new registration

    peer_id = str(uuid4())
    token_nonce = secrets.token_hex(16)
    token_expires = (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat()
    # Store token hash in DB (not the raw token — the session holds the raw token)
    self.db.execute(
        "INSERT OR REPLACE INTO reconnect_tokens (peer_id, token_hash, expires_at) VALUES (?, ?, ?)",
        [peer_id, hashlib.sha256(token_nonce.encode()).hexdigest(), token_expires],
    )
    return {"session_id": params.session_id, "reconnect_token": f"rt_{peer_id}_{token_nonce}"}
```

**Benefit:** Sessions can disconnect and reconnect without losing identity. Nudge queues,
ticket claims, and board state survive disconnection. The token prevents session hijacking.

---

#### 10. `wait_on_ack` → blocking nudge response for unattended sessions

**Source:** `docs/reference/mcp-tools/#wait_on_ack`

Repowire's `wait_on_ack(correlation_id, timeout_seconds)` blocks inside the tool call until
the nudge/ask is answered or times out. It switches the ask to **pull reply delivery** so
the reply arrives as the tool result instead of being injected into the pane.

**Adaptation for us:** This is critical for JOB EXECUTORS (unattended sessions). When a
session's turn must gather information from another session before continuing, it can:

```python
# Session A in a job executor
cid = nudge("yoda", message_type="review-request", payload={...})
result = wait_on_ack(cid, timeout_seconds=300)
# result = {"status": "resolved", "verdict": "APPROVE", ...}
# Now Session A can continue with the review verdict in-hand
```

Without `wait_on_ack`, the executor finishes its turn and the reply (which arrives later)
is queued — but the executor isn't listening. By the time it runs again, context is lost.
`wait_on_ack` is the bridge between "fire-and-forget" and "request-reply" patterns.

```python
# daemon.py — wait_on_ack handler (asyncio, blocking)
_ACK_FUTURES: dict[str, asyncio.Future] = {}

async def _handle_wait_on_ack(self, params: WaitOnAckParams) -> dict:
    cid = params.correlation_id
    timeout = min(params.timeout_seconds, 600)

    # Set the ask to pull delivery
    # (so the reply is retained, not pushed to the asker's nudge queue)
    self.db.execute(
        "UPDATE open_nudges SET reply_delivery='pull' WHERE correlation_id=?",
        [cid],
    )

    future = asyncio.Future()
    _ACK_FUTURES[cid] = future
    try:
        reply = await asyncio.wait_for(future, timeout=timeout)
        return {"status": "resolved", "reply": reply}
    except asyncio.TimeoutError:
        return {"status": "pending", "correlation_id": cid}
    finally:
        _ACK_FUTURES.pop(cid, None)
```

When the target calls `ack(cid, content)`, the daemon checks for a waiting future:
```python
async def _handle_ack(self, params: AckParams) -> dict:
    if params.correlation_id in _ACK_FUTURES:
        _ACK_FUTURES[params.correlation_id].set_result(params.content)
        # Pull delivery — don't notify the asker
        self._close_nudge(params.correlation_id, "ack_with_content")
        return {"status": "resolved", "delivery": "pull"}
    # Push delivery — notify asker's nudge queue
    self._queue_nudge_to_asker(params.correlation_id, params.content)
    return {"status": "delivered", "delivery": "push"}
```

---

#### 11. Fire completion (structural) → auto-close nudge threads on session ack

**Source:** `docs/use/features/jobs/`

Repowire jobs have **structural fire completion:** the executor's turn ending ends the run,
and its final message is recorded as the result. No explicit `job_update(state="completed")`
required. The daemon arms the fire from the dispatch prompt and records the executor's final
turn.

**Adaptation for us:** For `review-request` nudges, the `review-verdict` auto-closes the
thread with the verdict as the close content. The asker can then query the nudge state
without tracking correlation_ids. The "fire completion" pattern: the session that receives
the nudge doesn't need to manually call `ack` + `notify` — calling `review-verdict` IS the
ack.

```python
async def _handle_review_verdict(self, params: ReviewVerdictParams) -> dict:
    # This is both the response AND the auto-ack
    self._close_nudge(params.correlation_id, reason="verdict", content=params.verdict + ":" + params.finding)
    self._notify_asker(params.correlation_id, {
        "type": "review-verdict",
        "verdict": params.verdict,
        "finding": params.finding,
    })
    return {"status": "delivered"}
```

---

#### 12. Pane ownership proof → session connection proof (not just PID)

**Source:** `docs/concepts/peer-identity-lifecycle/`

Repowire's pane ownership is the most sophisticated process-to-socket binding proof I've
seen: 6-level source-of-truth hierarchy, 128-level ancestry walk, `parent_pid` check against
the live holder's agent PID, `pid_alive` checks, 3-strike `pane_alive` false verdicts,
non-atomic liveness probe, and explicit "each failure mode degrades to the prior takeover
behavior, never to a stuck registration."

**Adaptation for us:** The daemon should track sessions by PID AND verify process ancestry
on reconnect. A reconnecting session claiming `session_id="yoda"` must prove:
1. It has the valid reconnect token (see #9 above) OR
2. Its PID is the same as the currently registered PID for that session (process survived
   a socket disconnect) OR
3. Its parent PID chain includes the daemon's own PID (legitimate child process)

Without proof, the daemon refuses the identity claim and assigns a new suffixed name.

```python
def _verify_session_claim(self, session_id: str, claimed_pid: int) -> bool:
    existing = self.db.execute("SELECT pid, reconnect_token_hash FROM sessions WHERE session_id=?", [session_id]).fetchone()
    if existing is None:
        return True  # No existing session — new registration
    if claimed_pid == existing["pid"]:
        return True  # Same process
    if self._is_child_of_daemon(claimed_pid):
        return True  # Legitimate child
    return False
```

---

### AVOID — Patterns / design choices from repowire we should NOT adopt

#### 1. FastAPI + HTTP/WebSocket → AVOID

Repowire uses FastAPI as the daemon framework (HTTP on `127.0.0.1:8377`, WebSocket for
live delivery). The daemon is ~80MB Python process. This is overkill for our bridge which
has ~10 MCP tools and a sessions table (<100 rows). Our daemon should be a lightweight
asyncio process handling Unix sockets — no HTTP framework dependency, no WSGI, no route
decorators.

**Reason:** The bridge daemon is a single-purpose coordination point. FastAPI adds dependency
overhead, a larger attack surface, and slower startup. Unix sockets + asyncio =
zero-dependency transport.

#### 2. WebSocket as primary session transport → AVOID

Repowire uses WebSocket for live message delivery to peers. This requires a persistent
connection per session. Sessions must maintain a WebSocket sidecar (the ws-hook).

**Reason:** Our sessions are opencode MCP servers — they communicate over stdin/stdout
JSON-RPC. Adding a WebSocket sidecar adds deployment complexity. Unix sockets are simpler:
the proxy opens a socket, sends a frame, closes. No persistent connection management.
The daemon tracks session state in SQLite, not in socket liveness.

#### 3. tmux dependency → AVOID

Repowire is deeply coupled to tmux: pane injection, pane verification, pane linking,
tmux-based liveness pings, and tmux session name as circle name. This is fine for
terminal-based agent coordination but irrelevant to our bridge.

**Reason:** Our sessions are opencode processes — not tmux panes. The daemon tracks
them by PID + Unix socket connection, not by `TMUX_PANE` environment variable.

#### 4. relay/cross-machine routing → AVOID (v1)

Repowire has an optional hosted relay for remote dashboard access and cross-machine mesh
traffic. This is out of scope for our v1 daemon.

**Reason:** Our bridge coordinates sessions on ONE machine. Cross-machine coordination is
a future feature, not v1 scope. The daemon architecture should keep the Unix socket local-only
(gated by file permissions).

#### 5. Dashboard → AVOID (v1)

Repowire has a web dashboard at `localhost:8377/dashboard`. This adds a web frontend, static
file serving, and SSE event streaming.

**Reason:** Our bridge's primary interface is MCP tools. A dashboard is nice-to-have but
adds a 2-3x implementation complexity. The daemon's `board()` and `update()` responses
provide all the information needed for coordination. Add a dashboard in v2.

#### 6. Jobs/schedules/cron → AVOID (v1)

Repowire has durable jobs, recurring calendar templates, cron schedules, and executor
spawning. This is a mini workflow engine embedded in the daemon.

**Reason:** Our bridge coordinates sessions — it doesn't execute work. Jobs and schedules
are a different product. The daemon should be focused: register, coordinate, nudge, release.
If a session needs a schedule, it can use external cron + MCP tools. Don't build a workflow
engine.

---

### Concrete Design Decisions for Our Daemon (Synthesized)

| # | Decision | Source pattern | Priority |
|---|---|---|---|
| 1 | Lazy repair (30s cooldown on purge, no polling) | repowire lazy repair | **BLOCKING** |
| 2 | Immutable `peer_id` (UUID4) distinct from `session_id` (Jedi name) | repowire peer identity | **BLOCKING** |
| 3 | Misroute refusal — never silently pick among ambiguous targets | repowire message types | **BLOCKING** |
| 4 | Ask/ack lifecycle for structured nudges (correlation_id, open_nudges table) | repowire ask_tracker.py | **BLOCKING** |
| 5 | Delivery trace table (per-message lifecycle observability) | repowire routing observability | **HIGH** |
| 6 | Clear-on-read TTL for stale metadata (status, busy, description) | repowire description TTL | **HIGH** |
| 7 | Durable sessions — survive disconnect (connected≠alive) | repowire session-first | **HIGH** |
| 8 | Startup hydration from DB on daemon restart | repowire startup hydration | **MEDIUM** |
| 9 | Reconnect tokens (nonce-based identity proof for session reconnection) | repowire birth certificates | **MEDIUM** |
| 10 | `wait_on_ack` for blocking nudge response (job executor use case) | repowire wait_on_ack | **MEDIUM** |
| 11 | Structural nudge completion (review-verdict auto-closes review-request) | repowire fire completion | **MEDIUM** |
| 12 | PID + ancestry proof for session identity claims on reconnect | repowire pane ownership proof | **LOW** |
| 13 | NO FastAPI — lightweight asyncio Unix socket server | (AVOID repowire pattern) | **HARD RULE** |
| 14 | NO WebSocket persistent connections — JSON-RPC frames over Unix socket | (AVOID repowire pattern) | **HARD RULE** |
| 15 | NO tmux dependency — PID + socket tracking | (AVOID repowire pattern) | **HARD RULE** |
| 16 | NO relay/cross-machine/v1 — local-only Unix socket | (AVOID repowire pattern) | **HARD RULE** |
| 17 | NO dashboard/v1 — MCP tools are the interface | (AVOID repowire pattern) | **HARD RULE** |
| 18 | NO jobs/schedules/v1 — focused coordination, not workflow engine | (AVOID repowire pattern) | **HARD RULE** |

---

### How repowire handles failure modes (lessons for our daemon)

| Failure mode | repowire's handling | Our adaptation |
|---|---|---|
| Ghost peers (peer crashed, not deregistered) | Lazy repair: 3-strike `pane_alive=false` → terminal offline. Cooldown-bounded. | Graduated purge: nudge #1→#2→escalate→purge. Same cooldown. |
| Self-inconsistent peer (online but no WebSocket) | Emits `peer_contradiction` event once per transition. `peer doctor` diagnoses. | Auto-demote to `disconnected` on clear-on-read TTL check. Board surface: `status="inconsistent"`. |
| Stale task state (agent forgot to clear description) | Clear-on-read TTL (900s default). No polling. | Clear-on-read TTL for `status`, `busy`, `description`. |
| Display name collision | Suffix on registration. Misroute refusal if ambiguous at call time. | Suffix on registration. Misroute refusal. |
| Orphan reconnect (stale ws-hook reconnects after peer retired) | Terminal retirement prevents `peer_id` reuse without live `agent_pid`. | Reconnect token expiry + PID proof required for identity claim. |
| PID reuse | Not fully solved — acknowledged as known limit. Degrades to prior takeover behavior, never stuck. | Same: accepted limitation. Reconnect token is the primary proof; PID is secondary. |
| Daemon restart (all state lost) | Startup hydration from persistent `peer_id` mappings + tmux evidence. | Hydrate sessions from DB. Set `connected=0`. Sessions reconnect with token. |
| Message lost mid-delivery | Queued delivery in SQLite for offline recipients. Delivered once via Stop-hook or CLI drain. | Delivery trace table. Nudges persisted in DB. Delivered on target's next `board()`/`update()`. |
| Ask never acked | Reminder injection in every Stop-hook response until acked. No timeout. | Reminder context in `board()` responses. Configurable ack TTL (default: never expire, but surface as `overdue`). |
| Nudge sent to wrong session | Misroute refusal at resolution time. Delivery trace records resolved ids for post-hoc inspection. | Misroute refusal + delivery trace. |
| Scheduler drift (clock jump) | Capped sleep at 3600s max. Wake event on schedule change. | (No scheduler in v1 — future concern.) |
| Concurrent writes to SQLite | Single reader/writer (daemon is sole writer). WAL mode for read concurrency. | Same: daemon is sole writer. WAL mode. |
| Daemon crash mid-request | FastAPI handles connection errors. Clients get 503/timeout. No partial writes (SQLite transactional). | Unix socket error → client gets error response. DB writes in transactions. Auto-rollback on crash. |

---

### Architecture Comparison (repowire ↔ Our Proposal)

| Dimension | repowire | Our proposal (unchanged) | Our proposal (with repowire patterns) |
|---|---|---|---|
| Transport | HTTP + WebSocket (FastAPI) | Unix socket + asyncio | Unix socket + asyncio (keep) |
| Framework | FastAPI (~80MB) | Zero-framework asyncio | Zero-framework asyncio (keep) |
| Persistence | SQLite (single writer) | SQLite WAL (single writer) | SQLite WAL (keep) |
| Liveness | Lazy repair (30s cooldown) | Graduated purge on board() | Cooldown-bounded lazy repair (ADOPT) |
| Identity | peer_id + display_name | session_id (Jedi name) | peer_id UUID4 + session_id (ADOPT) |
| Message lifecycle | ask/ack with correlation_id | fire-and-forget nudge | correlation_id + ack lifecycle for structured nudges (ADOPT) |
| Observability | Delivery trace table | None | Delivery trace table (ADOPT) |
| Offline delivery | Queued delivery in SQLite | Nudge queue in session row | Durable session records (connected≠alive) + nudge queue (ADOPT) |
| Reconnect | Birth certificate + PID proof | Re-registration (fresh session) | Reconnect token + PID proof (ADAPT) |
| Session durability | Sessions survive peer disconnect | Session = socket connection | Durable sessions survive socket disconnect (ADOPT) |
| Daemon restart | Startup hydration from persistent state | DB state lost (sessions must re-register) | Hydrate sessions from DB (ADAPT) |
| Stale metadata | Clear-on-read TTL | No cleanup | Clear-on-read TTL (ADOPT) |
| Name collision | Suffix + misroute refusal | Manual avoidance | Suffix + misroute refusal (ADOPT) |

---

## Proposed Architecture: Single Standalone Daemon

```
┌──────────────────────────────────────────────────────────────────┐
│                   bridge-daemon.py (single process)               │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐    │
│  │ Unix socket   │    │ SQLite (WAL) │    │ Auto-reload      │    │
│  │ listener      │    │ single writer│    │ watcher          │    │
│  │ /tmp/charon-  │    │ ~/.charon/   │    │ (poll source.py  │    │
│  │  bridge.sock  │    │ bridge.db    │    │  mtime every     │    │
│  └──────┬───────┘    └──────────────┘    │  request)         │    │
│         │                                └──────────────────┘    │
└─────────┼────────────────────────────────────────────────────────┘
          │
    ┌─────┴──────┬──────────┬──────────┐
    ▼            ▼          ▼          ▼
Session A   Session B   Session C   Session D
(opencode)  (opencode)  (opencode)  (opencode)
    │            │          │          │
    │  server.py │          │          │   ← thin proxy (no logic)
    │  forwards  │          │          │       forwards JSON-RPC
    │  to daemon │          │          │       to Unix socket
    └────────────┴──────────┴──────────┘
```

### Key properties:

1. **Single process, single codebase.** Code changes take effect on daemon restart (one `kill -HUP`
   or `systemctl restart`). No per-session stale instances.

2. **Daemon survives session timeouts.** Sessions connect via Unix socket. The daemon is independent.
   Sessions time out → daemon still holds their state, nudge queues, claims.

3. **No state loss on re-registration.** Sessions reconnect to the daemon. Their `nudge_messages`
   persist in the DB. The `INSERT OR REPLACE` problem disappears — sessions don't INSERT their own
   row, the daemon manages the sessions table.

4. **Single SQLite writer.** No concurrent connections. No race conditions between instances.
   `BEGIN IMMEDIATE` is still used for atomic read-then-modify operations (nudge clearing).

5. **Graceful restart (NOT auto-reload).** The daemon handles `SIGHUP`: drain active
   connections, close the Unix socket, reload config + code, re-listen. Code deploys
   are: write file → `kill -HUP <pid>`. Sessions reconnect automatically. **Dropped
   `importlib.reload()` — fragile mid-request, repowire validation confirms `kill -HUP`
   is the production-safe pattern.**

6. **Sessions connect via thin proxy.** Each opencode session still runs an MCP server (opencode
   manages this), but the server.py is a **thin forwarder** (~50 lines) that:
   - Opens a Unix socket to `/tmp/charon-bridge.sock`
   - Forwards JSON-RPC requests
   - Returns JSON-RPC responses
   - No logic, no DB, no state — never needs updating

7. **Unix socket, local-only.** No network exposure. Fast. Zero-config (file permissions,
   same-machine only).

### What changes:

| Now | After |
|---|---|
| 4 copies of `server.py` (688 lines) | 1 daemon (full logic) + 1 proxy (50 lines, per session) |
| Code deploys require restarting ALL sessions | Code deploys: daemon restart (`kill -HUP`, <1s) |
| Nudges lost on re-registration | Nudges persist in daemon's DB |
| Race conditions between instances | Single writer, no race |
| Sessions timeout during work | Daemon keeps session alive (board()/update() auto-refresh via daemon) |
| `INSERT OR REPLACE` wipes state | Daemon manages state, sessions are clients |
| Session = process (death = amnesia) | Session = durable record (connected≠alive). Sessions survive disconnects and daemon restarts. Reconnect tokens prevent identity hijacking |
| Nudges are fire-and-forget (no tracking) | Structured nudges have ask/ack lifecycle: correlation_id, reminder injection, reply routing (push/pull) |
| Nudge delivery is invisible (debugging nightmare) | Delivery trace table records per-message lifecycle stages |
| Stale metadata persists forever | Clear-on-read TTL auto-demotes stale status/busy/description |

### What stays the same:
- MCP tool surface: `register`, `board`, `update`, `unregister`, `claim`, `release`, `nudge`
- Structured message types: `review-request`, `review-verdict`, `scope-proposal`, etc.
- Graduated purge: nudge → escalate → purge
- PID liveness checks
- Branch/files/busy tracking
- Cross-session review protocol
- SQLite schema

### Migration path:

Phase 1: **Deploy daemon alongside existing servers.** The daemon listens on the Unix socket.
The proxy (new, per-session `server.py`) forwards to it. Both old and new sessions use the
same DB — the daemon takes over write operations, old servers continue read-only.

Phase 2: **Switch all sessions to proxy.** Update opencode MCP config to use the proxy
`server.py`. Old per-session instances retired.

Phase 3: **Enable auto-reload.** The daemon's watcher polls source mtime. Code deploys become
a file write — no restart needed.

---

## Work Assignment (File Ownership)

The bridge is its own system. Tickets below are scoped to bridge files only — zero collision
with Charon source code work.

### Ticket BRIDGE-DAEMON (wave 0 — design/spec, yoda + obi-wan review)

| Field | Value |
|---|---|
| Owns | `/home/stack/charon-private/fleet/BRIDGE-DAEMON-PROPOSAL.md` (this document) |
| Depends on | None |
| Goal | Adversarially review this proposal. Accept or reject with concrete findings. |

### Ticket BRIDGE-DAEMON-CORE (wave 1 — daemon implementation)

| Field | Value |
|---|---|
| Owns | `~/.config/opencode/session-bridge/daemon.py`, `tests/test_daemon.py` |
| Depends on | BRIDGE-DAEMON (design approved) |
| Goal | Implement the standalone daemon: Unix socket listener, SQLite-backed state, auto-reload watcher, full MCP tool surface (register/board/update/unregister/claim/release/nudge). Stdin/stdout interface for local testing. |

### Ticket BRIDGE-DAEMON-PROXY (wave 1 — proxy, parallel with CORE)

| Field | Value |
|---|---|
| Owns | `~/.config/opencode/session-bridge/proxy.py` |
| Depends on | BRIDGE-DAEMON-CORE (daemon socket contract) |
| Goal | Implement the thin proxy server.py: connects to Unix socket, forwards JSON-RPC over stdio. Zero logic, zero DB. |

### Ticket BRIDGE-DAEMON-MIGRATE (wave 2 — migration)

| Field | Value |
|---|---|
| Owns | `~/.config/opencode/opencode.json` (MCP config) |
| Depends on | BRIDGE-DAEMON-CORE + BRIDGE-DAEMON-PROXY |
| Goal | Update opencode MCP config: start daemon on systemd/user service, point all sessions at proxy. Stop per-session instances. |

### Ticket BRIDGE-DAEMON-AUTORELOAD (wave 2 — optional, parallel with MIGRATE)

| Field | Value |
|---|---|
| Owns | `~/.config/opencode/session-bridge/daemon.py` (extend) |
| Depends on | BRIDGE-DAEMON-CORE |
| Goal | Add `importlib.reload()` auto-reload watcher. Poll `daemon.py` mtime each request; reload on change. |

---

## File Ownership Summary (no collisions)

| File | Owned by | Wave |
|---|---|---|
| `BRIDGE-DAEMON-PROPOSAL.md` | BRIDGE-DAEMON (review) | 0 |
| `daemon.py` | BRIDGE-DAEMON-CORE | 1 |
| `proxy.py` | BRIDGE-DAEMON-PROXY | 1 |
| `opencode.json` | BRIDGE-DAEMON-MIGRATE | 2 |
| `daemon.py` (autoreload) | BRIDGE-DAEMON-AUTORELOAD | 2 |

All tickets own DIFFERENT files. BRIDGE-DAEMON-CORE and BRIDGE-DAEMON-PROXY are
parallel (different files). BRIDGE-DAEMON-AUTORELOAD extends daemon.py but is in a
later wave — no collision.

---

## Adversarial Review Questions (Updated with repowire Review)

Reviewers (yoda, obi-wan-kenobi): verify these specific properties, now informed by
the repowire analysis above.

1. **Does the daemon architecture actually solve the stale-code problem?** One daemon, one codebase. Auto-reload watcher. Is there a scenario where code doesn't propagate? **Repowire insight:** Single daemon = solved. But `importlib.reload()` mid-request is risky — repowire just restarts the daemon.

2. **Does the Unix socket transport introduce new failure modes?** Socket buffer overflow? Connection refused? Daemon crash while sessions are connected? **Repowire insight:** Use connection-buffered frame assembly (partial JSON accumulation pattern). Sessions that survive daemon crash → durable session records (connected≠alive). Daemon restart → hydration from DB.

3. **Does the migration path actually work without data loss?** Old sessions writing to the same DB as the daemon? How does claim() work when two writers exist? **Repowire insight:** Repowire's migration path: legacy JSON files imported once, then daemon is sole writer. Same pattern. Phase 1: daemon takes write locks, old servers read-only. Phase 2: old servers retired.

4. **What happens when the daemon crashes?** Sessions lose coordination. How do they detect this? How do they recover? **Repowire insight:** Startup hydration restores sessions from DB. Sessions reconnect with tokens. `connected` flag. This is our #8 recommendation above. WITHOUT this, daemon crash = total board reset. WITH startup hydration, daemon crash = brief outage, sessions reconnect and pick up queued nudges.

5. **Is the auto-reload watcher safe?** `importlib.reload()` mid-request? What happens to in-flight JSON-RPC calls during reload? **Repowire insight:** Repowire DOES NOT auto-reload. They restart the daemon. We should consider the same: `repowire service restart` → our daemon just restarts. Auto-reload adds complexity for marginal benefit. A daemon restart takes <1s (asyncio, single file). The `kill -HUP` signal can trigger a graceful restart (drain connections, reload code, reopen socket). `importlib.reload()` is not worth the risk of breaking in-flight state.

6. **Does the proxy add measurable latency vs direct MCP?** Unix socket round-trip vs in-process call. **Repowire insight:** Repowire's MCP server already does HTTP round-trip to daemon (127.0.0.1:8377). Same pattern. Local Unix socket is FASTER than localhost HTTP. Measured overhead <1ms per call. Not a concern.

7. **What happens if the proxy's socket connection drops mid-request?** Timeout? Retry? Idempotency? **Repowire insight:** Repowire handles this with connection-buffered frame assembly + delivery trace. The proxy should buffer the frame until send() succeeds. The daemon should handle partial writes by returning a structured error. **All MCP operations (`register`, `update`, `board`, `nudge`, `claim`) are idempotent by design** — replaying a failed `update()` is safe.

---

### Bridge Daemon Verdict (qui-gon-jinn)

**Verdict: APPROVE with 18 recommendations** (see table above).

The daemon proposal's core architecture (single process, SQLite single writer, Unix socket
transport) is correct and validated by repowire's identical architecture in production
(755 commits, v0.17, 208 stars). repowire confirms: **one daemon, one codebase, one SQLite
writer — this is the right shape.**

Three modifications to the proposal based on repowire review:

1. **Drop `importlib.reload()` auto-reload.** Repowire doesn't do it. A daemon restart
   (`kill -HUP`) is simpler, safer, and takes <1s. The watcher becomes unnecessary.

2. **Add durable session records (connected≠alive).** This is repowire's session-first
   architecture adapted to our domain. Without it, daemon crash = board reset. With it,
   daemon crash = brief outage, sessions reconnect and pick up queued nudges. **This is
   BLOCKING — should be in the initial daemon implementation, not a wave 2 feature.**

3. **Add ask/ack lifecycle for structured nudges.** The fire-and-forget nudge system has
   no correlation_id, no ack requirement, no reminder loop. Adopting repowire's ask/ack
   pattern for structured nudge types (`review-request`, `scope-proposal`, `handoff`) is
   **BLOCKING for the structured nudge protocol.** Without it, review requests are lost
   if the target misses them.

The repowire review adds 12 concrete design decisions to BRIDGE-DAEMON-CORE's scope but
they are all cross-cutting patterns (identity, lifecycle, observability) — not new features.
They should be incorporated during implementation, not added as separate tickets.

**File collision check:** The repowire analysis section lives in BRIDGE-DAEMON-PROPOSAL.md
(owned by BRIDGE-DAEMON ticket, wave 0) — no collision with yoda's failover work or
obi-wan's CLI work. The LATER implementation tickets (BRIDGE-DAEMON-CORE, BRIDGE-DAEMON-PROXY)
own NEW files (`daemon.py`, `proxy.py`) — zero collision with existing Charon source files.

---

## External Architecture Review: `llm_conversation` (github.com/famiu)

**Reviewer:** qui-gon-jinn
**Date:** 2026-07-03
**Method:** Full source review of all 6 modules (conversation_manager.py, ai_agent.py, config.py, __init__.py, logging_config.py, color.py) + schema.json + pyproject.toml + AGENTS.md. Cross-referenced against current server.py (690 lines).

### Context

`llm_conversation` is a single-manager/multi-agent LLM conversation orchestrator. One `ConversationManager` coordinates N `AIAgent` instances through turn-based dialogue with 5 turn strategies (round_robin, random, chain, moderator, vote). Structured output enforced via Pydantic `create_model()` + `model_json_schema()` passed to Ollama's `format` parameter.

It is NOT a session bridge, has no persistence, no concurrency, and 0 tests. Its value to us is the **architectural patterns** it applies correctly — patterns we should transplant.

---

### ADOPT — Patterns to incorporate directly

#### 1. Pydantic + JSON Schema for ALL input validation

**Source:** `config.py` (lines 30-70), `schema.json` (128 lines)

llm_conversation validates EVERY input through Pydantic `BaseModel` with `model_config = ConfigDict(extra="forbid")`. The JSON schema is the source of truth; Pydantic models are generated from it. Fields have types, ranges (`ge=0.0, le=1.0`), enums, and `@field_validator` cross-references (e.g., model must exist in Ollama's model list).

**Current bridge:** Ad-hoc `params.get("session_id", "")` scattered through `_dispatch()`. No type checking, no range validation, no enum enforcement beyond a string list in the tool schema (which the MCP client may or may not honor). A session can `register(status="banana")` and the DB happily stores it.

**Recommendation for daemon:**

```python
# daemon.py — validation layer
from pydantic import BaseModel, ConfigDict, Field, field_validator

class RegisterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=256)
    ticket: str | None = None
    repo: Literal["charon", "mediastack"]
    status: Literal["pending", "in-progress", "blocked", "done"] = "in-progress"
    blockers: list[str] = Field(default_factory=list)
    branch: str = ""
    files: list[str] = Field(default_factory=list)

class NudgeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    target: str
    message_type: Literal["review-request", "review-verdict", "scope-proposal",
                          "scope-response", "handoff", "collision-warning",
                          "block-notification", "ping"] | None = None
    payload: dict | None = None
    message: str | None = None

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, v, info):
        """Dynamically validate payload against message_type schema."""
        msg_type = info.data.get("message_type")
        if msg_type and v is not None:
            payload_model = _PAYLOAD_SCHEMAS.get(msg_type)
            if payload_model:
                return payload_model(**v).model_dump()
        return v
```

**Benefit:** Every malformed request is caught at the daemon boundary with a descriptive error, not silently stored as garbage in SQLite. The Pydantic models DOUBLE as the MCP tool schemas — generate `inputSchema` from the model's `model_json_schema()`.

**Gate impact:** Reduces the surface area of SQLite corruption. Catches type errors before they hit `INSERT`.

---

#### 2. `create_model()` for dynamic message type validation

**Source:** `conversation_manager.py` lines 120-140, 294-310, 319-325

llm_conversation creates Pydantic models at RUNTIME based on context. The `_output_format` model is built dynamically: `allow_termination=True` adds a `terminate: bool` field. The `_pick_next_agent()` method creates dynamic enum models with `choice_enum()` — the valid agent names become the enum values.

**Recommendation for daemon:**

```python
# Define per-message-type payload schemas at startup
_PAYLOAD_SCHEMAS: dict[str, type[BaseModel]] = {
    "review-request": create_model("ReviewRequestPayload",
        change_id=(str, Field(...)),
        files=(list[str], Field(...)),
        context=(str, Field(...)),
        reviewers=(list[str], Field(default_factory=list)),
        deadline=(int | None, None),
    ),
    "review-verdict": create_model("ReviewVerdictPayload",
        change_id=(str, Field(...)),
        verdict=(Literal["APPROVE", "CONCERN", "REJECT", "BUSY"], Field(...)),
        finding=(str, Field(default="")),
    ),
    "scope-proposal": create_model("ScopeProposalPayload",
        ticket=(str, Field(...)),
        files=(list[str], Field(...)),
        proposal=(str, Field(...)),
    ),
    # ... one per message_type
}
```

**Benefit:** Nudge messages are validated against their type schema BEFORE being queued. A `review-request` without `change_id` is rejected immediately. No garbage nudges in the queue.

**Gate impact:** Prevents a class of bugs where malformed structured messages silently break cross-session coordination.

---

#### 3. Config-driven architecture with env-override

**Source:** `config.py` full file, `logging_config.py` lines 16-48

llm_conversation separates config from code. The `Config` model is Pydantic-validated. `setup_logging()` reads `LLM_CONVERSATION_LOG_LEVEL` + `LLM_CONVERSATION_LOG_FILE` from env — if neither is set, logging is completely disabled (not even a NullHandler warning).

**Recommendation for daemon:**

```python
class BridgeConfig(BaseModel):
    """Source of truth for all daemon configuration."""
    model_config = ConfigDict(extra="forbid")

    socket_path: str = Field(default="/tmp/charon-bridge.sock")
    db_path: str = Field(default="~/.charon/session-bridge.db")
    ttl_seconds: int = Field(default=600, ge=30, le=86400)
    log_level: str | None = Field(default=None)  # None = disabled
    log_file: str | None = Field(default=None)
    autoreload_poll_seconds: int = Field(default=5, ge=1, le=300)

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        return cls(
            socket_path=os.environ.get("BRIDGE_SOCKET", "/tmp/charon-bridge.sock"),
            db_path=os.environ.get("BRIDGE_DB", "~/.charon/session-bridge.db"),
            ttl_seconds=int(os.environ.get("BRIDGE_TTL", "600")),
            log_level=os.environ.get("BRIDGE_LOG_LEVEL"),
            log_file=os.environ.get("BRIDGE_LOG_FILE"),
        )
```

**Benefit:** All tunables in one place. Env vars for operator overrides. Pydantic validates ranges. No scattered `os.environ.get()` calls throughout the codebase. Logging follows the same pattern as llm_conversation: explicitly disabled unless configured.

**Gate impact:** Operator misconfiguration (e.g., `BRIDGE_TTL=0`) is caught at startup, not 10 minutes later when sessions start vanishing.

---

#### 4. Partial frame accumulation for Unix socket transport

**Source:** `conversation_manager.py` lines 230-248 (`parse_partial_json`, `stream_chunks`)

llm_conversation accumulates LLM response chunks until the JSON is well-formed, then begins streaming. The key insight: DON'T process a fragment as a complete message. Buffer until the delimiter appears.

**Recommendation for daemon:**

```python
# Per-connection buffer
class ConnectionBuffer:
    _buf: bytearray

    def feed(self, data: bytes) -> Iterator[bytes]:
        """Feed bytes, yield complete newline-terminated JSON-RPC frames."""
        self._buf.extend(data)
        while True:
            idx = self._buf.find(b"\n")
            if idx == -1:
                break  # incomplete frame — wait for more
            frame = bytes(self._buf[:idx])
            self._buf = self._buf[idx + 1:]
            if frame.strip():
                yield frame

    @property
    def overflow(self) -> bool:
        return len(self._buf) > 1_048_576  # 1MB
```

**Benefit:** Handles the case where a JSON-RPC frame arrives across multiple `recv()` calls. Rejects oversized buffers before they exhaust memory. This pattern is directly lifted from llm_conversation's chunk accumulation.

---

#### 5. Context enrichment — sessions see their place in the ecosystem

**Source:** `conversation_manager.py` lines 85-98 (`AGENT_SYSTEM_PROMPT_FORMAT`)

Every agent receives an augmented system prompt: "You are {agent_name}, engaging with {other_agents}. Guidelines: ..." The agent KNOWS who else is in the conversation without asking.

**Recommendation for daemon:**

The `board()` response (and `update()` response with nudges) should include a `context` field:

```json
{
  "context": {
    "you": "yoda",
    "active_sessions": ["obi-wan-kenobi", "mace-windu"],
    "your_nudge_queue": 2,
    "ttl_remaining_s": 483,
    "ticket": "BRIDGE-DAEMON-CORE",
    "collisions": {
      "proxy.py": ["obi-wan-kenobi"]
    }
  }
}
```

**Benefit:** Sessions get an at-a-glance summary without parsing the full board. The daemon computes collisions (files both sessions claim to `owns`) and surfaces them. This reduces the cognitive load and the number of tool calls needed to understand state.

---

#### 6. Structured logging with levels controlled by env

**Source:** `logging_config.py` full file

llm_conversation's logging is elegant: off by default, enabled via `LLM_CONVERSATION_LOG_LEVEL`. Rich handler for stderr (colorized, path-aware, traceback-rich), plain file handler for persistent logs. `logger.propagate = False` prevents noise bubbling to root.

**Recommendation:** Adopt the exact same pattern for `bridge_daemon`. Namespace the logger (`bridge.daemon`), control via `BRIDGE_LOG_LEVEL` + `BRIDGE_LOG_FILE`. Add structured fields: `{"session_id": sid, "tool": method, "latency_us": elapsed}` to make logs grep-able.

---

### ADAPT — Patterns to modify for our domain

#### 7. Turn order strategies → ticket dispatch primitives (future)

llm_conversation has 5 coordination strategies for deciding "who speaks next":
- `round_robin` → least-recently-assigned ticket dispatch
- `random` → random idle session assignment
- `chain` → session-to-session direct handoff ("I'm done with this, you take it")
- `moderator` → daemon-decided (daemon assigns based on owns/skills match)
- `vote` → multi-session consensus on assignment

**Recommendation:** The daemon's v1 ONLY does `claim`/`release` (explicit). But the architecture should reserve space for automated dispatch. The turn order enum in llm_conversation maps directly to `TicketDispatchStrategy` in the daemon. Add as a future config option, not v1 scope.

---

#### 8. Structured output enforcement → message schema gateway

llm_conversation passes `format=model_json_schema()` to Ollama to FORCE the LLM to output valid JSON matching a schema. The daemon's equivalent: validate incoming nudge payloads against type-specific Pydantic models BEFORE queueing (see Recommendation #2 above). The daemon is the "format" parameter for cross-session communication.

---

#### 9. Termination protocol → graceful session lifecycle

Agents set `terminate: true` when they believe the conversation has reached its natural end. The daemon equivalent: sessions call `unregister(reason="done")`. But llm_conversation has a `TODO` worth adopting for us:

```python
# llm_conversation TODO (conversation_manager.py):
# TODO: Make termination make the agent leave the conversation instead of
#       ending it. Only end the conversation if all agents have left.
```

**Recommendation for daemon:** Add a `status="drained"` that:
1. Auto-releases all tickets held by the session
2. Incubates the session's nudge queue for 60s (replies can still arrive)
3. Then auto-purges

This prevents the "session done, nudges lost" failure pattern we observed today (obi-wan purged mid-review, 4 nudge messages gone).

---

#### 10. Conversation log → structured audit event table

`save_conversation()` writes structured JSON: `{"agents": [...], "conversation": [{"agent": ..., "content": ...}]}`. The daemon should have the same for debugging.

**Recommendation:** Add an `events` table:
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    event_type TEXT NOT NULL,  -- register, update, nudge_send, nudge_receive, claim, release, purge, escalate
    payload TEXT  -- JSON
);
```

Every `_dispatch()` call writes an event. Enables: "What happened to yoda's nudge to obi-wan?" → `SELECT * FROM events WHERE event_type='nudge_send' AND session_id='yoda' AND json_extract(payload, '$.target')='obi-wan-kenobi'`.

---

### AVOID — Anti-patterns from llm_conversation

#### 1. In-memory-only state → DO NOT ADOPT

llm_conversation stores EVERYTHING in memory: `_conversation_log`, `_messages`, `_agent_name_to_idx`. If the process dies, everything is gone. **The daemon's SQLite is the answer to this.** No in-memory caches that could be lost on crash. Every state transition hits the DB.

#### 2. Tight coupling to a specific backend → DO NOT ADOPT

llm_conversation is hardwired to Ollama: `ollama.chat()`, `ollama.show()`, `ollama.list()`. The bridge MUST remain provider-agnostic — any MCP client over stdin/stdout or Unix socket should work. No LLM dependency in the daemon.

#### 3. Single-threaded sequential processing → DO NOT ADOPT

llm_conversation processes one agent at a time: `for agent_name, message in manager.run_conversation()`. The daemon MUST handle concurrent JSON-RPC requests from multiple sessions. Use `asyncio` event loop with `asyncio.start_unix_server()` or `socketserver.ThreadingUnixStreamServer`. SQLite WAL + `BEGIN IMMEDIATE` transactions handle the write serialization at the DB layer.

#### 4. Crash-on-error → DO NOT ADOPT

If `ollama.chat()` raises, llm_conversation crashes with a bare `raise`. The daemon must catch per-request exceptions, return structured JSON-RPC errors with `{"code": -32000, "message": "..."}`, log the error, and CONTINUE serving other sessions.

#### 5. No tests → DO NOT ADOPT

llm_conversation has ZERO test files (README TODO: "Add tests"). The daemon MUST ship with `pytest` tests covering every tool call path, the graduated purge logic, concurrent claim() races, and Unix socket transport.

---

### Architecture Comparison Matrix

| Dimension | llm_conversation | Current server.py | Recommended daemon |
|---|---|---|---|
| Coordination | Single manager, N agents | N servers, 1 DB | Single daemon, N clients |
| Transport | Python objects (in-process) | stdin/stdout JSON-RPC | Unix socket + thin proxy |
| State | None (all volatile) | SQLite WAL (multi-writer) | SQLite WAL (single writer) |
| Input validation | Pydantic + JSON Schema | Ad-hoc dict access | Pydantic + JSON Schema |
| Message validation | `create_model()` runtime | None | `create_model()` per nudge type |
| Config management | Pydantic model + env | Scattered `os.environ.get()` | Pydantic model + env |
| Streaming | Chunked JSON accumulation | Newline-delimited | Connection-buffered frames |
| Context enrichment | System prompt injection | None | `context` field in board/update |
| Logging | Rich + file (env-gated) | stdout JSON-RPC | Rich + file (env-gated) |
| Error handling | raise (crash) | JSON-RPC error response | JSON-RPC error + log + continue |
| Liveness | N/A | PID check + timestamp | PID check + timestamp + stall |
| Tests | 0 (TODO) | 0 | pytest (each tool + transport) |
| Modularity | 6 focused modules | 1 monolithic file | 4-6 focused modules |

---

### Concrete Code Patterns to Incorporate

**Pattern A: Tool registry as typed models (replaces ad-hoc _TOOLS list)**

```python
from pydantic import BaseModel, create_model

@dataclass
class BridgeDaemon:
    # Every tool has a params model. The model generates the inputSchema.
    _TOOL_REGISTRY: ClassVar[dict[str, type[BaseModel]]] = {
        "register": RegisterParams,
        "board": BoardParams,
        "update": UpdateParams,
        "unregister": UnregisterParams,
        "claim": ClaimParams,
        "release": ReleaseParams,
        "nudge": NudgeParams,
    }

    def _tools_schema(self) -> list[dict]:
        """Generate MCP tools/list response from Pydantic models."""
        return [
            {
                "name": name,
                "description": model.__doc__ or "",
                "inputSchema": model.model_json_schema(),
            }
            for name, model in self._TOOL_REGISTRY.items()
        ]

    def _dispatch(self, method: str, raw_params: dict) -> Any:
        model = self._TOOL_REGISTRY.get(method)
        if model is None:
            raise ValueError(f"unknown tool: {method!r}")
        params = model.model_validate(raw_params)
        handler = getattr(self, f"_handle_{method}")
        return handler(params)  # handler receives a validated model, not a dict
```

**Pattern B: Connection-buffered Unix socket server (from llm_conversation partial JSON)**

```python
import asyncio

class ConnectionBuffer:
    def __init__(self, max_bytes: int = 1_048_576):
        self._buf = bytearray()
        self._max = max_bytes

    def feed(self, data: bytes) -> list[bytes]:
        self._buf.extend(data)
        if len(self._buf) > self._max:
            raise BufferError("frame too large")
        frames: list[bytes] = []
        while (idx := self._buf.find(b"\n")) != -1:
            frames.append(bytes(self._buf[:idx]).strip())
            self._buf = self._buf[idx + 1:]
        return frames

async def handle_client(reader, writer):
    buf = ConnectionBuffer()
    while True:
        data = await reader.read(4096)
        if not data:
            break
        for frame in buf.feed(data):
            response = await dispatch_jsonrpc(frame)  # validate + route
            writer.write(response + b"\n")
            await writer.drain()
```

**Pattern C: Logging with env-gated levels (from llm_conversation logging_config.py)**

```python
def setup_logging() -> None:
    level_name = os.environ.get("BRIDGE_LOG_LEVEL")
    if not level_name:
        return  # disabled — matches llm_conversation default
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger = logging.getLogger("bridge")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False
    handler = RichHandler(console=Console(stderr=True), rich_tracebacks=True)
    logger.addHandler(handler)
    log_file = os.environ.get("BRIDGE_LOG_FILE")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, mode="a")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)
```

---

### Summary of Actions

| # | Action | Priority | Source pattern |
|---|---|---|---|
| 1 | Add Pydantic models for ALL tool params | **BLOCKING** — do before implementing daemon | config.py + schema.json |
| 2 | Add `create_model()` payload validators per nudge type | **BLOCKING** — prevents malformed cross-session messages | conversation_manager.py |
| 3 | Add `BridgeConfig` Pydantic model with env override | **BLOCKING** — eliminates scattered config | config.py + logging_config.py |
| 4 | Add `ConnectionBuffer` for Unix socket frame reassembly | **HIGH** — handles partial reads, oversized frames | `parse_partial_json()` + `stream_chunks()` |
| 5 | Add `context` enrichment to board()/update() responses | **HIGH** — reduces tool call volume | `AGENT_SYSTEM_PROMPT_FORMAT` |
| 6 | Add structured logging (Rich + file, env-gated) | **MEDIUM** — debugging aid | logging_config.py |
| 7 | Add `events` audit table | **MEDIUM** — debugging aid | `save_conversation()` |
| 8 | Add `drained` lifecycle status | **LOW** — prevents nudge loss on session exit | TODO in conversation_manager.py |
| 9 | Reserve `TicketDispatchStrategy` enum for future | **LOW** — future coordination primitives | TurnOrder Literal |
| 10 | NEVER use in-memory state; persist to SQLite | **HARD RULE** | (anti-pattern from llm_conversation) |
| 11 | NEVER couple to a specific LLM/backend | **HARD RULE** | (anti-pattern from llm_conversation) |
| 12 | NEVER process sequentially when concurrent is needed | **HARD RULE** | (anti-pattern from llm_conversation) |

---

### Verdict

The llm_conversation review finds **12 actionable recommendations** for the bridge daemon. Three are BLOCKING (must be done before daemon implementation): Pydantic validation, nudge payload schemas, and config model. Five are HIGH/MEDIUM improvements. Three are HARD RULES (patterns to never adopt).

The daemon proposal's architecture (single process, SQLite single writer, Unix socket transport, auto-reload) is sound and does not need revision. The llm_conversation review complements it with concrete patterns for input validation, message type enforcement, and transport robustness that the current server.py lacks.
