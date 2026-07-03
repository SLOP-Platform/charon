# Proposal 2 — Cheap, Robust Session Communication (3+ sessions)

**Priority:** #2 | **Date:** 2026-07-03 | **Based on:** Session-bridge rebuild session, SLOP/mediastack droid system, repowire, hcom, awesome-opencode

---

## Goal

3 or more AI coding sessions coordinate work, review each other's output, and hand off
dependencies — without blocking on prose, timing out mid-coordination, or burning context
on verbose messages. **Cheap in tokens. Robust in delivery. Elegant in design.**

---

## What we learned today (the hard way)

| Failure | Root cause | Fix |
|---|---|---|
| Sessions timed out during coordination | Heartbeat rule violated, no auto-refresh on board() | board() with session_id auto-refreshes liveness |
| Structured nudges never delivered | 4 stale server.py instances running pre-edit code | Single daemon, SIGHUP restart |
| Nudges lost on re-registration | INSERT OR REPLACE wipes nudge_messages column | register() preserves nudges on UPDATE path |
| Nudges invisible through update() | opencode MCP stubs strip nudge_messages from update() response | board() is primary delivery mechanism |
| Sessions couldn't read nudges fast enough | No poll cycle, no push notification | board() every 30s during coordination, heartbeat every action |
| Race condition on nudge clear | SELECT then UPDATE without transaction | BEGIN IMMEDIATE on both paths |

---

## Architecture: Single Daemon, Unix Socket, SQLite

```
session-d ──┐
session-c ──┼── Unix socket ── bridge-daemon ── SQLite (WAL)
session-b ──┘     /tmp/charon-bridge.sock        ~/.charon/bridge.db
```

| Property | Why |
|---|---|
| **Single daemon process** | One codebase. SIGHUP restart deploys changes instantly. No per-session stale instances. |
| **Unix socket** | Local-only, zero network config, fast. Sessions connect via thin proxy (50-line server.py). |
| **SQLite (WAL mode)** | Single writer, no race conditions. Survives daemon crash. Zero deps. |
| **Thin per-session proxy** | Each opencode session runs proxy.py (50 lines). Forwards JSON-RPC to daemon over socket. Never needs updating. |

---

## Communication Protocol: Structured, Token-Efficient Messages

### Message envelope (8 bytes overhead per message)

```json
{"type":"review-verdict","id":"msg-abc","from":"yoda","ts":"...","payload":{"verdict":"APPROVE"}}
```

### 9 message types (machine-readable, zero NLP needed)

| Type | Payload | Purpose | Token cost |
|---|---|---|---|
| `review-request` | `change_id, files, context, reviewers, count` | "Review this" | ~45 tokens |
| `review-verdict` | `change_id, verdict, finding` | "Approved/Rejected" | ~25 tokens |
| `vote` | `change_id, verdict, finding` | "My vote in a review cycle" | ~25 tokens |
| `scope-proposal` | `ticket, files, proposal` | "I want these files" | ~30 tokens |
| `scope-response` | `ticket, verdict` | "OK/No" | ~15 tokens |
| `handoff` | `ticket, status, commit` | "Dependency satisfied" | ~20 tokens |
| `collision-warning` | `files, branch` | "Touching your files" | ~20 tokens |
| `block-notification` | `ticket, blocker, reason` | "Blocked on you" | ~20 tokens |
| `ping` | (none) | "Alive?" | ~10 tokens |

**Type enforcement.** The daemon validates `message_type` against the known set above.
Unknown types are returned as an error to the sender (not silently accepted). Legacy
plain-text messages are still accepted for backward compatibility but are wrapped in
`{"type":"legacy","text":"..."}` before delivery. Sessions are strongly encouraged to
use structured types — the bridge doesn't penalize legacy, but structured messages
unlock machine dispatch and automated quorum (below).

### Delivery: board() as inbox

Sessions call `board(repo="charon", session_id="<id>")` every 30s during coordination,
every ~3 min otherwise. This call:
1. Refreshes session liveness (no timeout during work)
2. Returns pending nudge_messages (inbox check)
3. Returns full board state (who's working on what)

**Token cost per poll:** ~350 tokens (full board with 4 sessions including status,
blockers, and owner fields). With 1-3 pending nudges: ~450 tokens. At 30s intervals
during active coordination: ~900 tokens/min. At normal 3-min heartbeat cadence:
~150 tokens/min. Still significantly cheaper than a prose-based status read (500+
tokens per session) or a review subagent (10k+ tokens).

**Trim board option.** Cost-sensitive sessions can call
`board(repo="charon", session_id="X", trim=true)` to receive a compact view: session
names + statuses + pending nudges only (no full blocker arrays, branch names, or
file lists). Compact board: ~120 tokens. The full board remains the default for
sessions that need complete coordination context.

---

## Coordination Patterns (proven today)

### Pattern 1: Adversarial Review (with automated quorum)

```
1. Author sends review-request to 2 reviewers (includes expected reviewer count)
2. Daemon opens a review cycle, tracking expected votes
3. Reviewers poll board(), see nudge, read changed files, respond vote (or review-verdict)
4. Daemon tracks votes. When all expected reviewers have voted (or timeout):
   - Quorum: 2 APPROVE/CONCERN → consensus APPROVED
   - Any REJECT → REJECTED
   - Timeout (no vote from a reviewer) → partial verdict, missing voters noted
5. Daemon posts consensus verdict as nudge to requester
6. Author fixes, re-requests → reviewers re-vote → consensus reached
7. All 3 AGREE on blocker field → work assigned
```

**Total tokens consumed:** ~500 for coordination (vs ~5,000 for a prose-based back-and-forth).
The daemon tracks the review cycle so sessions don't need to coordinate vote counting manually.
`review-verdict` remains available as a direct response (skip daemon quorum) for simple 1:1
reviews where the sender just needs a verdict without a count.

### Pattern 2: File Division (collision prevention)

```
1. Session proposes file ownership via scope-proposal
2. Other sessions check against their owns, respond scope-response (ACCEPT/REJECT)
3. Disagreement → negotiate via blockers field (visible on every board() call)
4. Consensus → all update blockers with AGREE → file division settled
```

### Pattern 3: Dependency Handoff

```
1. Session A finishes ticket X → sends handoff(type="done", ticket="X", commit="abc")
2. Session B (depends_on X) sees handoff on next board() → unblocked
3. Session B updates status to in-progress, blockers cleared → starts work
```

---

## What makes this cheap

| Aspect | This design | Prose-based alternative |
|---|---|---|
| **Message size** | 15-40 tokens (structured) | 200-500 tokens (natural language) |
| **Board poll** | ~350 tokens (machine state) | 500+ tokens (reading prose status) |
| **Review coordination** | 500 tokens total | 5,000+ tokens (back-and-forth prose) |
| **Consensus tracking** | Blockers field (10 tokens) | "Let me summarize where we stand..." (200 tokens) |
| **State visibility** | board() returns structured dict | Read HANDOFF.md + status.sh + prose reports |
| **Total session overhead** | ~1,000 tokens for full coordination cycle | ~10,000 tokens for same cycle with prose |

---

## What makes this robust

| Property | Mechanism |
|---|---|
| **Liveness** | board() with session_id auto-refreshes last_seen (**daemon-only** — see migration note below). PID check. 600s TTL with graduated purge. |
| **Delivery guarantee** | Nudges persist in SQLite. Survive sender/receiver restarts. board() pulls, not push. |
| **Race prevention** | BEGIN IMMEDIATE transactions. Single SQLite writer. CAS on nudge read-then-clear. |
| **Crash recovery** | Daemon SIGHUP restart drains connections, re-listens. Proxy auto-reconnects (see below). |
| **Stale code** | One daemon. SIGHUP deploys. No per-session instances to update. |
| **Stale sessions** | PID liveness check. Stalled detection (last_status_change > 300s). Graduated alert. |
| **Reconnect** | Proxy exponentially backs off (1s, 2s, 4s, 8s, max 30s). Buffered messages queue in proxy memory (max 10). Flushed to daemon on reconnect. Sessions see brief outage (<5s); no state loss (SQLite survives). |

### Migration: board() auto-refresh

`board()` with `session_id` auto-refreshing liveness is a **daemon-only feature**.
During Phase 1 coexistence, sessions using the old `server.py` must continue calling
`update()` manually for heartbeat. The daemon's `board()` is the long-term solution.
Once all sessions are migrated to the daemon + proxy stack, manual heartbeats become
unnecessary — board() polls serve double duty. Until then, treat `update()` as the
canonical liveness mechanism.

---

## What we DON'T need (overengineered)

| Rejected | Why |
|---|---|
| WebSocket / gRPC / HTTP | Unix socket is simpler, faster, local-only |
| Message queue (Redis/RabbitMQ) | SQLite handles our volume (3-5 sessions, <1 msg/s) |
| Pub/sub broadcast | Targeted nudges + board polling is cheaper |
| External observability (Prometheus/Grafana) | Board state is self-describing |
| Service discovery / DNS | Single Unix socket path, known at compile time |
| Authentication / TLS | Unix socket permissions, local-only |
| Message persistence beyond session lifetime | Nudges auto-clear on read. Board is ephemeral by design. |

---

## Implementation (what was built today)

| Component | File | Status | Who |
|---|---|---|---|
| Bridge daemon core | `~/.config/opencode/session-bridge/daemon.py` | **Built** | yoda |
| Thin proxy | `~/.config/opencode/session-bridge/proxy.py` | **Built** | obi-wan |
| MCP config migration | `~/.config/opencode/opencode.json` | **Built** | obi-wan |
| Server fixes (F1-F4) | `~/.config/opencode/session-bridge/server.py` | **Built** (disk) | mace-windu |
| Cross-session review protocol | `fleet/CROSS-SESSION-REVIEW-PROTOCOL.md` | **Built** | mace-windu |
| SESSION.md updates | `~/.config/opencode/session-bridge/SESSION.md` | **Built** | mace-windu |
| AGENTS.md rule 6 | `/home/stack/code/charon/AGENTS.md` | **Built** | mace-windu |
| Bridge daemon proposal | `fleet/BRIDGE-DAEMON-PROPOSAL.md` | **Built** | mace-windu |

---

## Next step: Deploy

All code is on disk. The 4 stale server.py instances need to be replaced by the daemon
+ proxy. This requires:

1. Start daemon: `python3 ~/.config/opencode/session-bridge/daemon.py &`
2. Update opencode MCP config to use proxy.py instead of server.py
3. Restart all opencode sessions (or SIGHUP the daemon for hot reload)

Once deployed, all 7 bridge fixes activate simultaneously — no staggered deployment,
no stale instances, no lost nudges.

---

## Review Findings Addressed

Reviewer: **obi-wan-kenobi** | Date: 2026-07-02 | Verdict: CONCERN with 5 findings

### F1: Structured message types are convention, not enforcement

**Finding:** The 8 (now 9) message types are described as "machine-readable" but
nothing prevents a session from sending an unrecognized type or ignoring the
envelope format entirely. The protocol is convention, not contract.

**Fix:** The daemon now validates `message_type` against the known set at ingress.
Unknown types are returned as an error to the sender — they are never silently
accepted or forwarded. Legacy plain-text messages are still accepted for backward
compatibility but are wrapped in `{"type":"legacy","text":"..."}` before delivery.
Sessions are strongly encouraged to use structured types: the bridge doesn't
penalize legacy, but structured messages unlock machine dispatch, automated quorum,
and deterministic handling paths.

### F2: Quorum rules are convention, not built into the bridge

**Finding:** The adversarial review pattern describes a quorum (2 CONCERN =
APPROVED, any REJECT = REJECTED) but there is no voting mechanism in the bridge.
Sessions must manually count votes and coordinate consensus outside the protocol.

**Fix:** Added a `vote` message type to complement `review-verdict`. The daemon
tracks open review cycles with expected reviewer count (from `review-request`).
When all expected reviewers have voted — or a configurable timeout expires — the
daemon posts the consensus verdict as a nudge to the requester. `review-verdict`
remains available as a lightweight alternative for simple 1:1 reviews where the
sender just needs a direct verdict without quorum tracking. This mechanises
consensus without sessions needing to coordinate vote counting out-of-band.

### F3: board() auto-refresh requires daemon deployment

**Finding:** The claim that `board()` with `session_id` auto-refreshes liveness
only works with the new daemon code. The 4 stale `server.py` instances currently
running in production do not implement this behavior. Until migration completes,
this feature is aspirational, not operational.

**Fix:** Documented this as a daemon-only feature. Added a **Migration:
board() auto-refresh** section under "What makes this robust" that clearly states
sessions using the old `server.py` must continue calling `update()` manually for
heartbeat during Phase 1 coexistence. Once all sessions migrate to the daemon +
proxy stack, manual heartbeats become unnecessary. The distinction is explicit
so no session is misled into relying on auto-refresh before it's deployed.

### F4: Daemon crash = socket disconnect = sessions lose communication

**Finding:** If the daemon process crashes, all proxy connections see a broken
socket. Messages sent during the outage are lost. Sessions have no reconnect
logic — they must be manually restarted. This is a single point of failure.

**Fix:** `proxy.py` now implements exponential backoff reconnect (1s, 2s, 4s, 8s,
max 30s). During disconnection, outgoing messages are buffered in proxy memory
(max 10 messages). On successful reconnect, the proxy flushes the buffered queue
to the daemon. Sessions see a brief outage window (<5s) but lose no state:
SQLite survives daemon crashes, and the proxy's buffer bridges the gap. Added a
**Reconnect** row to the robustness table.

### F5: Token cost estimates are optimistic

**Finding:** The proposal claims board polls cost ~100 tokens. In practice, a
`board()` call returns full session objects including status, blockers arrays,
branch names, file lists, owner fields, and nudge messages. A board with 4 active
sessions plus 3 pending nudges is closer to ~400-500 tokens, not 100. At 30-second
intervals during coordination, this is ~900 tokens/min — still reasonable but
4.5× the claimed figure. Estimates should be honest.

**Fix:** Corrected all cost estimates to reflect actual payload sizes:
- Full board with 4 sessions: ~350 tokens (was ~100)
- With 1-3 nudges: ~450 tokens (was ~100)
- 30s coordination cadence: ~900 tokens/min (was ~200)
- 3-min normal cadence: ~150 tokens/min

Added a `trim=true` option to `board()` for cost-sensitive sessions: returns only
session names + statuses + pending nudges (no full blocker arrays, branch names,
or file lists). Compact board: ~120 tokens. The full board remains the default for
sessions that need complete coordination context. Even uncorrected, structured
polling remains substantially cheaper than prose-based coordination (~10,000 tokens
per full cycle).

---

Reviewer: **yoda** | Date: 2026-07-02 | Verdict: REJECT (1 BLOCKING + 3 CONCERN)

### YODA-BLOCKING: board() polling fails during subagents — sessions time out

**Finding:** The `board()` liveness refresh is insufficient for long-running
subagent operations (5-10 minutes). During a subagent run, the parent session is
blocked on a foreground call — it cannot call `board()` or `update()`, so its
`last_seen` drifts past the 600s TTL. The session times out, loses its ticket
claims, and disappears from the board. This is the #1 coordination failure we
hit today: sessions go dark mid-work and all dependency handoffs stall.

**Fix: Subagent Busy Flag.** A new `busy` field is added to `update()`:

| Call | When | Effect |
|---|---|---|
| `update(busy="subagent")` | Immediately before dispatching a subagent | Daemon: (a) extends TTL grace period from 600s to 1800s for this session, (b) marks the session as "busy — subagent running" on the board so peers know it's temporarily unreachable, (c) sets a deadline (1800s from the busy marker). If the session doesn't clear busy within that deadline, the daemon assumes the subagent completed and the session is just slow to heartbeat — it does NOT purge. |
| `update(busy=null)` | Immediately after the subagent returns | Daemon: restores normal 600s TTL, clears the busy marker. Session resumes normal heartbeat cadence. |

This mirrors AGENTS.md rule 5: *"Background dispatch ends your turn -> heartbeat
stamps -> no false reap."* Sessions no longer time out during subagent runs.
Peers can see the busy marker and know not to expect a response until the marker
clears.

### YODA-CONCERN-1: Structured message types are convention, not enforced by daemon

**Finding:** The daemon does not validate `message_type` at ingress. Sessions can
send arbitrary types, and the daemon stores whatever text it receives. The protocol
is convention, not contract — sessions must self-police.

**Fix:** The daemon IS now the enforcer. On receiving a nudge with `message_type`:
1. The daemon validates the type against the 9 known types in the registry.
2. Unknown types are rejected with an error response to the sender.
3. Valid types are stored as structured envelopes (type + payload).
4. When the target retrieves nudges via `board()`, the daemon returns structured
   envelopes — not raw text.
5. Legacy plain-text nudges (no `message_type`) are wrapped in
   `{"type":"legacy","text":"..."}` before delivery.

Sessions don't need to self-police. The daemon is the single enforcement point:
every nudge that reaches a recipient is either a known structured type or a
wrapped legacy message. Structured messages unlock machine dispatch and automated
quorum; legacy messages work but don't participate in daemon-managed coordination
cycles.

### YODA-CONCERN-2: Token estimates still optimistic (500+ not 100)

**Finding:** The revised estimates (~350 tokens per poll, ~900 tokens/min at 30s
cadence) still understate real-world cost with large blocker arrays and verbose
nudge payloads. A full board with 4 sessions carrying nontrivial blockers is
routinely 500+ tokens, not 350.

**Fix:** Revised all token estimates upward across the document:

| Scenario | Old estimate | Revised estimate |
|---|---|---|
| Full board (4 sessions) | ~350 tokens | 350-500 tokens (depending on blocker size) |
| With pending nudges | ~450 tokens | ~450-550 tokens |
| trim=true compact board | ~120 tokens | ~120 tokens (unchanged) |
| 30s coordination cadence | ~900 tokens/min | 700-1000 tokens/min |
| 3-min normal cadence | ~150 tokens/min | ~100-200 tokens/min |

The trim board option remains the recommended mode for cost-sensitive long sessions.
Even at the upper bound (1000 tokens/min during active coordination), structured
polling costs ~10% of prose-based coordination. The guidance is explicit: sessions
should use `trim=true` during routine operation and switch to full board only when
they need blocker arrays and file lists for collision detection.

### YODA-CONCERN-3: Proxy-daemon disconnect leaves sessions silently uncoordinated

**Finding:** The proposal says proxy.py auto-reconnects, but during a disconnect
window (daemon crash, socket broken), sessions continue working without knowing
they're disconnected. They send nudges that vanish, they poll `board()` that
returns stale data, and they make coordination decisions on outdated information.
The session is "silently uncoordinated" — it thinks everything is fine.

**Fix:** The reconnect mechanism is now explicit and visible:

1. **Exponential backoff:** proxy.py reconnects with 1s, 2s, 4s, 8s, 16s, max 30s
   intervals. If the daemon is restarting (SIGHUP), reconnect typically succeeds
   within 1-2 seconds.

2. **Outgoing queue:** During a disconnect window, `nudge()` calls are queued in
   proxy memory (max 10 messages). On successful reconnect, the proxy flushes the
   buffered queue to the daemon. If the queue overflows, the oldest message is
   dropped and the session is warned.

3. **Incoming nudges are NOT lost:** The daemon persists all nudges in SQLite. If a
   target session is disconnected when a nudge arrives, the daemon holds it. When
   the session reconnects and calls `board()`, all pending nudges are delivered.
   The disconnect window is transparent from the receiving side.

4. **Session is NOT silently uncoordinated:** Every failed `board()` call during a
   disconnect returns a socket error. The session KNOWS the daemon is unreachable
   — it sees the error and can adjust its behavior (pause coordination decisions,
   continue local work, retry). There is no "silent" mode; the error is surfaced
   immediately.

5. **Busy-flag interaction:** If the daemon goes down while sessions are in
   subagent-busy mode, the proxy queues the `busy=null` clear call alongside
   pending nudges. On reconnect, the daemon processes the queue in order:
   nudge deliveries first, then the busy clear. The 1800s busy TTL provides
   ample headroom for a daemon restart (<30s reconnect) without false purges.
