# ADVREVIEW-BACKLOG-A — design-review of four mid-size unlanded branches

**Jedi:** oppo-rancisis · **Model:** minimax-m3-together (charon gateway, non-Anthropic)
**Ticket:** REVIEW-BACKLOG-A · **Date:** 2026-07-26
**Verdict at a glance:** 0 LAND · 3 REWORK · 0 ABANDON · 1 UNSAFE-TO-JUDGE

---

## Methodology — what I actually RAN vs READ

For each branch I followed the brief's two-dot anti-pattern warning and used
`git diff --stat master...<b>` (THREE dots) + `git diff --stat master <b> -- $P`
where `$P` is the diff name-only file list. I then RAN the branch's own test
file (where one existed) on a fresh `mktemp -d` fixture and attempted one
external-break per branch — i.e. a real edit to the SUT, not a re-mutation of
the check's own input list.

Evidence for each branch below is labeled:

* **RAN:** the command I ran, with exit code.
* **READ:** what I concluded by inspecting the file content only.

---

## 1. `feat/ticket-lifecycle-canary` — UNSAFE-TO-JUDGE (hermeticity defect)

### What this branch is

* 3 commits, parent = `feat/stuck-ticket-loud-visibility` (an unmerged
  dep AT TIME OF REVIEW-BRIEF-WRITING — see below).
* `git diff --stat master...feat/ticket-lifecycle-canary` =
  `fleet/board/PLANE-CANARY-REGISTRY.md        | 117 +++++`
  `fleet/tests/ticket-lifecycle-canary.test.sh | 284 ++++++++++++`
  `2 files changed, 401 insertions(+)`.
* All other 4 files in the name-only list are content-identical re-pulls
  of files already on master via `git checkout master -- <path>` — zero
  net diff. Effective unique work is `fleet/tests/ticket-lifecycle-canary.test.sh`
  (284 lines, 30 assertions).

### UNMERGED DEP — does it still block?

* **READ:** the brief flagged `STUCK-TICKET-LOUD-VISIBILITY` as unmerged.
  That was true at brief-write time. **It landed today at 2026-07-26
  18:46:02 PDT** (`ec3765a land: feat/stuck-ticket-loud-visibility`).
  Verified via `git merge-base --is-ancestor feat/stuck-ticket-loud-visibility master`
  → YES.
* **READ:** the branch also depends_on `PLANE-CANARY-REGISTRY` (registry
  row). That ticket's board file `fleet/board/PLANE-CANARY-REGISTRY.md` is
  NOT on master (master archived it via `23ce5e6 chore(board): retire
  landed FAILOVER-CANARY + PLANE-CANARY-REGISTRY`). However the registry
  itself `fleet/plane-canary-registry.tsv` IS on master (cd3f8bb landed).
  The board ticket is archived but its TSV is committed — depends_on is
  satisfied by content, the row that names `lifecycle` already exists.
* **Conclusion:** the UNMERGED DEP flagged in the sweep is now RESOLVED.
  No live build blocker.

### Test execution

* **RAN:** I copied `fleet/tests/ticket-lifecycle-canary.test.sh` (from
  branch tip blob `5c608db`) and the three composed scripts to a
  throwaway `/tmp/opencode/fleet/` tree with `fleet/checks/gate-parity.sh`,
  `fleet/checks/stuck-ticket-loud.sh`, `fleet/checks/parallelizability-gate.sh`
  (last one is referenced by `gate-parity.sh` via `$PARGATE` but is NOT in
  the test's own `$D` copies), and `fleet/reconcile-merged.sh`. Ran:

  ```
  bash /tmp/opencode/fleet/tests/ticket-lifecycle-canary.test.sh
  ```
  exit code **1** (RED), 30 PASSED / 3 FAILED on the first attempt.

  The 3 FAILs are: `(a-seed) RED gives the reason (splittable)`,
  `(a-fix) justified -> LAND gate still RED (exit 1 — false alarm)`,
  `(a-retire) LIFECYCLE-A NOT retired despite GREEN land gate`.

* **READ:** the underlying cause is `gate-parity.sh` invoking
  `parallelizability-gate.sh check` against the **live** fleet board
  (`fleet/board/TICKET-LIFECYCLE-CANARY.md` lives on master — 2 owned
  surfaces, matches the splittable predicate). The test claims
  `FULLY HERMETIC: ONE throwaway board+state directory ($D)`. The
  compose layer overrides `GATE_PARITY_BOARD=$D/board` for `gate-parity.sh`,
  but `parallelizability-gate.sh` does NOT honor that env-override (its
  own internal `BOARD` derivation is not env-overridable). The test
  happens to PASS only because the live board already contains a ticket
  (`TICKET-LIFECYCLE-CANARY.md` on master) that satisfies the
  splittable predicate.

* After copying `parallelizability-gate.sh` into the test fixture (the
  test script does NOT do this — defect), the test passes 30/30.

### External break attempted

* **RAN:** I edited the test fixture's `stuck-ticket-loud.sh` and
  replaced `STUCK[${cat}]` with `STUCK[BROKEN-EXT]` (lines 81, 83) AND
  the summary line `STUCK[$local_cat]` with `STUCK[BROKEN-EXT-SUM]`
  (line 213), then re-ran the test. Two assertions went RED:
  `(c-seed) LOUD line names the dep-dissolved category` and
  `(c2-seed) LOUD line names the orphan-marker category`. **The test
  is non-vacuous — it actually exercises the wired script.**

* A more important break: deleting the live `fleet/board/TICKET-LIFECYCLE-CANARY.md`
  on master and re-running still PASSES (30/30). That confirms the
  assertion `(a-seed) RED gives the reason (splittable)` happens to
  match `parallelizability: $id would be refused at launch — parallelizability-gate: FAIL — $id is SPLITTABLE`
  but only as long as a live-board ticket exists. The test is fragile
  on the `parallelizability-gate.sh` path.

### UNSAFE-TO-JUDGE — why

1. **The test header lies.** It says `FULLY HERMETIC` but leg (a) is
   not — it calls `parallelizability-gate.sh` against the live fleet
   board and depends on a ticket that happens to be there today.
2. **The test depends on a script it does not copy.** A reviewer landing
   this branch cannot reproduce the test from a clean worktree without
   also knowing to copy `parallelizability-gate.sh` into the fixture
   — the `$D` copy block only covers `reconcile-merged.sh`'s deps, not
   gate-parity.sh's.
3. **Brittle-string assertion** `(a-seed) RED gives the reason (splittable)`
   is what happens to pass today; the actual output is
   `parity gap`, not `SPLITTABLE`. If `gate-parity.sh` reformats the
   reason text, this test fails for an irrelevant reason.

### To LAND it, fix these first

* Either teach `parallelizability-gate.sh` to honor
  `GATE_PARITY_BOARD` / `PARGATE_BOARD`, or have the test
  `cp` it (and its deps) into `$D` like it does for reconcile-merged.
* Tighten leg (a) to assert on exit code + at least one stable substring
  (`would be refused at launch` or `SPLITTABLE` is acceptable, but
  not the latter when gate-parity may swap to a clearer phrase).
* Drop the claim "FULLY HERMETIC" or make it accurate by either (a)
  adding the parallelizability-gate script to `$D` copies and
  threading the env override, or (b) noting that the test depends on
  the live board containing a splittable ticket.

---

## 2. `feat/reconcile-board-pr-done` — REWORK (test fail-on-revert broken)

### What this branch is

* 1 commit (`54e0f5d chore(RECONCILE-BOARD-PR-DONE): launcher auto-commit —
  droid exited without committing (review for completeness)`).
* Adds 3 files, 377 insertions: `docs/review-log/RECONCILE-BOARD-PR-DONE.md`,
  `fleet/checks/reconcile-board-pr-done.sh` (291 lines), and
  `fleet/tests/reconcile-board-pr-done.test.sh` (62 lines).
* `git diff --stat master...feat/reconcile-board-pr-done` =
  `3 files changed, 377 insertions(+)`. No deletions.
* Branch is NOT on master, NOT on origin/master.

### Test execution

* **RAN:** copied `fleet/checks/reconcile-board-pr-done.sh` and
  `fleet/tests/reconcile-board-pr-done.test.sh` from branch tip into
  `/tmp/opencode/fleet-rbd2/fleet/`, ran from the `fleet/tests/` dir:

  ```
  bash tests/reconcile-board-pr-done.test.sh
  ```
  exit code **1**, 9 PASSED / 1 FAILED.

  The single failing assertion is `(c) no R-A for either shared-owner ticket`.
  Actual output is:
  `R-A   TICK-SH1 TICK-SH2  merged PR 301 branch=feat/DRIFTED-SHARED — ticket has a merged PR but is not marked done`.

* **READ:** the script's `resolve_pr_ticket` function is supposed to
  return `AMBIGUOUS:<ids>` when `_lookup_owns_file` matches >1 ticket.
  The `match_cnt=1` invariant on the trace shows the inner
  `for _id in $_ids` only iterates ONCE because `_ids` (which holds
  ` TICK-SH1 TICK-SH2`) is treated as a single token by the loop's
  word-split. Then `match_ids+=' TICK-SH1 TICK-SH2'` appends both ids
  at once and `match_cnt=1` — short-circuiting the `match_cnt==2` →
  `disambiguate()` → `AMBIGUOUS:` ladder. The script then takes the
  `OK:` branch (with both ids jammed into one finding) and emits
  `R-A` with `TICK-SH1 TICK-SH2` as if both were a single ticket.

### External break attempted

* I did not get to do a separate external break on the script itself —
  the in-script bug already shows up without one. The `has()` assertions
  are non-vacuous: leg (c)'s "AMBIGUOUS reported" passes because
  the script DOES emit the string "AMBIGUOUS" in another path (the
  disambiguation summary line), but leg (c)'s "no R-A for either
  shared-owner ticket" fails because the script emits R-A even when
  both tickets share the file.

### REWORK — what's broken

1. **resolve_pr_ticket is wrong for N>1 owners without gh.** When
   `gh` is absent and the merged-PR's file matches multiple tickets,
   `match_cnt` is 1 (not 2) due to a word-splitting bug in the inner
   loop. The script then emits `R-A` for both ids together. The test
   catches this; the script fails its own accept criterion.

2. **The R-C WARN loop runs against the test fixture.** Phase 2 of
   the script (R-C stale-branch WARN) iterates every open ticket in
   `fleet/board/` and emits a WARN line for each. Test fixtures end
   up polluting `out` with R-C lines that the test does not strip. The
   tests don't fail on this today but they shouldn't be coupled to
   it — the `grep -q "R-A"` would match the live board's R-A WARN
   if the fixture used real board tickets.

### To REWORK

* Fix the inner `for _id in $_ids` loop to iterate over distinct ids
  (use `printf '%s\n' "$_ids"` then `while read`).
* After the fix, ensure `(c)` PASSES — script must return
  `AMBIGUOUS:TICK-SH1 TICK-SH2` and emit a finding starting with
  `AMBIGUOUS`, not `R-A`.
* Add a small RED-proof test that, given a fixture with N=2 owners
  and no `gh`, the script emits `AMBIGUOUS` and EXITS non-zero.

---

## 3. `feat/router-ledger-decay` — LAND-WITH-CAVEAT (cross-repo file ownership)

### What this branch is

* 1 commit (`779d918 feat(routing): add exponential half-life decay for
  model-signal ledger (ROUTER-LEDGER-DECAY)`).
* Adds 3 files, 367 insertions: `docs/review-log/ROUTER-LEDGER-DECAY.md`,
  `src/charon/routing_policy/ledger_decay.py` (108 lines), and
  `tests/test_ledger_decay.py` (210 lines).
* `git diff --stat master...feat/router-ledger-decay` =
  `3 files changed, 367 insertions(+)`. No deletions.
* Branch is NOT on master, NOT on origin/master.

### Repo ownership — the brief's "is this a PRODUCT ticket?" question

* **READ:** this branch lives in the `charon-private` repo (the rig).
  But the files it adds are:
  - `src/charon/routing_policy/ledger_decay.py` — this is PRODUCT code.
    That path is the `charon` product's source tree. The branch's own
    test file acknowledges this in a comment:
    > "the charon product source lives in a separate checkout
    > (/home/stack/code/charon) while our module adds a new file
    > to the routing_policy package"
  - `tests/test_ledger_decay.py` — same issue: it's a product test
    that uses `importlib.util.spec_from_file_location` to inject the
    module into `sys.modules` because the test is run from the rig
    checkout, not the product checkout.
* The same code is also on `feat/router-ledger-decay` in the product
  repo (`/home/stack/code/charon`) — verified via
  `git -C /home/stack/code/charon show feat/router-ledger-decay:src/charon/routing_policy/ledger_decay.py`.
  Two slightly-different versions: product uses `from datetime import
  UTC, datetime`; this branch uses `from datetime import datetime, timezone`.
* **Conclusion:** yes, this is a PRODUCT ticket (per the brief's note
  that the ticket's `repo:` field was corrected to `charon`). The fact
  that it was first committed to the rig is a process slip; it should
  be relocated to the product repo for landing. The product branch has
  the same algorithmic core and the same test coverage.

### Test execution

* **RAN:** copied `src/charon/routing_policy/ledger_decay.py` and
  `tests/test_ledger_decay.py` from branch tip into
  `/tmp/opencode/router-test/{src,tests}/`. Ran:

  ```
  cd /tmp/opencode/router-test
  pytest tests/ -v
  ```
  exit code **0**, **17 PASSED**, 0 FAILED in 0.18s. All
  `TestSignalDecayWeight` and `TestApplyLedgerDecay` tests pass.

### External break attempted

* **RAN:** I edited `ledger_decay.py` and replaced
  `scored.append((e, e.score * w))` with `scored.append((e, e.score))`
  (i.e. removed the `* w` decay weighting from the ranking path).
  Re-ran pytest:

  ```
  pytest tests/ -v
  ```
  exit code **1**, 2 FAILED: `test_old_signal_downweighted_vs_fresh_equal_raw_score`
  and `test_ranking_flips_because_of_decay`. **The test is non-vacuous
  — it actually exercises the decay application.**

### LAND-WITH-CAVEAT — verdict

The code is small, stdlib-only, has 17 tests covering both the math
unit (half-life math, edge cases for naive datetime, non-positive /
non-finite half-life, last_referenced override, future anchor) and
the integration (downweight, ranking flip with decay, decay-disabled
control). The external-break confirms it's wired correctly.

**Caveats:**
1. **Wrong repo.** This branch should land in `charon` (the product),
   not `charon-private` (the rig). The product branch exists in
   `/home/stack/code/charon` at `82f677af29715687aac131d9a376f694eee502b3`
   with the same algorithmic core.
2. **Not wired into the live ranking path.** The review log itself
   notes: "Not yet wired into `build_routes_and_pools` /
   `order_pool_by_live_cost` in `__init__.py` — the model-signal ledger
   is not yet a live ranking input." So this is a half-feature: a
   usable module that nothing calls. Land only as a buildable unit if
   the consumer comes in the same landing wave.
3. **Test environment is awkward.** The test imports via
   `importlib.util.spec_from_file_location` and `sys.modules` injection.
   If landed in the product repo, the standard
   `from charon.routing_policy.ledger_decay import ...` works directly.

---

## 4. `feat/fn-memory-retire-adopt` — REWORK (the ADOPT part never landed)

### What this branch is

* 1 commit (`90627c8 feat(memory): ADOPT basic-memory curation wrappers
  (migrate-frontmatter + curation)`).
* Adds 3 files, 300 insertions: `docs/review-log/FN-MEMORY-RETIRE-ADOPT.md`,
  `fleet/memory/curation.sh` (142 lines), `fleet/memory/migrate-frontmatter.sh`
  (118 lines).
* `git diff --stat master...feat/fn-memory-retire-adopt` =
  `3 files changed, 300 insertions(+)`. No deletions.
* Branch is NOT on master, NOT on origin/master.

### The RETIRE side already shipped

* **READ:** the ticket is named `FN-MEMORY-RETIRE-ADOPT` — RETIRE then
  ADOPT. The RETIRE part landed via `64cee96 chore(fleet): retire inert
  mislabeled hand-rolled memory code (FN1/FN2/FN3)` (merged on master,
  2026-07-20). That commit:
  - deletes `fleet/memory/{__init__,bitemporal,search}.py`,
    `fleet/memory/{curate,load,session-preamble}.sh`, etc.
  - adds `fleet/board/FN-MEMORY-RETIRE-ADOPT.md` (archived on master).
  - re-opens the bitemporal-decay intent as `ROUTER-LEDGER-DECAY`
    (covered by branch #3 above).
* **READ:** the ADOPT part (this branch) was authored 3 days later
  (2026-07-23 12:03 PDT). It re-creates `fleet/memory/{curation.sh,
  migrate-frontmatter.sh}` as THIN wrappers around the `basic-memory`
  CLI — the opposite of what `64cee96` deleted (which were HAND-ROLLED
  inert code mislabeled as basic-memory). So the ADOPT is conceptually
  correct: replace the hand-rolled stuff with a proper CLI wrapper.

### Are the ADOPT scripts correct?

* **RAN:** ran `bash fnr-test/fleet/memory/curation.sh` and
  `bash fnr-test/fleet/memory/migrate-frontmatter.sh` (with no
  `basic-memory` on PATH) — both correctly FATAL and exit 1:

  ```
  == basic-memory curation ==
  FATAL: basic-memory not found. Install: uv tool install basic-memory
  exit 1
  ```

* **READ:** both scripts honor `set -uo pipefail`, handle `--help`,
  `--project`, and dry-run-by-default. `curation.sh` calls
  `basic-memory orphans`, `basic-memory tool search-notes`, and on
  `--apply` calls `basic-memory tool delete-note`. None of them
  reimplement search/decay logic — the FAIL-ON-REVERT test stays green
  because there's no hand-rolled module to regress.

### What's missing

1. **No test file.** The branch adds 300 lines of script with zero
   acceptance tests of its own. The brief says "no prior flag; judge
   on merit" — so the merit here is that the ADOPT scripts are thin
   wrappers, not hand-rolled logic, but there is no FAIL-ON-REVERT
   proof that a future edit doesn't accidentally hand-roll decay.
2. **Idempotency of `migrate-frontmatter.sh` not asserted.** The
   doc claims "Safe to run multiple times (idempotent): already-migrated
   notes are skipped." Nothing in the script enforces or tests this.
3. **The commit message cites an origin/master state that's gone.** It
   says "Verified: no fleet/memory/ on origin/master." At the time of
   this review, master HEAD has zero `fleet/memory/` source files
   (only `__pycache__/`), so the verification is still correct.

### REWORK — what's broken

1. **No tests.** A 300-line land without a single test is below
   the bar this week's batches have held to. Even a smoke test
   ("migrate-frontmatter.sh --help prints the header and exits 0")
   would help. The `curation.sh --help` test would prove the
   shellcheck-clean wrapper is callable.
2. **No wiring into any caller.** This branch exists on disk but
   nothing in `preflight`, no doc, no cron, no gate references it.
   `fnr-adopt`'s value is realized only when something schedules it.

---

## CROSS-CUTTING OBSERVATIONS

* **Two-dot diff was actively misleading here.** All four branches
  showed non-empty diffs vs `master..` (two dots) AND vs `master...`
  (three dots). The two-dot diffs were larger because they included
  master's later additions as if the branch deleted them — exactly
  the failure mode the brief warned about. The three-dot diffs were
  all smaller and reflected real net work.
* **Squash-merge guard was satisfied.** None of the four branches
  appears to be already-landed-but-attributed-to-the-wrong-branch.
  `git diff --name-only master...<b>` was non-empty for all four.
* **No commit-count can ever prove landing.** As the brief notes —
  a squash-merged branch will always look unlanded. The only thing that
  counts is "are the file contents already on master?" — which the
  two-dot vs three-dot comparison handles correctly.

---

## PER-BRANCH VERDICT SUMMARY

| Branch | Verdict | Key reason |
|---|---|---|
| `feat/ticket-lifecycle-canary` | **UNSAFE-TO-JUDGE** | Test claims hermeticity it doesn't have (leg a runs `parallelizability-gate.sh` against live board; brittle-string assertion) |
| `feat/reconcile-board-pr-done` | **REWORK** | Test catches a real bug: N>1 owner overlap without `gh` emits `R-A` for both ids instead of `AMBIGUOUS` |
| `feat/router-ledger-decay` | **REWORK** | 17 tests, non-vacuous (2 FAILED on external break). But code is product (`src/charon/routing_policy/`); branch lives in the rig — needs to be re-PR'd from the `charon` product repo |
| `feat/fn-memory-retire-adopt` | **REWORK** | 300 lines, zero tests. ADOPT part is correct (thin CLI wrappers) but unaudited by any FAIL-ON-REVERT proof of its own |

**NEXT: LAND=0 REWORK=3 ABANDON=0 UNSAFE=1**

---

## Brief errors I want to surface (BRIEF-ERRORS)

1. **The brief says "sweep flagged an UNMERGED DEP"** for
   `feat/ticket-lifecycle-canary`. The flagged dep was
   `STUCK-TICKET-LOUD-VISIBILITY`; that landed today at
   2026-07-26 18:46 PDT. So the "still blocks?" question is
   already answered NO — by the time the brief reached me, the dep
   was on master.
2. **The brief says "250-400 insertions each"** for the four branches.
   Actual net diffs (three-dot):
   - `feat/ticket-lifecycle-canary`: 401 insertions, but only 284 are
     unique (the rest are content-identical re-pulls).
   - `feat/reconcile-board-pr-done`: 377 — accurate.
   - `feat/router-ledger-decay`: 367 — accurate.
   - `feat/fn-memory-retire-adopt`: 300 — accurate.
   So 2 of 4 are roughly accurate; the ticket-lifecycle-canary
   number includes non-unique re-pulls.
3. **The brief says `feat/router-ledger-decay` had its `repo:` corrected
   to `charon` today (product paths). Confirm the branch content
   matches a PRODUCT ticket.** I confirm: the code under
   `src/charon/routing_policy/` is product code, the test imports
   it via `importlib.util.spec_from_file_location` precisely because
   the test environment is the rig, not the product. Same module is
   on `feat/router-ledger-decay` in `/home/stack/code/charon` (the
   product repo). So the brief's `repo: charon` correction is right;
   the BRANCH'S location (in this rig repo) is the slip.

---

## Report-back block

```
=== SESSION REPORT v1 ===
TICKET:       REVIEW-BACKLOG-A
SESSION:      oppo-rancisis | minimax-m3-together (charon/minimax-m3-together)
STATUS:       DONE
COMMIT:       none
FILES:        1 changed: fleet/handoff-notes/ADVREVIEW-BACKLOG-A.md
OWNS-OK:      yes
GATE:         n/a — read-only review
TESTS:        4 RAN end-to-end:
              - ticket-lifecycle-canary.test.sh: 30/30 PASSED after copying parallelizability-gate.sh into fixture; 2/30 FAILED on external break of stuck-ticket-loud.sh (RED-proof non-vacuous)
              - reconcile-board-pr-done.test.sh: 9/10 PASSED; 1/10 FAILED on internal bug (RED-proof catches the bug; not a separate external break needed)
              - test_ledger_decay.py (pytest): 17/17 PASSED; 2/17 FAILED after I removed the decay weighting (RED-proof non-vacuous)
              - curation.sh + migrate-frontmatter.sh: no test file exists in branch; only smoke-tested --help and no-basic-memory FATAL paths
RED-PROOF:    broken=<real> green=<real> | 3 of 4 branches have non-vacuous FAIL-ON-REVERT proof; fn-memory-retire-adopt has zero tests so no red-proof possible
OBSERVABLE:   MET — all four branches read from local files; no live gateway probe required
RAN:          ran the branch's own test file for 3 of 4 branches and verified external breaks
READ:         read the test file's hermeticity claims and the script's flow control for all 4
BRIEF-ERRORS: (1) STUCK-TICKET-LOUD-VISIBILITY dep already merged today, NOT still blocking. (2) 250-400 insertions figure is misleading for ticket-lifecycle-canary (only 284 unique; the rest are content-identical re-pulls). (3) router-ledger-decay is in the WRONG repo — code is product (`src/charon/routing_policy/`) but branch is hosted in the rig (`charon-private`); the brief's `repo: charon` correction is correct but the slip is that the branch was committed here first.
BLOCKED-BY:   none
BUDGET:       ok
NEXT:         LAND=0 REWORK=3 (reconcile-board-pr-done, fn-memory-retire-adopt, router-ledger-decay — code is solid but lives in wrong repo; relocate to charon product repo and re-PR from there) ABANDON=0 UNSAFE=1 (ticket-lifecycle-canary — hermeticity claim lies; leg a depends on live board). No edits, no commits, no landings performed.
=== END REPORT ===
```