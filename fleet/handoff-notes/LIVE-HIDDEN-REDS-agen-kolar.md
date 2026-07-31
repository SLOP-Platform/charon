# LIVE HIDDEN REDS — inert enforcement checks, run for real (read-only)

**Scope:** `/home/stack/charon-private` @ `9055478` (master) + `/home/stack/code/charon` @ `6782236`.
**Mode:** PROPOSE-ONLY. Nothing was reaped, cleared, killed, archived, or modified. No `--fix`,
no `--apply`, no reaper invoked. Checks were run in their default read-only reporting mode.
**Run at:** epoch `1784934895` (2026-07-24 ~16:14 local).

---

## 0. Why these were invisible (the inertness itself)

| Check | Wired into? | How the RED is lost |
|---|---|---|
| `fleet/stale-check.sh` | **nothing** — only caller in the tree is its own test `fleet/tests/stale-check.test.sh` | Fully inert. It even self-narrates: *"standalone check — preflight.sh should call this; not wired in here"*. Also **exits rc=0 while printing `2 issue(s)`** — so even if wired, it would not fail a gate. |
| `fleet/dark-work-check.sh` | `fleet/watchdog/discover-services.sh:130` (`leg_dark`) → sets `RED=1` correctly | Swallowed one level up: `fleet/foreman-cadence.sh:153` = `bash "$wdir/discover-services.sh" 2>&1 \|\| true`. `fleet/status.sh:24` also only prints an advisory line. Direct run gives **rc=1**. |

Two distinct defects: stale-check is *unreachable AND non-failing*; dark-work-check is *reachable
and correctly RED* but its exit code is discarded by the cadence caller.

---

## 1. `fleet/stale-check.sh` — verbatim result (rc=0 despite 2 issues)

```
STALE-CHECK  threshold=900s
STALE  REGISTRY-META-CATALOG  claimed-by=ticket:  age=13728s  threshold=900s
QUARANTINED  GRACEFUL-DEGRADE  droid=frontier-3656758  since=2026-07-23T20:54:17Z
             reason=repeated zero-commit re-claims (claim->no-op->release spin)
  2 issue(s)
```

Confirmed current state (not trusting the scan's older numbers):
- `fleet/state/claims/` contains **exactly one** file: `REGISTRY-META-CATALOG`.
- `fleet/state/loop-guard/` contains **exactly one** quarantine: `GRACEFUL-DEGRADE`.
  `LITELLM-CI-DEPS` and `STRANDED-WORK-AUDIT` quarantines are **gone** — the earlier clear is real.
- The reported age is **13728s (~3.8h)**, not the ~10,591s in the class scan — it is still aging
  because the heartbeat (`1784921152`) is not being refreshed, even though the session is alive.

---

## 2. `fleet/dark-work-check.sh` — direct run, **rc=1** (real, currently swallowed)

2 DARK sessions (register leg) + 9 STRANDED jobs (pickup leg). The scan's "~3 dark" is now 2.

---

## 3. Full item table

Legend — **Live?**: owner process alive / worktree advancing. **At-risk**: commits or edits that
exist on no remote and in no other tree.

### 3a. Stale claim + loop-guard

| # | Item | Age | Live or dead | At-risk work | Proposed disposition |
|---|---|---|---|---|---|
| 1 | claim `fleet/state/claims/REGISTRY-META-CATALOG` (wt `/home/stack/charon-private-wt/REGISTRY-META-CATALOG`, branch `feat/registry-meta-catalog` @ `78dd0c7`) | 13728s (~3.8h) since heartbeat | **LIVE — one of the four active sub-sessions** | **YES — 2 commits ahead of master, on NO remote** (`78dd0c7` reconcile-catalog-after-refresh, `ad5fe51` index-only registry-of-registries + fail-closed discovery). Worktree clean. | **DO-NOT-TOUCH / preserve.** The claim is stale only because the heartbeat is not refreshed and the owner field is malformed (`claimed-by=ticket:`, no PID) — it is a *heartbeat/format* bug, not a dead claim. Reaping it would strand 2 unpushed commits. Fix the heartbeat writer later; do not touch the claim now. |
| 2 | loop-guard quarantine `fleet/state/loop-guard/GRACEFUL-DEGRADE` (droid `frontier-3656758`, count=2/threshold=2) | since 2026-07-23T20:54:17Z (~19h) | **DEAD** — PID 3656758 not alive (`kill -0` fails) | **NO** — the quarantine reason is literally *zero-commit re-claims*; there is no worktree and no unmerged branch for it in the rig repo. (`feat/graceful-degrade` exists only in the **code** repo and **is on `origin`**.) | **Leave in place (do not clear).** It is a correct, load-bearing quarantine of a spinning droid. Clearing it re-opens the claim→no-op→release loop. Revisit only when the underlying GRACEFUL-DEGRADE ticket is re-scoped. |

### 3b. Dark sessions (register leg) — both benign false positives

| # | Item | Age | Live or dead | At-risk work | Proposed disposition |
|---|---|---|---|---|---|
| 3 | pid `1794003` `claude` | 1h11m | **LIVE** | None (no worktree of its own) | **Leave.** This is the operator's own coordinator Claude session — it is dark only because interactive `claude` never self-registers on the session-bridge. Killing it kills the session issuing this review. |
| 4 | pid `1794037` `python3 …/session-bridge/proxy.py` | 1h11m | **LIVE** | None | **Leave — and fix the check.** This process *is* the session-bridge proxy; the check flags the bridge itself as "not on the bridge". This is a detector bug (the `CRITICAL_REGEX`/register leg should exempt the proxy), not dark work. |

### 3c. Stranded jobs (pickup leg) — all 9 owner PIDs are DEAD

| # | Job | Ticket | Age | Live? | At-risk work | Proposed disposition |
|---|---|---|---|---|---|---|
| 5 | `strong-976340-DIFF-COVER-MUTMUT-ADOPT` | DIFF-COVER-MUTMUT-ADOPT | 22724s (~6.3h) | PID 976340 **DEAD** | **YES — HIGHEST RISK.** `/home/stack/code/charon-fleet-DIFF-COVER-FIX`, branch `feat/diff-cover-mutmut-adopt` @ `404881d`, **3 commits, +692/-1 over 8 files, on NO remote and in NO other tree.** See §4. | **LAND (or at minimum push the branch) before anything else.** Do not reap this worktree. |
| 6 | `strong-976945-LITELLM-CI-DEPS` | LITELLM-CI-DEPS | 22553s (~6.3h) | PID **DEAD** | **NO.** `/home/stack/code/charon-fleet-LITELLM-CI-DEPS` is at `6782236` = master, clean, 0 ahead; `feat/litellm-ci-deps` also exists on `origin`. | **Reap the job record** (or `--waive` with "no-op run, branch already on origin"). Worktree may be pruned. |
| 7 | `strong-978142-LITELLM-CI-DEPS` | LITELLM-CI-DEPS | 22031s (~6.1h) | PID **DEAD** | **NO** (same worktree as #6; duplicate re-launch) | **Reap the job record / waive.** Duplicate launch is itself the signal — this ticket re-launched twice with zero commits, i.e. the same failure class the GRACEFUL-DEGRADE quarantine caught. Consider a loop-guard entry rather than a silent reap. |
| 8 | `frontier-1486567-GRACEFUL-DEGRADE` | GRACEFUL-DEGRADE | 760655s (~8.8d) | PID **DEAD** | **NO** — zero-commit spin; `feat/graceful-degrade` is on `origin` in the code repo | **Reap / waive** ("superseded by loop-guard quarantine"). |
| 9 | `frontier-25951-GRACEFUL-DEGRADE` | GRACEFUL-DEGRADE | 722126s (~8.4d) | PID **DEAD** | **NO** | **Reap / waive** (same). |
| 10 | `frontier-3697177-GRACEFUL-DEGRADE` | GRACEFUL-DEGRADE | 748158s (~8.7d) | PID **DEAD** | **NO** | **Reap / waive** (same). |
| 11 | `frontier-387675-BROADEN-TIER-CHAINS` | BROADEN-TIER-CHAINS | 773109s (~8.9d) | PID **DEAD** | **NO** — `feat/broaden-tier-chains` exists on **both** `origin` and `gitea` in the rig repo; no worktree | **Reap / waive**; if the branch is still wanted, open a PR — but nothing can be lost. |
| 12 | `frontier-4162762-BUILD-SERVER-EPHEMERAL-PORT` | BUILD-SERVER-EPHEMERAL-PORT | 1032039s (~11.9d) | PID **DEAD** | **NO** — `fix/build-server-ephemeral-port` on `origin`; no worktree | **Reap / waive.** |
| 13 | `frontier-65779-R46-BALANCE-WIRE` | R46-BALANCE-WIRE | 1030666s (~11.9d) | PID **DEAD** | **NO** — `feat/r46-balance-wire` on `origin`; no worktree | **Reap / waive.** |

Note on 8–13: six of the nine strandings are **8–12 days old**. The pickup leg has been RED and
unheard for nearly two weeks — this is the concrete cost of the `|| true` at
`fleet/foreman-cadence.sh:153`.

### 3d. Worktree cross-check — everything else holding UNPUSHED commits

Full sweep of both repos' `git worktree list` for commits reachable from HEAD but on **no remote**.

| # | Worktree | Branch | Unpushed | Live? | What would be lost | Proposed disposition |
|---|---|---|---|---|---|---|
| 14 | `/home/stack/code/charon-fleet-DIFF-COVER-FIX` | `feat/diff-cover-mutmut-adopt` | **3** | dead (job #5) | see §4 | **LAND — top priority.** |
| 15 | `/home/stack/charon-private-wt/REGISTRY-META-CATALOG` | `feat/registry-meta-catalog` | **2** | **LIVE sub-session** | registry-of-registries + fail-closed discovery + catalog reconcile | **DO-NOT-TOUCH.** Owning session will push. |
| 16 | `/home/stack/charon-private-wt/FLEET-DEMAND-BROKER` | `feat/FLEET-DEMAND-DRIVEN-ROUTING-avail-cap` | **1** (+4 modified files, was 2-ahead minutes earlier → actively advancing) | **LIVE sub-session** | capped-exclusion dispatcher wiring + cost-band spill-up, in flight | **DO-NOT-TOUCH.** |
| 17 | `/home/stack/code/charon-wt-GATE-REENTRANCY` | `fix/gate-reentrancy-guard` @ `2b6d2ad` | **1** | dead (no process; .git mtime 2026-07-24 15:24 — recent but no owner) | `tools/gate_contract.py` (+106) and `tests/test_gate_reentrancy.py` (+317); +497/-3 over 4 files, gate↔test-suite recursion guard. Exists nowhere else. | **PRESERVE then LAND.** Second-highest loss risk. Verify with the operator that no session owns it before any reap. |
| 18 | `/home/stack/code/charon-fleet-router-ledger-decay` | `feat/router-ledger-decay` @ `d7caabb` | **1** + 1 uncommitted (`docs/review-log/ROUTER-LEDGER-DECAY.md` modified) | dead (mtime 2026-07-23 12:15) | `src/charon/routing_policy/ledger_decay.py` (+79) and `tests/test_ledger_decay.py` (+186); +312 over 4 files, **plus** uncommitted review-log edits. NB: the rig repo has a same-named `feat/router-ledger-decay` worktree — **different repo, different content**; it does not back this up. | **PRESERVE / land.** Commit the review-log edit first or it is lost separately. |
| 19 | `/home/stack/code/charon/.claude/worktrees/agent-a4896ad6d2bfe5d06` | `feat/gateway-litellm-live-wire` @ `42a7440` | **1** | dead (mtime 2026-07-21 00:28) | `tools/dogfood_litellm_live_probe.py` (+190) and `DOGFOOD-litellm-live.txt` (+51). Commit subject is an explicit **STOP, do not half-migrate the money-path** finding — evidence, not just code. | **PRESERVE.** Land the probe + evidence, or at least push the branch; a deliberate stop-signal is exactly the thing that must not vanish. |
| 20 | `/home/stack/code/charon-fleet-LITELLM-SPIKE` | `spike/litellm-router-adapter` @ `f2cee9d` | **1** | dead (mtime 2026-07-19 14:15) | `spike_litellm/` adapter + runner, +394 over 4 files — proves `litellm.Router` fits under Charon's policy layer. Untracked `.litellm-venv/` is cruft. | **PRESERVE (push branch), low urgency.** It is a spike; its value is the finding. Do not reap silently. |
| 21 | `/home/stack/code/charon-fleet-INERT-INSTANCE-DETECT` | `feat/inert-instance-detect` | 0 ahead, **4 modified files uncommitted** | dead | Uncommitted edits only; ticket is already in `fleet/state/needs-push/` | **Preserve until pushed** — it is the one entry in `needs-push`, so it is already tracked; just complete the push. |
| 22 | 25 × `charon-fleet-dogfood-*` worktrees (PROVIDER-URL-HELPER / RFL-3 / SECRET-HOTROTATE, 2026-07-14/15) | `dogfood-eval/*` | 0 ahead; 0–4 dirty each = eval scratch | dead | **NO** — dirty files are eval run artifacts, all ~9–10 days old | **Reap (bulk), after the items above are landed.** These are the bulk of the worktree sprawl and carry no unlanded source. |
| 23 | `order-a`, `charon-wt-meter-kwh`, `agent-a4294af67f9d41d80`, `agent-ab00727b804e8f8db`, `charon-fleet-BENCH-OOB-GRADING`, `charon-fleet-EVAL-CONTROL-GATE-FIX`, `charon-fleet-LITELLM-COST-FIELD-FIX` | various | 1 ahead each, **all pushed** | dead | **NO** | **Reap when convenient** — commits are on a remote. |
| 24 | rig worktrees `ISSUE-BOARD-SURFACE`(5 dirty), `WORK-LEASE-GATE`(1), `HANDOFF-NAME-ALLOCATOR`(1), `STRANDED-WORK-DETECT`, `FIXTURE-BYPASS-GATE`, `ISSUE-BOARD-DEMO` | various | 0 unpushed; uncommitted edits only | dead | Uncommitted working-tree edits only — small, but they *are* unique | **Leave / triage individually.** No commit loss; a reaper that deletes worktrees would still discard these edits. |
| 25 | `/home/stack/charon-private-wt/WATCHDOG-RESTART-VERIFY` (7 modified + 3 untracked, incl. new `fleet/tests/verify-restart-cmds.test.sh`) and `/home/stack/charon-private-wt/META-GATE-CALLSITE` (2 modified) | — | 0 committed yet | **LIVE — owner PIDs 1299378 / 1171066 confirmed alive with cwd in the worktree** | **YES, and uncommitted** — a reap right now destroys in-flight, never-committed work | **DO-NOT-TOUCH.** |

---

## 4. Loss-risk ranking (highest first)

1. **`/home/stack/code/charon-fleet-DIFF-COVER-FIX` — `feat/diff-cover-mutmut-adopt` @ `404881d`, 3 commits, on no remote.**
   Exactly what is lost if reaped: `tools/diff_cover_gate.py` (+150), `tools/mutmut_diff_gate.py` (+190),
   `tests/test_diff_cover_mutmut_gate.py` (+269), `tools/gates.json` (+26, two new gate registrations),
   `.github/workflows/ci.yml` (+6), `src/charon/gate_runner.py` (+2), `pyproject.toml` (+5/-1),
   `docs/review-log/DIFF-COVER-MUTMUT-ADOPT.md` (+45) — **692 insertions, 8 files.** Top commit says
   *"real fail-closed gates verified against mutmut 3.6"*. `master` contains no `diff-cover` commit;
   `git branch -r --contains 404881d` is empty. It is a **finished, verified, gate-registered adoption**
   that has been dark for 6.3h behind a swallowed exit code.
2. **`/home/stack/code/charon-wt-GATE-REENTRANCY` — `fix/gate-reentrancy-guard` @ `2b6d2ad`, +497/-3.**
   New `tools/gate_contract.py` + 317-line reentrancy test. No remote copy, no owning process.
3. **`/home/stack/code/charon-fleet-router-ledger-decay` — `feat/router-ledger-decay` @ `d7caabb`, +312**,
   *plus* an uncommitted `docs/review-log/ROUTER-LEDGER-DECAY.md` edit that would be lost separately.
4. **`agent-a4896ad6d2bfe5d06` — `feat/gateway-litellm-live-wire` @ `42a7440`, +241**, incl. a deliberate
   money-path STOP finding recorded in `DOGFOOD-litellm-live.txt`.
5. **`/home/stack/charon-private-wt/REGISTRY-META-CATALOG` — 2 unpushed commits** — *would* be #1, but the
   session is live and its stale claim is the only thing that makes it look reapable. This is the single
   most dangerous false positive on the board.
6. **`charon-fleet-LITELLM-SPIKE` — `spike/litellm-router-adapter` @ `f2cee9d`, +394** — spike evidence.
7. Uncommitted-only edits across items 21/24 — small, unique, silently destroyed by worktree deletion.

Everything else (items 6–13 job records, 22, 23) is a **dead artifact**: dead owner PID, and either
zero commits or commits already on `origin`/`gitea`.

---

## 5. DO-NOT-TOUCH set (explicit)

Live sub-sessions — **no reap, no claim clear, no worktree prune, no branch delete**:

- `/home/stack/charon-private-wt/FLEET-DEMAND-BROKER` — `feat/FLEET-DEMAND-DRIVEN-ROUTING-avail-cap`, actively committing (2→3 ahead during this scan), 4 modified files, 1 unpushed commit.
- `/home/stack/charon-private-wt/WATCHDOG-RESTART-VERIFY` — owner **PID 1299378 alive**, cwd in worktree; 7 modified + 3 untracked incl. a brand-new test file, **nothing committed yet**.
- `/home/stack/charon-private-wt/REGISTRY-META-CATALOG` — **2 unpushed commits**; its `fleet/state/claims/REGISTRY-META-CATALOG` entry is the "stale" claim in §1 and its owner field is malformed (`claimed-by=ticket:`, no parseable PID). **Do not clear this claim and do not reformat it.**
- `/home/stack/charon-private-wt/META-GATE-CALLSITE` — owner **PID 1171066 alive**, cwd in worktree; 2 modified files uncommitted.

Also do not touch: **PID 1794003** (operator's coordinator Claude) and **PID 1794037**
(session-bridge proxy) — both flagged "dark" but both are infrastructure/false positives.

---

## 6. Proposed follow-ups (no action taken)

- **F1 — highest value:** push/land `feat/diff-cover-mutmut-adopt` (3 commits) before any cleanup pass.
- **F2:** wire `fleet/stale-check.sh` into `preflight.sh` **and** make it `exit 1` when issues > 0 — it
  currently returns 0 while printing `2 issue(s)`, so wiring it in as-is would still be inert.
- **F3:** drop the `|| true` at `fleet/foreman-cadence.sh:153` (or capture and surface the rc). Six
  strandings sat unheard for 8–12 days behind it.
- **F4:** fix the dark-work register leg to exempt the session-bridge proxy itself and interactive
  `claude`, otherwise the leg is permanently RED on false positives and will be re-muted by habit.
- **F5:** fix the heartbeat writer that leaves live claims ageing past the 900s threshold — the
  malformed `claimed-by=ticket:` owner field is the reason the orphan-reaper skips it (per brief,
  the format itself is left alone).
