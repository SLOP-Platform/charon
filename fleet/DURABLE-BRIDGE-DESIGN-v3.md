# ADR (v3): Durable, Cross-Host, Push-Notifying Session Bridge — targeted defect closure

**Status:** PROPOSED v3 (design-only — no code, no infra/config/opencode.json changes, no push, no SSH)
**Date:** 2026-07-06
**Scope:** BUILD-RIG infra (the fleet session-bridge). NOT the Charon product.
**Supersedes:** `DURABLE-BRIDGE-DESIGN-v2.md` (v2), in response to `DURABLE-BRIDGE-REVIEW-v2.md`
(verdict: REWORK — architecture PASSED, three new-in-v2 blockers + three residual majors found).
**Relationship to ADR-0008 / obol:** unchanged from v1/v2 — orthogonal, rig-only, not coupled to obol,
not leaked into the product (memory: product-vs-build-rig-boundary).

**This is NOT a re-architecture.** The re-review explicitly passed the v2 architecture (lease model,
per-fleet process isolation, ack/replay, static-enrollment anti-split-brain, dedicated coordinator host).
Every v2 section not amended below is carried forward **unchanged** — see §0 for the closure map. v3
touches exactly six things: NB1, NB2, NB3, M5(partial residue), G2, Mi2. Section numbers below are
prefixed with the v2 section they amend (e.g. **§4-AMEND** amends v2 §4) so this reads as a diff, not a
rewrite. Where a v2 section is not listed, it stands as-is — do not re-derive it from this document alone.

---

## 0. Closure map — what changed and why (read this first)

| Item | v2 verdict | v3 mechanism | v3 verdict |
|---|---|---|---|
| NB1 — lease token leaks via `SELECT *`/`dict(row)` | **SHIP-BLOCKER** | Allowlist serialization chokepoint in `_row_to_dict` (daemon.py:117–151); `status` RPC reuses the same function, no second `SELECT *` | **CLOSED** — §6-AMEND |
| NB2 — `seq` in-memory, resets on restart; None/int sort crash | **SHIP-BLOCKER** | DB-backed single-row persisted counter (`seq_counter` table), incremented in the same transaction as the nudge write; sort key is `(has_seq, seq_or_ts)` — total-order-safe with legacy no-seq rows | **CLOSED** — §7-AMEND |
| NB3 — push-mode TTL (120s) shorter than a woken turn; self-reap mid-work | **SHIP-BLOCKER** | Lease renewal decoupled from watcher/turn cycle: always-running renewer daemon (`charon-bridge-renewer.service`, `Restart=always`, ticks every 20s) + renew-on-wake before the watcher exits. TTL now backed by the renewer's guaranteed cadence, not by "was `poll_wait` in flight" | **CLOSED** — §5-AMEND |
| M5 — two shared failure domains re-introduced (one tunnel, one filesystem) | **PARTIAL** | Two independent tunnel units per client host (one per repo); two disk-quota-isolated data mounts on `$COORDINATOR_HOST` (one per repo) | **CLOSED** — §9-AMEND |
| G2 — at-least-once redelivery risks double-action; no consumer dedup | **STILL-OPEN** | Client-side idempotency ledger (local SQLite, `(session_id, message_id)` PK) checked-then-claimed via `INSERT OR IGNORE` before any side-effecting action; `ack()` is the cleanup step, not the dedup gate | **CLOSED** — §8-AMEND |
| Mi2 — guard exists but unwired, and pattern-incomplete for the coordinator's real address form | **WEAKER THAN STATED** | Guard wired into `charon gate` (→ CI, already invoked by ci.yml) via `gate_runner.py` CHECKS; new `.pre-commit-config.yaml` local hook; new named pattern for the coordinator's LAN octet family + broadened RFC1918 coverage | **CLOSED** — §10-AMEND |

**Everything else stands exactly as v2 left it** — see the full re-verified table in §11 (this document's
closing table). No CLOSED v2 item (B1, B2, M1, M2, M3, M6, G3, G4, Mi1, Mi3, Mi4, Mi5) is touched,
reargued, or reopened below.

One adjacent, zero-new-scope correction, made only because it sits one sentence away from the NB3 fix and
costs nothing to fix while touching that text: v2 §12 claimed DEFECT 1 is killed "for *every* session type
… by construction," which the re-review correctly flagged as false for poll-mode (opencode) — poll-mode's
600s TTL still depends on the model's own call cadence, unchanged from today, and that was never in either
review's required-closure list. §5-AMEND restates §12's language to match the (already-honest, unchanged)
capability matrix instead of contradicting it. This is not a new fix; it's removing a contradiction next to
one.

---

## §5-AMEND (amends v2 §4 "Lease model" and §12 consequences) — NB3: decoupling renewal from the turn cycle

### The defect, restated precisely
v2's push-mode lease renews only when `poll_wait` is actually in flight (on reissue, on timeout, on wake).
But on wake the watcher **exits 0** so the harness can re-invoke the session, and v2 §11 re-arms it on the
**`Stop`** hook — i.e., at the *end* of the woken turn. During the turn itself (the only time real work
happens — the entire reason a wake exists) there is no watcher process and no `poll_wait` in flight. A
120s TTL against an unbounded turn duration is a live-reap gap, not a tuning number to raise: raising the
constant doesn't fix a renewal mechanism that isn't running during the window that matters.

### Fix: sever renewal from turn/watcher state entirely
Two changes, both required, doing different jobs:

**1. An always-running renewer, independent of the watcher and independent of turn state.**
New unit: `charon-bridge-renewer.service` (client host, `systemd --user`, `Restart=always`) running
`bridge-renew.sh` — a tiny loop, *not* the watcher, *not* spawned per-turn:
```
while true; do
  for f in ~/.charon/active-sessions.*.list; do        # one line per locally-active session_id
    while read -r session_id lease_token repo; do
      proxy.py update session_id="$session_id"          # renew-only; no status/blockers change
    done < "$f"
  done
  sleep "$RENEW_TICK_S"     # 20s
done
```
`~/.charon/active-sessions.<repo>.list` is written by the `SessionStart` hook at register time (one line:
`session_id lease_token repo`) and the line is removed by `unregister`/the `Stop` hook. This process has no
knowledge of turns, watchers, or `poll_wait` — it renews on a flat wall-clock cadence for as long as the
session is registered, full stop. If the renewer itself dies, `Restart=always` brings it back within
systemd's default restart delay (seconds), not minutes.

**2. Renew-on-wake, synchronous, before the watcher exits.**
`bridge-watch.sh`'s `poll_wait` return handler calls `update(session_id)` once, synchronously, **before**
exiting 0 to let the harness re-invoke — this is the "AND renew-on-wake before processing" half of the
fix. It closes the worst-case gap between "wake happens" and "the renewer's next tick" (up to
`RENEW_TICK_S`), so the lease is freshly renewed at the exact moment the turn starts, not just periodically
during it.

Together: renew-on-wake guarantees a fresh renewal at turn-start; the independent renewer guarantees
renewal keeps happening every `RENEW_TICK_S` for the rest of the turn, **no matter how long the turn
runs**, because it is not gated on the turn, the watcher, or `poll_wait` at all.

### Re-deriving `LEASE_PUSH_TTL_S` (was: assumed `poll_wait` in flight — false; now: backed by the renewer)
```
RENEW_TICK_S          = 20   # bridge-renew.sh loop interval — OS-scheduled, turn-independent
RENEW_MISS_TOLERANCE  = 3    # tolerate up to 3 missed ticks (transient renewer hiccup, GC pause, etc.)
SSH_KEEPALIVE_BOUND_S = 45   # unchanged from v2 §4 — worst-case time for a dead tunnel to surface
LEASE_PUSH_TTL_S = RENEW_TICK_S * RENEW_MISS_TOLERANCE + SSH_KEEPALIVE_BOUND_S + 15   # = 120s
```
Same numeric value as v2 (120s) — **the number didn't need to change; what it's derived from did.** v2's
120s assumed the renewal source (`poll_wait`) was live throughout the turn, which was false. v3's 120s is
derived from a renewal source (the independent renewer) that genuinely is live throughout the turn,
turn-length notwithstanding.

### Worked timeline — proving a busy session cannot self-reap
Assume a wake at `T+0` and a turn that runs for an unusually long 10 minutes (600s) of continuous work —
well past both v2's broken 120s and v1's original 600s DEFECT-1 horizon:

| Time | Event | `lease_expires_at` after event |
|---|---|---|
| T+0 | `poll_wait` returns `{woke:true}`; renew-on-wake fires synchronously | T+120 |
| T+0 | watcher exits 0; harness re-invokes the session; turn begins | (unchanged) |
| T+20 | renewer tick (independent of turn/watcher) | T+140 |
| T+40 | renewer tick | T+160 |
| T+60 … T+580 | renewer ticks every 20s, 26 more times, entirely independent of what the turn is doing | keeps rolling forward, always ≥ now+100s |
| T+600 | turn ends; `Stop` hook re-arms watcher; watcher issues fresh `poll_wait` | T+700ish (poll-registration also renews per §5 v2, unchanged) |

At no point does `lease_expires_at` fall behind `now` while the renewer process is alive — the margin
never drops below `RENEW_TICK_S * RENEW_MISS_TOLERANCE + SSH_KEEPALIVE_BOUND_S` regardless of turn length,
because renewal frequency is a property of the renewer's own loop, not of the turn. The **only** way the
lease lapses under a live session is if the renewer process itself is down for the full tolerance window —
which is a genuine liveness failure (host crash, `systemd --user` session torn down), correctly reaped, not
a false positive.

### Push-mode vs poll-mode TTL, reconciled
| Mode | Renewal driver | Cadence guarantee | TTL | Self-reap-while-alive risk |
|---|---|---|---|---|
| **Push** (watcher-equipped, e.g. Claude Code) | `charon-bridge-renewer.service` (OS-scheduled, `Restart=always`) + renew-on-wake | Every 20s, guaranteed by systemd, decoupled from turn/watcher state | 120s | **None**, for any turn length, as long as the renewer process is alive (the only failure mode is host/session-manager death, which is a real liveness failure) |
| **Poll** (opencode, no persistent process) | Model-issued `update()`/`board()` calls | No OS-level guarantee — model's own call cadence | 600s (unchanged from today) | **Unchanged, accepted, documented** (the original DEFECT-1 scenario for silent runs > 600s) — not a v3 regression, not in this pass's required-closure list; carried forward exactly as v2 §4/§12's honest capability matrix states |

§12's consequences section is restated (not re-derived) to read: *"Kills DEFECT 1 (false reaps) for
push-mode sessions by construction, independent of turn length. Poll-mode's DEFECT-1 exposure (silent runs
exceeding 600s) is unchanged from today and remains an accepted, documented limitation — see the capability
matrix above."* This removes the B1-review-flagged overstatement without touching anything that was
CLOSED.

### New touch-points (additive to v2 §11's table)
| File | Change | Phase |
|---|---|---|
| `~/.config/opencode/session-bridge/bridge-renew.sh` **(new)** | Independent renewer loop (above); reads `active-sessions.<repo>.list`, calls `update()` per session every `RENEW_TICK_S` | 2 |
| `~/.config/systemd/user/charon-bridge-renewer.service` **(new, client hosts)** | `Restart=always`, runs `bridge-renew.sh` | 2 |
| `~/.charon/active-sessions.<repo>.list` **(new, gitignored, ephemeral)** | One line per locally-active session (`session_id lease_token repo`); written by `SessionStart` hook, line removed by `unregister`/`Stop` | 2 |
| `~/.config/opencode/session-bridge/bridge-watch.sh` | Amend (not new): renew-on-wake call added to the `poll_wait`-return handler, before exit | 2 |

---

## §6-AMEND (amends v2 §4/§7 secret handling) — NB1: redaction by construction, single chokepoint

### The defect, restated precisely
`_board_result` (daemon.py:439–452) runs `SELECT * FROM sessions` (lines 443/445); `_row_to_dict`
(daemon.py:117–151) does `d = dict(row)` (line 120) — every column, unconditionally. v2's §4 schema adds
`lease_token` as a column. The moment that column exists, it flows unredacted through `_board_result` →
`board()`/`register()`'s embedded board → **every session** that ever calls `board()`. Any peer can read
another session's `lease_token` and impersonate its `poll_wait` renewal / steal its claim — the exact thing
the lease was invented to prevent. This is a security defect inside the newly-designed core, not a
pre-existing one to route around.

### Fix: allowlist, not denylist, at the one function every peer-visible response already funnels through
`_row_to_dict` (daemon.py:117–151) **is already the single serialization chokepoint** — `_board_result`
(called by both `register` and `board`) is its only caller today, and v3's new `status` RPC is *required*
to call it too (below), not a second hand-rolled `SELECT *`. The fix changes what that one function
constructs the dict from:

```python
# daemon.py — replace the `d = dict(row)` line (was line 120) with an allowlist, not a denylist:
_PEER_VISIBLE_COLUMNS = frozenset({
    "session_id", "name", "ticket", "status", "blockers", "repo",
    "registered_at", "last_seen", "last_status_change", "branch",
    "files", "busy", "nudges", "nudge_messages",
    "pid",                 # decorative only (Mi5) — never read for correctness
    "lease_expires_at",    # NOT secret — an expiry timestamp reveals nothing exploitable,
                           # and status/observability (§7) needs it to show lease_expires_in_s
})
# lease_token is deliberately absent — this is an allowlist, so *any future secret column*
# is excluded by default, not just the ones we remember to deny today.

def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = {k: row[k] for k in _PEER_VISIBLE_COLUMNS if k in row.keys()}
    ...  # rest of the function (json.loads on blockers/files/nudge_messages, age_seconds,
         #  expiring_soon, stall_seconds, etc.) is unchanged — it only ever read from `d`
```
Why allowlist over denylist: a denylist (`d.pop("lease_token", None)`) only protects against the *specific*
secret column someone remembered to pop. An allowlist means a schema change that adds a next secret column
(anything) is **excluded by default** until a human deliberately adds it to `_PEER_VISIBLE_COLUMNS` — the
single-chokepoint guarantee the re-review asked for ("how do you guarantee no future column leaks") is
structural, not a matter of remembering.

### `lease_token` is still returned — just never through this path
`register`'s own dispatch handler (daemon.py:261–280 today) keeps `lease_token` as a **local Python
variable**, minted at registration, and attaches it to the **top level** of its own response dict directly
— `{"ok": True, "session_id": sid, "lease_token": lease_token, "board": _board_result(conn, ...)}`. The
`board` sub-object is built via `_row_to_dict`/the allowlist (redacted); the top-level `lease_token` field
is a sibling key the allowlist never touches, because it was never a row round-trip in the first place. No
other RPC (`board`, `update`, the new `status`) ever puts `lease_token` in scope.

### `status` RPC (v2 §7) — reuses the same chokepoint, closing the reviewer's stated follow-on risk
The re-review flagged that `status` "will inherit the same `SELECT *` risk" if implemented naively. v3
mandates: `status`'s `sessions` array is built by calling the **same** `_row_to_dict` over the **same**
`SELECT * FROM sessions` query (safe now, because redaction lives in `_row_to_dict`, not in the query) —
never a hand-written second projection. Anyone implementing `status` who tries to add a *new* field reads
it from the already-redacted `d`, not from a fresh `dict(row)`.

### Regression test (spec, not code — names the exact assertion for the implementer)
Add to `tests/test_bridge_daemon.py` (or wherever daemon unit tests land): register a session, call
`board()` and `status()`, assert the string `lease_token` value returned by `register` does **not** appear
anywhere in `json.dumps(board_response)` or `json.dumps(status_response)`. This is a substring/grep
assertion on the serialized response, not a schema assertion — it catches the leak even if some future
change reintroduces it via a different code path.

---

## §7-AMEND (amends v2 §6 "Durable delivery") — NB2: persisted, restart-proof, migration-safe `seq`

### The defect, restated precisely
v2 §6 defines `seq` as "in-memory, process-global counter." Two concrete failures: (1) `Restart=always`
(guaranteed by design, §11) resets the counter to its initial value, so post-restart nudges get **low**
`seq` values that sort *before* pre-restart un-acked messages with high `seq` — replay order breaks across
the single most common operational event. (2) During Phase 1→2 rollout, pre-existing messages have no
`seq` at all (`.get(..., None)`); sorting a list containing both `None` and `int` raises `TypeError` in
Python, so the *entire* board/update read for that session throws — total, not partial, unavailability.

### Fix part 1 — persisted, transactionally-consistent counter (closes "resets on restart")
```sql
CREATE TABLE IF NOT EXISTS seq_counter (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    next_seq INTEGER NOT NULL DEFAULT 1
);
INSERT OR IGNORE INTO seq_counter (id, next_seq) VALUES (1, 1);
```
One row, one daemon (per-repo, per §8 isolation — each daemon has its own DB, so its own counter; no
cross-daemon coordination is needed because ordering is only ever required per-recipient within one repo's
pool). In the `nudge()` handler (daemon.py:409–433 today), inside the **same** `with _db() as conn:`
transaction that writes the new `nudge_messages` array:
```python
row = conn.execute("SELECT next_seq FROM seq_counter WHERE id = 1").fetchone()
seq = row["next_seq"]
conn.execute("UPDATE seq_counter SET next_seq = ? WHERE id = 1", (seq + 1,))
nudge_obj["seq"] = seq
# ... existing nudge_messages append + UPDATE, same conn.commit() as today
```
Because the counter increment and the message write commit atomically together, a crash between them is
impossible (SQLite's single transaction either both happens or neither does) — there is no window where a
message exists with no `seq` reserved for it, and no window where the counter advances without a
corresponding message. Restart is a non-event: the counter's value is read from disk, not memory, so it
picks up exactly where it left off regardless of how many times `Restart=always` fires.

### Fix part 2 — total-order-safe sort across a None/int mix (closes the migration-window crash)
The read path (v2 §6, board()/update()) sorts unacked messages before returning them. Messages written
before Phase 2 (no `seq` field, but they do carry the pre-existing `ts` field) and messages written after
(have `seq`) can coexist in the same array during and immediately after the Phase 1→2 rollout. The sort key
must total-order both groups without ever comparing `None` to `int`:
```python
def _sort_key(m: dict) -> tuple:
    seq = m.get("seq")
    if seq is None:
        return (0, m.get("ts") or "")   # legacy, pre-seq: always sorts before any seq'd message
    return (1, seq)                      # seq'd: sorted by seq within this group

messages = sorted(unacked, key=_sort_key)
```
This is correct **during** migration (legacy no-seq messages, being strictly older, always sort first,
ordered among themselves by their existing `ts`) and correct **after** migration (once every legacy message
has been acked or GC'd via the existing `NUDGE_TTL_S` path, only group `(1, seq)` remains, which is exactly
v2's intended pure-seq ordering) — no separate backfill migration step, no code path that ever calls
Python's `<` on a `None` and an `int`.

### Why this doesn't touch anything already CLOSED
Nothing in v2's ack/GC/replay/wire-frame-truncation design (the rest of §6) changes — `seq` was always
meant to be "monotonic, collision-proof, no wall-clock ambiguity"; v3 keeps exactly that property, it just
grounds it in a durable table instead of a process-lifetime variable, and defines a total-order sort key
that survives the one migration window v2 didn't specify.

---

## §9-AMEND (amends v2 §8 "Per-fleet isolation") — M5: closing the residual coupling

The re-review found process isolation genuinely real (two daemons, two DBs, two selector loops — unchanged,
still true) but flagged **two new shared failure domains** v2 introduced while closing the original M5:

### (a) One shared client SSH tunnel → closed with two independent tunnel units
v2 §8: "One SSH tunnel unit can carry both forwards … so this is operationally one tunnel, not two, per
client host." A blip/restart of that one tunnel drops push for **both** fleets simultaneously on that host
— exactly the coupling M5 was meant to eliminate, just moved from the daemon to the transport. **Fix:**
one tunnel unit **per repo**, per client host:
- `charon-bridge-tunnel-charon.service` — `autossh`/`ssh -N -L <charon-sock-forward>`, its own
  `ServerAliveInterval`/`CountMax`, its own `Restart=always`.
- `charon-bridge-tunnel-mediastack.service` — same, independent process, independent forward.

A charon-tunnel restart (network blip, `ssh` reconnect backoff) has zero effect on the mediastack tunnel's
socket, and vice versa — the isolation promise now holds at the transport layer, not just the daemon layer.
Operationally this is "two tunnels instead of one" per client host — the accepted cost is explicitly named
in §12's Negative/accepted list (below), not hidden.

### (b) Shared filesystem/no quota → closed with per-repo disk isolation
v2 §8: both DBs/WAL files live under the same `~/.charon` path on `$COORDINATOR_HOST` with no quota; a
mediastack WAL/queue bloat (v1 already observed a 1.2MB WAL under storm conditions) can fill the disk and
fail charon's SQLite writes even though charon's own daemon is healthy. **Fix:** each repo's data directory
is isolated onto its own size-capped mount:
- `~/.charon/charon-data/` — mounted from a dedicated sparse loopback image (e.g., `/var/lib/
  charon-bridge/charon.img`, ext4, capped e.g. 512MB), mounted via a `charon-bridge-data-charon.mount`
  systemd unit.
- `~/.charon/mediastack-data/` — same pattern, its own image, its own mount unit.
(If `$COORDINATOR_HOST`'s root filesystem is XFS, an XFS project quota on each subdirectory is an equally
valid, lighter-weight alternative to a loopback image — either satisfies the requirement; the loopback
image is specified as the default because it works on any filesystem, not just XFS.)

A repo hitting its disk cap gets a normal SQLite `disk full`/`database or disk is full` error **on its own
writes only** — the other repo's daemon, on its own filesystem, is entirely unaffected. This is the hard
OS-level backstop; v2 §6's `MAX_QUEUE_LEN`/`MAX_QUEUE_BYTES`/`NUDGE_TTL_S` application-level caps (unchanged,
still in force) are the soft backstop that should prevent this from ever being hit in practice — the quota
exists for the case those caps are misconfigured or bypassed by a bug, not as the primary defense.

### What stays exactly as v2 said
Two processes, two sockets, two DBs, one crash domain each, `bridge-status` as a client-side federated read
dialing both sockets — **unchanged**. Only the tunnel and the disk are newly separated.

### Amended touch-points table (additive to v2 §11)
| File | Change | Phase |
|---|---|---|
| `~/.config/systemd/user/charon-bridge-tunnel-charon.service` **(new, client hosts)** | Replaces the single dual-forward tunnel unit; own `autossh`, own keepalive, own `Restart=always` | 1 |
| `~/.config/systemd/user/charon-bridge-tunnel-mediastack.service` **(new, client hosts)** | Same, independent | 1 |
| `/var/lib/charon-bridge/charon.img`, `mediastack.img` **(new, `$COORDINATOR_HOST`)** | Size-capped loopback ext4 images, one per repo | 1 |
| `~/.config/systemd/user/charon-bridge-data-charon.mount`, `...-mediastack.mount` **(new, `$COORDINATOR_HOST`)** | Mounts the per-repo image at `~/.charon/<repo>-data/`; daemon's `DB_PATH`/`SOCK_PATH` for that repo point inside its own mount | 1 |

---

## §8-AMEND (amends v2 §6 delivery model) — G2: consumer-side idempotency, closing double-action risk

### The defect, restated precisely
v2's delivery model (ack/replay/GC, unchanged and still sound) is genuinely at-least-once. At-least-once
means a message can be delivered, acted on, and — if the acting session crashes or reconnects before
`ack()` lands — **redelivered** and acted on **again**. For any side-effecting nudge (spawn a droid, kick
off a build, post a PR comment), that is double-execution, not a benign duplicate read. v2 never specified
consumer-side dedup; the re-review correctly named this a compounding of a pre-existing gap (v1's G2,
"non-interrupting/coalesced wakes"), now sharper because delivery is genuinely at-least-once.

### Fix: a local idempotency ledger, checked-then-claimed before any action, ack'd after
This lives **client-side** (colocated with whatever process performs the wake's action — today that's
`bridge-watch.sh` / the harness turn it triggers), **not** on the coordinator daemon — it is a consumer
concern, and keeping it client-side means the daemon's job stays exactly what v2 §6 already specifies
(at-least-once delivery with ordering/replay/GC), no new server-side state or RPC.

```sql
-- ~/.charon/acted-ids.db (new, local, gitignored, one file per client host)
CREATE TABLE IF NOT EXISTS acted_message_ids (
    session_id  TEXT NOT NULL,
    message_id  TEXT NOT NULL,
    acted_at    TEXT NOT NULL,
    PRIMARY KEY (session_id, message_id)
);
```
Sequence, on every wake (whether via `poll_wait` or a plain `board()`/`update()` read):
1. Fetch the pending (unacked) message set, as v2 §6 already returns it.
2. For each message, attempt `INSERT OR IGNORE INTO acted_message_ids VALUES (session_id, message_id, now)`
   and check the SQLite rowcount.
   - **rowcount = 1** (first time this session has seen this id): this is the atomic "claim" — proceed to
     perform the message's side-effecting action.
   - **rowcount = 0** (already claimed — a redelivery of a message this session already acted on): **skip
     the action entirely**, but still call `ack(session_id, lease_token, [message_id])` so the shared queue
     gets cleaned up (the action was already done; only the ack was missing).
3. After the action completes (only in the rowcount=1 branch), call `ack()` as v2 §6 already specifies.

The `INSERT OR IGNORE` + rowcount check is the atomic claim primitive — SQLite's own `PRIMARY KEY`
uniqueness constraint does the compare-and-set, so there is no separate lock to get wrong. A crash between
step 2's claim and step 3's action-completion is safe by construction: on restart/redelivery, the ledger
already shows this `(session_id, message_id)` as claimed, so the action is (correctly) **not** repeated —
the worst case is a message whose action started but never finished, which is a "did the action itself
crash mid-way" problem, orthogonal to and out of scope for delivery-layer dedup (same as it would be for
any at-least-once system; the ledger's job is only "never invoke the action twice for the same id," not
"guarantee the action itself is transactional").

### GC — bounded, tied to the same horizon as the server-side queue
`acted_message_ids` rows are pruned on the same cadence as the daemon's own `NUDGE_TTL_S` GC (v2 §6, default
24h): `DELETE FROM acted_message_ids WHERE acted_at < now - NUDGE_TTL_S`. Once a message has aged out of the
server's own queue (acked or force-dropped), there is no way for it to be redelivered, so there is nothing
left for the local ledger to protect against past that horizon — bounded growth, one small local SQLite
file, no unbounded accumulation.

### New touch-points (additive to v2 §11)
| File | Change | Phase |
|---|---|---|
| `~/.charon/acted-ids.db` **(new, local, gitignored, per client host)** | Idempotency ledger, schema above | 2 |
| `~/.config/opencode/session-bridge/bridge-watch.sh` | Amend (not new): claim-before-act / skip-and-ack-if-already-claimed logic wraps the action dispatch; GC tied to `NUDGE_TTL_S` | 2 |

---

## §10-AMEND (amends v2 §9 Mi2) — wiring the guard for real, and closing the pattern gap

### The defect, restated precisely
v2 §9/§11 states the leak-safety story rests entirely on `tools/check_public_clean.py`. Verified against
the live repo: the guard is **not** in `gate_runner.py`'s `CHECKS` list (`src/charon/gate_runner.py:6–12` —
five entries: ruff, mypy, SLOP-boundary, version, gate-registry; `check_public_clean.py` is absent), **not**
referenced anywhere in `.github/workflows/*.yml`, and there is **no** `.pre-commit-config.yaml` in the repo
at all (only the untouched `.git/hooks/pre-commit.sample`). It runs only when a human remembers to invoke
it manually, or indirectly via `tests/test_public_clean.py`'s unit tests (which test the function in
isolation, not the whole tree). Additionally, its pattern list (`tools/check_public_clean.py:11–18`) only
covers a bare `10\.\d+\.\d+\.\d+` (any 10.0.0.0/8 address, generic) plus `4-?lom`/`charon-?vm`/
`/home/stack`/`charon-private`/40+-char hex — nothing names the coordinator's actual subnet explicitly, and
nothing covers the other two RFC1918 ranges at all, so a `$COORDINATOR_HOST` interface on `172.16/12` or
`192.168/16` would sail past entirely.

### Fix 1 — wire into CI (rides the existing `charon gate` step, no new CI step needed)
Add one entry to `CHECKS` in `src/charon/gate_runner.py` (currently lines 6–12), as the 6th tuple:
```python
CHECKS: list[tuple[list[str], str]] = [
    (["ruff", "check", "src", "tests"], "ruff"),
    (["mypy", "src", "tests"], "mypy"),
    (["python3", "tools/check_boundary.py", "src"], "SLOP-boundary"),
    (["python3", "tools/check_version.py"], "version"),
    (["python3", "tools/check_gate_registry.py"], "gate-registry"),
    (["python3", "tools/check_public_clean.py"], "public-clean"),   # NEW
]
```
`.github/workflows/ci.yml`'s existing `charon gate (lint, type, boundary, version, gate-registry)` step
(ci.yml:37–38) already runs `python3 -m charon.cli gate`, which calls `run_gate()`, which iterates
`CHECKS` — so this one-line addition to `gate_runner.py` is sufficient; **no change to any workflow YAML is
needed**. This closes "not wired into CI" without adding a new job/step to maintain.

### Fix 2 — wire into pre-commit (new file — none exists today)
New `.pre-commit-config.yaml` (repo root):
```yaml
repos:
  - repo: local
    hooks:
      - id: public-clean
        name: public-clean (no personal/internal info in tracked files)
        entry: python3 tools/check_public_clean.py
        language: system
        pass_filenames: false     # the tool walks `git ls-files` itself, not the changed-file set
        always_run: true
```
Documented (README/CONTRIBUTING, Phase 3 doc touch-point below) as requiring one manual `pre-commit
install` per contributor clone — same as any standard pre-commit adoption; this is the first pre-commit
hook in the repo, so it is new infra, not a reuse of existing infra, and is called out as such rather than
implied to already exist.

### Fix 3 — close the pattern gap for the coordinator's real address form
Add to `_PATTERNS` in `tools/check_public_clean.py` (currently lines 11–18), after the existing generic
`10\.\d+\.\d+\.\d+` entry:
```python
(re.compile(r'10\.0\.1\.\d+'), 'coordinator LAN subnet (10.0.1.0/24)'),   # NEW — named, explicit;
    # redundant with the generic 10.x pattern above by design (defense in depth: this survives even if
    # the generic pattern is ever narrowed/refactored, because it names the coordinator's actual
    # subnet directly rather than relying on a broad bucket to happen to cover it)
(re.compile(r'192\.168\.\d+\.\d+'), 'internal IP (192.168.0.0/16)'),      # NEW — RFC1918 coverage gap
(re.compile(r'172\.(1[6-9]|2\d|3[01])\.\d+\.\d+'), 'internal IP (172.16.0.0/12)'),  # NEW — same
```
Verified (`python3 -c` against the live regex): the existing generic `10\.\d+\.\d+\.\d+` **already**
matches `10.0.1.x` today — so this was never a silent hole in the narrow "does 10.0.1.x match" sense. The
gap the re-review actually found is broader: (a) the guard wasn't *running* automatically at all (Fix 1/2
close that, and it dominates — an unwired guard with perfect patterns still catches nothing), and (b) the
coordinator (`$COORDINATOR_HOST`) is a **third, neutral host**, per v2 §3.3 — nothing in this design
guarantees its real interface is even in the 10.0.0.0/8 range the way 4-LOM's is, so the other two RFC1918
ranges were a genuine, previously-uncovered gap regardless of the specific-subnet question. The new named
`10.0.1.\d+` pattern is added anyway, explicitly, as defense-in-depth so the coordinator's subnet has its
own dedicated, testable guard entry rather than depending solely on the generic bucket.

Regression tests (spec, add to `tests/test_public_clean.py`, same style as the existing eight): one asserts
`10.0.1.42` is flagged by name (`"coordinator LAN subnet"` in the violation string), one each for a
`192.168.x.x` and a `172.20.x.x` sample.

### New/amended touch-points (additive to v2 §11)
| File | Change | Phase |
|---|---|---|
| `src/charon/gate_runner.py` | Add `public-clean` as a 6th `CHECKS` entry (rides existing `charon gate` → ci.yml wiring, no YAML change) | 0 |
| `.pre-commit-config.yaml` **(new)** | Local hook running `check_public_clean.py`, `always_run: true` | 0 |
| `tools/check_public_clean.py` | Add named `10.0.1.\d+` pattern + `192.168.\d+.\d+` + `172.(16-31).\d+.\d+` patterns to `_PATTERNS` | 0 |
| `tests/test_public_clean.py` | Add 3 regression tests for the new patterns | 0 |
| `README.md`/`CONTRIBUTING.md` | One line: `pre-commit install` after clone | 3 |

This upgrades Mi2 from "the guard exists, unverified whether it runs" to "the guard runs on every push (CI)
and every local commit (pre-commit), with an explicit test suite proving it, before Phase 1 ever touches a
real coordinator host." Non-blocking, but now closed rather than deferred.

---

## 11. Full closure table (v1 → v2 → v3, supersedes v2's table)

| Finding | v1→v2 | v2→v3 | v3 status |
|---|---|---|---|
| B1 — PID category error | CLOSED | untouched | **CLOSED** |
| B2 — lost-wakeup race | CLOSED | untouched | **CLOSED** |
| B3 — keepalive/grace derivation | PARTIAL (in-turn gap = NB3) | in-turn gap closed via §5-AMEND | **CLOSED** |
| M1 — waiter reverse-index | CLOSED | untouched | **CLOSED** |
| M2 — split-brain from local-daemon degrade | CLOSED | untouched | **CLOSED** |
| M3 — wake/re-invoke storm, no backoff | CLOSED (in spec) | untouched | **CLOSED (in spec)** |
| M5 — cross-fleet coupling | PARTIAL (shared tunnel + shared disk) | both closed, §9-AMEND | **CLOSED** |
| M6 — opencode overstatement | CLOSED as honesty (undercut by §12) | §12 contradiction removed, §5-AMEND | **CLOSED** |
| G1 — delivery/ordering/replay/GC/observability/kill-switch | PARTIAL (NB1, NB2, G2 residual) | NB1/NB2/G2 all closed | **CLOSED** |
| G2 — non-interrupting/coalesced/dedup | STILL-OPEN | consumer-side idempotency ledger, §8-AMEND | **CLOSED** |
| G3 — AGENTS.md migration | CLOSED | untouched | **CLOSED** |
| G4 — bridge-health.py + mailbox independence | CLOSED | untouched | **CLOSED** |
| Mi1 — watcher singleton | CLOSED | untouched | **CLOSED** |
| Mi2 — guard reuse | CLOSED, weaker than stated | wired into CI + pre-commit + pattern gap, §10-AMEND | **CLOSED** |
| Mi3 — path clarity | CLOSED | untouched | **CLOSED** |
| Mi4 — clock skew | CLOSED | untouched | **CLOSED** |
| Mi5 — `import struct` placement | CLOSED | untouched | **CLOSED** |
| **NB1** — lease token leak via `SELECT *` | *(new in v2)* | allowlist chokepoint, §6-AMEND | **CLOSED** |
| **NB2** — `seq` in-memory / None-int sort crash | *(new in v2)* | persisted counter + total-order sort key, §7-AMEND | **CLOSED** |
| **NB3** — push-mode self-reap mid-work | *(new in v2)* | decoupled renewer + renew-on-wake, §5-AMEND | **CLOSED** |
| DEFECT-1 poll-mode / §12 overstatement (majors, not required this pass) | — | §12 restated for consistency (zero-scope adjacent fix) | **CLOSED** (bonus) |
| Bounded auto-ack loss (`REDELIVER_WINDOW_S`) | tunable, accepted (v2 §12 open questions) | unchanged — not in this pass's required list | **OPEN, accepted/tunable** — carried forward, not silently dropped |
| Kill-switch mislabels `unregister` as read-only (minor) | v2 re-review minor | unchanged — not in this pass's required list | **OPEN, minor** — carried forward |
| Queue-cap vs auto-nudge-append inconsistency (minor) | v2 re-review minor | unchanged — not in this pass's required list | **OPEN, minor** — carried forward |

The three rows explicitly marked **OPEN, carried forward** were named by the re-review but were not in
this pass's required-closure scope (NB1/NB2/NB3/M5/G2/Mi2) — they are listed here rather than dropped, per
standing practice of never letting a known finding go silent. They are candidates for the next review pass,
not blockers to Phase 0/1 of this ADR.

---

## 12. Consequences — amendments only (v2's Positive/Negative lists otherwise stand)

**Additional positive (v3):**
- The lease/auth model is now actually load-bearing — NB1's fix means the confidentiality property §4/§5
  assert is structurally true, not asserted-but-violated by an inherited read path.
- Delivery ordering survives the single most common operational event (daemon restart) and the single
  riskiest window (Phase 1→2 rollout) without a crash or a silent reorder.
- A live, busy session cannot be reaped out from under itself regardless of turn length — the exact
  motivating DEFECT-1 scenario, now genuinely closed for push-mode, not just relocated to a shorter horizon.
- Redelivery — an inherent property of at-least-once delivery, correctly kept rather than removed — no
  longer risks double-executing a side effect.
- Per-fleet isolation now holds at every layer (process, tunnel, disk), not just the process layer.
- The leak-safety story is enforced automatically (CI + pre-commit), not aspirational.

**Additional negative / accepted (v3):**
- One more always-running process per client host (`charon-bridge-renewer.service`) — small, but another
  thing to monitor, alongside the watcher and the tunnel(s).
- Two tunnel units instead of one per client host (M5 fix) — doubles the tunnel-management surface in
  exchange for genuine isolation; named explicitly, not hidden inside "operationally one tunnel."
- A new small local SQLite ledger (`acted-ids.db`) per client host — bounded by the same TTL as the
  server-side queue, but it is new local state to reason about.
- `gate_runner.py`'s `CHECKS` list grows by one; `charon gate` takes marginally longer (a full tracked-file
  regex sweep — cheap, but non-zero).

**Open questions carried forward from v2 §12 (unchanged, not re-litigated):**
- `LEASE_POLL_TTL_S` (600s), `REDELIVER_WINDOW_S` (120s), `NUDGE_TTL_S` (24h), `MAX_QUEUE_LEN`/
  `MAX_QUEUE_BYTES` under real subagent-duration data — reasoned defaults, not measured.
- Whether opencode ever gains a hook surface capable of holding a long-lived process (revisits M6/poll-mode
  ceiling, not a blocker).

**New open question (v3):**
- `RENEW_TICK_S` (20s) / `RENEW_MISS_TOLERANCE` (3) are reasoned, not measured, exactly like v2's other
  constants — same epistemic status, flagged the same way, not overstated as validated.
