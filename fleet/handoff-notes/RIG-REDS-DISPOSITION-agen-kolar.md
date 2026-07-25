# RIG-REDS — one-time disposition of the rig gate's persistent RED checks

**Session:** agen-kolar · **Date:** 2026-07-24 · **Worktree:** `/home/stack/charon-private-wt/RIG-REDS`
**Branch:** `fix/rig-reds-disposition` · **Base:** local master `5d24ce6`

## TRUE starting red set (established by execution, not by report)

`bash fleet/gate.sh`, run twice in this worktree before any change:

| run | result | failing set |
|---|---|---|
| 1 | 68 passed / **9 failed** | assign-dispatch, capture-wiring, handoff-mechanize, priority-validator, promotion-gate, reconcile-merged, selfcheck-cycle, submit-checkin, w0b-harden |
| 2 | 67 passed / **10 failed** | the same 9 **+ rule-coverage** |

**The gate was NON-DETERMINISTIC** — two consecutive runs of an unchanged tree gave
different failing sets. That, not the count, is the headline finding. The coordinator's
concurrently-reported "12 failed" list resolves to the SAME underlying checks (route-pick
/`--print-model` = assign-dispatch · capture-timeout = capture-wiring · handoff-check
gotchas = handoff-mechanize · promotion-gate selftest 0/4 · selfcheck-cycle · checkin
headers = submit-checkin · branch-reaper guard = w0b-harden · perf 8.7s = reconcile-merged
case (g)); the divergence was runner noise, not extra defects. `priority-validator` was
**still red** here despite the local-only `5d24ce6` priority-9 fix — that commit corrected
a *different* ticket and missed one.

## Root cause of the non-determinism: `fleet/gate.sh` (the RUNNER, not the checks)

`fleet/gate.sh:45` launched **all 77 test files at once, unbounded**, on a 16-core box
while seven other sub-sessions were running. Consequences observed:

* `fork: retry: Resource temporarily unavailable` inside `selfcheck-cycle.test.sh`
  (which sets `ulimit -u 256` as a fork-bomb backstop — a **per-user** limit, so an
  overloaded box starves it).
* `reconcile-merged.test.sh` case (g): 2445/2532/2676 ms standalone vs 5188/6673/7704 ms
  under the fan-out, against a 5000 ms wall budget.
* `rule-coverage.test.sh`: 3/3 green standalone, red under the fan-out.

Three "product reds" that were purely the runner. Fixed by bounding in-flight tests to
`nproc` (`CHARON_GATE_JOBS` override). Cost: 1m38s → 1m47s wall. Also made a missing
`.rc` file an explicit per-test RED instead of a `set -e` abort mid-report.

## Disposition table

| # | check | bucket | evidence | action | owner (if collision) |
|---|---|---|---|---|---|
| 1 | **gate.sh runner** (meta) | (a) broken | 2 runs of an unchanged tree → different failing sets; `fork: Resource temporarily unavailable`; wall budgets tracking load average | **FIXED** — bounded concurrency at `nproc`; missing-`.rc` now a loud RED | — |
| 2 | `promotion-gate` | (a) broken | `promotion-gate.test.sh:95` hard-coded `FLEET_DIR = Path("/home/stack/charon-private-wt/EVAL-PROMOTION-GATE/fleet")` — a worktree that no longer exists. Every scenario died with `ModuleNotFoundError: No module named 'promote'`, and both JSON parsers swallowed it via `2>/dev/null`, so all four FAIL lines printed an **EMPTY reason**. VACUOUS RED. | **FIXED** — harness reads `CHARON_FLEET_DIR` exported by the wrapper; unparseable harness output now reports the raw traceback. 0/4 → **4/4** | — |
| 3 | `assign-dispatch` | (a) broken (stale fixture) | `assign.py` REFUSED: EVAL-PROMOTION-GATE's F13 control-panel admission gate (`grades.py` `_rows_for`) requires a per-ref `strong-control` (N≥3, mean≥80) **and** `deepseek-v4-flash` (N≥3, mean≤20) before a `source=live` row counts. The fixture predates the gate and had **zero** control rows → every row excluded → no candidate. Nothing to do with the S4 dispatch wiring under test. | **FIXED** — added the control panel to the fixture. 3/6 → **6/6** | — |
| 4 | `submit-checkin` | (a) broken (stale contract) | `submit.sh` deliberately skips the auto check-in when `SESSION` is unset (a `<UTC>-submit-auto.md` note is globbed by no reader and strands untracked, which is what makes `land.sh` refuse on a dirty tree). The test ran submit with `SESSION` **unset**, i.e. asserted the pre-narrowing contract. | **FIXED** — drives the named-session path; **added case (d)** pinning the no-SESSION skip so the narrowing is itself fail-on-revert covered. 1/7 → **9/9** | — |
| 5 | `capture-wiring` | (a) broken (stale contract) | `rc=124` is no longer a blanket infra fault. EVAL-LATENCY-GATE split it three ways and, per `[[latency-is-a-failure-class]]`, "streamed output then killed" is **model-attributable** → a BLOCK capture row is correct. The stub `echo "hanging..."; exit 124` is exactly that leg, and the test asserted "no row". | **FIXED** — covers the real three-way split (no-output → no row; streamed → BLOCK row; pool-exhausted → no row). 32/33 → **36/36** | — |
| 6 | `w0b-harden` | (a) broken (stale assertions) | `branch-reaper.sh` grew `_rp_glob_ok`, an EARLIER and STRICTLY STRONGER config-time refusal ("INVALID CONFIG — worktree glob … would admit the protected tree …") that fires before the per-candidate `REFUSE` line the test matched. B5's "legitimate stale worktree" fixture was a bare dir, which the reaper now (correctly) KEEPs as "not a readable git working tree — state undecidable (fail-closed)" — so the anti-over-block case had **no coverage at all**. | **FIXED** — accept either refusal channel; **added B4b** so the depth rule (`/*` → "rooted directly at '/'") keeps explicit coverage; B5 rebuilt as a real, clean, fully-pushed linked worktree (remote ref planted with `update-ref`, **no `git push`**). 37/40 → **41/41** | — |
| 7 | `selfcheck-cycle` | (a) broken — **real fork-bomb-class defect** | Not a test bug. `fleet/checks/selfcheck-cycle.sh` reported `rig-ci-scope -> rig-ci.test -> rig-ci-scope` as an **UNGUARDED** self-referential edge: `rig-ci-scope.sh` `cmd_tests` runs `fleet/tests/rig-ci.test.sh`, which runs `rig-ci-scope.sh` — and `run_scope` honours `$RIG_CI_SCRIPT`, so nothing structurally stops re-entry into `tests`. Same class as the ~18,900-proc handoff↔gate incident. | **FIXED** — added the `RIG_CI_TESTS_ACTIVE` reentrancy guard (same shape as `gate.sh`'s `CHARON_GATE_ACTIVE`). Checker: 2 unguarded → **0**. 9/11 → **11/11** | — |
| 8 | `reconcile-merged` (g) | (b) flake — **fault is in the CHECK**, exposed by the runner | Wall-clock budget on a shared box measures scheduler queueing, not work. **Worse: the case was also VACUOUS for the regression it claims to catch** — re-introducing the per-PR `ticket_for_pr` re-scan produced ~4.0 s wall, *under* the 5000 ms bound, so it would have stayed GREEN through its own target regression while going RED on a busy box. Both halves wrong. | **FIXED** — budget on children **CPU** (`times`), which load does not inflate. Measured separation, 3 samples each: indexed 1197/1219/1327 ms · re-scan 2503/2529/2621 ms → threshold **1900 ms**. Wall kept only as a 60 s HANG backstop. Now genuinely fail-on-revert (see below). | — |
| 9 | `rule-coverage` | (b) flake — **fault is in the RUNNER** | 3/3 green standalone (`rc=0`, 0 FAILs each), red only under the unbounded fan-out. Case (e)'s "phantom" message assertion. | **FIXED indirectly** by #1; green in both bounded gate runs since | — |
| 10 | `priority-validator` | (a) broken — **COLLISION, ticketed** | `fleet/board/UNIFIED-PLANE-CANARY-FRAMEWORK.md:3` carries `priority: 9`; `PRIORITY-LADDER.md` allows integer 0..5 only. The ticket was RETIRED in `99c709c` as a redirect stub superseded by `SG-ISSUE-CONTROL-PLANE`, but the file was left behind with the out-of-range value. `5d24ce6`'s 9→5 sweep missed it. **One-character fix**, but `fleet/board/*` is owned. | **TICKETED — not edited.** Fix: `priority: 9` → `priority: 5` in that file (or retire the stub outright). This is one of the two remaining gate reds. | **ticket-bundling session** (`fleet/board/*`, `fleet/state/ROADMAP.tsv`) |
| 11 | `handoff-mechanize` | (a) broken — **COLLISION, ticketed** | `b1 stripping gotchas -> handoff-check exits 1 (expected '1', got '0')` and `b2 the failure did not name 'gotchas' as missing`. `fleet/handoff-check.sh` has a `[gotchas]='GOTCHA\|avoid\|DENIED'` rule and a VACUOUS-0 guard, but the strip case is not detected. Exactly the stale-gotcha ticket in flight. | **TICKETED — not edited.** The owning worktree has `fleet/handoff.sh`, `fleet/handoff-check.sh` **and** `fleet/tests/handoff-mechanize.test.sh` all modified — direct collision. | **HANDOFF-GOTCHA** (`/home/stack/charon-private-wt/HANDOFF-GOTCHA`, `fix/handoff-gotcha-verifiable`) |

**Bucket counts:** (a) genuinely broken **9** · (b) slow/concurrency flake **2** (one the
runner's fault, one the check's) · (c) obsolete **0** · (d) environmental **0**.

## Fail-on-revert proofs (exit codes both directions)

Every fix was proved by breaking the thing it protects and re-running:

| fix | revert applied | rc reverted | rc restored |
|---|---|---|---|
| `rig-ci-scope` reentrancy guard | delete the `RIG_CI_TESTS_ACTIVE` block | **1** (2 FAILs, selfcheck-cycle) | 0 |
| `promotion-gate` FLEET_DIR | point `CHARON_FLEET_DIR` at the dead worktree | **1** (now names "promote.py missing under …" instead of an empty reason) | 0 |
| `submit.sh` SESSION narrowing | `if [ -z "${SESSION:-}" ]` → `if false` | **1** (`d2` red) | 0 |
| `charon-run.sh` rc=124 too-slow BLOCK | remove the `cap … BLOCK` call | **1** (streamed-output case red) | 0 |
| S4 assign-reorder wiring | remove `assign_reorder_chain` from `resolve` | **1** (`a1` red) | 0 |
| `branch-reaper` catastrophic guards | remove both the per-candidate and config-level refusals | **1** (B1b/B2b/B3b red) | 0 |
| `reconcile-merged` index | re-introduce the per-PR board+archive re-scan | **1** (`3287 ms CPU ≥ 1900 ms`) | 0 |

## Result

| gate run | before/after | result |
|---|---|---|
| run 1 (before) | before | 68 / **9 failed** |
| run 2 (before) | before | 67 / **10 failed** |
| run 3 (after) | after | 75 / **2 failed** |
| run 4 (after) | after | 74 / 3 failed — the third was `reconcile-merged` (g) at 5188 ms wall, fixed afterwards by the CPU budget |

**Reds remaining after my changes: 2.** Both are collisions I was instructed not to edit:
`priority-validator` (one-character board fix) and `handoff-mechanize` (owned by the
in-flight stale-gotcha ticket).

**Can `land.sh` pass the rig gate now? NOT YET — but it is 2 checks away, and one of them
is a single character.** The fastest unblock is for the board owner to set
`fleet/board/UNIFIED-PLANE-CANARY-FRAMEWORK.md:3` to `priority: 5` (or retire the stub) and
for HANDOFF-GOTCHA to land its `handoff-check.sh` gotchas fix. Nothing else stands between
the rig and a green gate.

## Secondary findings (not blocking, worth a ticket each)

1. **Hard-coded worktree paths are a class, not an incident.**
   `fleet/tests/lease-exactly-once.test.sh:35,39` references
   `/home/stack/charon-private-wt/WORK-LEASE-GATE/…` and `…/FAKTORY-ADOPT/…` — the latter
   worktree **does not exist**, and both reads are `|| true`, so the test passes vacuously.
   Same defect as #2 above but currently hidden behind a green. `fleet/work-lease.sh` is
   owned, so this was not touched. `[[no-hardcoded-cross-boundary-paths]]`
2. **`fleet/tests/handoff-mechanize.test.sh` WRITES INTO THE MAIN CHECKOUT**
   (`:60-62` `mkdir -p /home/stack/charon-private/fleet` + `cp` a file there; `:153`
   `git -C /home/stack/charon-private rev-parse`). A test run from any worktree mutates the
   shared tree — a direct source of cross-session churn and of the dirty-tree state that
   makes `land.sh` refuse. Owned by HANDOFF-GOTCHA; flagged to them.
3. **Cross-repo contract divergence on the control-panel gate.** The rig's
   `fleet/capability/grades.py` keeps the hard "no control split → EXCLUDE" rule, and
   `promotion-gate.test.sh` case (c) *deliberately pins it*. The product repo moved the
   opposite way in `0947401` (no-control → **admit flagged provisional**, because
   `strong-control` had 0 rows in the entire ledger and the gate was structurally
   unsatisfiable). Two copies of the same gate now disagree. Not resolved here — it needs
   an operator decision, not a sub-session's.
4. **For the `4LOM-CANARY-SERVICE` sensor:** the discriminating signal is **CPU time, not
   wall-clock** — it separated the real re-scan regression (2.5 s) from a clean run (1.2 s)
   while the box's load average swung 5→11 and moved wall-clock by 3x.
