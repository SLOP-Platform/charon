# LANDING CAMPAIGN STATUS — 2026-07-24 (sub: land-5-branches)

origin/master after campaign = `ec34714`. **All 5 target branches LANDED and merge-verified
(`gh pr view … state=MERGED`, and `git merge-base --is-ancestor <sha> origin/master` = YES for all 5).**
Nothing is mid-flight. No PR is created-but-unmerged. No force, no bypass, no `WORK_LEASE_BYPASS`.

## LANDED (all 5) — do NOT re-land

| # | branch | branch sha | PR | merge commit |
|---|--------|-----------|-----|--------------|
| 1 | feat/meta-gate-callsite-enum | a92019d | #266 | a00c044 |
| 2 | feat/branch-ticket-map-gate  | b784de1 | #267 | d31b140 |
| 3 | feat/wci-contention-teeth    | 300e9a4 | #268 | 3c8919b |
| 4 | feat/plane-canary-wire       | aed5fc2 | #269 | c61c552 |
| 5 | feat/4lom-canary-service     | 0c6b9e6 | #270 | ec34714 |

Every land exited **rc=8** = `DONE-WITH-WARNING`: merge succeeded and was verified `state=MERGED`,
but step-7 base-sync was REFUSED (rc=3) because the MAIN checkout `/home/stack/charon-private`
holds `master` and is DIRTY. Per brief, that is a continue-condition, not a failure.

Gate ran GREEN on every land (auto-detected gate = `validate_board.sh` from the worktree).
Leases released before each land: META-GATE-CALLSITE-ENUM, TICKET-MAP-GATE, PLANE-CANARY-WIRE,
4LOM-CANARY-SERVICE (WCI-CONTENTION-TEETH had no lease). Auto-done-mark ran for each.

## VERIFIED-LIVE EVIDENCE (executed against a detached worktree at origin/master)

Verification checkout: `/home/stack/charon-private-wt/VERIFY-MASTER` (detached @ `ec34714`).
**Remove it when done: `git -C /home/stack/charon-private worktree remove /home/stack/charon-private-wt/VERIFY-MASTER`**

### 2. guard-branch — LIVE AND REACHED (red-proofed + green-proofed)
- Present on master at `fleet/work-lease.sh:244` (`cmd_guard_branch`), dispatched at `:408`,
  **wired at `fleet/fleet-droid.sh:619`** (`bash "$FLEET/work-lease.sh" guard-branch "$branch" "ticket $id"`).
- RED-PROOF, run on master: `bash fleet/work-lease.sh guard-branch feat/definitely-not-a-real-ticket-xyz verify`
  → `WORK-LEASE CREATION REFUSED: branch '…' maps to NO board ticket`, **rc=1**.
- GREEN-PROOF: same command with `feat/inventory-table` → `work-lease: branch 'feat/inventory-table'
  -> ticket 'INVENTORY-TABLE'`, **rc=0**. Not vacuous, fails loud.

### 4. plane-canary — LIVE AND NOW REACHED (was ZERO callers)
- Caller on master: `fleet/foreman-cadence.sh:85` (`PLANE_CANARY_SH`), surface rides EVERY trigger,
  dispatch at `:288` (`plane-canary)`), fail-closed at `:92` if the detector file is absent.
- RUN on master: `bash fleet/foreman-cadence.sh plane-canary verify` → **rc=1**, LOUD RED banner:
  `8 of 10 DECLARED PLANES HAVE NO TRUSTWORTHY CANARY`
  RED planes: data/serving failover egress-key review lifecycle balance config-ssot reconciliation.
  GREEN planes: landing, map-freshness. **It fires on a trigger. Confirmed by execution.**

### 1. meta-gate callsite enum — LIVE, REACHED BY THE TEST SUITE, **NOT wired into validate_board**
- RUN on master: `bash fleet/checks/gate-creation-standard.sh` → **rc=1, 11 findings** (was 4).
  The NEW class fires on real machinery:
  `RED unaudited-callsite: fleet/validate_board.sh is invoked by an enforcement entrypoint but has
   no companion test … placing it outside fleet/checks/ is no longer an exemption`.
  Other 10: unproofed-gate reachability-gate; no-red-proof-test large-file-guard.sh, rig-ci-scope.sh;
  fail-quiet _lib.sh, gh-cache.sh, push-verify.sh, repo-registry.sh, watchdog/watchdog-lib.sh;
  no-red-proof-marker handoff-generated-state.test.sh; class-untraced 'no-decision-time-gate'.
  **This is the deliverable (more findings), not a regression.**
- Call-site population floor on master: `CALLSITE_MIN=36` (`gate-creation-standard.sh:82`); the
  enumeration is append-only and goes RED on shrink. I did NOT get an exact live node count printed
  (the script does not emit one; extracting it timed out). **OPEN: report the exact live
  `${#CALLSITE[@]}` — expected 57 per the ticket. Cheapest way: add a `[ -n "$GCS_DEBUG" ] && echo`
  of the count, or run the B0 block standalone.**
- **REACHABILITY CAVEAT, stated plainly:** the only invoker of `gate-creation-standard.sh` on master
  is its own companion test `fleet/tests/gate-creation-standard.test.sh` (run by `fleet/gate.sh`).
  The script itself prints, honestly:
  `ADVISORY not-wired: validate_board.sh does not yet run this meta-gate's scan … owned by another ticket`.
  So the 11 findings are VISIBLE but **do not block a merge** — `validate_board.sh` is the rig merge
  gate and it does not call this scan. This is the "merged but not fully reached" state the campaign
  exists to end, and it is only PARTLY closed for this branch. The wiring is owned by another ticket
  (see `fleet/GATE-CREATION-STANDARD.md` 'Wiring status' for the one-liner). **FOLLOW-UP REQUIRED.**

### 3. wci-contention-teeth — merged; NOT independently execution-verified (budget cut)
- `fleet/wci-contention.sh` and `fleet/wci-actions.sh` present on master. `validate_board.sh` emits
  live WCI-ADVISORY lines (observed in every land's gate output, incl. `parallelizability` and
  `justified-disjoint-dep` rows), so the WCI path is reached by the merge gate.
- **OPEN: the ratchet ships OFF (leave it off) and the 4 closed fail-open paths were NOT
  individually red-proofed on master.** Next session should red-proof those 4.

### 5. 4lom-canary-service — merged; NOT execution-verified (budget cut)
- Added on master: `fleet/canary-service/run-canary.sh`, `fleet/canary-service/deploy-4lom.sh`,
  `fleet/tests/canary-service.test.sh`, `fleet/watchdog/monit.d/canary-service.conf`,
  and 5 rows in `fleet/state/service-registry.tsv` (831 insertions).
- **OPEN: it is a DEPLOYED SERVICE — merging the files does not start it on 4-LOM.** Not verified
  running. Next session: deploy via `fleet/canary-service/deploy-4lom.sh` and confirm monit picks up
  `canary-service.conf`, then confirm the SLOW-vs-BROKEN attribution report is being produced.
  Ticket's own measurement on-branch was 66 green / 8 BROKEN / 4 SLOW on the 78-file suite.

## STILL OPEN / NOT DONE BY THIS SUB
1. `fleet/gate.sh` on master — **NOT RUN** (budget). Required by the brief.
2. Post-landing `fleet/validate_board.sh` — **NOT RE-RUN** after the 5 lands (budget).
   PRE-landing run was **rc=0 GREEN** (`GREEN board structurally valid`), and validate_board ran
   GREEN as the gate inside each of the 5 lands, the last of which was against the fully-landed
   worktree content. So the last observed rc is 0, but a clean post-merge run on master is owed.
3. Local `master` in `/home/stack/charon-private` is **STALE** (`4e1715f`) vs origin (`ec34714`)
   because the checkout is DIRTY. Dirty set is board hygiene only:
   deleted `fleet/board/{DEGRADE-ALERT,EVAL-CONTROL-GATE-FIX,LITELLM-CI-DEPS,LITELLM-COST-FIELD-FIX}.md`
   + untracked `fleet/board/archive/` copies of the same four.
   Manual sync (from the brief's own land.sh output):
   `(cd /home/stack/charon-private && git stash -u && git merge --ff-only origin/master && git stash pop)`
   **Until this is done every future land will also return rc=8.** This is the single highest-value
   next action — it is the root cause of all five rc=8s.
4. Worktrees `/home/stack/charon-private-wt/{TICKET-MAP-GATE,PLANE-CANARY-WIRE}` were auto-removed by
   the post-land done-mark. `META-GATE-CALLSITE`, `WCI-TEETH`, `4LOM-CANARY` still exist and can be reaped.
5. `feat/tier-classifier` (wt TIER-BALANCE) was OUT OF SCOPE and NOT touched — another sub owns it.
6. Remove the verification worktree `VERIFY-MASTER` (command above).

## Pre-existing reds observed, NOT mine, NOT fixed
- `validate_board` WARN: `RECONCILE-BOARD-PR-DONE` owns `fleet/checks/reconcile-board-pr-done.sh`
  and `fleet/tests/reconcile-board-pr-done.test.sh`, neither of which exists yet.
- The 8 RED planes listed above pre-date this campaign; plane-canary now makes them VISIBLE,
  which is the point of landing #4.
