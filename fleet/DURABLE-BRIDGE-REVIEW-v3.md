# Focused Verification Gate — DURABLE-BRIDGE-DESIGN-v3.md

**Reviewer:** scoped convergence gate (read-only; design-only; no code/infra/push/SSH)
**Date:** 2026-07-06
**Target:** `fleet/DURABLE-BRIDGE-DESIGN-v3.md` (the fixes) vs `fleet/DURABLE-BRIDGE-REVIEW-v2.md` (required closures)
**Grounded against live code:** `~/.config/opencode/session-bridge/daemon.py` (607 lines),
`src/charon/gate_runner.py`, `src/charon/cli.py`, `tools/check_public_clean.py`, `.github/workflows/*.yml`.
Ran `tools/check_public_clean.py` against the live tree.

**VERDICT: BUILD GO-WITH-CONDITIONS for Phase 0–1.** Five of six required closures (NB1, NB2, M5, G2,
Mi2-patterns) hold under adversarial test and are grounded in the real code. One (NB3) is closed for the
stated defect but introduces a *new*, opposite-direction failure mode that is Phase-2-only. And the Mi2
*wiring* step, marked Phase 0, has a real precondition the design omits: wiring the guard into the gate as-is
turns the entire CI gate RED on the first commit. That one is the only Phase-0 must-fix.

---

## TASK 1 — do the six closures actually hold?

### NB1 (lease-token leak) — **CLOSED.** Verified total chokepoint.
`_row_to_dict` (daemon.py:117–151) is the **only** function that does a full-row `dict(row)`, and
`_board_result` (daemon.py:439–452) is its only full-row caller — confirmed by reading every RPC:
- `register`/`board` → `_board_result` → `_row_to_dict` (the allowlist path). ✓
- `update` selects **explicit columns** (`status, blockers, nudges, nudge_messages`, :307) and returns only
  `session_id` + the caller's own `nudge_messages`. No `SELECT *`. ✓
- `unregister` (`SELECT ticket`), `claim` (`SELECT name, repo` / `session_id, pid`), `release`, `nudge`
  (`SELECT nudges, nudge_messages`) — all explicit projections; `lease_token` never enters scope in any of
  them. ✓
So the allowlist in `_row_to_dict` **is** total, and it **fails closed**: any future column not in
`_PEER_VISIBLE_COLUMNS` is dropped by default. The design correctly keeps `lease_token` as a top-level
sibling minted as a local var in `register`, never a row round-trip. The `status` RPC is mandated to reuse
`_row_to_dict`. Regression test (substring-grep on serialized `board`/`status`) is the right assertion.
*Pre-existing note (not NB1, not a v3 regression):* `nudge_messages` is peer-visible through `board()` today
— every peer already reads every session's pending wake payloads. Out of scope here; flag for a later pass.

### NB2 (seq persistence + None/int sort) — **CLOSED.** Total order verified.
Persisted `seq_counter` single-row table, incremented in the **same** `with _db() as conn:` transaction as
the nudge write (daemon is single-threaded via `selectors`, so no concurrent-txn hazard; one `commit()` at
:432). Restart-proof: value read from disk. Per-recipient monotonicity is sufficient because ordering is only
needed per-recipient, and each recipient lives in exactly one repo → one daemon → one counter. ✓
The `_sort_key` = `(0, ts_or_"")` for legacy/None vs `(1, seq)` for seq'd is a genuine total order: the
first tuple element (0 vs 1, both int) always decides cross-group comparisons, so Python **never** compares
`None`/`str` to `int`. Within group 0 both are strings; within group 1 both ints. No crash path during or
after migration. Legacy-sorts-first is correct because pre-Phase-2 messages are strictly older. ✓

### NB3 (push-mode self-reap) — **CLOSED for the stated defect; NEW Phase-2 hole introduced.**
For the reviewed defect the fix holds: renew-on-wake is **synchronous before** the watcher exits (no
exit race), and the always-on `charon-bridge-renewer.service` (`Restart=always`, 20s tick) renews on a
turn-independent cadence, so a busy session cannot self-reap regardless of turn length. 120s TTL derivation
is now backed by a renewal source that is actually live during the turn. ✓
**But decoupling opens the opposite failure:** the renewer renews from `active-sessions.<repo>.list`, whose
line is removed only by graceful `unregister`/`Stop`. On a **hard crash** (SIGKILL/OOM — Stop never fires)
the line persists, the renewer keeps calling `update()` forever, `last_seen` refreshes forever, and — since
`os.kill` PID-liveness is cross-host-meaningless (that was B1) — the lease/claim of a **dead** session is
**never reaped**. This is a real new failure mode the v3 timeline table doesn't cover (it only models
"renewer alive + session alive"). It is **Phase 2** (renewer/watcher/lease-renewal are all Phase-2
touch-points), and its blast radius is "stale claim lingers," milder than the original live-reap. **Not a
Phase-0–1 blocker; must be closed when Phase 2 builds the renewer** — cheapest fix: `SessionStart` writes
the session PID into the list line, renewer does a **same-host** `os.kill(pid,0)` before renewing (same-host
PID check is valid, unlike the cross-host one B1 removed).

### M5 (cross-fleet isolation) — **CLOSED.** Real per-repo isolation.
Two independent tunnel units per client host (own `autossh`, own keepalive, own `Restart=always`): a
mediastack tunnel blip/reconnect no longer touches charon's forward. Two size-capped data mounts (loopback
ext4 or XFS project quota) bound each repo to its own disk cap, so repo-A cannot starve repo-B's SQLite
writes. Residual shared deps — **same sshd**, **same coordinator root fs** — are the *same failure domain as
"the single coordinator host is up,"* which the design deliberately never claimed to isolate (one coordinator
by design, v2 §3.3). A capped (even sparse) image can consume at most its virtual size on the host, so the
per-repo bound genuinely holds. M5's actual concern (one repo's activity harming the other) is closed. ✓

### G2 (double-action) — **CLOSED.** Idempotency ledger is correct.
`INSERT OR IGNORE` + rowcount on `(session_id, message_id)` PK is a sound atomic claim (SQLite's uniqueness
constraint is the compare-and-set). Crash between claim and action → redelivery sees rowcount=0 → action
**skipped** → at-most-once *invocation* (the design honestly names the residual "action crashed mid-way"
as orthogonal, which is the correct at-least-once↔at-most-once tradeoff). Skip-but-still-`ack` cleans the
shared queue. GC (`acted_at < now - NUDGE_TTL_S`, 24h) is keyed on *our* act-time ≥ message creation, so the
ledger entry always outlives the message's server-side redelivery window (over-retention = safe). Bounded. ✓

### Mi2 (guard wiring + patterns) — patterns **CLOSED**, but wiring has a Phase-0 precondition the design omits (see Task 3).
Grounded: `gate_runner.py` CHECKS has exactly the 5 entries the design names; `check_public_clean.py`
`_PATTERNS` is exactly as described (generic `10\.\d+…` **does** already match `10.0.1.x` — the design's own
admission is correct; the real gaps were the missing `192.168/16` + `172.16/12` ranges). ci.yml:38 runs
`python3 -m charon.cli gate` → `run_gate()` → iterates CHECKS, so a 6th CHECKS tuple **does** ride into CI
with no YAML change — the wiring *mechanism* is accurate. The added RFC1918 patterns + named coordinator
subnet + regression tests are all correct. **However** — see Task 3 — turning the guard on against the
current tree fails hard.

---

## TASK 2 — the 3 carried-forward OPEN items, ruled for Phase 0–1

**Phase 0 = local-compatible proxy shim. Phase 1 = cross-host daemon + tunnels. Push/durable delivery = Phase 2–3.**

- **(a) Bounded auto-ack message loss (`REDELIVER_WINDOW_S`) — DEFER to Phase 2.** Auto-ack lives entirely
  inside the push/redelivery delivery model, which is Phase 2. Not reachable in Phase 0–1 (no push queue yet).
- **(b) Kill-switch mislabels `unregister` as read-only — DEFER (non-blocker).** `unregister` is a real
  mutation (`DELETE FROM sessions`, daemon.py:354). This is a spec-labeling clarity nit, not a runtime bug;
  worst case an implementer mis-gates it. One-sentence doc clarification during the build that carries the
  kill-switch; no correctness exposure in Phase 0–1.
- **(c) Queue-cap vs auto-nudge inconsistency — DEFER to Phase 2.** The `MAX_QUEUE_LEN` cap is a Phase-2
  delivery addition; the inconsistency only exists once cap + auto-nudge coexist. *Sharper than the review
  stated:* the live `_purge_stale` (daemon.py:101–105) **overwrites** `nudge_messages` with a single
  auto-nudge (not "appends"), i.e. it currently **clobbers** any pending directed messages for a stale-but-
  alive session. That is a live pre-existing data-loss edge the Phase-2 durable-queue rewrite must reconcile,
  but it is not reachable as designed in Phase 0–1 and is not a v3 regression.

None of the three block Phase 0–1.

---

## TASK 3 — NEW ship-blocker introduced by v3

**YES — one, Phase 0. Wiring `check_public_clean.py` into the gate turns the whole CI gate RED on contact.**
The design's Mi2 Fix 1 (tagged **Phase 0**) adds `check_public_clean.py` to `gate_runner.py` CHECKS and
asserts it cleanly "rides existing `charon gate` → ci.yml, no YAML change." But I **ran the guard against the
live tree**: it returns **exit 1 with ~93 violations**, and `tools/.public-clean-exceptions.json` is **empty
(`{}`)**. The hits are all *legitimate, intentional, already-public* content:
- the `4-lom` runner label across `ci.yml`, `release.yml`, `heavy.yml`, `windows-exe.yml`,
  `actionlint.yaml`, and **`CONTRIBUTING.md`** (which documents the label to contributors on purpose);
- the `>=40-char hex` pattern firing on every **pinned GitHub Action SHA** (`actions/checkout@34e1148…`
  etc.) — a supply-chain best practice the repo deliberately uses.

So adding the CHECKS entry as-written makes `charon gate` fail immediately — blocking **all** CI for the
entire repo, not just bridge work. The design presents a false precondition (that the tree passes the guard).
This is a genuine v3-introduced Phase-0 blocker, and the fix is mechanical but **mandatory before/with the
wiring**: curate `tools/.public-clean-exceptions.json` (or add `public-clean: allow` waivers / context-narrow
the `4-lom` and hex-SHA patterns) so the current tree is green *first*, then flip on the CHECKS entry in the
same change. (NB1/NB2/M5/G2 introduce no new blocker.)

---

## Must-fix-during-build (Phase 0–1)

1. **[Phase 0, BLOCKER]** Before/with wiring `check_public_clean.py` into `gate_runner.py` CHECKS: green the
   current tree — populate `tools/.public-clean-exceptions.json` for the ~93 legitimate `4-lom` + pinned-SHA
   hits (or narrow those two patterns). Verify `charon gate` passes locally before the CHECKS entry lands, or
   CI goes red repo-wide.
2. **[Phase 2, track now]** NB3 renewer must not renew a hard-crashed session forever — add a same-host
   `os.kill(session_pid,0)` liveness check (session PID written into `active-sessions.<repo>.list`) before
   each renew; otherwise the lease-reaping guarantee is defeated for OOM/SIGKILL exits.
3. **[Phase 2, track now]** The durable-queue rewrite must reconcile `_purge_stale`'s clobber of
   `nudge_messages` (daemon.py:101–105) with the ack/replay queue, and reconcile `MAX_QUEUE_LEN` vs the
   daemon's own auto-nudge writes (carried item c).

**BUILD GO-WITH-CONDITIONS for Phase 0–1** — proceed; land must-fix #1 as part of the Mi2 change; carry #2/#3
into the Phase-2 build brief.
