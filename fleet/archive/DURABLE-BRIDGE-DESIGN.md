> ARCHIVED 2026-07-08 — superseded by DURABLE-BRIDGE-DESIGN-v3.md (v1 in the v1->v2->v3 chain)

# ADR: Durable, Cross-Host, Push-Notifying Session Bridge

**Status:** PROPOSED (design-only — no code, no infra change)
**Date:** 2026-07-06
**Scope:** BUILD-RIG infra (the fleet session-bridge). NOT the Charon product.
**Author:** design sub-session (architect)
**Supersedes/extends:** BRIDGE-DAEMON-PROPOSAL.md, PROPOSAL-2-SESSION-COMMUNICATION.md
**Relationship to ADR-0008 / obol:** Orthogonal. obol is the *product-side* portable
orchestration store (ships in Charon). This bridge is *rig-only* transport for coordinating
live build sessions and MUST NOT be coupled to it or leak into the product (see memory:
product-vs-build-rig-boundary). One line, no more.

---

## 1. Context

The current session-bridge (`~/.config/opencode/session-bridge/daemon.py` + `proxy.py`,
wired into opencode via the `session-bridge` local-MCP block in `opencode.json`) is a
single-process **AF_UNIX socket daemon** at `~/.charon/bridge.sock` (mode 0600) backed by
**SQLite-WAL** at `~/.charon/session-bridge.db`. It exposes 7 tools —
`register / board / update / unregister / claim / release / nudge` — with repo separation
(charon vs mediastack), the Jedi/droid naming convention (Grand Master names reserved for
managers), and typed nudge messages. It works well **on one host**.

Two structural defects remain, and a third has emerged:

- **DEFECT 1 — Liveness is model-driven.** A 600s TTL reaps any session that stops
  heartbeating, and heartbeats depend on the LLM remembering to call `update()`/`board()`
  mid-work. It forgets during long subagent runs → false reaps. The `busy` flag and
  graduated-purge patched the symptom, not the cause.
- **DEFECT 2 — Pull-only.** Nothing wakes a session when a message targets it; it must poll
  `board()`. A nudge sitting in the queue is invisible until the model next chooses to look.
- **DEFECT 3 — Local-only.** Zero network bind. A session on **BB-8 / 4-LOM (10.0.1.60)** —
  or any future host, or the shared self-hosted runner — cannot see this board at all.

The harness gives us a primitive that kills DEFECT 1 and 2 together: **a backgrounded Bash
process re-invokes its owning session when it exits.** So a session can launch one background
**watcher** that BLOCKS on the shared store and EXITS the instant a message targets it → the
harness wakes the session → it reads the message → relaunches the watcher. Because the watcher
is a live PID/connection, **presence = watcher-alive**, with zero model involvement.

DEFECT 3 forces the transport question. The operator prefers the simplest tooling that is
robustly cross-host (memory: operator-prefers-simplest-tooling); heavy infra must earn its
place.

---

## 2. Decision (summary)

1. **Transport: SSH-tunnelled Unix socket (Option C).** Keep the daemon exactly as it is —
   an AF_UNIX + SQLite-WAL process, no network bind. Remote hosts reach it through an
   OpenSSH Unix-socket forward over the **already-working `~/.ssh/4lom` key**. The SSH key
   *is* the auth and the encryption; no new token, no `0.0.0.0` bind, nothing secret to
   commit.
2. **Daemon host: the always-on box (4-LOM / BB-8, 10.0.1.60).** It already runs 24/7 as the
   gateway host; the dev WSL box sleeps. SPOF mitigated by `systemd --user Restart=always`
   + client-side `autossh` tunnels + proxy reconnect-with-backoff.
3. **Push: server-side long-poll (`poll_wait`) over that socket/tunnel.** Add ONE blocking
   RPC to the daemon. The watcher calls it; it returns the instant a nudge is queued for that
   session (or on timeout). Return → watcher bash exits → harness wakes the session.
4. **Liveness: connection-derived.** While a session's `poll_wait` connection is open, the
   session is PRESENT — independent of the model. Disconnect starts a short grace timer
   (~90s); the 600s model-heartbeat TTL is demoted to a legacy fallback for poll-only clients.
5. **Security: SSH-key-gated, socket stays 0600, no network port.** All host/port/key/socket
   config lives in a **gitignored** `~/.charon/bridge-hosts.env` (same pattern as the existing
   uncommitted `~/.charon/secrets.json`). Nothing personal ever enters the public repos.
6. **Back-compat: the 7 tool interfaces are byte-for-byte unchanged.** Only the transport
   under `proxy.py` changes. Phased rollout, each phase independently revertible.
7. **Auto-bootstrap: harness hooks + cron, never the model.** A `SessionStart` hook brings up
   the tunnel and launches the watcher; a `Stop` hook re-arms it; cron heals the tunnel/daemon.
8. **Blast radius: graceful degradation to today's single-host behavior.** Unset `BRIDGE_HOST`
   → proxy falls back to the local socket → exactly the current product-safe state.

---

## 3. Options considered (transport) — with tradeoffs

The core question is DEFECT 3: how does a session on another host reach the board?

### Option A — Small HTTP/TCP daemon on the LAN, SQLite-WAL, long-poll/SSE
Bind the daemon on a LAN interface (e.g. `10.0.1.x:8378`), sessions long-poll or SSE for push.
- **Pro:** SSE is a clean native push; browser/dashboard-friendly later; language-agnostic.
- **Con:** Now a **network-reachable service** → must invent + rotate a bearer token, must
  bind a specific LAN IP (never `0.0.0.0`), must firewall it, must not commit the token/IP.
  Rewrites the transport layer (HTTP server, framing) that already works over Unix sockets.
  More moving parts, larger attack surface. Fails the simplicity bias unless we need browsers.

### Option B — SQLite on a shared network FS (NFS / SSHFS)
Put `session-bridge.db` on a mount every host sees.
- **Pro:** Zero daemon changes; "just a shared file."
- **Con:** **Rejected.** SQLite's locking is documented-unsafe over NFS/SSHFS — POSIX advisory
  locks are unreliable across the network, WAL shared-memory (`-shm`) is not coherent across
  hosts, and concurrent writers corrupt the DB. This is the classic "don't put SQLite on a
  network share" footgun. It also breaks the single-writer invariant the daemon relies on.
  Non-starter for a coordination store whose whole job is atomic claims.

### Option C — SSH-tunnelled Unix socket  ✅ RECOMMENDED
Daemon stays AF_UNIX + SQLite-WAL, **single writer, unchanged**. Remote hosts run an SSH
Unix-socket forward (`ssh -N -L <local.sock>:<remote.sock> stack@10.0.1.60`, OpenSSH ≥6.7
supports UNIX-domain forwarding). `proxy.py` on the remote host dials the *local* end of the
tunnel; the daemon sees an ordinary local socket connection.
- **Pro:** Reuses the **entire working daemon** and the **already-in-daily-use `~/.ssh/4lom`
  access path**. SSH provides auth (key), encryption, and host identity for free — no token to
  mint or commit, no `0.0.0.0`, no new firewall rule. Single SQLite writer preserved (only the
  daemon touches the DB; everyone else is a socket client). Simplest robustly-cross-host option.
- **Con:** Tunnel liveness must be managed (solved by `autossh` + `systemd`). One extra hop of
  latency (~1ms LAN, negligible for <1 msg/s). SSH must be reachable host→host (already true).

### Option D — Broker (Redis / NATS / MQTT)
- **Pro:** Purpose-built pub/sub, native push, battle-tested.
- **Con:** **Rejected for v1.** A whole new always-on service + client library + auth + its own
  config-secret to keep out of the repo, to coordinate 3–6 sessions at <1 msg/s. Directly
  contradicts the simplicity bias (PROPOSAL-2 already ruled out Redis/RabbitMQ for volume).
  Revisit only if the fleet grows to dozens of hosts or needs fan-out broadcast.

### Recommendation & justification against the simplicity bias
**Option C.** It is the *only* option that adds cross-host reach **without adding a new
network service, a new secret to commit, or a rewrite** — it bolts onto infrastructure that
already exists and already works (the daemon, the SSH key). Option A is the fallback if a
web dashboard or non-SSH clients ever become a hard requirement; Option D if scale explodes.
B is unsafe at any size.

---

## 4. Where the daemon lives + SPOF

**Host: the always-on box — 4-LOM / BB-8 (10.0.1.60).** Rationale: it already runs 24/7 as
the gateway container host; the dev WSL box sleeps/reboots and is a poor SPOF anchor. Putting
the canonical DB where uptime is highest minimizes "the board is gone because my laptop slept."

**Single-point-of-failure implication:** if that box or the daemon is down, no host can
register/nudge/claim cross-host.

**Mitigations (layered):**
- `systemd --user` unit on the daemon host with `Restart=always` (+ `RestartSec=2`) — daemon
  crash self-heals in ~2s.
- Client-side `autossh` (or a `systemd` tunnel unit with `Restart=always`) keeps each host's
  tunnel up; drops reconnect automatically.
- `proxy.py` reconnect-with-backoff (already specced in PROPOSAL-2 F4: 1/2/4/8s… max 30s) so a
  brief daemon or tunnel blip is transparent to sessions.
- **Degrade, don't die:** if the tunnel is down, `proxy.py` returns a structured "bridge
  unreachable" error and the session continues *local* work; on the dev host it can even fall
  back to a local daemon for same-host coordination (unset `BRIDGE_HOST`).
- A cron healthcheck (see §7) restarts the tunnel/daemon if either is missing.

(Alternative considered: run the daemon on the dev host and have BB-8 tunnel *in*. Rejected —
anchors the SPOF on the least-reliable-uptime host.)

---

## 5. Push mechanism (concrete)

**Chosen: server-side long-poll via a new blocking `poll_wait` RPC** over the same
socket/tunnel. Rejected alternatives: SSE (needs the HTTP daemon of Option A); inotify over a
mount (needs Option B's unsafe shared FS, and inotify is unreliable over NFS/SSHFS).

### The `poll_wait` RPC (new — the only new tool, and it is watcher-facing, not model-facing)
`poll_wait(session_id, timeout_s)`:
- Registers the calling connection as a **waiter** for `session_id` in an in-memory
  `_waiters: dict[session_id, list[conn]]` on the daemon.
- Blocks (holds the socket open) until **either** a nudge is queued for that session **or**
  `timeout_s` (e.g. 55s, under the tunnel's keepalive) elapses.
- Returns `{woke: true, reason: "nudge"|"timeout"}`. It does **not** return the message body —
  the woken session reads it via the existing `board(session_id=...)`, so nudge semantics and
  the clear-on-read path are untouched.

### Daemon event-loop change
The daemon is already `selectors`-based and single-threaded. Integrate waiters into the loop:
- On `poll_wait`, add the connection to `_waiters[sid]` and do **not** reply yet.
- In the existing `nudge()` handler (and the auto-nudge path in `_purge_stale`), after the DB
  write, check `_waiters[target]`; if present, write the `poll_wait` reply to each waiting
  connection and drop them from the map.
- A 1s selector tick (already present) expires waiters past their `timeout_s`.
This keeps single-writer SQLite and adds no threads.

### Mapping message-arrival → clean process exit → session wake
1. Session start: harness hook launches `bridge-watch.sh <sid> &` (backgrounded Bash).
2. `bridge-watch.sh` opens one `poll_wait(<sid>, 55)` call through the proxy/tunnel and blocks.
3. A peer `nudge()`s `<sid>` → daemon wakes that waiter → `poll_wait` returns → the script's
   blocking call completes → **the backgrounded Bash process exits 0**.
4. The harness re-invokes the owning session on that background exit.
5. The session calls `board(session_id=<sid>)` (existing tool) → gets the queued nudge(s),
   dispatches per the typed-message table in SESSION.md.
6. The session (via a `Stop` hook, §7) re-launches `bridge-watch.sh` → back to step 2.
On a `timeout` return the script simply re-issues `poll_wait` (loop), so a live session with an
idle inbox holds a continuous presence connection without ever waking the model.

---

## 6. Durable liveness (replacing the 600s TTL)

**Presence = an open `poll_wait` connection**, tracked by the daemon per session (a
`connected` boolean + the waiter's socket, not the model's `last_seen`). Concretely:

- Watcher connects → daemon sets `connected=1`; session shows **live** on the board regardless
  of whether the model has called anything in minutes.
- Watcher disconnects (script died, tunnel dropped, host slept) → daemon sets `connected=0`,
  stamps `disconnected_at`, and starts a **grace timer** (`DISCONNECT_GRACE_S`, default ~90s).
  Within grace the session shows `status="reconnecting"` and **keeps its nudge queue and ticket
  claims** (durable-session pattern from BRIDGE-DAEMON-PROPOSAL rec #7). Autossh/backoff
  usually reconnects inside grace → no churn.
- Past grace with no reconnect → demote to `disconnected` (claims auto-released after a longer
  `disconnected_claim_ttl`, e.g. 300s; row purged after `stale_session_ttl`, e.g. 3600s).
- **PID check retained** as a second signal for same-host sessions (a live PID is never reaped).

**What replaces the 600s TTL:** connection-liveness is primary. The old 600s
model-heartbeat TTL is **demoted to a legacy fallback** applied ONLY to sessions with no
active `poll_wait` connection (i.e. poll-only clients that never launched a watcher). Once
Phase 3 lands and every session runs a watcher, model heartbeats are never required.

**Capability matrix (honest about harness differences):**

| Session kind | Presence | Push-wake on nudge |
|---|---|---|
| Harness session with background-exit re-invoke (Claude Code) | watcher connection | **Yes** — full push |
| opencode session (no background re-invoke) | proxy holds a `poll_wait` connection for durable presence | No auto-wake; still reads via `board()` poll, but never false-reaped |

So even where the harness can't push-wake the model, connection-based presence still **kills
DEFECT 1** (false reaps) for every session type.

---

## 7. Security

Because Option C never opens a network port, the threat model barely changes from the 0600
socket — the daemon socket **stays AF_UNIX, mode 0600**, bound to no interface.

- **Auth = the SSH key.** Cross-host reach requires `~/.ssh/4lom` (or a per-host equivalent).
  No bearer token to mint, store, or rotate; SSH already gives auth + transport encryption +
  host-key verification.
- **Never `0.0.0.0`.** There is no TCP listener at all. (If Option A is ever adopted, it MUST
  bind the specific LAN IP and require a token — but that is explicitly out of scope here.)
- **PUBLIC-REPO HYGIENE (hard rule, memory: public-repo-no-personal-info).** charon and
  mediastack are public. **No token, IP, hostname, or `/home/stack` path may be committed.**
  All such config lives in a **gitignored** file, mirroring the existing uncommitted
  `~/.charon/secrets.json`:

  ```
  # ~/.charon/bridge-hosts.env   (gitignored; 0600; NOT in any repo)
  BRIDGE_HOST=<lan-ip-or-hostname>        # daemon host, e.g. the always-on box
  BRIDGE_SSH_KEY=~/.ssh/4lom              # key for the tunnel
  BRIDGE_REMOTE_SOCK=/home/<user>/.charon/bridge.sock   # daemon-side socket
  BRIDGE_LOCAL_SOCK=/home/<user>/.charon/bridge-remote.sock  # tunnel local end
  BRIDGE_TUNNEL_USER=<user>
  ```
  The scripts read this file; nothing that identifies the host or the operator ever enters
  version control. On the `/data`-volume deploy target the same file lives on the mounted
  volume (per memory: charon-deploy-drift-lessons — config/secrets belong on `/data`).
- **`.gitignore` guard:** add an explicit entry + a preflight check that fails if
  `bridge-hosts.env`-style content or a `10.0.1.` literal appears in a tracked file.

---

## 8. Back-compat & migration (7 tools stay identical)

**Invariant:** `register / board / update / unregister / claim / release / nudge` keep their
exact `inputSchema` and semantics — repo separation, Jedi/droid + Grand-Master reservation,
typed nudges. Sessions do not change how they call anything. Only the bytes under `proxy.py`
(which socket it dials) and one *additive* watcher-facing `poll_wait` change.

Phased, each phase independently revertible:

- **Phase 0 — local-compatible shim (zero behavior change).** Teach `proxy.py` to read
  `bridge-hosts.env`: if `BRIDGE_HOST` is **unset**, dial the local `BRIDGE_SOCKET` exactly as
  today. Ship this first; it is a no-op on the dev host and proves the config plumbing.
- **Phase 1 — cross-host daemon.** Stand up the daemon as a `systemd --user` service on the
  always-on host; bring up the `autossh` tunnel on remote hosts; set `BRIDGE_HOST`. Remote
  `proxy.py` now dials the tunnel's local socket. Board is cross-host. Still pull-only.
- **Phase 2 — push watcher.** Add `poll_wait` + the waiter registry to `daemon.py`; add
  `bridge-watch.sh`; wire the `SessionStart`/`Stop` hooks (§ below). Push wake is live for
  harness sessions; opencode sessions gain durable presence.
- **Phase 3 — retire model heartbeat.** Flip liveness to connection-primary; demote the 600s
  TTL to the poll-only fallback. Drop the "heartbeat before every subagent" guidance from
  SESSION.md for watcher-equipped sessions.

**Rollback at any phase:** unset `BRIDGE_HOST` → single-host local behavior (today). Remove the
hooks → no watcher, pure poll. Revert `daemon.py` → drop `poll_wait`; the 7 tools are untouched.

---

## 9. Auto-bootstrap (never rely on the model)

Three independent layers so a session is present-and-watching without the LLM remembering:

1. **`SessionStart` hook (primary).** In `~/.claude/settings.json` for harness sessions (and
   the opencode equivalent), a `SessionStart` hook runs a `bridge-up.sh` that: (a) ensures the
   `autossh` tunnel is up (idempotent — no-op if already up), (b) `register`s the session, (c)
   launches `bridge-watch.sh <sid> &`. Harness-executed, not model-executed (memory:
   update-config — automated "on session start" behavior must be a hook, not a preference).
2. **`Stop` hook (re-arm).** A `Stop` hook re-launches `bridge-watch.sh` if no watcher PID is
   alive, so the watcher is re-armed after every turn without the model having to remember —
   closing the one residual model dependency in §5 step 6.
3. **Cron healthcheck (belt-and-suspenders).** A per-host cron entry (via CronCreate /
   crontab) every 1–2 min runs `bridge-heal.sh`: restart the tunnel if down, and (on the
   daemon host) restart the daemon if the socket is missing. This catches slept/rebooted hosts
   and is the recovery path that needs no live session at all.

`START-SESSION.md` documents the flow for humans, but correctness never depends on a human or
the model performing a step — the hook is the source of truth.

---

## 10. Blast radius

**If the daemon (or its host) is down:**
- Cross-host `register/board/nudge/claim` fail; `proxy.py` returns a structured
  "bridge unreachable" error (not a hang) — the session KNOWS it is uncoordinated (PROPOSAL-2
  F4/YODA-CONCERN-3), so it doesn't make silent stale-data decisions.
- Sessions **continue local work.** On the dev host, unsetting `BRIDGE_HOST` gives immediate
  same-host coordination via a local daemon.
- **Claim safety during outage:** claims are repo-scoped; cross-host claim coordination is the
  thing that degrades. Mitigation: during a bridge outage sessions should avoid *new*
  cross-host claims (guidance in SESSION.md); worst case is a double-claim across hosts,
  resolved when the daemon returns (owner-PID conflict check already rejects the loser).
- Nudges are **not lost** — they persist in SQLite; a disconnected target drains them on
  reconnect (durable-session grace, §6).

**Both product surfaces degrade gracefully:**
- Charon-repo sessions and SLOP/mediastack-repo sessions are **separate pools**; a charon-side
  bridge problem cannot corrupt the mediastack pool (repo separation is enforced in `claim`).
- The **Charon product is unaffected** — this is rig infra; no product code imports it (memory:
  product-vs-build-rig-boundary). If the whole bridge vanished, Charon still builds/ships.

**Failure/rollback story:** every layer self-heals (systemd Restart=always, autossh, proxy
backoff, cron heal) and every layer is individually revertible to today's known-good single-host
behavior by unsetting one env var or removing one hook. No phase is a one-way door.

---

## 11. Implementation plan — concrete file touch-points

| File | Change | Phase |
|---|---|---|
| `~/.config/opencode/session-bridge/proxy.py` | Read `bridge-hosts.env`; dial local vs tunnel socket by `BRIDGE_HOST`; passthrough `poll_wait`; reconnect backoff | 0, then 2 |
| `~/.charon/bridge-hosts.env` **(new, gitignored)** | Host/key/socket config — no secrets in repo | 0 |
| `~/.config/opencode/session-bridge/daemon.py` | Add `poll_wait` RPC + `_waiters` registry; wake waiters in `nudge()`/auto-nudge; `connected`/`disconnected_at` + grace timer; demote 600s TTL to poll-only fallback | 2, 3 |
| `~/.config/opencode/session-bridge/bridge-watch.sh` **(new)** | Background watcher: loop `poll_wait`, exit 0 on nudge return | 2 |
| `~/.config/opencode/session-bridge/bridge-up.sh` **(new)** | Idempotent tunnel-up + register + launch watcher | 1, 2 |
| `~/.config/opencode/session-bridge/bridge-heal.sh` **(new)** | Cron healthcheck: restart tunnel/daemon | 1 |
| `~/.config/systemd/user/charon-bridge.service` **(new, daemon host)** | `Restart=always` daemon unit | 1 |
| `~/.config/systemd/user/charon-bridge-tunnel.service` **(new, client hosts)** | autossh tunnel unit, `Restart=always` | 1 |
| `~/.claude/settings.json` | `SessionStart` hook → `bridge-up.sh`; `Stop` hook → re-arm watcher | 2 |
| `~/.config/opencode/opencode.json` | Add `BRIDGE_HOST` (and friends) to the `session-bridge` MCP `env`; opencode-side start hook if available | 1, 2 |
| crontab / CronCreate | Per-host `bridge-heal.sh` every 1–2 min | 1 |
| `~/.config/opencode/session-bridge/SESSION.md` | Document connection-liveness, watcher bootstrap, outage guidance; drop mandatory heartbeat for watcher sessions | 3 |
| `fleet/START-SESSION.md` | Human-facing bootstrap note | 2 |
| `.gitignore` + preflight guard | Ignore `bridge-hosts.env`; fail on committed IP/host/path literals | 0 |

**Sequencing:** Phase 0 (proxy shim + config plumbing) → Phase 1 (daemon-on-host + tunnels +
systemd + cron) → Phase 2 (`poll_wait` + watcher + hooks) → Phase 3 (liveness flip). Phases 0–1
are pure additive plumbing with no behavior change on the dev host; Phase 2 is where push turns
on; Phase 3 is the cleanup that finally removes the model-heartbeat dependency.

---

## 12. Consequences

**Positive:**
- Kills DEFECT 1 (false reaps) for *all* session types via connection-based presence.
- Kills DEFECT 2 (pull-only) for harness sessions via genuine push; poll-only clients still
  gain durable presence.
- Kills DEFECT 3 (local-only) with the simplest robustly-cross-host transport, reusing the
  daemon and an SSH key that is already in daily use.
- Nothing secret enters the public repos; the socket stays 0600 with no network port.
- Fully revertible, phase by phase, to today's behavior.

**Negative / accepted:**
- Adds an always-on daemon host + tunnels to manage (mitigated by systemd/autossh/cron).
- The full push loop is harness-specific; opencode sessions get durable presence but not
  auto-wake (documented, acceptable).
- `poll_wait` adds mild complexity to the daemon's selector loop (bounded: one map, no threads).
- SSH is a hard dependency for cross-host reach (already true operationally).

**Open questions for review:**
- Confirm the daemon host: always-on box vs a future dedicated node vs the shared runner.
- `DISCONNECT_GRACE_S` / `disconnected_claim_ttl` tuning under real subagent durations.
- Whether opencode's hook surface can launch a watcher at session start (if not, opencode stays
  poll-only-with-durable-presence, which is still a strict improvement).
