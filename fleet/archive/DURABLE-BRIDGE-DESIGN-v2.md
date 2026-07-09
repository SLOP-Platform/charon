> ARCHIVED 2026-07-08 — superseded by DURABLE-BRIDGE-DESIGN-v3.md (v2 in the v1->v2->v3 chain)

# ADR (v2): Durable, Cross-Host, Push-Notifying Session Bridge

**Status:** PROPOSED v2 (design-only — no code, no infra/config/opencode.json changes, no push, no SSH)
**Date:** 2026-07-06
**Scope:** BUILD-RIG infra (the fleet session-bridge). NOT the Charon product.
**Supersedes:** `DURABLE-BRIDGE-DESIGN.md` (v1), in response to `DURABLE-BRIDGE-REVIEW.md` (verdict: REWORK on Phases 2–3).
**Relationship to ADR-0008 / obol:** Orthogonal, one line, unchanged from v1 — obol is the product-side
portable orchestration store; this bridge is rig-only transport for live build sessions and MUST NOT be
coupled to it or leak into the product (memory: product-vs-build-rig-boundary).

---

## 0. What changed since v1, and why

The adversarial review (`DURABLE-BRIDGE-REVIEW.md`) approved the **transport decision** (Option C,
SSH-tunnelled Unix socket) and the **leak posture**, and shipped Phases 0–1 of v1 with minor fixes. It
REWORKED the entire Phase 2–3 core because v1's liveness/claim/push/delivery model rested on two false
premises: (a) PID-derived liveness (`SO_PEERCRED` + `os.kill`) is meaningful over an SSH forward (it is
not — the peer is the forwarder, shared by every multiplexed session), and (b) a coordination store can
ship with clear-on-read delivery and no ordering/replay/GC/observability/kill-switch.

v2 replaces the liveness/claim mechanism wholesale (PID → **lease**) and adds a real delivery model
(at-least-once + ack + ordering + replay + GC + observability + kill-switch). It also folds in an
**operator decision made after v1 was reviewed**: the daemon does not live on either fleet's own host
(4-LOM/BB-8) — it lives on a **third, neutral, dedicated coordinator host**, which resolves the v1 §4
host-placement debate (M4) by construction rather than by isolation gymnastics on a product host.

**Hard constraint carried through this entire document:** the coordinator host is referred to ONLY as
`$COORDINATOR_HOST` (operator's symbolic name for it: "Rocinante"). Its real IP/hostname lives *exclusively*
in the gitignored `~/.charon/bridge-hosts.env` and is never written here, in any script, or in any
committed file — enforced by the existing `tools/check_public_clean.py` guard (see §9, Mi2).

---

## 1. Context (carried from v1, condensed)

Today's bridge (`~/.config/opencode/session-bridge/daemon.py` + `proxy.py`) is a single-process AF_UNIX +
SQLite-WAL daemon at `~/.charon/bridge.sock`, 7 tools (`register/board/update/unregister/claim/release/
nudge`), repo-separated (charon vs mediastack). It works on one host. Three defects motivated v1:

- **DEFECT 1 — Liveness is model-driven** (600s TTL + heartbeat discipline; forgets during long subagent runs).
- **DEFECT 2 — Pull-only** (nothing wakes a session; must poll `board()`).
- **DEFECT 3 — Local-only** (no cross-host reach at all).

v1 chose **Option C (SSH-tunnelled Unix socket)** for transport — REVIEW-APPROVED, unchanged in v2 — and a
long-poll `poll_wait` RPC for push, using the harness's "backgrounded process re-invokes on exit" primitive.
**What v2 changes is *how liveness, claims, and message delivery are represented*, and *where the daemon
lives*.** Sections 3–8 below are the reworked core; §2 restates the (unchanged) transport decision briefly.

---

## 2. Decision (summary) — v2

1. **Transport: unchanged from v1 — SSH-tunnelled Unix socket (Option C).** Daemon stays AF_UNIX +
   SQLite-WAL, no network bind, reused as-is. (Full Option A/B/C/D tradeoff table lives in v1 §3; the
   review approved this reasoning outright and v2 does not relitigate it.)
2. **Coordinator host: `$COORDINATOR_HOST` — a dedicated, neutral, THIRD host.** Not 4-LOM (Charon's
   host), not BB-8/the mediastack test host. Operator decision, resolves M4: there is no product-host
   coupling to isolate against, and no test-reboot host to be disqualified, because the daemon never lives
   on a fleet's own box. Real IP lives only in `~/.charon/bridge-hosts.env` (gitignored); this document and
   all scripts use the placeholder `$COORDINATOR_HOST` (or `<coordinator-host>`) throughout.
3. **Liveness & claims: LEASE, not PID.** `register` mints a UUID-scoped **secret lease token** + an
   expiry (`lease_expires_at`). Every liveness/claim/purge decision compares `now` to `lease_expires_at`.
   `os.kill`/`SO_PEERCRED` are removed from the authority path entirely — kept, if at all, as a decorative
   diagnostic field, never read for correctness. Cross-host-correct by construction (B1, M6).
4. **Two lease *renewal cadences*, chosen dynamically by which RPC a client actually uses — no schema
   change to any existing tool.** A session that never calls the new `poll_wait` renews its lease via
   plain `update()`/`board()` calls, exactly as today, on the same 600s TTL (poll-mode — this is opencode's
   honest story, M6). A session that runs the new backgrounded watcher renews via `poll_wait` on a short,
   *derived* TTL (push-mode). The lease itself doubles as the "grace timer" — there is no separate
   connect/disconnect/grace state machine to get subtly wrong (this directly closes B3 and simplifies M1).
5. **Push: `poll_wait` with check-then-wait (closes B2) + a real delivery model (closes G1).** Messages are
   never destructively cleared on first read; they carry a monotonic `seq`, become `delivered_at`-stamped
   on read, and are only durably removed on explicit `ack()` or outer GC/TTL. A crash/compaction between
   read and act no longer loses the message.
6. **Per-fleet isolation on the coordinator (closes M5): two daemon processes, two sockets, two DBs** — one
   per repo (`charon`, `mediastack`) — so load or failure in one fleet's pool cannot touch the other's
   selector loop. A federated read (`bridge-status`) can still see both; writes never cross.
7. **Single-writer guarantee, no reactive fallback (closes M2):** `$COORDINATOR_HOST` is THE authority for
   any host that is *enrolled* cross-host. A tunnel outage returns a structured error — it never causes
   `proxy.py` to spin up a second, local, *authoritative* daemon. "Local-only daemon" is a **static,
   boot-time enrollment choice** for hosts that were never cross-host-enrolled at all (today's exact
   single-host shipped behavior) — never a runtime toggle triggered by a transient failure.
8. **Observability + kill-switch (closes the rest of G1):** a new read-only `status` RPC + `bridge-status`
   CLI (waiters, live sessions, per-recipient queue depth, lease ages, last-seen, per-repo counts), and a
   file-sentinel kill-switch (`bridge-killswitch.sh on|off`) that drains/disables mutating RPCs without
   ever creating a second writer.
9. **Back-compat: the 7 tool interfaces stay byte-identical** (inputSchema untouched). All new state
   (lease token, seq, delivered_at, ack_at) rides in *response* fields (additive) or inside the existing
   `nudge_messages` JSON blob (no column/schema change needed for messages at all). `poll_wait`, `ack`,
   `status` are the only new RPCs, and they are additive/watcher-facing, not model-facing.
10. **Auto-bootstrap unchanged in spirit from v1:** `SessionStart`/`Stop` hooks + cron heal, never the model.

---

## 3. Options reconsidered

### 3.1 Liveness/claim authority: PID vs lease-token vs external lock service
- **PID (`os.kill` + `SO_PEERCRED`) — v1's choice. Rejected (B1).** Meaningless the instant a peer is
  multiplexed through an SSH forwarder; the reviewer proved this is not a tuning problem, it's a category
  error (the PID being tested is never the session's).
- **External lock service (e.g. a lease/lock table in a shared broker) — rejected.** Same "new always-on
  service" objection v1's Option D raised for Redis/NATS; unnecessary when SQLite already gives us atomic
  single-writer semantics and all we need is a compare-and-swap on a timestamp column.
- **Lease-token (UUID + secret + expiry, stored in the existing SQLite row) — CHOSEN.** Zero new
  infrastructure (same DB, same daemon), cross-host-correct by construction (the token is opaque to
  transport — SSH forwarding, tunneling, multiplexing, none of it matters), and directly matches the
  operator's explicit mandate. This is also *simpler* than v1's model: one mechanism (an expiring lease)
  replaces v1's three (PID check + connected-boolean + grace-timer state machine).

### 3.2 Daemon topology: one shared daemon+DB (row-scoped by repo) vs two isolated daemons
- **One shared daemon, `repo` column separation — v1's choice, and today's actual code. Rejected for the
  coordinator role (M5).** `_recv_all`'s blocking `settimeout(2.0)` recv inside the single-thread selector
  means one slow/stormy client of *either* fleet head-of-line-blocks the other's every RPC. Logical
  row-separation isn't process/resource isolation.
- **Non-blocking recv + per-repo quotas on one shared daemon — considered, rejected as more complex than
  the alternative** for the amount of isolation it actually buys (still one process, one crash domain, one
  WAL file to bloat).
- **Two fully independent daemon processes/sockets/DBs, one per repo — CHOSEN.** Cleanest isolation the
  reviewer named as the alternative to quotas; a mediastack storm literally cannot block a charon
  `poll_wait`. Manager-level cross-repo visibility is a client-side federated read (`bridge-status` dials
  both sockets), never a server-side cross-repo query.

### 3.3 Coordinator host: 4-LOM vs BB-8 vs shared runner vs dedicated neutral host
v1 debated 4-LOM (always-on, but the Charon *product* host — coupling risk) vs BB-8 (disqualified, reboots
for SLOP tests) vs "evaluate the shared runner." **Operator decision: neither.** A dedicated, neutral third
host (`$COORDINATOR_HOST`) that belongs to neither fleet's product/test surface. This is not a compromise
between the two rejected options — it removes the tradeoff entirely: no product-host coupling question to
isolate against (nothing of Charon's or SLOP's runs there), no test-reboot fragility (it's not a test box).

### 3.4 Delivery/ack model: destructive clear-on-read vs full-ack-required vs bounded redeliver window
- **Clear-on-read (today, and v1's implicit inheritance) — rejected.** This *is* G1's core finding: a
  woken session that reads then crashes/compacts before acting has already lost the message.
- **Full explicit ack required for every client — rejected as a compatibility break.** Would require every
  existing caller (including any not yet migrated, and the honest opencode poll-mode story in §3.1) to
  learn a new RPC or lose messages outright; too sharp a discontinuity for an additive-only migration.
- **Bounded redeliver window + legacy auto-ack, real ack for watcher-equipped clients — CHOSEN.** A message
  read via `board()`/`update()` is stamped `delivered_at`, not deleted, and keeps reappearing in
  `nudge_messages` until either (a) an explicit `ack()` clears it (new, watcher-equipped clients), or (b) a
  bounded `REDELIVER_WINDOW_S` elapses past first delivery with no ack, at which point it is auto-acked
  (identical risk profile to today for legacy callers — never worse, and strictly better within the
  window). See §6.

---

## 4. Lease model (closes B1, B3, M6; simplifies M1)

### Schema (additive columns only — `_migrate()` pattern, no data loss, no behavior change until used)
```
ALTER TABLE sessions ADD COLUMN lease_token     TEXT DEFAULT '';
ALTER TABLE sessions ADD COLUMN lease_expires_at TEXT DEFAULT '';
```
(`pid` stays as-is, purely decorative — see §9 Mi5.)

### Minting and renewal
- **`register`** (inputSchema unchanged) mints `lease_token = secrets.token_hex(16)` server-side and sets
  `lease_expires_at = now + LEASE_POLL_TTL_S` (default **600s** — identical to today's `SESSION_TTL_S`, so
  poll-mode behavior for existing/legacy callers is byte-for-byte unchanged). The token is returned **only**
  in the `register` response (`{ok, session_id, lease_token, board}` — an *additive* response field, the
  inputSchema is untouched) and is never exposed via `board()` to other sessions (prevents a peer from
  impersonating another session's lease renewal).
- **Poll-mode renewal (unchanged cadence):** any `update()` or `board(session_id=...)` call for a given
  `session_id` renews `lease_expires_at = now + LEASE_POLL_TTL_S`. This is exactly today's heartbeat
  semantics, just reframed as a lease instead of a bare `last_seen` timestamp — **zero behavior change**
  for any client that never calls the new RPCs.
- **Push-mode renewal (new):** `poll_wait(session_id, lease_token, timeout_s)` must present the
  `lease_token` it got from `register`. A mismatched or missing token is rejected (`-32001,
  "invalid lease token"`) — this is the one place a credential check is added, and it's on a brand-new,
  additive RPC, so it does not touch the "byte-identical" 7 tools. On **every** `poll_wait` reply (pending,
  nudge-wake, or timeout — see §5), the daemon renews `lease_expires_at = now + LEASE_PUSH_TTL_S`.

### Why the lease *is* the grace timer (no separate state machine)
v1 needed three moving parts to reason about liveness: a `connected` boolean, a `disconnected_at` stamp,
and a grace-timer TTL — and the reviewer found the transition into that state machine (M1) was never
actually wired to fire. v2 has one number: `lease_expires_at`. A watcher that cleanly exits (to let the
harness re-invoke the session) and relaunches within `LEASE_PUSH_TTL_S` never produces a visible liveness
gap — its lease is still valid, full stop. A watcher that dies for real (host crash, no relaunch) simply
lets the lease lapse at a bounded, *derived* horizon. There is no "was that a clean exit-to-relaunch or a
real death?" ambiguity to resolve at the daemon layer — that ambiguity is exactly what v1's disconnect
handler had to get right and didn't (M1).

### Deriving `LEASE_PUSH_TTL_S` (closes B3 — no more arbitrary 90s)
```
POLL_TIMEOUT_S        = 55   # poll_wait's own blocking timeout
SSH_ALIVE_INTERVAL_S  = 15   # client tunnel: ServerAliveInterval
SSH_ALIVE_COUNT       = 3    # client tunnel: ServerAliveCountMax
SSH_KEEPALIVE_BOUND_S = SSH_ALIVE_INTERVAL_S * SSH_ALIVE_COUNT   # = 45s: worst-case time for a
                                                                  #  dead tunnel to surface at the TCP layer
LEASE_PUSH_TTL_S = POLL_TIMEOUT_S + SSH_KEEPALIVE_BOUND_S + 20   # = 120s safety margin
```
Ship these as named constants in `daemon.py`/`bridge-hosts.env`, not magic numbers, so the derivation is
auditable and re-tunable. Also specify concretely (closing the rest of B3):
- Client tunnel unit (`autossh`/`ssh -N -L`) sets `ServerAliveInterval=15 ServerAliveCountMax=3`.
- `$COORDINATOR_HOST`'s sshd (scoped to the forwarding user, not global) sets
  `ClientAliveInterval=15 ClientAliveCountMax=3`.
- The `poll_wait` loop itself is an application-level heartbeat once these bounds are below
  `LEASE_PUSH_TTL_S` — no separate PING RPC is needed.

### Claim/purge rewritten to use the lease (closes B1)
- `_purge_stale` no longer touches `pid`/`os.kill` at all. It becomes: `WHERE lease_expires_at < now` →
  the existing graduated nudge→escalate→purge ladder is unchanged past that point (it was already correct
  once "is this session alive" is answered correctly).
- `claim`'s steal-check becomes: read the current owner's `lease_expires_at`; if `now > lease_expires_at`,
  the owner's lease has lapsed → clear the ticket and proceed (steal allowed); if still valid → reject with
  `claimed_by` (unchanged response shape). This is correct regardless of host, tunnel, or multiplexing,
  because it never asks "is PID N alive" — it asks "did *this session* renew *its own* lease in time,"
  which is answerable identically on every host.

### Honest opencode story (closes M6)
`proxy.py`'s `main()` is a per-call connect→send→close forwarder (confirmed: no persistent connection
across model turns). opencode therefore **cannot** run the watcher/`poll_wait` loop, and v2 does not claim
otherwise. It stays in **poll-mode**: its lease renews on the existing 600s cadence via `update()`/`board()`
exactly as today. What v2 changes for opencode is narrower but real: it is no longer subject to the PID
category error (B1) — a poll-mode session's lease is evaluated purely on its own renewal calls, so it is
never falsely kept alive by a shared forwarder PID, and never falsely reaped by one either. No push-wake;
no false liveness in either direction. Documented plainly in SESSION.md (§9) and in the capability matrix
below.

| Session kind | Liveness mechanism | Push-wake | Notes |
|---|---|---|---|
| Harness session w/ watcher (Claude Code) | push-mode lease, renewed by `poll_wait` | **Yes** | `LEASE_PUSH_TTL_S` (~120s) |
| opencode (no persistent process) | poll-mode lease, renewed by `update`/`board` | No | `LEASE_POLL_TTL_S` (600s, unchanged) |

---

## 5. `poll_wait` — check-then-wait, closes B2

`poll_wait(session_id, lease_token, timeout_s)`:
1. Validate `lease_token` (see §4). Invalid → error, no registration, no lease renewal.
2. **Check-then-wait (the actual B2 fix):** before registering as a waiter, check whether `session_id` has
   any pending (unacked) entries in `nudge_messages` *right now*. If yes → reply immediately
   `{woke:true, reason:"pending"}`, renew the lease, done. Only if the pending set is empty does the daemon
   add `(conn → session_id)` to the waiter registry and defer the reply.
3. This closes the literal race the reviewer found (a nudge landing between a drain and the next
   `poll_wait` registration) **and** is reinforced by §6's delivery model: because messages are no longer
   destroyed on read (only marked `delivered_at`, cleared on `ack`), there is no way for a message to exist
   in a state where it's "gone from the DB but not yet seen by a waiter" — the worst case left is a small
   latency-to-notice bounded by one `poll_wait` round trip, not a lost message.
4. On nudge arrival for a waited-on `session_id` (in the existing `nudge()` handler, and the auto-nudge
   path in `_purge_stale`): after the DB write, look up the reverse-index (§6), reply to any waiting
   conn(s) `{woke:true, reason:"nudge"}`, renew their lease, remove them from both waiter maps.
5. On the existing 1s selector tick, any waiter whose `timeout_s` has elapsed gets `{woke:true,
   reason:"timeout"}`, its lease is renewed anyway (a timeout reply still proves the connection was alive a
   moment ago), and it's removed from the maps — `bridge-watch.sh` immediately reissues.

Still single-threaded, still zero new threads — one dict, one reverse dict (below), one tick check.

---

## 6. Durable delivery: ack, ordering, replay, GC, wire-frame errors (closes G1)

No new schema column is needed for messages — `nudge_messages` is already a JSON array column; each
element (a "nudge object") simply gains fields. Old rows/objects without these fields are read with
`.get(..., default)`, so no migration step blocks this.

### Message shape (additive fields only)
```json
{
  "type": "...", "id": "msg-...", "from": "...", "ts": "...", "payload": {...},   // unchanged (v1/today)
  "seq": 481203,            // NEW: monotonic, process-global counter (in-memory, incremented per
                             //      nudge() call under the single-threaded dispatch — collision-proof
                             //      by construction, no wall-clock ambiguity)
  "delivered_at": null,     // NEW: stamped the first time this object is returned by board()/update()
  "ack_at": null            // NEW: stamped by the new ack() RPC; once non-null the object is dropped
                             //      from the array on the next write
}
```

### Read path (`board`/`update`) — no longer destructive
- Returns messages where `ack_at IS NULL`, sorted by `seq` ascending (ordering, per-recipient).
- On return, any message with `delivered_at IS NULL` is stamped `delivered_at = now` (in place — still no
  deletion). A message already `delivered_at`-stamped keeps reappearing on subsequent reads **until**
  either `ack()` clears it or `REDELIVER_WINDOW_S` (default 120s, tunable) has elapsed since
  `delivered_at`, at which point the daemon auto-acks it for the caller (identical risk profile to today's
  clear-on-read — never a regression — but with a genuine replay window for callers that do use `ack()`).
- **Response shape for `board`/`update` is unchanged** (`nudge_messages` is still a plain array); the new
  fields are additive keys inside each object, so legacy callers that only read `.text`/`.payload` are
  unaffected.

### New `ack` RPC (additive, watcher-facing)
`ack(session_id, lease_token, message_ids: list[str])`: for each id, if it belongs to `session_id`, stamp
`ack_at = now`; the next write to that row drops fully-acked entries from the array. Idempotent (acking an
already-acked or unknown id is a no-op, not an error) — safe to retry.

### Replay after sleep/reconnect
Because delivery never deletes, a session that reconnects (fresh `poll_wait` or fresh `board()` call) after
being asleep for hours simply sees the full un-acked set again, in `seq` order — this is the literal
"replay since last ack" behavior requested. No separate replay RPC is needed; it falls out of "don't delete
on read."

### GC / TTL (bounds the queue so it can't grow forever)
- Per-message outer bound: `NUDGE_TTL_S` (default 24h) — during the existing `_purge_stale` tick, any
  message with `now - ts > NUDGE_TTL_S` is dropped regardless of ack state. This is a **visible** drop:
  increment a per-session `dropped_unacked` counter (surfaced in `status`, §7) rather than vanishing
  silently — satisfies the observability ask even for the terminal GC case.
- Per-session queue cap: `MAX_QUEUE_LEN` (default 200) / `MAX_QUEUE_BYTES` (default 256 KB). A `nudge()`
  call that would exceed either cap is **rejected outright** — `{ok:false, error:"target queue full",
  target, queue_len}` — so the sender is told delivery did not happen (fail loud), rather than the queue
  silently truncating or dropping the oldest entry.
- When a session's row itself is purged (lease fully lapsed past the graduated ladder), any still-unacked
  messages in its `nudge_messages` are logged (one line, `status`-visible counter) before the row is
  deleted — no silent loss even in the terminal case.

### Wire-frame truncation (the *other* half of G1's "silent 1MB truncation")
Today `_recv_all` breaks the read loop at `MAX_MSG_BYTES` (1MB) with no signal — a line split mid-frame
fails `json.loads` inside the `for line in data.split(b"\n")` loop and is silently `continue`d, i.e. the
request itself is dropped with no error to the caller. **Fix:** if `_recv_all` detects the size cap was hit
*before* a newline was seen, respond on that connection with an explicit error
(`-32000, "request exceeds MAX_MSG_BYTES"`) before closing, instead of silently discarding the frame. No
chunking protocol is needed — request frames this large are themselves a bug to surface, not a size class
to support (the queue-cap above is where large *cumulative* backlogs are handled, via explicit rejection,
not this per-frame limit).

---

## 7. Observability + kill-switch (closes the rest of G1)

### `status` RPC (new, additive, read-only, no token required — same trust model as `board` today)
```json
{
  "ok": true,
  "daemon": {"repo": "charon", "uptime_s": 12345, "kill_switch": false, "kill_switch_reason": null},
  "sessions": [
    {"session_id": "...", "watch_mode": "push"|"poll", "lease_expires_in_s": 87,
     "last_renewed_s_ago": 3, "ticket": "...", "queue_depth": 2,
     "oldest_unacked_age_s": 41, "dropped_unacked_total": 0}
  ],
  "waiters": {"count": 3}
}
```
### `bridge-status` CLI (new script)
Calls `status` via `proxy.py` for **each** configured repo socket (federated read across the per-repo
daemons from §8) and pretty-prints a merged table — the "manager can see across both pools, without either
pool's write path ever crossing" requirement from M5.

### Kill-switch (file sentinel, not a session-callable RPC — deliberately not exposed to sessions)
`~/.charon/bridge.disabled[.{repo}]` — if present, the daemon's dispatch rejects **mutating** RPCs
(`register/update/claim/release/nudge/poll_wait/ack`) with `{ok:false, kill_switch:true, error:"bridge
disabled: <reason>"}`; **read-only** RPCs (`board`, `status`, `unregister`) still work so sessions can see
the drain and exit cleanly. `bridge-killswitch.sh on <repo> "<reason>" / off <repo>` toggles it. Kept
operator-only (a file, not a tool) so a buggy/compromised session can never disable the board itself — it
can only ever *not write*, never grant itself write access to a second store.

---

## 8. Per-fleet isolation on the coordinator (closes M5)

Two fully independent daemon processes on `$COORDINATOR_HOST`, each `systemd --user`-managed:

- `charon-bridge-charon.service` → socket `~/.charon/bridge-charon.sock`, DB
  `~/.charon/session-bridge-charon.db`.
- `charon-bridge-mediastack.service` → socket `~/.charon/bridge-mediastack.sock`, DB
  `~/.charon/session-bridge-mediastack.db`.

Each is its own process, own selector loop, own SQLite writer, own WAL file. A blocking `settimeout(2.0)`
recv or a waiter/nudge storm in one can never head-of-line-block the other — there is no shared code path
below the OS process boundary. One SSH tunnel unit can carry both forwards (`-L sock1:sock1 -L
sock2:sock2` in one `ssh`/`autossh` invocation) so this is operationally one tunnel, not two, per client
host. A client's `proxy.py` picks its repo's socket via `bridge-hosts.env` (`BRIDGE_SOCKET_CHARON` /
`BRIDGE_SOCKET_MEDIASTACK`) — the caller already knows its own repo at registration time (existing
convention), so no new input param is needed on any of the 7 tools.

Manager-level cross-repo visibility is exactly `bridge-status` (§7) dialing both sockets client-side and
merging — never a server-side join. Writes are structurally incapable of crossing repos: there are two
separate SQLite files, on disk, full stop.

---

## 9. Migration, docs, and minor fixes (closes G3, G4, Mi1–Mi5)

- **G3 — `AGENTS.md`** (public, tracked) is added to the touch-point table (§10, Phase 3). Its "Session-
  bridge — keep alive (NEVER let it time out)" section is rewritten to state the capability matrix from
  §4: watcher-equipped (push-mode) sessions drop the mandatory-heartbeat language entirely; opencode
  (poll-mode) sessions keep it, unchanged. It also gains one line on the new `ack()` convention: a
  watcher-woken session should `ack()` handled messages before its `Stop` hook re-arms the watcher (not
  required for correctness — the redeliver window covers a missed ack — but keeps queues clean).
- **G4 — `fleet/checks/bridge-health.py`** hardcodes `~/.charon/bridge.sock` and only proves same-host
  round-trips. Migrated (Phase 1) to take a `--repo` argument and dial through `proxy.py`/the tunnel like
  any other client, so it actually exercises the cross-host path it's meant to be redding on.
- **G4 — mailbox/droid-harness independence.** One line, per the reviewer's ask: the mediastack
  `.claude/mailbox/` scripts (`warden.sh`, `heartbeat.sh`, `claim_role.sh`, `team_supervisor.sh`) are a
  **separate, file-based coordination layer, not built on the session-bridge** — this ADR does not touch
  them, and the two systems are not required to reconcile.
- **Mi1 — watcher singleton.** `bridge-watch.sh` takes an `flock` on `~/.charon/bridge-watch.<sid>.lock` at
  start; if already held, exit immediately. Closes the `Stop`-hook double-relaunch → double-waiter → one
  nudge double-wakes a session.
- **Mi2 — reuse the existing guard, don't reinvent one.** `tools/check_public_clean.py` already flags
  `10\.\d+\.\d+\.\d+`, `4-?lom`, `/home/stack`, `charon-private`, and 40+ char hex tokens. v2 adds no new
  guard — it relies on this one, and this document itself is written to pass it (placeholder
  `$COORDINATOR_HOST` throughout, no literal IP/hostname/`/home/stack` path). Follow-up (non-blocking,
  ticket it): confirm the guard is actually wired into CI/pre-commit — a grep at review time found it in
  neither `.github/` nor a `Makefile` target, i.e. it may currently run only manually.
- **Mi3 — path clarity.** Every touch-point in §10 below uses the full `~/.config/opencode/session-bridge/
  ...` path so an implementer never confuses it with the product's `src/charon/proxy.py`.
- **Mi4 — clock skew is a non-issue, unchanged from v1.** All timestamps are server-stamped via the
  daemon's own `_now()`; no client clock is ever trusted for a liveness/lease decision. No NTP dependency
  introduced.
- **Mi5 — `import struct` placement.** Since PID capture is now decorative (never read for correctness),
  it would be reasonable to delete `SO_PEERCRED` handling outright; if it's kept purely for a human-
  readable `pid` field in `status`, move `import struct` to module top-level regardless, so `daemon.py`
  never `NameError`s if imported as a module (e.g., for tests of the new lease/ack logic).

---

## 10. Phased rollout — each phase independently, provably non-split-brain revertible

**Key correction vs v1:** v1 deferred the lease/claim fix to "Phase 2–3" while its Phase 1 was already
cross-host — exactly the configuration in which PID-based claims are broken (B1). v2 folds the lease model
into Phase 1, before any cross-host claim ever happens for real.

| Phase | Content | Revert | Split-brain provably impossible because |
|---|---|---|---|
| **0** | `bridge-hosts.env` support in `proxy.py`; `daemon.py` gains `lease_token`/`lease_expires_at` columns (inert — no dispatch logic reads them yet) | Ignore the env file / unused columns | No behavior changed at all; purely additive schema |
| **1** | `$COORDINATOR_HOST` stands up **two isolated daemons** (§8); tunnels with `ServerAliveInterval/CountMax` + matching sshd `ClientAliveInterval/CountMax` (§4); `register`/`claim`/`_purge_stale` switch to lease-based (§4) — PID path becomes decorative; `bridge-health.py` gets `--repo` + dials the tunnel (G4). Still pull-only. | Unset `BRIDGE_HOST` on a given host → that host statically reverts to **not cross-host-enrolled** (its own pre-migration local daemon config) | Enrollment is a static per-host config choice, not a runtime fallback; other enrolled hosts are unaffected (isolated per-repo daemons, §8); at no point does an enrolled host have two candidate authorities live simultaneously |
| **2** | `poll_wait` (check-then-wait, §5) + waiter registry w/ reverse-index cleanup (M1, built in from the start — not retrofitted) + push-mode lease renewal (§4); `ack`/`seq`/`delivered_at`/redeliver-window/GC (§6); `bridge-watch.sh` (backoff+jitter+circuit-breaker, M3; flock singleton, Mi1); `SessionStart`/`Stop` hooks | Disable the hooks / stop calling `poll_wait` | Sessions fall back to Phase-1 poll-mode lease renewal (`update`/`board`), which is unconditionally present since Phase 1 — `poll_wait`/`ack` are pure additions to the *same single-authority* daemon, never a second store |
| **3** | `status` RPC + `bridge-status` CLI (§7); kill-switch sentinel + `bridge-killswitch.sh` (§7); docs: `AGENTS.md` (G3), `SESSION.md`, `fleet/START-SESSION.md` | Stop using `status`/kill-switch | Both are read-only or write-*disabling* — a kill-switch can only remove write capability, it can never grant a second writer |

**Sequencing note:** Phase 0 is a no-op everywhere until Phase 1 sets `BRIDGE_HOST`; Phase 1 is where the
board actually becomes cross-host **and correctly-live** (unlike v1, which shipped cross-host-but-PID-
broken at this step); Phase 2 turns on push; Phase 3 is pure ops surface + docs.

---

## 11. File touch-points (concrete)

| File | Change | Phase |
|---|---|---|
| `~/.config/opencode/session-bridge/proxy.py` | Read `bridge-hosts.env`; dial local vs per-repo tunnel socket; `poll_wait`/`ack`/`status` passthrough; reconnect backoff+jitter | 0, 1, 2 |
| `~/.charon/bridge-hosts.env` **(new, gitignored)** | `$COORDINATOR_HOST` real value, per-repo socket paths, SSH key path, keepalive constants | 0 |
| `~/.config/opencode/session-bridge/daemon.py` | Lease columns + migrate; lease-based claim/purge (removes `os.kill` from the authority path); `poll_wait` + `_waiters`/reverse-index; `ack`/`seq`/`delivered_at`/redeliver-window/GC; `status` RPC; kill-switch sentinel check; explicit oversized-frame error; `struct` import moved to top | 0, 1, 2, 3 |
| `~/.config/opencode/session-bridge/bridge-watch.sh` **(new)** | Watcher loop: `poll_wait`, exponential backoff+jitter on connection failure (not on timeout/wake), circuit-breaker after N fast failures, `flock` singleton, exit-0 only on real wake | 2 |
| `~/.config/opencode/session-bridge/bridge-up.sh` **(new)** | Idempotent tunnel-up (with keepalive opts) + register + watcher launch; refuses to start a local daemon if `BRIDGE_HOST` is set | 1, 2 |
| `~/.config/opencode/session-bridge/bridge-heal.sh` **(new)** | Cron healthcheck: restart tunnel / either per-repo daemon if down, with reconnect jitter | 1 |
| `~/.config/opencode/session-bridge/bridge-status.sh` **(new)** | Calls `status` on both per-repo sockets, federated pretty-print | 3 |
| `~/.config/opencode/session-bridge/bridge-killswitch.sh` **(new)** | Toggle `~/.charon/bridge.disabled[.repo]` with a reason string | 3 |
| `~/.config/systemd/user/charon-bridge-charon.service` **(new, `$COORDINATOR_HOST`)** | Per-repo daemon unit, `Restart=always` | 1 |
| `~/.config/systemd/user/charon-bridge-mediastack.service` **(new, `$COORDINATOR_HOST`)** | Per-repo daemon unit, `Restart=always` | 1 |
| `~/.config/systemd/user/charon-bridge-tunnel.service` **(new, client hosts)** | `autossh`/`ssh -N` with both `-L` forwards, `ServerAliveInterval=15`/`CountMax=3`, `Restart=always` | 1 |
| `$COORDINATOR_HOST` sshd config (forwarding-user scoped) | `ClientAliveInterval=15`/`ClientAliveCountMax=3` | 1 |
| `~/.claude/settings.json` | `SessionStart` → `bridge-up.sh`; `Stop` → re-arm watcher (+ document the ack-before-stop convention) | 2 |
| `~/.config/opencode/opencode.json` | `BRIDGE_HOST` (+ friends) in the `session-bridge` MCP `env` (confirmed untracked) | 1, 2 |
| crontab / CronCreate | `bridge-heal.sh` per host, every 1–2 min | 1 |
| `~/.config/opencode/session-bridge/SESSION.md` | Lease/liveness model, watcher bootstrap, ack convention, push-vs-poll capability matrix, outage guidance | 3 |
| `fleet/checks/bridge-health.py` | Add `--repo`; dial via `proxy.py`/tunnel instead of a hardcoded local socket | 1 |
| `AGENTS.md` (public, tracked) | Rewrite heartbeat section per push-vs-poll matrix; note `ack()` convention; note mailbox independence | 3 |
| `fleet/START-SESSION.md` | Human bootstrap note; mention `bridge-status` | 2, 3 |
| `tools/check_public_clean.py` | No code change — reused as the guard this design relies on; flag CI-wiring as a non-blocking follow-up | 0 (verify only) |
| `.gitignore` | Confirm `bridge-hosts.env` pattern ignored | 0 |

---

## 12. Consequences

**Positive:**
- Kills DEFECT 1 (false reaps) for *every* session type, correctly, cross-host, by construction (lease, not
  PID) — the thing v1 only claimed.
- Kills DEFECT 2 (pull-only) for watcher-equipped sessions via genuine push, with an honest (not
  overstated) story for opencode.
- Kills DEFECT 3 (local-only) with the same reviewer-approved SSH-tunnel transport as v1.
- Delivery is now at-least-once with ordering, replay, GC, and observability — the board is finally a
  coordination store an operator can actually trust and inspect, not a best-effort side channel.
- Per-fleet isolation means a mediastack incident cannot degrade Charon's coordination, or vice versa.
- No reactive split-brain path exists anywhere in the design — every degrade/rollback is either static
  config or strictly write-disabling.
- Nothing secret enters any committed file; the coordinator's real address is a single gitignored value.

**Negative / accepted:**
- Two daemon processes to run/monitor on `$COORDINATOR_HOST` instead of one (isolation's cost).
- The lease model is a bigger change to `daemon.py` than v1's incremental patch — but it's *simpler* in
  aggregate (one mechanism vs three), which is why it was chosen over patching PID-liveness in place.
- `poll_wait`/`ack`/`status` add three new RPCs and a waiter registry to the selector loop; still no new
  threads, still bounded (one map + one reverse map + one in-memory counter).
- opencode sessions still do not get push-wake — an accepted, now-honestly-documented limitation, not a
  false claim.

**Open questions for the next review pass:**
- Confirm `LEASE_POLL_TTL_S` (600s), `LEASE_PUSH_TTL_S` (~120s, derived), `REDELIVER_WINDOW_S` (120s),
  `NUDGE_TTL_S` (24h), `MAX_QUEUE_LEN`/`MAX_QUEUE_BYTES` (200 / 256KB) under real subagent-duration data —
  these are reasoned defaults, not measured ones.
- Whether opencode ever gains a hook surface capable of holding a long-lived process (revisits M6's
  ceiling, not a blocker today).
- Whether `check_public_clean.py` should be wired into CI/pre-commit (Mi2 follow-up; ticket, don't block
  this ADR on it).
