# BRIDGE CONVERGE TRIAGE — Phase 1 (read-only, 2026-07-27)

## Ticket status table

| Ticket | Real status | Evidence | Verdict |
|--------|------------|----------|---------|
| D24-SESSION-CTL-SPIKE | **already-in-master** | `spike/session-ctl` tip c74e85b IS merge-base; 0 commits in `master..spike/session-ctl`; `fleet/session-ctl.sh` exists in master (151 lines, verified via `bash fleet/session-ctl.sh` prints usage). Worktree at `/home/stack/charon-private-wt/D24-SESSION-CTL-SPIKE` exists but HEAD is master tip 8962967 (stale). | **RETIRE** |
| BRIDGE-REPLACE-PHASE1 | **already-in-master** | `feat/bridge-replace-phase1` tip 3b7d9a5 IS ancestor of master; landed at merge commit 656cb89 ("land: BRIDGE-REPLACE-PHASE1 — HTTP control plane adapter + summary.sh migration"). `fleet/session-ctl.sh:1-151` (expanded from spike 60→151 lines), `fleet/summary.sh:119` now calls `session-ctl.sh -R … board` instead of `session-bridge_board`, `fleet/tests/session-ctl.test.sh` exists (203 lines). Worktree stale (HEAD at master). | **RETIRE** |
| DROID-BRIDGE-REGISTER | **already-in-master** | `feat/droid-bridge-register` tip 128605a IS ancestor of master. `fleet/droid-bridge.sh` exists (175 lines, shells to proxy.py), `fleet/tests/droid-bridge.test.sh` (338 lines, 42/0 tests per handoff note f2b85ee), `fleet/fleet-droid.sh:730-783` has push-mode register+heartbeat+unregister wiring. Actual build work was on `fix/DROID-CLIENT-PREFLIGHT-PATH` (8f0a4e5 "push mode — a droid that idles until the manager dispatches work"), also in master. Worktree stale. | **RETIRE** |
| BRIDGE-PROXY-HEARTBEAT | **already-built** (unlanded board ticket) | `~/.config/opencode/session-bridge/proxy.py:98-192` HAS heartbeat: `_heartbeat_interval` (TTL/3), `_send_heartbeat` via threading.Timer (`:148`), `_start_heartbeat` (`:153`) gated on `BRIDGE_PROXY_NO_HEARTBEAT`, `atexit.register(_cleanup)` (`:190`), SIGTERM/SIGINT → `_handle_signal` (`:191-192`), `_cleanup` cancels timer + calls unregister (`:164-182`). Built at commit `9ee20d2` ("proxy: heartbeat the lease and unregister on exit"). Test harness: `test_proxy.py` (345 lines, 4 tests), `verify_idle_proof.py`, `verify_kill_proof.py`. Board ticket is stale — code exists, ticket was never retired. | **RETIRE** |
| DURABLE-BRIDGE-PHASE-2 | **parked** | File is `fleet/board/DURABLE-BRIDGE-PHASE-2.md.parked` (`.parked` suffix). Filed 2026-07-08. No worktree, no branch. Two action items noted in its `note:` (confirm owns paths, add D&S to brief) have not been done. | **PARK** |

## True consumer count

DURABLE-BRIDGE-PHASE-2 states "5 remaining consumers" (filed 2026-07-08). That count is **stale — the actual number is higher** because DROID-BRIDGE-REGISTER (landed after) added new consumers:

### Runtime consumers of `~/.config/opencode/session-bridge/` (7 total)

| # | File | What it does | How |
|---|------|-------------|-----|
| 1 | `fleet/droid-bridge.sh` `:37-38` | Full bridge client (register/poll/unregister/claim/nudge) | Shells to `~/.config/opencode/session-bridge/proxy.py` directly |
| 2 | `fleet/fleet-droid.sh` `:730-783` | Push mode: register/heartbeat/unregister via bridge | Calls droid-bridge.sh; tick IS heartbeat (board() as refresh) |
| 3 | `fleet/capability/availability.py` `:27-109` | Live availability probe | Shells to proxy.py via subprocess |
| 4 | `fleet/capability/assign.py` `:45,439-443` | Claim via bridge after recommendation | Calls availability.py + MCP `claim` tool |
| 5 | `fleet/dark-work-check.sh` `:45,54,79-176` | Dark work detection | Reads bridge SQLite DB at `~/.charon/session-bridge.db` |
| 6 | `fleet/handoff.sh` `:232-260` | Auto-pull bridge board into handoff | Reads bridge SQLite DB via python3 |
| 7 | `fleet/checks/bridge-health.py` `:1-23` | Health check (register+unregister round-trip) | Shells to proxy.py |

### Already migrated (1)
| # | File | Evidence |
|---|------|----------|
| — | `fleet/summary.sh` `:118-119` | Now uses `session-ctl.sh -R … board` (HTTP control plane), replaces `session-bridge_board` |

### Informational only (not runtime)
| # | File | Evidence |
|---|------|----------|
| — | `fleet/end-session.sh` `:572-573` | Prints "session-bridge" section header, no API call |
| — | `fleet/handoff-check.sh` `:24` | Regex checks for bridge section existence |

**Before DROID-BRIDGE-REGISTER:** 5 runtime consumers (~match DURABLE-BRIDGE-PHASE-2).
**After DROID-BRIDGE-REGISTER:** 7 runtime consumers (+2: droid-bridge.sh, fleet-droid.sh push mode).

## Contradictions found (LOUD — these contradict the brief, the tickets, or each other)

### C1: BRIDGE-REPLACE-PHASE1 vs DROID-BRIDGE-REGISTER — OPPOSITE GOALS
BRIDGE-REPLACE-PHASE1 `:2` says **replace** the bridge. DROID-BRIDGE-REGISTER `:1,42,103-111` says **wire droids INTO** the bridge (register/heartbeat/unregister-trap/pickup-gate + push mode). Both are P0, both landed in master. The bridge grew MORE consumers at the same moment the replacement started. BRIDGE-REPLACE-PHASE1's own text `:33-34` says "This ticket takes the only collision-free slice" because the rest was supposed to migrate inside owners' tickets later — but instead of migrating off, the droids moved ONTO the bridge.

### C2: BRIDGE-REPLACE-PHASE1 `depends_on: D24-SESSION-CTL-SPIKE` is a NO-OP
The ticket declares `dep-kind: build` and says "TRUE build prereq and shared single-owner... Land the spike first, then build on it." But the spike (c74e85b) was already merged before BRIDGE-REPLACE-PHASE1 even started — both are ancestors of master and the spike's `session-ctl.sh` was already in the tree. The declared `depends_on` was satisfied before the ticket was ever claimed. This is a paperwork edge, not a blocker.

### C3: BRIDGE-PROXY-HEARTBEAT declared "moot" — but the replacement has stalled
BRIDGE-REPLACE-PHASE1 `:75-76`: "Makes moot: BRIDGE-PROXY-HEARTBEAT's nudge-clearing defect... `steer` replaces the nudge queue entirely." True for the nudge queue, but FALSE for the heartbeat/liveness hole. The replacement migrated 1 of 7 consumers, made zero progress on the other 6, and the bridge is STILL the liveness backbone for fleet-droid.sh's push mode. Sessions continue to go dark while working. The heartbeat hole is **not moot by proxy work** — it is a live P0 harm.

### C4: D24-SESSION-CTL-SPIKE ticket exists in master but the ticket content still claims it's on a branch
`fleet/board/D24-SESSION-CTL-SPIKE.md` exists at master HEAD and declares `branch: spike/session-ctl`. The spike landed. The ticket is stale. Same for BRIDGE-REPLACE-PHASE1 and DROID-BRIDGE-REGISTER boards — all three board tickets exist in master declaring work on branches whose content is already in master. This is board hygiene debt.

## Phase 2 verification — hermetic test transcripts (RED → GREEN)

All tests in `test_proxy.py` pass against an isolated daemon (TTL=10s for speed):

```
=== RED-PROOF: heartbeat disabled → session purged ===
test_proxy.py::test_heartbeat_disabled_session_is_purged PASSED          [100%]
============================== 1 passed in 30.69s ==============================

=== GREEN-PROOF: heartbeat keeps idle session alive past TTL ===
test_proxy.py::test_idle_session_survives_ttl_with_heartbeat PASSED      [100%]
============================== 1 passed in 15.69s ==============================

=== NON-VACUOUS: short wait does not falsely pass ===
test_proxy.py::test_short_wait_does_not_falsely_pass PASSED              [100%]
============================== 1 passed in 3.66s ===============================

=== KILL-TEST: proxy death removes entry and releases ticket ===
test_proxy.py::test_kill_proxy_removes_entry PASSED                      [ 20%]
=== HEARTBEAT-STOPS: killed proxy stops refreshing ===
test_proxy.py::test_killed_proxy_does_not_keep_refreshing PASSED         [ 40%]
```

Full suite: 5 passed in 72.00s. Exit code 0.

## Recommended sequence

```
1. VERIFY HEARTBEAT (DONE in Phase 2)
   └─ Code exists at proxy.py:98-192 (commit 9ee20d2). Run hermetic tests (red/green).
   └─ Status: heartbeat is built and testable. The board ticket just needs retirement.

2. Retire stale board tickets (REPORT-ONLY — propose, do not execute)
   └─ D24-SESSION-CTL-SPIKE: RETIRE — all content in master
   └─ BRIDGE-REPLACE-PHASE1: RETIRE — landed at 656cb89
   └─ DROID-BRIDGE-REGISTER: RETIRE — content in master via fix/DROID-CLIENT-PREFLIGHT-PATH
   └─ BRIDGE-PROXY-HEARTBEAT: RETIRE — built at 9ee20d2, verified via tests
   └─ DURABLE-BRIDGE-PHASE-2: stays PARKED — re-scope when replacement resumes

3. RESOLVE THE CONTRADICTION (REPORT-ONLY — propose, do not execute)
   └─ BRIDGE-REPLACE-PHASE1's replacement direction is correct per decision 34.
   └─ DROID-BRIDGE-REGISTER's wiring of droids INTO the bridge is ANTAGONISTIC to replacement.
   └─ Proposal: migrate droid-bridge.sh OFF proxy.py and onto session-ctl.sh (HTTP control plane)
     as the next consumer migration. This is the single change that both advances replacement
     AND undoes the contradiction.
   └─ fleet-droid.sh already calls droid-bridge.sh as a middleware; replace bridge calls with
     session-ctl equivalents. The push-mode tick-as-heartbeat concept translates cleanly.

4. DURABLE-BRIDGE-PHASE-2 (PARKED — do not un-park yet)
   └─ Only un-park when consumer count reaches 0 or when replacement is formally abandoned.
```
