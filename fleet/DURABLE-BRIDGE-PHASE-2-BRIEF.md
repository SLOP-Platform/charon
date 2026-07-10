# SESSION — DURABLE-BRIDGE-PHASE-2: push watcher + observability + wiring cleanup

**Repo A (build-rig, not a git repo):** `~/.config/opencode/session-bridge/`
(`daemon.py`, `proxy.py`, `idempotency.py`, `test_daemon.py`) — current state is Phase 0-1
BUILT per `DURABLE-BRIDGE-DESIGN-v3.md` + `DURABLE-BRIDGE-REVIEW-v3.md` (BUILD
GO-WITH-CONDITIONS verdict). `daemon.py`'s own module docstring (lines 19-21) already
names everything below as explicitly deferred: `poll_wait`, `bridge-watch.sh`, the
renewer service, `SessionStart`/`Stop` hook wiring, the `status` RPC, the kill-switch,
and the `AGENTS.md` heartbeat-retirement rewrite.

**Repo B (public, git):** `/home/stack/code/charon` — `AGENTS.md` only (item 5's G3
sub-item). Public-clean guard is already wired and green (`[public-clean] OK` in
`charon gate`) — no Repo-B wiring work remains from Mi2.

**Source docs to read first (in this order):**
1. `fleet/DURABLE-BRIDGE-DESIGN-v3.md` — the design. §4 (lease model), §6/§7-AMEND
   (non-destructive delivery, redeliver window, observability/kill-switch), §8-AMEND
   (idempotency ledger), §10 (phased rollout table — Phase 2/3 rows), §11 (file
   touch-points).
2. `fleet/DURABLE-BRIDGE-REVIEW-v3.md` — the adversarial gate that approved Phase 0-1
   and named the Phase-2-only NB3 gap (Task 1, NB3 section) and the must-fix-during-build
   list (items 2-3).
3. `fleet/scratch/bridge-phase01-review.md` — the SHIP verdict for the Phase 0-1 commit,
   ranked follow-up #3 (bounded auto-ack) and #4 (destructive→non-destructive back-compat).
4. `~/.config/opencode/session-bridge/daemon.py` — current live Phase 0-1 code; read the
   module docstring (lines 1-21) and `_process_read`/`_purge_stale` (lines 148-249)
   before touching anything.

No commit exists yet for this brief's scope. Do not restart or SSH into the live daemon
(`~/.charon/bridge.sock`) as part of design/build work — coordinate any live-daemon
restart separately, after this Phase-2 code is reviewed.

---

## Deferred item 1 — NB3: renewer must not immortalize a hard-crashed session

**Problem.** Design-v3 §4/§6-AMEND (renewer section) decouples lease renewal from the
watcher's own turn cadence: an always-on `charon-bridge-renewer.service` (`Restart=always`,
20s tick, not yet built) renews every registered session's lease independent of whether
that session is still doing anything. This closes the *original* NB3 defect (a busy
session self-reaping mid-turn) but **review-v3 (Task 1, NB3 section, lines 46-60)**
found it opens the opposite failure: on a **hard crash** (SIGKILL/OOM — the `Stop` hook
never fires, so `unregister` never runs), the session's row in
`active-sessions.<repo>.list` is never removed. The renewer has no way to distinguish
"session busy but alive" from "session dead," so it keeps calling `update()` for that
`session_id` forever, `last_seen`/`lease_expires_at` refresh forever, and the dead
session's ticket claim is **never reaped** — `_purge_stale` (daemon.py:217-249) never
sees a lapsed lease for it because the renewer is the one keeping it alive.

**Concrete approach (per review-v3 line 58-60, "cheapest fix"):**
1. `SessionStart` hook writes the session's own PID into its
   `active-sessions.<repo>.list` line (new field; today that file only exists as a
   design concept — check whether Phase 1 build already wrote a variant of it under a
   different name, e.g. via `bridge-watch.sh`'s own bookkeeping, before adding a new one).
2. Before each renewal tick, the renewer does a **same-host** `os.kill(session_pid, 0)`
   liveness check on that PID. This is valid here — unlike the cross-host PID check B1
   removed from the daemon's claim/purge path (which was broken because traffic crosses
   an SSH tunnel), the renewer runs **on the same host** as the session it's renewing for,
   so `os.kill(pid, 0)` is a legitimate same-process-tree liveness probe.
3. If the PID is dead, the renewer stops renewing that session and calls `unregister`
   (or lets the lease lapse naturally so `_purge_stale`'s graduated nudge→escalate→purge
   ladder reaps it) instead of calling `update()`.
4. Bound the renewal count as defense in depth even if the PID check has a gap (e.g. PID
   reuse by an unrelated process): cap renewals per session at some max (e.g.
   `MAX_RENEWALS_WITHOUT_LIVENESS_PROOF`) so a renewer bug can only extend a lease so far
   before requiring a fresh liveness proof, not renew unboundedly.

**Files:** `~/.config/opencode/session-bridge/bridge-renewer.py` or `.sh` (new, Phase 2,
per design-v3 §11 touch-points table — not yet created), whatever `SessionStart` hook
script writes the PID (new or amend), `daemon.py` only if the liveness check needs a new
lightweight RPC (prefer doing the PID check client-side in the renewer so the daemon
stays PID-agnostic, consistent with B1's removal of PID authority from the daemon).

**Acceptance test:** simulate a hard-crashed session — register a session, kill its PID
(`SIGKILL` a dummy sleep process used as the stand-in), let the renewer run its tick loop
against a scratch daemon/DB, and assert the session's lease is **not** renewed past the
point the PID died (i.e. `_purge_stale` eventually reaps it) — as opposed to the pre-fix
behavior where a mocked always-renewing renewer keeps `lease_expires_at` in the future
forever. Add to `test_daemon.py` or a new `test_renewer.py` alongside it.

---

## Deferred item 2 — bounded 120s auto-ack: decide and document the message-loss policy

**Problem.** `_process_read` (daemon.py:148-181) auto-acks (drops) any message that has
been visible for more than `REDELIVER_WINDOW_S` (default 120s, daemon.py:50) without an
explicit `ack()` — see the `age > REDELIVER_WINDOW_S` branch (daemon.py:177-180). This is
correct and intentional for Phase 0-1 (it bounds queue growth and prevents a permanently-
offline consumer from wedging another session's queue), but it means: if a session is
offline (crashed, not yet re-registered, watcher not yet started) for more than 120s
after a message was first delivered to it, that message is **silently lost** — auto-acked
without ever being acted on. Review-v3 (§10-AMEND context, `bridge-phase01-review.md`
ranked follow-up #3) flags this as dormant now (no push consumer exists yet in Phase 0-1)
but load-bearing once Phase 2's `poll_wait`/push watcher exists, because a push consumer
is exactly the case where "offline for >120s" becomes a real, not theoretical, scenario
(daemon restart, tunnel blip, watcher crash-loop).

**Concrete approach — decide one of:**
- **(a) Keep 120s, document the tradeoff.** Cheapest: no code change, just an explicit
  `SESSION.md`/`AGENTS.md` note that a message can be lost if the target session is
  offline >120s, and that idempotency-ledger-wrapped actions (item 4 below) should treat
  "did I get this message" as best-effort, not guaranteed — callers needing guaranteed
  delivery should use a different mechanism (e.g. a durable ticket/ledger write, not a
  bridge nudge).
- **(b) Raise the window / make it configurable per-message-type.** `BRIDGE_REDELIVER_WINDOW_S`
  is already an env var (daemon.py:50) — a caller-tunable "important" message type could
  get a longer window (e.g. 24h, same as `NUDGE_TTL_S`) while routine pings keep 120s.
  Requires threading a `redeliver_window_s` field through `nudge()`'s payload and
  `_process_read`'s per-message age check instead of the current single global constant.
- **(c) Escalate instead of silently auto-acking.** On the auto-ack branch (daemon.py:178),
  instead of just dropping, write a one-line stderr log (mirroring `_gc_nudge_ttl_all`'s
  existing GC-drop logging at daemon.py:213) so an operator watching daemon logs can
  see message loss happening, even if the design keeps the drop itself.
Recommend (c) as the Phase-2 minimum (cheap, non-breaking, closes the "silent" part of
"silent message loss" — matches the `AGENTS.md` framing that G1 was about eliminating
*silent* truncation/drop, not eliminating drop entirely) with (a)'s doc note regardless
of whether (b) is also built.

**Files:** `daemon.py` (`_process_read`, the auto-ack branch), `SESSION.md`/`AGENTS.md`
if (a)'s doc note is added, `test_daemon.py` for the new stderr-log assertion.

**Acceptance test:** a message delivered, never ack'd, read again after
`REDELIVER_WINDOW_S` has elapsed (mock `_now()` or use a small window in the test) →
assert it is returned exactly once more and then absent from `nudge_messages` on the
next read (already implicitly covered by existing behavior) **and** assert a stderr log
line was emitted naming the auto-acked message id, if (c) is built.

---

## Deferred item 3 — destructive→non-destructive nudge reads: daemon-restart cutover note

**Problem.** Phase 0-1 changed nudge reads from destructive (old: reading
`nudge_messages` cleared it immediately) to non-destructive (new: a message stays visible
until explicitly `ack()`'d or the redeliver window lapses — see `_process_read`,
daemon.py:148-181). `bridge-phase01-review.md` ranked follow-up #4 flags a back-compat
gap: **a legacy consumer that reads the `nudge_messages` array directly (not the
`nudges` counter) will re-see a nudge it already "consumed" for up to
`REDELIVER_WINDOW_S` (120s) after the semantics change takes effect** — i.e. after the
daemon is restarted running the new code. This only activates once (on the restart that
flips old→new behavior); it is not an ongoing steady-state issue, but it is a real
one-time surprise for any caller not yet updated to the `ack()` convention.

**Concrete approach:**
1. This is a docs/ops item, not a code fix — the non-destructive behavior is correct and
   intentional (that's the whole point of G1's redeliver/ack model). The fix is a cutover
   note, not a behavior change.
2. Add a short paragraph to the daemon restart/deploy runbook (wherever the Phase-1
   cutover steps live, or `SESSION.md` once it exists per design-v3 §11) stating: "the
   first `REDELIVER_WINDOW_S` (120s) after a daemon restart onto this code, any consumer
   reading `nudge_messages` directly instead of calling `ack()` may see an
   already-handled message repeated once. This is expected and self-resolving; no action
   needed unless a consumer's nudge-handling is not idempotent" — which is exactly why
   item 4 (idempotency ledger) matters for any consumer built after this point.
3. Cross-reference this note from wherever `bridge-watch.sh` (Phase 2's own new consumer)
   is documented, since it is the first real non-legacy consumer and should call `ack()`
   from day one rather than relying on redeliver-window tolerance.

**Files:** `SESSION.md` (new, per design-v3 §11 touch-point table, Phase 3 row — pull the
cutover note forward into whatever doc exists at the time this is built), or a
`fleet/HANDOFF-*.md` entry if `SESSION.md` doesn't exist yet when this item is picked up.

**Acceptance test:** none needed (documentation-only item) — reviewer check is "does the
runbook/handoff doc for the next daemon restart mention the 120s legacy-reread window."

---

## Deferred item 4 — wire `idempotency.py` into its actual consumer

**Problem.** `~/.config/opencode/session-bridge/idempotency.py` (built, tested
standalone) implements the G2 client-side dedup ledger exactly as design-v3 §8-AMEND
specifies: `claim(session_id, message_id)` does an atomic `INSERT OR IGNORE` against a
local `~/.charon/acted-ids.db` and returns whether this is the first time this
`(session_id, message_id)` pair has been seen; `gc()` prunes rows past `NUDGE_TTL_S`. The
module's own docstring (lines 1-24) states plainly: **"NOT yet wired into any consumer,
because the consumer the design specifies (`bridge-watch.sh`, the push watcher) is
Phase 2 and explicitly out of scope."** `bridge-watch.sh` does not exist yet (confirmed:
no `.sh` files in `~/.config/opencode/session-bridge/` as of this brief).

**Concrete approach (design-v3 §8-AMEND, "Sequence, on every wake"):**
1. Build `bridge-watch.sh` (design-v3 §10 Phase-2 row, §11 touch-points table) — the
   `poll_wait`-driven watcher loop with backoff+jitter+circuit-breaker (M3) and `flock`
   singleton (Mi1). This is the bulk of Phase 2's new code and is a prerequisite for this
   item, not a parallel task — the ledger has nothing to wire into until the watcher
   exists.
2. Inside the watcher's wake-handling path, wrap the action dispatch exactly as
   design-v3 §8-AMEND specifies: for each pending message, call
   `idempotency.claim(session_id, message["id"])`; if `True`, perform the message's
   side-effecting action then `ack()`; if `False` (already claimed — a redelivery),
   **skip the action** but still call `ack()` so the shared queue cleans up.
3. Tie `idempotency.gc()` to the same cadence as the daemon's own `NUDGE_TTL_S` GC
   (design-v3 §8-AMEND, "GC" section) — e.g. call it once per watcher startup or on a
   timer inside the watcher loop, not on every single wake (unnecessary DB churn).

**Files:** `~/.config/opencode/session-bridge/bridge-watch.sh` (new, Phase 2),
`~/.config/opencode/session-bridge/idempotency.py` (no change expected — already
correct per its own docstring; import and call only), new integration test exercising
watcher-wake → claim → skip-on-redelivery → ack, likely `test_bridge_watch.py` or folded
into wherever the watcher's own unit tests live.

**Acceptance test:** simulate two deliveries of the same `message_id` to the same
`session_id` (e.g. call the watcher's wake-handler function directly twice with the same
message dict) and assert the side-effecting action mock is invoked exactly once, while
`ack()` is called both times. This directly exercises the "at-least-once delivery,
at-most-once action" guarantee design-v3 §8-AMEND promises.

---

## Deferred item 5 — Phase-3 leftovers: `status` RPC, `bridge-status` CLI, kill-switch, `AGENTS.md` rewrite (G3)

**Problem.** Design-v2 §7 (unchanged/still-current per v3's "no CLOSED v2 item... is
touched" note, design-v3 line 32) specifies observability and an operator-only
kill-switch that closes the rest of G1. None of it is built yet — `daemon.py`'s own
docstring (lines 19-21) lists `status` RPC and the kill-switch as explicitly deferred.

**5a. `status` RPC (design-v2 §7, read-only, no token required — same trust model as
`board` today).** Returns `{ok, daemon: {repo, uptime_s, kill_switch, kill_switch_reason},
sessions: [{session_id, watch_mode, lease_expires_in_s, last_renewed_s_ago, ticket,
queue_depth, oldest_unacked_age_s, dropped_unacked_total}], waiters: {count}}` — add as a
new branch in `_dispatch` (daemon.py:424+), reusing `_row_to_dict`'s
`_PEER_VISIBLE_COLUMNS` allowlist per NB1 (review-v3 line 31: "The `status` RPC is
mandated to reuse `_row_to_dict`" — do not hand-roll a second serialization path that
could leak `lease_token`).

**5b. `bridge-status` CLI (design-v2 §7/§8, new script).** Calls `status` via `proxy.py`
for each configured repo socket and pretty-prints a merged table — the client-side
federated read that gives cross-repo visibility (M5) without ever crossing the two
daemons' write paths. New file `~/.config/opencode/session-bridge/bridge-status.sh`
(design-v2 §11 touch-points table).

**5c. Kill-switch (design-v2 §7, file sentinel, deliberately not a session-callable
RPC).** `~/.charon/bridge.disabled[.{repo}]` — if present, `_dispatch` rejects mutating
RPCs (`register/update/claim/release/nudge/poll_wait/ack`) with
`{ok:false, kill_switch:true, error:"bridge disabled: <reason>"}`; read-only RPCs
(`board`, `status`, `unregister`) keep working so sessions can see the drain and exit
cleanly. `bridge-killswitch.sh on <repo> "<reason>" / off <repo>` toggles the sentinel
file. Kept operator-only (a file check in `_dispatch`, not a tool a session can call) —
review-v3's deferred item (b) flags a pre-existing spec-labeling nit here: **`unregister`
is a real mutation** (`DELETE FROM sessions`, currently daemon.py:539) despite
being listed among the "read-only, still works during kill-switch" RPCs in design-v2 §7.
When implementing, either (i) keep `unregister` allowed during kill-switch deliberately
(so sessions can still exit cleanly, accepting it's technically a write) and document
that explicitly, or (ii) move it to the blocked list — pick one and state the reasoning
in the implementation's commit/doc, since the current spec text is ambiguous, not wrong.

**5d. `AGENTS.md` heartbeat-section rewrite (G3, design-v2 §9 + design-v3 line 488
"CLOSED... untouched").** Repo B, public: `/home/stack/code/charon/AGENTS.md` has two
"Session-bridge — keep alive (NEVER let it time out)" sections (lines 195-227 and a
near-duplicate at 307+ — confirm at build time whether these are genuinely duplicated
content that should be reconciled into one, or intentionally scoped to two different
audiences). Per design-v2 §9: rewrite to state the capability matrix — watcher-equipped
(push-mode, Phase-2-built) sessions drop the mandatory-heartbeat language entirely
(their lease is kept alive by the renewer, item 1 above, not by their own polling);
opencode/poll-mode sessions keep the heartbeat requirement unchanged. Also add one line
on the `ack()` convention: a watcher-woken session should `ack()` handled messages before
its `Stop` hook re-arms the watcher (not required for correctness — item 2's redeliver
window covers a missed ack — but keeps queues clean, per design-v2 §9's own phrasing).
This is a **Repo B, public-repo** change — run `PYTHONPATH=src python3 -m charon.cli gate`
(the `[public-clean]` check will scan the rewritten section; keep it placeholder-clean,
no literal hostnames/paths, matching the rest of `AGENTS.md`'s existing style) and
`PYTHONPATH=src python3 -m pytest -q` before committing.

**Files:** `daemon.py` (`_dispatch`, new `status` branch + kill-switch check gating the
mutating-RPC branches), `~/.config/opencode/session-bridge/bridge-status.sh` (new),
`~/.config/opencode/session-bridge/bridge-killswitch.sh` (new), `AGENTS.md` (Repo B,
both heartbeat sections).

**Acceptance test:** (5a) `status` response never contains the substring of any
minted `lease_token` in a test that registers a session and asserts on the serialized
`status` payload (same grep-based regression style review-v3 recommends for NB1, line
32). (5b) `bridge-status` output includes both repos' session lists when pointed at two
scratch sockets. (5c) a mutating RPC (`update`) returns `kill_switch:true` and does
**not** apply the write when the sentinel file is present; `board`/`status` still
succeed; toggling the sentinel off restores normal `update` behavior — assert with the
sentinel file created/removed via `tmp_path` in the test, not the real
`~/.charon/bridge.disabled` path. (5d) `charon gate` and `pytest -q` both green after
the `AGENTS.md` edit (Repo B, no `src/` or product-code change expected).

---

## Suggested build order

1. Item 4's prerequisite (`bridge-watch.sh`) and item 1 (renewer) first — both are
   Phase-2's actual new runtime processes and the rest of this brief either builds on
   top of them (item 4's wiring) or is independent docs/observability (items 2, 3, 5).
2. Item 2 (auto-ack policy decision) can land alongside item 1/4 since it touches the
   same `_process_read` code path the watcher will exercise for real the first time.
3. Item 3 (cutover doc note) is a five-minute addition once `SESSION.md` or an
   equivalent runbook exists — fold it into whichever of items 1/4/5 first creates that
   doc, rather than a standalone session.
4. Item 5 (status/kill-switch/bridge-status/AGENTS.md) is independent of 1/2/4 (pure
   additive observability + one Repo-B doc edit) and can be built in parallel or last.

## GATE (Repo B changes only — item 5d)
- `cd /home/stack/code/charon && PYTHONPATH=src python3 -m charon.cli gate`
- `PYTHONPATH=src python3 -m pytest -q`

Repo A (`~/.config/opencode/session-bridge/`) is not a git repo — its own test command
is `python3 -m pytest test_daemon.py -q` (and whatever new test files this brief adds)
run from that directory, against scratch DB/socket paths only. Never touch the live
`~/.charon/bridge.sock` daemon as part of building/testing this brief.

## LAST STEP
No push/merge implied by this brief — it is a spec handoff. Whoever picks up an item
follows the existing droid-brief convention (commit is required at the end of a build
session; pushing/merging is the manager's job; do NOT push).
