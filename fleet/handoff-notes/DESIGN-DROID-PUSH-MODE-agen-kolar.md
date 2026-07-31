# DESIGN — DROID PUSH MODE (manager dispatches to an idle droid)

**Author:** agen-kolar · **Date:** 2026-07-24 · **Status:** DESIGN ONLY (no code written, no script touched)
**Operator ask:** *"a version of a droid which IDLES until the MANAGER/SUPERVISOR session sends them work."*

**VERDICT UP FRONT: the bridge already supports push. This is WIRING, not invention.**
Verified by execution, not by reading (§6). No daemon change, no new transport, no new RPC.

---

## 1. WHAT THE BRIDGE ALREADY DOES — reuse verdict

| Push requirement | Already built? | Evidence (`file:line`) |
|---|---|---|
| Manager→specific-droid directed message | **YES** | `nudge` RPC writes the target's `nudge_messages` queue: `~/.config/opencode/session-bridge/daemon.py:606-643`; schema mirrored at `proxy.py:230-252` |
| Droid receives it while idle | **YES** | `board(session_id=…)` returns the caller's queue: `daemon.py:463-487` (`result["nudge_messages"] = to_return`, :483). `update()` delivers the same: `daemon.py:530-535` |
| Delivery is durable / at-least-once | **YES** | non-destructive read + `delivered_at`/`ack_at` + `REDELIVER_WINDOW_S` auto-ack: `daemon.py:153-189`; explicit `ack` RPC `daemon.py:645-681`; total order via persisted `seq` minted in the write txn `daemon.py:133-140,629-643` |
| Reachable from **bash** (no MCP, no LLM turn) | **YES** | daemon is line-oriented JSON-RPC on a Unix socket (`daemon.py:44` `SOCK_PATH`); `proxy.py:279-298` is a pure forwarder — any shell can speak the same frames. **Proven by execution, §6.** |
| Heartbeat that keeps idle ≠ dead | **YES, free** | every `board()` poll refreshes the lease: `daemon.py:485-488` (`last_seen`, `lease_expires_at = _now_plus(600)`); TTL `daemon.py:46,51` |
| Dead-droid detection | **YES** | graduated purge nudge→nudge→`escalated`→`DELETE` keyed on lease expiry (never PID): `daemon.py:222-253`. Board rows already carry `expires_in_seconds`, `expiring_soon`, `stalled` (observed live, §6) |
| Blocking long-poll (`poll_wait`) | **NO — deliberately deferred** | `daemon.py:23`; already gap-tabled in `fleet/state/BRIDGE-PUSH-BUILD-PLAN.md` §1, which recommends the client-poll watcher as the ship-now tier. **This design takes that tier.** |
| Manager-side assignment logic | **YES** | `fleet/assign.sh` → `fleet/capability/assign.py` (ticket → best agent) |
| Named-ticket pin on the droid side | **YES** | `fleet-droid.sh --only <TICKET>` → `export CLAIM_ONLY` → `claim.sh` honours it (`fleet-droid.sh:446,461`; `claim.sh:26-30`) — **but only at launch time**. This is the one true gap. |

**Reuse verdict: ADOPT. Zero new mechanism.** Push = `nudge` (manager) + `board` poll (droid) + the *already existing* `CLAIM_ONLY` pin, moved from launch-time to runtime.

## 2. THE GAP (small, and it is on the fleet side, not the bridge side)

1. **`fleet-droid.sh` has ZERO bridge wiring** — it never registers, so there is nothing to nudge. This is exactly what `board/DROID-BRIDGE-REGISTER.md` `source:` already states (`fleet-droid.sh:232` sets `DROID="$TIER-$$"`, a PID label). **Push is blocked on that ticket, and is its natural completion.**
2. **Idle is a blind `sleep`** — `fleet-droid.sh:567` sleeps `WAIT_MIN*60` with no wake path. Needs to become a *ticking* wait that polls `board()`; nothing else about the loop changes.
3. **`CLAIM_ONLY` is launch-time only** — needs to be settable per-iteration from a received dispatch.
4. **No dispatch message shape** — `nudge` carries free text (`message`); a dispatch needs a parseable, single-field payload.
5. **`idempotency.py` is built but NOT wired** (its own docstring says so; `BRIDGE-PUSH-BUILD-PLAN.md` §1) — a redelivered dispatch must not double-launch.

## 3. THE DESIGN

### 3.1 Roles (and the `manager-never-spawns-droids` boundary)
- **OPERATOR** opens droid tabs — unchanged. `fleet-droid.sh <tier> --wait 3 --retries 0` already gives a persistent idle tab.
- **MANAGER** only ever calls `nudge(target=<session_id>)` against an **already-registered** session. It never spawns a process. If no idle droid is registered, `nudge` has no valid target → the manager **reports "no idle droid for tier X"** to the operator and stops. That is the whole boundary: *push assigns work to a live tab; it never creates one.*

### 3.2 Dispatch flow (nothing here is new machinery)
1. Manager picks a ticket (`fleet/next.sh` / `assign.sh`) and an idle target from `board(repo=charon)` — a row with `status=pending` and a fresh lease.
2. Manager sends `nudge(session_id=manager, target=<droid>, message="DISPATCH ticket=<ID>")`.
3. The idle droid's next tick sees it in `board()`'s `nudge_messages` (≤ one tick of latency).
4. Droid parses `ticket=<ID>`, checks `idempotency.claim(sid, msg.id)` (already-built module, finally wired) — a redelivered copy is skipped and acked, never re-run.
5. Droid sets `CLAIM_ONLY=<ID>` **for exactly one loop iteration** and falls into the existing `claim.sh` call at `fleet-droid.sh:562`.
6. **Everything downstream is untouched:** `claim.sh` does the atomic flock claim, `lease-enqueue.sh` is still the single enqueue chokepoint, the parallelizability gate (`fleet-droid.sh:571-586`), work-class chain resolution, `work-lease.sh bind/dispatch` (`work-lease.sh:142-168`), loop-guard, worktree leak-guard — all unchanged.
7. Droid `update(status=in-progress, ticket=<ID>)` (which also acks the queue, `daemon.py:530-535`) and `ack`s the message id explicitly.
8. On finish: `update(status=pending, busy="idle since <ts>")` → back to idle, available for the next push.

**No dark work:** push transports a *ticket id only*. The droid never accepts a work description over the wire. If `claim.sh` returns `NONE` (ticket unknown, already claimed, dep-blocked, parked, done), the dispatch is **REFUSED** — droid `nudge`s the reason back to the manager, acks, and resumes idle. A dispatch can therefore never create a branch without a board ticket and a lease.

### 3.3 Idle, heartbeat, and "idle must never look like dead"
- Idle droid registers with `status=pending`, `busy="idle since <ts>"`; working droid is `status=in-progress` + `ticket`. **The board distinguishes them by field, not by inference.**
- The tick *is* the heartbeat — `board()` refreshes `lease_expires_at` (`daemon.py:485-488`), so no separate heartbeat loop is needed for push-mode idling. (The working-state heartbeat is DROID-BRIDGE-REGISTER's existing scope.)
- Tick interval: **60s default** (`DROID_TICK_S`), independent of `--wait`. 60s ≪ the 600s TTL, so a live idle droid can never appear stale; a dead one expires within 600s and the daemon's own graduated purge (`daemon.py:222-253`) flips it to `escalated` then removes it. **A silently-dead idle droid therefore reads as ESCALATED/absent, never as "waiting"** — the exact failure that cost this rig a grader for 9 days.
- Cost: a tick is one socket round-trip from a sleeping shell. **No model session runs while idle** — the existing property from `fleet-droid.sh:7-11` is preserved exactly.

### 3.4 Failure modes — fail-CLOSED on work, fail-LOUD always
| Condition | Behaviour | Why |
|---|---|---|
| Bridge unreachable, droid in **default (hybrid) mode** | LOG LOUD each tick (`BRIDGE-DOWN`), write `state/push-degraded/<droid>`, and **degrade to today's pull loop** | Fail-closed on *dispatch* (never invents work) while staying useful if the manager or bridge dies. Directly satisfies "do not break pull". |
| Bridge unreachable, droid in **`--push-only`** | LOUD every tick; after `--retries` consecutive unreachable ticks, **STAND DOWN with exit 3** + a persistent marker | A push-only droid with no bridge has *no* way to get work. Silently spinning forever is the 9-day-grader failure; a loud nonzero exit is visible in the tab, in the reaper, and in the marker. Never silent, in either direction. |
| Dispatch names an unclaimable/unknown ticket | REFUSE, `nudge` the reason back, ack, stay idle | Non-vacuous + loud; no dark branch. |
| Duplicate/redelivered dispatch | idempotency-skipped + acked, logged | `REDELIVER_WINDOW_S` guarantees redelivery (`daemon.py:153-189`); without this a dispatch could double-launch. |
| Manager dies mid-dispatch | Droid completes the claimed ticket normally, returns to idle | The lease and the board file, not the manager, own the work. |
| Two managers push the same ticket to two droids | Second `claim.sh` loses the flock → `NONE` → REFUSED | The atomic claim, not the transport, is the arbiter. Push adds no new race. |
| Droid killed mid-work | Existing exit trap unregisters; else lease expires ≤600s → escalated → purged | Unchanged from DROID-BRIDGE-REGISTER. |

### 3.5 Fallback to pull — explicit
Push is **additive and opt-in**. A droid launched exactly as today behaves exactly as today. Modes:
- **hybrid (DEFAULT):** tick the bridge for a dispatch; if none *and* the free-claim pool has eligible work, claim it as today. A pushed ticket simply pre-empts the free ladder for one iteration.
- **`--push-only`:** never free-claims; the dedicated "waits to be told" droid the operator asked for.
- **`--wait 0` / no bridge configured:** the current one-shot pull behaviour, byte-identical.

A droid that can only be pushed to is opt-in and never the default, so a dead manager session can never idle the whole pool.

## 4. WHICH TICKET OWNS IT

**Extend `DROID-BRIDGE-REGISTER` (P0, `feat/droid-bridge-register`, owns `fleet/droid-bridge.sh` + `fleet/tests/droid-bridge.test.sh`). Do NOT create a new ticket.**
Rationale: push mode is *the same file, the same session lifecycle, and the same launch block*. Its `serial_justified:` already argues that name-claim + register + heartbeat + unregister are one lifecycle; **idle-tick + dispatch-consume are the same lifecycle's idle branch.** A separate ticket would fork `fleet/droid-bridge.sh` and collide inside `fleet-droid.sh`'s launch block — which the ticket already flags as shared with SUBAGENT-WORKTREE-SANDBOX.

Add to that ticket (scope + accept only; the `owns:` list is unchanged):
> `--push-only` / hybrid idle-tick, dispatch parse → per-iteration `CLAIM_ONLY`, refuse-and-report, bridge-down degrade/stand-down, idempotency wire.

Adjacent tickets — **consume, do not duplicate:**
- **`DROID-LIFECYCLE-REAP` (P2, PR-OPEN):** reaping must read the bridge's `escalated`/expired signal (`daemon.py:222-253`) rather than growing a second liveness notion. Note the dependency; do not parallel-edit `fleet-droid.sh`.
- **`WORK-LEASE-WORKTREE-RESOLVE`:** a pushed dispatch resolves its worktree through that ticket's resolver — push adds no worktree logic.
- **`SERVICE-LIVENESS-WATCHDOG`:** owns the bridge daemon's own liveness. **Hard prerequisite for push-only mode** (see §5 risk).

## 5. ACCEPTANCE CRITERIA (objectively checkable, fail-on-revert)

1. **E2E DOGFOOD, real droid:** operator launches `fleet-droid.sh <tier> --push-only`; it appears on `board` as `status=pending`; manager `nudge`s `DISPATCH ticket=<ID>`; within ≤2 ticks the droid claims that exact ticket (`state/claims/<ID>` exists, owner = that droid), runs it, and returns to `status=pending`. Real run, no simulation.
2. **Idle ≠ dead:** an idle droid left ≥1 full TTL (600s) is still on the board with `expiring_soon=false` and `nudges=0`. `kill -9` the same droid → within 600s+one purge pass its row is `escalated` or gone. **Both halves asserted.**
3. **Fail-on-revert (tick):** remove the idle tick → assertion 2's "still on the board past one TTL" goes RED.
4. **Fail-on-revert (pin):** remove the per-iteration `CLAIM_ONLY` set → assertion 1's "claims *that exact* ticket" goes RED (droid free-claims something else or nothing).
5. **No dark work:** dispatch a ticket id with no board file → droid REFUSES, replies to the manager, creates **no** branch, **no** worktree, **no** claim file. Assert all three absences.
6. **Pull unbroken:** `fleet-droid.sh <tier>` with the bridge daemon stopped completes a normal pull-claim run and exits 0. Fail-on-revert: this is the regression guard for "push must be additive".
7. **Bridge-down is loud:** with the daemon stopped, hybrid mode emits `BRIDGE-DOWN` + writes the degraded marker and still pulls; `--push-only` exits **3** after `--retries` ticks with a persistent marker. Assert exit code and marker, not just log text.
8. **Idempotency:** deliver the same dispatch message id twice (force a redelivery inside `REDELIVER_WINDOW_S`) → exactly ONE claim, one launch. Fail-on-revert: unwire idempotency → two launches.
9. **Zero idle burn:** an idle droid over ≥5 ticks starts no model session (assert no new agent process / no gateway spend row).
10. **ADVERSARIAL REVIEW** (reviewer ≠ builder) — inherited from DROID-BRIDGE-REGISTER; edits the shared money-path launcher.

## 6. VERIFIED BY EXECUTION vs READ

**Executed (this session):**
- Started a scratch daemon (`BRIDGE_SOCKET`/`BRIDGE_DB` into scratchpad) and ran the **full push path from bare bash over the raw Unix socket — no MCP, no model turn**: `register(droid-agen, status=pending)` → `lease_token` + 600s lease; `nudge(manager → droid-agen, "DISPATCH ticket=DROID-BRIDGE-REGISTER")` → `{"ok":true,"nudges":1,"seq":1}`; `board(session_id=droid-agen)` → returned the message with `seq`, `from:"manager"`, `delivered_at`, `ack_at` **and** live liveness fields `expires_in_seconds:600, expiring_soon:false, stalled:false`. **Push works today; the design is wiring.** Scratch daemon and DB removed afterwards.
- **The LIVE bridge daemon is DOWN:** `/tmp/charon-bridge.sock` does not exist; only `proxy.py` (pid 1794037) is running, and it errors "Bridge daemon not running" (`proxy.py:346-348`). Confirms `lens-registry.tsv:4` ("bridge daemon DOWN — reboot casualty").
- Confirmed **`work-lease.sh` has NO `guard-branch` subcommand** — the real subcommands are `acquire|check|holds|bind|dispatch|release|heartbeat|pre-commit|commit-msg|install|ensure|uninstall` (`work-lease.sh:306-317`). The branch→ticket gate landed as `b784de1` and enforces at **`bind`/`dispatch`** (`work-lease.sh:142-168`). Any brief citing `guard-branch` is citing a name that does not exist.

**Read only (not executed):** `daemon.py` line-level semantics for purge/TTL/ack; `fleet-droid.sh` loop structure (`:558-600`) — **and it is being edited concurrently (PATH preflight), so its current contents are not final**; this design touches only two anchors in it (the `sleep` at `:567` and the `CLAIM_ONLY` export at `:461`), both of which should be applied *after* that sub lands, on the DROID-BRIDGE-REGISTER branch.

## 7. BIGGEST RISK

**The bridge daemon is not supervised and is currently DOWN.** Push mode's entire wake path depends on a process that has already died once to a reboot with nothing to restart it. Shipping `--push-only` before `SERVICE-LIVENESS-WATCHDOG` supervises the daemon converts a single daemon death into a silently idle droid pool. Mitigation is in the design (loud degrade / exit 3 + marker), but the ordering is a hard sequencing constraint: **hybrid mode may ship with DROID-BRIDGE-REGISTER; `--push-only` should not be the operator's default until the daemon is supervised.**
