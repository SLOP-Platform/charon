# Adversarial Design Review — DURABLE-BRIDGE-DESIGN.md (Option C)

**Reviewer:** adversarial design-gate sub-session (read-only)
**Date:** 2026-07-06
**Target:** `fleet/DURABLE-BRIDGE-DESIGN.md` — SSH-tunnelled Unix socket + `poll_wait` push + connection-liveness
**Verdict:** **REWORK** (Phases 0–1 are SHIP-WITH-FIXES; the Phase 2–3 liveness+claim+push core must be re-designed before any code)

Grounded in the live implementation: `~/.config/opencode/session-bridge/daemon.py` (single-thread `selectors` loop, SQLite-WAL, `os.kill` PID liveness, `SO_PEERCRED`), `proxy.py` (per-call connect-send-close forwarder), `opencode.json` MCP block (`BRIDGE_SOCKET=~/.charon/bridge.sock`, untracked config), `tools/check_public_clean.py` (existing leak guard), `fleet/checks/bridge-health.py`, public `AGENTS.md`.

---

## Verdict rationale (one paragraph)

The **transport decision (Option C) is sound and well-argued**, and the **leak posture is essentially safe** (config lives in untracked `opencode.json` + a gitignored env file, and an IP/host/path guard already exists). Phases 0–1 (config shim + cross-host board, still pull-only) can proceed with fixes. **But the design's two headline claims — "connection-liveness kills false reaps for ALL session types" and "the owner-PID conflict check keeps claims safe cross-host" — are both false as written.** The PID-based liveness the whole claim-safety story rests on is host-local and breaks the instant a session is reached over the SSH forward; `poll_wait` as specified has a lost-wakeup race and no dead-tunnel detection; and the biggest gap is that a *coordination* store is being shipped with **no delivery guarantee, no ordering/replay, no GC, no observability, and no kill-switch.** These are core-invalidating, not polish. Hence REWORK of the Phase 2–3 core.

---

## BLOCKERS (must fix before Phase 2 code)

### B1 — PID-based liveness & claim-steal are HOST-LOCAL and break cross-host  *(the single most important defect)*
`daemon.py` derives client PID from `SO_PEERCRED` (line 546) and gates both claim-steal (lines 369–387) and stale-purge (lines 92–98) on `os.kill(owner_pid, 0)`. **Over an SSH Unix-socket forward the peer is the local ssh/sshd forwarder on the daemon host, not the remote session.** Consequences:
- Every remote session multiplexed over one tunnel is stamped with the **same PID** (the forwarder's) → `os.kill` tests the forwarder, not the session.
- A remote session that **dies while its tunnel stays up looks alive forever** — never reaped, its claim never stealable.
- If that forwarder PID is later reused by an unrelated local process → false-alive; if the forwarder is gone → all sessions on that tunnel falsely dead at once.

§10 asserts "worst case is a double-claim … resolved when the daemon returns (owner-PID conflict check already rejects the loser)." **That check cannot work cross-host.** The design introduces `connected`-based liveness for *presence* but never rewires `claim`/`_purge_stale` to use it. **Fix:** claims and purge must key off connection-liveness (the waiter socket / `connected` flag) plus an explicit `owner_host` column; disable the `os.kill` path for any non-local (tunneled) peer; add a connection-based steal gate.

### B2 — Lost-wakeup race registering `poll_wait`
§5: "on `poll_wait`, add the connection to `_waiters[sid]` and do not reply yet." A nudge that arrives **after** the woken session drained via `board()` (which atomically clears `nudge_messages`, daemon.py:296) but **before** the watcher re-registers `poll_wait` writes to SQLite with no waiter present → the wake is lost; the next `poll_wait` blocks on an already-queued message until the 55s timeout (or forever if timeouts are later dropped). **Fix:** `poll_wait` must, at registration and under the daemon's single thread, check the DB for pending `nudge_messages` for that sid and return `{woke:true, reason:"pending"}` immediately if non-empty (check-then-wait), closing the gap.

### B3 — No half-open / dead-tunnel detection → the 90s grace is meaningless in both directions
Presence = an open `poll_wait` connection. But the daemon side is an **AF_UNIX** socket fed by ssh's forward — `SO_KEEPALIVE` does not apply to AF_UNIX, and ssh holds the local socket open until *it* notices the drop (default TCP timeouts = many minutes to hours). The design specifies **no** `ServerAliveInterval`/`ServerAliveCountMax` on the client tunnel and **no** `ClientAliveInterval` on sshd. Therefore:
- A dead remote session's socket stays half-open → daemon never sees EOF → `disconnected_at`/grace never starts → **shows live and holds its claim indefinitely** (compounds B1).
- Conversely, when ssh *does* tear down a briefly-blipped forward, the daemon sees EOF and starts the 90s grace on a **live, working** session; if reconnect > `disconnected_claim_ttl` (300s) the claim is released under a live worker → **cross-host double-claim**.

**Fix:** mandate `ServerAliveInterval=15 / ServerAliveCountMax=3` (client) + `ClientAliveInterval` (sshd) so drops surface in ~45s; add an application-level PING inside the `poll_wait` protocol; specify exactly which event stamps `disconnected_at` and cleans `_waiters` (see M1). Until dead-tunnel detection is bounded and *below* the grace, connection-liveness is not trustworthy.

---

## MAJORS

### M1 — Waiter reverse-index leak + `connected` transition never fires
`_waiters` is `dict[sid]→[conn]`, but there is no `conn→sid` reverse map. The existing selector disconnect path (daemon.py:535–542, empty recv → `unregister`+`close`) does **not** remove the conn from `_waiters` nor stamp `disconnected_at`. Dead conns accumulate; a later nudge writes to a dead socket; and the presence `connected=0`/grace transition — the entire liveness model — has no place to fire from. **Fix:** maintain `conn→sid`; in the disconnect branch pop from `_waiters`, stamp `disconnected_at`, start grace.

### M2 — Split-brain from the local-daemon degrade path (self-inflicted)
§4/§10 offer "on the dev host, fall back to a local daemon (unset `BRIDGE_HOST`) for same-host coordination" during a tunnel outage — and §8 names that same unset as the **rollback**. Either creates a **second board/DB**; claims made locally are invisible to the canonical board and never reconcile on tunnel return → double-claims survive recovery. Nothing prevents a stray `systemd --user` daemon on the dev box coexisting with the 4-LOM one (two DBs, no lease/leader election). **Fix:** the local fallback must be **read-only/advisory** (no claims, no cross-host nudges) or removed; document exactly one canonical daemon host; guard that a client with `BRIDGE_HOST` set refuses to also start a local daemon.

### M3 — Re-invoke / wake storm with no backoff (direct token-cost blast; violates memory: optimize-execution-wallclock-tokens)
Wake = "watcher bash exits → harness re-invokes the session." When the daemon is unreachable, `poll_wait` fails fast → bash exits → harness re-invokes → `SessionStart`/`Stop` hook relaunches watcher → fails fast → **tight loop burning model turns/API calls.** Same **thundering herd** on any daemon restart (Phase 2 deploy, `systemd Restart=always`): every watcher connection drops at once → every session re-invoked simultaneously. `proxy.py` has backoff, but the watcher→exit→re-invoke→relaunch cycle does not. **Fix:** exponential backoff + jitter *inside* `bridge-watch.sh` before re-issuing `poll_wait`; a circuit-breaker after N fast failures; exit-0-to-wake **only** on a real nudge, exit-nonzero-and-sleep on connection errors so the hook can rate-limit.

### M4 — Host placement is not actually decided (name/IP confusion)
The design conflates the two boxes: "BB-8 / 4-LOM (10.0.1.60)" (§1) vs "4-LOM / BB-8 (10.0.1.60)" (§2/§4). Ground truth: **4-LOM = 10.0.1.60** (always-on PRODUCT box, gateway container) and **BB-8 = 10.0.1.61** (SLOP test box that reboots/sleeps for tests). BB-8 as anchor takes the whole board down on every test reboot — **disqualified.** 4-LOM is the only always-on option **but it is the product host** — rig infra there risks the product/rig boundary (memory: product-vs-build-rig-boundary). **Verdict:** 4-LOM is the safer anchor, acceptable **only** as a strictly-isolated `systemd --user` unit (no root, resource-bounded, own socket/DB under `$HOME`, never imported by product code — verified: no `src/` import) and explicitly documented as non-product. **Fix:** correct names/IPs, commit to 4-LOM=10.0.1.60, add the isolation guarantees, and evaluate the shared self-hosted runner as a neutral third anchor if it is genuinely always-on.

### M5 — Cross-fleet coupling: the shared daemon becomes a NEW single point of coupling between two previously-independent fleets
Today charon and mediastack are separated only by a `repo` column **in one DB/daemon**. Going cross-host keeps **one process, one selector loop, one SQLite writer, one 1s tick** for both. §10's "separate pools cannot corrupt each other" is only *logical row-separation*. Real coupling: `_recv_all` runs a **blocking `settimeout(2.0)` recv INSIDE the single-thread selector** (daemon.py:534) — one slow client of *either* fleet head-of-line-blocks every session of *both*; a mediastack waiter leak / nudge storm / WAL bloat (the live `session-bridge.db-wal` is already **1.2 MB**) degrades the same daemon Charon depends on. **Fix:** either run one daemon per repo (two sockets/DBs — cleanest isolation) or make the recv non-blocking and add per-repo quotas + a kill-switch. Do not let a SLOP failure be able to take down the Charon board.

### M6 — opencode "durable presence" is unfounded → the "kills DEFECT 1 for ALL session types" claim is overstated
§6's matrix says opencode sessions "gain durable presence because the proxy holds a `poll_wait` connection." But `proxy.py` is a **per-call connect→send→close** forwarder (lines 178–197, `main()` reads one MCP line, forwards, the socket is closed each call); nothing holds a long-lived connection when the model isn't calling a tool. There is **no opencode-side process** to hold `poll_wait` open unless a watcher is launched — and §12 lists exactly that as an OPEN QUESTION. So for opencode, DEFECT 1 is **not** killed; those sessions still depend on the 600s heartbeat. **Fix:** stop claiming durable presence for opencode until a holder process is proven; keep and document the 600s fallback for them.

---

## BLAST-RADIUS GAPS (what the design OMITS / disturbs downstream)

### G1 — HIGHEST-LEVERAGE GAP: no delivery guarantee, ordering, replay, GC, or observability — a coordination store with no operational surface
`poll_wait` returns no body and relies on `board()` to drain, but:
- **Delivery is at-most-once and loss-prone.** `board()` clears `nudge_messages` atomically on read (daemon.py:296). If the woken session is re-invoked, reads the board, and then crashes/compacts before acting → the messages are already cleared → **lost**. There is no ACK.
- **No ordering/replay** across a reconnect; drain is all-or-nothing.
- **No TTL/GC and a silent truncation cliff.** `nudge_messages` is an unbounded appended JSON array; a broadcast/storm or a long-asleep target bloats it, and `_recv_all` truncates at `MAX_MSG_BYTES` (1 MB) — messages silently dropped mid-frame. Stale nudges ride until the 3600s row purge.
- **No observability and no kill-switch.** The only health surface is `bridge-health.py` (host-local register/unregister round-trip). Nothing exposes waiter counts, connected sessions, tunnel state, per-repo load, or a stuck board; there is no documented emergency "revert every host to local no-op" switch.

For a system whose *entire job* is coordinating claims and wakes, the absence of at-least-once delivery + an ops view is the biggest single gap. **Fix:** make `board()`'s clear-on-read an explicit **ACK** (clear only after the session confirms handling); use the already-present per-message `id` for idempotent at-least-once delivery; cap + GC the queue with a message TTL; add a `bridge_status` admin RPC (waiters, connections, per-repo counts, tunnel health) and a documented kill-switch env flag.

### G2 — Destructive interaction with the harness's own background re-invoke + long subagent runs
Wake semantics are undefined against an in-flight turn. The harness **also** re-invokes on other background-task completions; a nudge-wake arriving mid-long-subagent-run either queues behind it or, if it interrupts, can truncate/derail the run — the exact long-run scenario DEFECT 1 was meant to protect. Each push-wake is also a **fresh model turn** (context reload / possible auto-compact) → real token burn. **Fix:** define wakes as **non-interrupting** (deliver at the next natural turn boundary) and **coalesce** multiple queued nudges into one wake (already feasible since `board()` drains all).

### G3 — AGENTS.md (PUBLIC, tracked) is the one bridge-referencing file in a public repo and is omitted from the migration
`AGENTS.md` (git-tracked, public charon repo) mandates the bridge and heartbeat: "**Session-bridge — keep alive (NEVER let it time out)**" plus register/board/heartbeat steps. Phase 3 removes the heartbeat requirement, but §11's touch-point table **omits AGENTS.md** → public docs go stale/contradictory, and it is a standing product-leak (a public repo instructing use of a private rig bridge). **Fix:** add AGENTS.md to the migration; reconcile or de-couple the public workflow doc from rig-internal liveness mechanics.

### G4 — Observability/health tooling and adjacent coordination systems not addressed
- `fleet/checks/bridge-health.py` hardcodes `BRIDGE_SOCKET=~/.charon/bridge.sock` and only works on the daemon host post-migration; §11 omits it. Migrate it cross-host or it silently reds on remote hosts.
- The mediastack `.claude/mailbox/` scripts (`warden.sh`, `heartbeat.sh`, `claim_role.sh`, `team_supervisor.sh`, droid-harness) are a **separate file-based coordination layer — NOT on the session-bridge** — so they are not directly broken, but the design never states the two systems coexist or which is canonical. **Fix:** one line clarifying the mailbox/droid harness is independent, plus migrate bridge-health cross-host.

---

## MINORS / NOTES

- **Mi1 — Watcher singleton race.** The `Stop`-hook relaunch can transiently create two watchers → two waiters per sid → one nudge double-wakes. Add a pidfile/`flock` singleton in `bridge-watch.sh`.
- **Mi2 — Reuse the EXISTING leak guard.** `tools/check_public_clean.py` already flags `10.x` IPs, `4-lom`, `/home/stack`, `charon-private`, and hex tokens. The design's "add a preflight check" duplicates it — **extend/reuse** it and verify it is actually wired into pre-commit/CI (grep found it in **no** `.github/`/`Makefile` target — it may run only manually). `opencode.json` is confirmed **untracked**, so adding `BRIDGE_HOST` there is leak-safe; keep a guard that `opencode.json` never becomes tracked.
- **Mi3 — Name-collision footgun.** Product `src/charon/proxy.py` vs rig `~/.config/opencode/session-bridge/proxy.py`. The ADR must always use the full rig path so an implementer doesn't edit the product file.
- **Mi4 — Clock skew is a NON-issue (design got this right implicitly).** All timestamps are server-stamped via the daemon's `_now()`; cross-host clock skew does not affect liveness. State this so no one adds needless NTP complexity.
- **Mi5 — `struct` import placement.** `struct` is imported only under `if __name__ == "__main__"` (daemon.py:606); if `daemon.py` is ever imported as a module the `SO_PEERCRED` path `NameError`s. Move the import to module top.

---

## Stress-point scorecard (as requested)

1. **Tunnel-drop storms** — REAL, **BLOCKER** (B3 + M3): no keepalive spec → drops surface late; no watcher backoff → re-invoke/token storm; nudges are *not* lost (persist in SQLite) but delivery can still drop at the ACK gap (G1).
2. **Split-brain / two daemons** — REAL, **MAJOR** (M2): the degrade/rollback path IS the split-brain trigger; no lease/leader election.
3. **`poll_wait` / `_waiters` correctness** — REAL, **BLOCKER + MAJOR** (B2 lost-wakeup, M1 leak/no reverse-index).
4. **Reap-during-disconnect** — REAL, **BLOCKER** (B3): both false-alive (half-open) and false-reap (blip > claim_ttl) occur; keepalive unspecified.
5. **Security / leak** — LOW/OK: no network port, socket stays 0600, config in untracked files, and a guard already exists. Residual: 0600 assumption is fine single-user on 4-LOM; extend the guard and keep it in CI (Mi2). Not a blocker.
6. **Host placement** — REAL, **MAJOR** (M4): 4-LOM=10.0.1.60 is the only viable (always-on) anchor; BB-8=10.0.1.61 reboots and is disqualified; product-host coupling must be isolated + documented. Names/IPs in the doc are wrong.
7. **Degradation when daemon down** — MOSTLY OK: `proxy.py` returns a structured error (no silent stale board); **Charon product verified independent** — no `src/` import of the bridge (only `AGENTS.md`, a workflow doc, references it), so the product ships even if the bridge vanishes. The one hole is the split-brain degrade path (M2).
8. **Migration reversibility** — MOSTLY OK: env-unset revert works and no phase is a one-way door. Two non-bricking hazards: Phase 1 cutover creates a **transient split board** (locally-registered live sessions vanish when `BRIDGE_HOST` flips — sequence a drain/re-register); Phase 2 daemon restart to add `poll_wait` drops all connections → wake storm (M3).

---

## What to do before writing code

- **Phases 0–1 (config shim + cross-host board, pull-only): SHIP-WITH-FIXES** — safe additive plumbing; apply M4 (host/isolation), Mi2/Mi3 (guard reuse, path clarity), and add AGENTS.md/bridge-health.py to the touch-point list (G3/G4).
- **Phases 2–3 (poll_wait, connection-liveness, claim rewiring): REWORK** — resolve B1 (cross-host claim/liveness off connections, not `os.kill`), B2 (check-then-wait), B3 (keepalive + PING below grace), M1 (waiter cleanup), M3 (watcher backoff), M5 (fleet isolation), M6 (honest opencode story), and the G1 delivery/observability/kill-switch gap **before** any daemon code lands.
