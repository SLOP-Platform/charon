# Adversarial Re-Review — DURABLE-BRIDGE-DESIGN-v2.md

**Reviewer:** adversarial re-review gate (read-only, design-only)
**Date:** 2026-07-06
**Target:** `fleet/DURABLE-BRIDGE-DESIGN-v2.md` (rework) vs `fleet/DURABLE-BRIDGE-REVIEW.md` (v1 findings)
**Grounded in:** live `~/.config/opencode/session-bridge/daemon.py` (607 lines), `proxy.py` (258 lines), `charon/tools/check_public_clean.py`, charon `.gitignore`, `.github/`.

**VERDICT: REWORK** — the *architecture* (lease model, per-fleet process isolation, ack/replay, static-enrollment anti-split-brain) is sound and most v1 blockers are genuinely closed. But three defects sit **inside the newly-designed core**: the lease-auth secret leaks by construction through the read path the design inherits but never touches (NB1); `seq` ordering breaks across the most common event, a daemon restart, and crashes the board read during rollout (NB2); and the push-mode lease TTL is *shorter than a real woken turn*, so a live session self-reaps mid-work (NB3). Plus the motivating DEFECT-1 is still open for poll-mode/opencode while §12 claims it closed "for every session type by construction" — the exact overstatement class that sent v1 back. These are correctness/security, not polish.

---

## Did v2 close the v1 findings? (adversarially tested)

| v1 finding | Status | Why |
|---|---|---|
| **B1** PID category error (cross-host claim/liveness) | **CLOSED** | `os.kill`/`SO_PEERCRED` removed from the authority path; lease token is transport-opaque, so multiplexing/forwarding/blips no longer poison liveness. Correct fix. (Residual liveness gaps are new — NB3, DEFECT-1-poll below — not the PID error.) |
| **B2** lost-wakeup race (check-then-wait) | **CLOSED** | Single-threaded dispatch makes pending-check + waiter-registration atomic w.r.t. any concurrent `nudge()` (also single-threaded) — no interleave window exists. Reinforced by non-destructive delivery (§6). Confirmed the deferred-reply/1s-tick model does **not** block the selector, so the 55s poll doesn't head-of-line-block the repo. |
| **B3** keepalive + derived grace | **PARTIAL** | Numbers compose for detecting a *dead* tunnel (45s keepalive < 120s TTL) and for bounding a dead session's lingering claim (≤120s). But they do **not** close the *in-turn* gap — see **NB3**. |
| **M1** waiter reverse-index / connected-transition never fires | **CLOSED (in spec)** | Lease deletes the `connected`/`disconnected_at`/grace state machine entirely (one number), removing the un-fireable transition; reverse-index built in from Phase 2 start. Unverifiable at code level but adequately specified. |
| **M2** split-brain from local-daemon degrade | **CLOSED** | Local-only is now a **static boot-time enrollment** choice, never a runtime fallback; enrolled-host tunnel outage returns a structured error (matches `proxy.py:196` → `-32603`, no second daemon spawned). Genuine, best fix in the doc. |
| **M3** wake/re-invoke storm, no backoff | **CLOSED (in spec)** | `bridge-watch.sh` gets exp backoff+jitter+circuit-breaker, exit-0 only on real wake, `flock` singleton. Script-level so unverifiable here, but the thundering-herd-on-restart case is named and mitigated. |
| **M5** cross-fleet coupling | **PARTIAL** | Two processes / sockets / DBs is real server-side isolation (a mediastack storm cannot HOL-block charon's selector). But two NEW shared failure domains are re-introduced — see the M5-partial note below. |
| **M6** opencode "durable presence" overstated | **CLOSED as honesty / UNDERCUT by §12** | §4 is now honest (opencode = poll-mode, no push, 600s). But §12 then re-asserts "Kills DEFECT 1 … for *every* session type … by construction" — false for poll-mode (below). Same overstatement the v1 verdict punished. |
| **G1** delivery/ordering/replay/GC/observability/kill-switch | **PARTIAL** | ack/replay/GC/status/kill-switch all designed and mostly sound. Residual: NB1 (auth leak), NB2 (seq), bounded auto-ack loss, and G2 dropped (below). |
| **G2** non-interrupting / coalesced wakes | **STILL-OPEN (silently dropped)** | v2 never re-addresses G2. With at-least-once redelivery this is now *worse* — see the G2 note. |
| **G3** AGENTS.md migration | **CLOSED** | Added to touch-points; heartbeat section rewrite specified. |
| **G4** bridge-health.py cross-host + mailbox independence | **CLOSED** | `--repo` + dial-through-tunnel; mailbox-independence one-liner added. |
| **Mi1–Mi5** | **CLOSED**, except **Mi2 weaker than stated** (below). |

---

## NEW BLOCKERS (introduced or left open by v2)

### NB1 — The lease token leaks to every peer through `board()` — the entire auth model is defeated by construction  *(HIGHEST-LEVERAGE)*
The design states the token is "returned **only** in the `register` response … never exposed via `board()`" (§4). **The inherited read path contradicts this and the design never touches it.** `_board_result` runs `SELECT * FROM sessions` (daemon.py:443 and :445); `_row_to_dict` does `d = dict(row)` (daemon.py:120) and returns *every column*. Add `lease_token` as a column (§4 schema) and it flows, unredacted, into the `board` result that **every** session receives on **every** `board()`/`register` call. Any session can read every peer's `lease_token`, then call `poll_wait(other_sid, stolen_token)` / renew / steal that peer's claim — exactly the impersonation the token was meant to prevent. This is not a tuning issue; the secret's confidentiality is the whole basis of §4/§5, and the design asserts a property its own read path violates. **Fix:** explicitly strip `lease_token` (and any future secret column) in `_row_to_dict`/`_board_result` **and** in the new `status` RPC (which will inherit the same `SELECT *` risk); add a regression test that greps board/status output for the token. Until then the lease machinery is security theater.

### NB2 — `seq` is an in-memory counter → ordering breaks on daemon restart, and mixed None/int `seq` crashes the board read during rollout
§6 defines `seq` as "in-memory, process-global counter." Two concrete failures:
1. **Restart resets it.** `systemd Restart=always` (§11) and the Phase-2 deploy restart both reset the counter to its initial value. Un-acked messages already in SQLite carry high `seq` (e.g. 481203); post-restart new nudges start low → they sort *before* older un-acked messages → replay order violated across the single most common operational event. The design's "sorted by `seq` ascending (ordering)" guarantee does not survive a restart. **Fix:** seed the counter from `MAX(seq)` across all DBs at boot, or persist a monotonic counter row.
2. **Rollout sort crash.** During Phase 1→2, messages nudged under Phase 1 have **no** `seq` (read back as `None` via `.get`). The Phase-2 read path sorts by `seq`; `sorted(..., key=lambda m: m["seq"])` with `None` mixed with `int` raises `TypeError: '<' not supported between 'NoneType' and 'int'` — the **entire** board/update read for that session throws, making *all* its messages unreadable until manually cleared. **Fix:** coerce missing `seq` to a sentinel (0 or an assigned-on-read value) before sorting.

### NB3 — Push-mode lease TTL (120s) is shorter than a woken turn → a live session self-reaps mid-work
`LEASE_PUSH_TTL_S` = 120s (§4). The watcher renews the lease only when it issues `poll_wait` (on timeout re-issue, or on wake). **But on a wake the watcher exits-0** (to let the harness re-invoke the session), and §11 re-arms it on the **`Stop`** hook — i.e. at the *end* of the woken turn. So during the woken turn there is **no watcher running and no `poll_wait` in flight**. If that turn does real work for >120s (routine — a wake exists precisely to trigger work, and a single subagent run routinely exceeds 120s), the lease lapses **while the session is alive and working** → `_purge_stale` reaps it / its claim becomes stealable → cross-host double-claim under a live worker. This reintroduces the motivating DEFECT-1 on the *push* path with a **shorter** horizon than the 600s it replaced. The design's own §4 rationale ("renews within `LEASE_PUSH_TTL_S`") silently assumes the watcher is re-armed at turn **start**, concurrently — but §11 wires it to `Stop` (turn end), and never guarantees `SessionStart`/`bridge-up.sh` re-launches the watcher on a background re-invoke. **Fix:** re-arm the watcher at the *start* of every (re-)invoked turn so it renews concurrently during the turn, or raise `LEASE_PUSH_TTL_S` well above the worst-case turn/subagent duration. Until one of those, B3 has a live-reap gap.

---

## MAJORS / STILL-OPEN

- **DEFECT-1 NOT closed for poll-mode/opencode; §12 overstates.** An opencode/poll-mode session renews its lease only via `update()`/`board()` on the 600s TTL. A silent subagent run >600s (the *original* DEFECT-1 scenario, verbatim §1) still lapses the lease → false reap / stealable claim. §4 admits "identical risk profile to today"; §12 then claims "Kills DEFECT 1 (false reaps) for *every* session type … by construction." Those contradict. The category error (B1) is fixed for poll-mode; the false-reap-on-long-run is **not**. This is the same overstatement pattern the v1 review flagged in M6 and made a REWORK basis — do not let it recur. **Fix:** restate §12 to match the capability matrix (DEFECT-1 closed for push-mode only; poll-mode unchanged), or give poll-mode a cheap keep-alive.

- **G2 silently dropped + at-least-once makes it worse (double-action).** v2 never re-addresses G2 (non-interrupting / coalesced wakes). Now compounded: at-least-once redelivery means a nudge delivered → acted on → (crash before ack) → **redelivered → acted on again**. The design supplies `id`/`seq` but specifies **no consumer-side dedup**. For any side-effecting nudge (spawn a droid, run a build, post a PR comment) that is double-execution. **Fix:** define wakes as non-interrupting + coalesced (v1 G2), and mandate consumer dedup by message `id` before acting on a redelivered message.

- **M5 isolation is partial — two shared failure domains re-introduced.** (a) §8 routes *both* repos through **one** client SSH tunnel ("operationally one tunnel, not two"); a tunnel blip drops push for **both** fleets on that host simultaneously — undoing the isolation story at the client edge. (b) Both DBs/WALs live on the **same filesystem** under `~/.charon` on `$COORDINATOR_HOST` with no per-fleet disk quota; a mediastack queue/WAL bloat (v1 already observed a 1.2 MB WAL) that fills the disk makes charon's SQLite writes fail. Process isolation is real; disk and client-tunnel isolation are not. **Fix:** separate tunnels (or accept + document the coupling); per-fleet disk quota or separate mounts.

- **Bounded at-least-once = bounded loss.** `REDELIVER_WINDOW_S` = 120s auto-acks (§6). "A crash between read and act no longer loses the message" (§2.5) holds **only** if re-invoke + act completes within 120s. A woken session that reloads context / auto-compacts (v1 G2 noted this is slow) can exceed 120s → auto-ack → message lost. Tune `REDELIVER_WINDOW_S` to worst-case re-invoke latency, and count auto-acked-without-explicit-ack in `status` so the loss is visible.

- **Leak backstop is weaker than the design claims (sharpens Mi2).** The design's leak-safety "enforced by the existing `tools/check_public_clean.py` guard" (§0/§9). Verified: the guard is wired into **neither** `.github/` **nor** any Makefile/pre-commit (runs manually only), and `bridge-hosts.env` is **not** in charon's `.gitignore` (it lives outside the tree, which is the actual protection — the gitignore line in §11 is moot). Worse, the guard's patterns match `10.x` IPs and the hostnames `4-lom`/`charon-vm` only — it has **no pattern for the coordinator's actual address** ("Rocinante"); if that host is a public DNS name, a `192.168.x`, or a tailscale name, a stray paste into a tracked file sails past. The design leans its entire secret-safety story on an unenforced, pattern-incomplete guard. **Fix:** wire the guard into CI/pre-commit (elevate from "ticket later") and add a pattern covering the coordinator's real address form before Phase 1.

---

## MINORS

- **Kill-switch mislabels `unregister` as read-only** (§7). `unregister` does `DELETE FROM sessions` (daemon.py:354) — a mutation. Allowing it during drain is fine intent, but calling it "read-only" is wrong; be explicit that it's a *permitted mutation* so an implementer doesn't gate it with the read-only RPCs.
- **Queue cap vs auto-nudge inconsistency.** `nudge()` rejects on a full queue (§6), but `_purge_stale`'s auto-nudge appends unconditionally (daemon.py:101-105). A wedged session with a full unacked queue can never receive its own escalation nudge, and the cap is bypassed by the daemon's own writes. Reconcile.
- **`status` needs the same NB1 redaction** — flagged inline above; restate in §7 so it isn't implemented with a naive `SELECT *`.

---

## Highest-leverage remaining risk

**NB1 — the lease token leaking through `board()`/`status`.** It silently converts the entire new lease/auth core into security theater: any session reads every peer's token from a routine `board()` and can then renew, impersonate, or steal any other session's claim across the fleet. Root cause is one line the design inherits but never touches (`SELECT *` → `dict(row)`), and it is invisible in the ADR prose because the ADR *asserts* the opposite. This is the first thing that breaks the moment the design meets reality, and it defeats the very property (cross-host-correct, un-spoofable claims) v2 exists to deliver. Fix + regression-test it before any Phase-1 code.
