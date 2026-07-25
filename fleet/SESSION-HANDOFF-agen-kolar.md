# Charon Fleet — Session Handoff — agen-kolar (2026-07-24)

## Bootstrap (copy-paste into next session)

```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-agen-kolar.md — you are the fresh Charon fleet MANAGER, carry it out, then flip to fleet mode.
```

**Session ended at ~95% budget. Everything was committed and pushed before stop; nothing lost.**

---

## FIRST ACTIONS (priority order)

0. **`bash fleet/pending.sh list`** — your operator decision list, persists across sessions,
   labels never reused. 8 open (S,T,U,V,W,Y,Z). Read it before anything else.

1. **Finish the last gate red.**
   ⚠️ **CORRECTION — a false premise ran through most of this session.** I claimed repeatedly that
   the rig gate reds BLOCK every `land.sh` and were therefore the keystone gating 21 branches.
   **That is FALSE for the rig repo.** `fleet/land.sh:298` auto-detects and runs
   `bash $REPO/fleet/validate_board.sh $REPO/fleet` — a board STRUCTURAL check — **not**
   `fleet/gate.sh`. `validate_board` has been GREEN throughout, so rig landing was never blocked
   by the reds. Anything in this file or in `pending.sh` implying otherwise is wrong; trust this note.

   🔴 **The real finding underneath it is worse, and needs a ticket:** rig merges are **NOT
   TEST-GATED AT ALL.** `land.sh` never runs the rig test suite, so a rig branch can merge with
   any number of failing tests. `MANAGER-OPERATING-RULES.md` §8 mandates the FULL gate as the merge
   gate; the rig path does not honour it. Decide whether `land.sh`'s auto-detect should select
   `gate.sh` for the rig without breaking the product path.

   The reds are still REAL defects worth closing (7 were fixed this session, `f65c5f2`) — they were
   simply never the landing blocker.
   **Reds went 10 → 1 this session** (`fix/rig-reds-disposition` @ `f65c5f2`, pushed).
   - Remaining: **`handoff-mechanize`** — owned by `fix/handoff-gotcha-verifiable`, whose work is
     finished and STAGED in `/home/stack/charon-private-wt/HANDOFF-GOTCHA` but uncommitted because
     no board ticket maps that branch. **Create the ticket, commit, and the gate should go green.**
   - (`priority-validator` is already fixed on master — `UNIFIED-PLANE-CANARY-FRAMEWORK` is `priority: 5`.)
   - Root cause found and fixed: `gate.sh` launched all 77 tests unbounded on 16 cores →
     `fork: Resource temporarily unavailable` → the gate was **non-deterministic** (9 vs 10 reds on an
     unchanged tree). Also killed a **real unguarded fork-bomb cycle** in `rig-ci-scope`.

2. **Mechanize "built but no caller" from the code map** — operator-designated #2.
   Requirement, verbatim: *"mechanized, fully wired in, anti-stale, with loud notices."*
   A ticket was being created at session end — **REUSE-CHECK FIRST**: `INERT-INSTANCE-DETECT`,
   `INERT-WIRING-ENFORCEMENT-DURABLE`, `WIRE-GRAPHIFY-FRESHNESS` and product
   `tools/check_inert_code.py` may already cover it. Extend one rather than create a fourth —
   a duplicate ticket for "find what we already built and forgot" is self-refuting.
   - **Why it is #2:** every built-but-unused thing found this session was found by a human
     asking, never by a tool — `decompose_effort.py` (ignored by the tier classifier),
     `budget-derive.py` (p95×1.5, tested, ZERO callers, its `budgets.tsv` absent),
     `plane-canary.sh` (0 callers), `stale-check.sh` (0 callers), `litellm_params["order"]`
     (computed then discarded), 33 never-run tests, 21 unlanded branches.
     Graphify was refreshed and current all day. **Nothing ever queried it for "no caller."**
   - Must-haves: wired on SessionStart + post-land triggers (note `foreman-cadence.sh`'s own
     `cadence` leg has NO cron/systemd caller — wiring only there recreates the bug one level up);
     stale graph reads UNKNOWN/RED never last-known-good; loud where a session will see it
     (`handoff.sh:383` and every SessionStart hook in `settings.json` are `|| true`, so loudness
     rides on TEXT not exit code); fail-closed; zero nodes examined = RED; and it MUST distinguish
     genuinely-inert from legitimately-uncalled (entrypoints/CLI/plugin hooks) with explicit
     recorded exemptions — a detector that screams about every `__main__` gets switched off in a day.
   - Reuse the WCI auto-ticket emitter (`fleet/wci-contention.sh`, `300e9a4`) — it is already
     idempotent, board-valid and self-closing; it needs a generalized `emit --source <x> --key <k>` seam.

3. **Finish the board regroup — operator-designated #3. UNRESOLVED, not done.**

4. **Fix the work-lease CLAIMS-STORE SPLIT — operator-designated #4.**
   `fix/work-lease-worktree-resolve` (`5d951e8`, pushed) is **explicitly PARTIAL**: it fixes
   `_link_src` only and does NOT satisfy its own first accept criterion. A lease acquired from
   inside a worktree still writes to the WORKTREE's `fleet/state/claims` while the hook reads the
   MAIN checkout's — the cause of every lease refusal this session.
   **`feat/branch-ticket-map-gate` (`b784de1`, pushed) closes it properly**: `_state_root()` resolves
   the store from `git rev-parse --git-common-dir`, plus a `work-lease.sh guard-branch` wired into
   `fleet-droid.sh:375` so an unmapped branch is refused at DISPATCH, before any work happens.
   Land that; do not re-derive it. It still needs a ticket carrying
   `branch: feat/branch-ticket-map-gate`. Note: `feat/work-lease-gate` is **already merged into
   master** (stale, 98 behind) — delete it, there is nothing to land there.

5. **Then LAND — but the queue below is CORRECTED. Two items were booby-trapped.**
   A four-lane triage at session end verified these by CONTENT, not commit graph. Read this before landing anything.

   ⚠️ **① PR #211 (`RECONCILE-GATE-WIRED`) — DO NOT LAND AS-IS.** Its head `d603494` is
   **detector-only and LACKS THE WIRE**. Merging it ships the meta-gate INERT, and it leaves a live
   `VALID_AREA` landmine that **aborts ALL of preflight on any rig-meta RED**. The wire exists on
   `feat/reconcile-gate-wired-salvaged` (pushed this session @ `6d4d6db`, ls-remote proven) which is
   the SAME sha as local `feat/reconcile-gate-wired` — a duplicate ref, not a fork. Land the wired
   version, not #211's head. See TP-1 in `reviews/TRIAGE-LANE3-RECONCILE-agen-kolar.md`.

   🛑 **② `feat/github-limits-hardening` — DO NOT LAND. It is a REGRESSION.** It DELETES 66/15/36/87
   lines across 4 files and still carries the dead `gh pr list -r` bug. Both it AND its `-v2` are
   dead — the real work already landed by RE-DERIVATION (master is ahead: `gh-cache` +7 lines
   `pr_number_is_merged`; `end-session` +34 lines M2 stale-handoff guard). Reap both.

   Remaining queue, unaffected: #207 · #222 · #208 `REPO-FIELD-REQUIRED` ·
   `feat/meta-gate-callsite-enum` · `feat/sync-schedule` · #205 `INVENTORY-TABLE`.

   🛑 **Also do NOT land `feat/issue-board-surface`** (salvaged + pushed @ `42b3904` for preservation
   only). Two of its five files wire the **STRUCK** `fleet/state/issue-board.tsv` fork into the LIVE
   SessionStart hook and `foreman-cadence`. Landing it installs the design that was explicitly
   rejected this session. Recommend CLOSE PR #261 and retire `fleet/board/ISSUE-BOARD-SURFACE.md`.

   ### ⚠️ METHOD — `git cherry` LIES in this rig. Do not trust the commit graph.
   Work here lands by **RE-DERIVATION, not cherry-pick**: someone re-implements on a fresh branch and
   merges that, so original SHAs never appear upstream. `git cherry` and `git log origin/master..<br>`
   both keep reporting "unique commits" for branches that are **fully landed**. Lane 1 got a false
   "+" on all six of its branches; Lane 2's warning caught `feat/stranded-work-detect` the same way.
   **Proof must be content-level:** diff the branch's OWNED files vs `origin/master`, and check for an
   archived `status: done` ticket. This is the generalised `feat/work-lease-gate` trap.

### Detail on #3 — the board regroup (INTERRUPTED mid-flight)
   A sub misread "bundle" and MERGED 9 tickets into 3. **Operator clarified: bundle = GROUP by
   lens/project at the same priority, keeping tickets SEPARATE so agents work in PARALLEL.**
   Merging into fat serial tickets defeats the wall-clock goal.
   - Recoverable verbatim from git: `DONE-SH-INTEGRITY-FIX`, `DISCOVERY-{NORMALIZE,DIFF,QUEUE,APPROVAL-WIRE,CADENCE}`
   - NOT in git (created today, never committed, then deleted): `PREFLIGHT-GATE-RUN-HELPER`,
     `META-GATE-PREFLIGHT-WIRE-CLOSED` — reconstruct from content absorbed into `WCI-CONTENTION-TEETH`.
   - Group via existing ROADMAP.tsv `project`/`wave` + same `priority:`. Do not invent a field.
   - Check for `fleet/state/reviews/BOARD-REGROUP-STATUS-agen-kolar.md`.

---

## Pushed this session (ls-remote proven; NONE merged)

| Branch | SHA | What |
|---|---|---|
| `fix/rig-reds-disposition` | `f65c5f2` | **7 gate reds fixed**, bounded gate concurrency, fork-bomb cycle killed |
| `feat/tier-classifier` | `f1f162c` | tier-drift gate can go RED / fails closed / non-vacuous (manager-verified) |
| `fix/gate-reentrancy-guard` | `2b6d2ad` | product: prevents gate↔test-suite unbounded recursion |
| `feat/registry-meta-catalog` | `78dd0c7` | rebased; both behaviours proven by execution |
| `feat/watchdog-restart-cmds-verify` | `a23fce3` | 4 restart_cmds fixed; dogfood proven (break→refuse, fix→allow) |
| `feat/meta-gate-callsite-enum` | `a92019d` | meta-gate audits by CALL SITE not directory: nodes 21→57, findings 4→11 |
| `feat/FLEET-DEMAND-DRIVEN-ROUTING-avail-cap` | `4f33f87` | broker cost-cap (detain-on-cap) + capped-filter fail-closed |
| `feat/wci-contention-teeth` | `300e9a4` | wci auto-tickets at P1, idempotent, 4 fail-open paths closed |
| `feat/plane-canary-wire` | `aed5fc2` | plane-canary wired to 4 triggers (had ZERO callers) |
| `feat/4lom-canary-service` | `0c6b9e6` | slow-vs-broken attribution sensor, staleness-proof |
| `feat/sg-issue-control-plane` | `b9d314b` | design 639→298→403; registry seeded with 12 classes |
| `fix/work-lease-worktree-resolve` | `5d951e8` | **PARTIAL** — `_link_src` only; claims-store split NOT fixed |
| `feat/gw-cutover-live-wire` | `064d197` | **STOP** — refused; money path untouched; 5 guard tests mechanize the stop |
| `feat/diff-cover-mutmut-adopt` | `404881d` | preserved only (DO-NOT-LAND; 6-item fix list on its ticket) |
| `feat/gateway-litellm-live-wire` | `5ebe5c0` | evidence preserved, hex redacted, gate 16/16 |
| rig `master` | `859e3b9` | board + 14 review/audit docs |

**Blocked on a ticket:** `fix/handoff-gotcha-verifiable` (staged, see action 1);
`docs/contributing-hook-install` (staged; ticket now exists).

---

## STRANDED / UNFINISHED INVENTORY — audited at session end, nothing here is lost

**Everything from THIS session is committed and pushed.** The items below are either
(a) pushed-but-unmerged by design, or (b) PRE-EXISTING strandings this session surfaced but did
not create. Listed so the next session does not have to rediscover them.

**a) Pushed, proven on origin, NOT merged — 18 branches.** All named in the table above.
None are lost; all need landing via the queue in action 5. Note `WCI-CONTENTION-TEETH` in
particular: its ticket exists AND its branch is pushed, but it is dep-blocked behind the
`preflight.sh` owners, so it will not appear claimable — that is expected, not a fault.

**b) Finished work still UNCOMMITTED in a worktree (needs its ticket first):**
- `/home/stack/charon-private-wt/HANDOFF-GOTCHA` — 5 files staged. **This is action 1.**
  Ticket `HANDOFF-GOTCHA-VERIFIABLE` now exists, so it should commit cleanly.

**c) PRE-EXISTING unpushed branches with commits (predate this session, unexamined):**
`chore/gitignore-state-negations` (+1), `chore/retire-wire-graphify` (+1),
`design/unified-reconciliation-gate` (+1), `doctrine/adopt-substrate-first` (+2),
`feat/coverage-meta-gate-rederive` (+5), `feat/github-limits-hardening-v2` (+3),
`feat/reconcile-gate-wired-salvaged` (+2), `feat/semgrep-ci-v2` (+3),
`feat/session-end-push-gate-v2` (+3), `feat/stranded-work-detect-v2` (+1),
`feat/substrate-first-gate` (+1), `feat/substrate-first-gate-v2` (+3).
**These exist on NO remote.** Triage: rescue or reap. Several look like `-v2` retries of
branches that already landed — check before assuming they are live work.

**d) PRE-EXISTING dirty worktrees (uncommitted edits only, no commit loss):**
`FIXTURE-BYPASS-GATE`, `FLEET-DEMAND-BROKER`, `HANDOFF-NAME-ALLOCATOR`, `ISSUE-BOARD-DEMO`,
`ISSUE-BOARD-SURFACE` (5 files), `STRANDED-WORK-DETECT`, `WORK-LEASE-GATE`; product
`charon-fleet-INERT-INSTANCE-DETECT` (4), `charon-fleet-LITELLM-SPIKE`,
`charon-fleet-router-ledger-decay`. A worktree reaper would silently destroy these edits.

**e) Branches with NO ticket (the lease gate will refuse their commits):**
`feat/fixture-bypass-gate`, `feat/handoff-name-allocator`, `demo/issue-board-surface`,
`feat/ksf-vendor-gates`, `salvage/preflight-verify-merged-ghcache-wip`,
`fix/substrate-first-owns-base-ref`, `feat/substrate-first-gate-v2`, `feat/work-lease-gate`
(already merged to master — delete), `feat/coverage-meta-gate`.
`feat/branch-ticket-map-gate` was also missing a ticket; one was requested at session end —
verify it exists before relying on it.

**f) Obsolete, safe to delete once measurements are confirmed captured:**
`spike/litellm-router-adapter` — superseded by shipped `src/charon/litellm_plane/`; its durable
measurements were extracted to `fleet/state/LITELLM-SPIKE-MEASUREMENTS.md`.

**g) 25 × `charon-fleet-dogfood-*` product worktrees** — eval scratch, 9-10 days old, no unlanded
source. Bulk-reapable AFTER the above are dispositioned.

---

## Classes found (evidence in `fleet/state/reviews/*-agen-kolar.md`)

1. **Gates that cannot go RED** — tier-drift's RED-set file absent → every mismatch WARN at rc 0.
2. **Gates that fail OPEN** — 9 `[ -f ] || return 0` blocks in `preflight.sh`.
3. **Red-proofs no runner executes** — **33 never-run rig test files** + 63 reachable only via
   `handoff.sh`. 7 guard money/security/data-loss (`test_real_shell_injection.py`,
   `test_grader_daemon.py`, `test_land_safe_sync.sh`, `test_droid_reap.sh`).
   **Worst: product `reachability-gate`** — enforcer `../charon-private/fleet/checks/no-unreachable-paths.sh`
   **does not exist**, `optional:true` → SKIP, reports OK rc=0. A fake affirmative green in the PUBLIC repo.
4. **Enforcement invisible to the meta-gate** — membership by DIRECTORY; 23 checks outside scope.
5. **Vacuous passes** — zero items scanned = GREEN.
6. **Budget breaches that SILENTLY disable checks — 12 found.** Worst: `validate_board.sh:393`
   parallelizability gate needs ~21.7s vs a hardcoded 15s → prints `parallelizability-check-failed`
   and **does not run**, board still GREEN. Root cause O(n²) (`is_decomposed()` re-walks 113 tickets
   per ticket), not the 15. `fleet/benchmark/budget-derive.py` (p95×1.5) exists, tested, **zero callers**.
7. **Inert detectors** — `plane-canary.sh` (0 callers, now wired), `stale-check.sh` (0 callers),
   `dark-work-check.sh` (rc discarded by `|| true`).
8. **Built-but-unlanded — 21 branches.** THE bottleneck.
9. **No ticket mapping** — 4 finished branches blocked today; **10 more** worktree branches have no ticket.
10. **Stale docs asserting false behaviour** — the `land.sh` gotcha is FALSE; it suppressed working tooling.
11. **Rig→product boundary leak** — product `.git/hooks` displaced the public-clean guard on a PUBLIC repo.
12. **Adopted-tool under-utilization** — below.

---

## Adopted tools we under-use (highest-value finding; all execution-verified)

`Router.__init__` takes **52 params; `make_router` sets 6.**

- **U1 `litellm_params["order"]`** — we already COMPUTE the funding-class chain order and throw it away.
  Setting it = **300/300 deterministic** first-leg vs today's 97/105/98 coin flip.
  **This is the GW-CUTOVER blocker, and it is one parameter.**
- **U2 `enable_pre_call_checks=True`** is off → `max_input_tokens` at `litellm_router.py:142` is dead
  config; a 4000-token prompt can route to a 100-token leg.
- **U3 ruff `S`+`BLE`** → **72 findings incl. `shell=True` and bind-all-interfaces**, while our
  hand-rolled 330-line `check_security.py` reports clean. **Security fake-green.**
- **Does NOT serve (do not retry):** `routing_strategy="cost-based-routing"` is *intentionally
  unimplemented on the sync path we call* (raises `RouterRateLimitError`); even async it ranks on static
  list price with a 5.0 sentinel. LiteLLM rate limits are minute-only (no RPD) → `quota.py` /
  `FT-WIRE-QUOTA` remain real work.
- **F5 answered:** `src/charon/decompose_effort.py` ALREADY implements the effort scorer
  (`2.0·difficulty + 0.15·size + 1.0·behaviours`) the tier classifier ignores. On our board
  `nsurf` vs tier ρ=+0.075 (noise), `difficulty` ρ=+0.413. radon/lizard/scc/COCOMO killed on our own
  data (maxCC vs SLOC ρ=+0.901 — measuring size again).

---

## Operator decisions RECORDED

- **Gitea is PRIMARY** → `FORGE-PRIMARY-GITEA` (P:1); acceptance demands *executed* failover both ways.
- **TIER-BALANCE F11 REJECTED** — review-class keeps its capability tier (reviews caught 3 fake-greens,
  the recursion hazard and a design fork that no gate caught). Recorded on the ticket with rationale.
- **F5 OPEN** — interim `nsurf>=3 AND difficulty-floor` approved pending research; research now supports
  it and offers better (`decompose_effort.py`).
- **Preflight decomposition APPROVED, sequenced:** `PREFLIGHT-GATE-RUN-HELPER`'s fail-closed `_gate_run`
  FIRST → chain drains → THEN extract the 8 inline `*_gate()` into `fleet/checks/<gate>.sh` (which also
  drops them into the meta-gate's glob). Decomposing first clobbers 5 branches.
- **Economy starvation is LEGITIMATE** — 1 genuine candidate only; idle economy tabs are correct.
- **Monit: WAIT for instruction.** Gate: reds clear → land `WATCHDOG-RESTART-CMDS-VERIFY` →
  `fleet/watchdog/verify-restart-cmds.sh` exits 0 → THEN two sudo steps on the **LOCAL WSL box, not 4-LOM**.
- **Bundle = GROUP by lens at same priority, NOT merge into fat serial tickets.**
- **Report cadence:** batch 3+ agent completions before summarising; token-lean prose.

---

## Gotchas

- **`land.sh` DOES create PRs** (`:395` create, `:399` ready, `:404` merge). The old "does NOT create one"
  gotcha is FALSE. It needs HEAD on the branch; use `land-push.sh <branch> [repo]` for a named branch.
  Refuses on RED gate.
- **`git add` aborts entirely if any pathspec fails** → nothing stages, and a later commit can silently
  capture only what was already staged. `5d24ce6` claimed content it did not contain for exactly this
  reason. **Always check `git diff --cached --name-only` before committing.**
- Work-lease refuses any worktree branch with no board ticket → **create the ticket BEFORE firing a sub
  that will commit.** Acquire via the MAIN checkout's `work-lease.sh` from the worktree cwd (the
  worktree's own copy writes to the wrong claims store — that split is NOT yet fixed).
- Hooks now wired via `core.hooksPath` (rig → `fleet/hooks`; product → `.git/hooks-active/` chaining
  public-clean FIRST then work-lease). Sessions were clobbering `.git/hooks` into whichever worktree
  booted last.
- Do **NOT** run `charon gate` on `feat/diff-cover-mutmut-adopt` — unbounded pytest↔gate recursion.

---

## Open question the operator raised — unanswered, worth a ticket

**The code map (graphify) did not proactively surface any of this prior art.** We repeatedly found work
already built but unwired/unlanded: `decompose_effort.py`, `budget-derive.py`, `feat/work-lease-gate`'s
dispatch-time enforcement, 21 unlanded branches, `litellm` capabilities. Graphify refreshes at
SessionStart and after every land, yet nothing ever queries it for **"built but no caller"**.
That query, on a cadence, surfaced loudly, would have found most of today's findings without a human asking.

## Prior art NOT yet evaluated — reuse-check BEFORE building

`feat/work-lease-gate` @ `e6eacea` — *"dispatch-time enforcement, single store, auto-wire, fail-closed
+ tests"*. That is precisely the branch→ticket mechanization AND the claims-store fix. Unlanded,
unticketed. A sub was evaluating it at session end; check
`fleet/state/reviews/BRANCH-TICKET-MAP-agen-kolar.md` and
`/home/stack/charon-private-wt/TICKET-MAP-GATE` before rebuilding anything.
