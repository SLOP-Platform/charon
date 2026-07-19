# AUDIT & RE-SEQUENCE — 2026-07-18

READ-ONLY audit across both repos. No edits, commits, pushes, board or ref changes were made.
Every status claim below is code-confirmed with file:line. Markers, docstrings, review-logs and
prior summaries were treated as untrusted per the standing directive.

Repos:
- Rig: `/home/stack/charon-private` (`Nnyan/charon-private`)
- Product: `/home/stack/code/charon` (`SLOP-Platform/charon`)

State at audit time: rig main tree is at **detached HEAD `522c147`** (a concurrent agent is
reconciling master). 63 worktrees, ~62 unlanded feature branches. Board = 57 live tickets,
174 done-markers.

---

## PART 1 — STATUS AUDIT OF LIVE WORK

### 1.1 Board is stale in the "already landed" direction — 10 tickets

Verified with the now-repo-aware `verify_merged`. These occupy the live board but are provably
landed and should be retired:

| ticket | board state | truth |
|---|---|---|
| ENV-REGISTRY-WIRE | DONE | rig PR #87 MERGED `01b4060` — RETIRABLE |
| EVAL-TAXONOMY-ALIGN | DONE | `f83810b` in rig origin/master — RETIRABLE |
| FOREMAN-WIRE | DONE | verify_merged RC=0 — RETIRABLE |
| GRAPHIFY-MAP-FRESHNESS | DONE | verify_merged RC=0 — RETIRABLE |
| SALVAGE-STASH-CHARON-RUN | DONE | verify_merged RC=0 — RETIRABLE |
| FOREMAN-MULTI-TRIGGER | **PR-OPEN** | rig PR #106 **MERGED** — board lies |
| LAUNCH-PLAN-SH | **PR-OPEN** | rig PR #92 **MERGED** — board lies |
| ON-DEMAND-TOOL-AUDIT | **PR-OPEN** | rig PR #98 **MERGED** — board lies |
| STALE-CHECK-SH | **PR-OPEN** | rig PR #94 **MERGED** — board lies |
| TSV-APPEND-UNIFY | **PR-OPEN** | rig PR #99 **MERGED** — board lies |

The 5 `PR-OPEN`-but-merged rows are the more dangerous shape: they hold dependents blocked on a
ticket that is already done.

### 1.2 Tickets whose PREMISE IS NOW FALSE

| ticket | verdict | evidence |
|---|---|---|
| DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD | **NO-LONGER-NEEDED** | its PR (prod #162) was CLOSED, but the work was **rebuilt and landed** as `72a11d8` "route decomposer through the switchboard (rebuilt on master w/ #165)", merged via #168 `6805be1`. Board still says PR-OPEN pointing at a closed PR. |
| GATEWAY-NONTOKEN-METERING | **NO-LONGER-NEEDED** | prod #155 CLOSED, but rebuilt and landed as `da600d2` "non-token metering (rebuilt on master w/ #165)", merged via #167 `093d520`. Board says PR-OPEN. Note **FT-WIRE-QUOTA and METER-KWH-USD-FIX both list this as a blocking dep** — clearing it unblocks two tickets. |
| PROJECT-MEMBERSHIP-GATE | **PREMISE MISATTRIBUTED** | board has **no `repo:` field**; its PR-OPEN points at product PR #130 (CLOSED), but the ticket is rig-side (`owns:` = `fleet/validate_board.sh`, `fleet/state/ROADMAP.tsv`; created by rig commit `e945926`). No rig PR exists; `fleet/checks/*membership*` does not exist. Work **NOT-STARTED**, ticket is merely mis-pointed. It blocks CREATION-GATE-DECOMPOSE-WIRE. |
| ADR0016-DEPLOY-PRICED-COMPLETENESS | **STILL NEEDED** (board wrong) | prod #153 CLOSED and **not** rebuilt — no `priced-completeness` commit in product master. `owns: src/charon/routing_policy/cost_rank.py`. Board says PR-OPEN; it is really NOT-STARTED. |

### 1.3 GH-SEAM-CHOKEPOINT — premise CONFIRMED and WIDER than ticketed

The handoff claimed "15 direct `gh`/`git fetch` sites in 8 files". Actual count on current master:
**32 sites across 13 files** (excluding tests and `gh-cache.sh` itself):

```
11 fleet/land.sh      3 fleet/fleet-droid.sh   2 fleet/submit.sh
 2 fleet/status.sh    2 fleet/repo-registry.sh 2 fleet/reconcile-held-markers.sh
 2 fleet/land-needs-push.sh  2 fleet/done.sh   2 fleet/_lib.sh
 1 fleet/reconcile-merged.sh 1 fleet/handoff.sh 1 fleet/deploy-session-end.sh
 1 fleet/checks/base-integrity.sh
```

`fleet/gh-cache.sh` exists; the declared guard `fleet/checks/gh-direct-call-guard.sh` **does not**.
Ticket scope should be revised upward before it is claimed.

### 1.4 `repo:` field gap on the live board

6 of 57 live tickets carry no `repo:` field: **BENCH-OOB-GRADING, GRACEFUL-DEGRADE,
GRADER-SECFIX-RECONCILE, PROJECT-MEMBERSHIP-GATE, WEB-ROADMAP-GENERATOR,
WORK-ROUTING-TO-CHARON-ENGINE**. Each is a live instance of the REPO-FIELD-REQUIRED premise, and
PROJECT-MEMBERSHIP-GATE (1.2) shows the field's absence actively producing a wrong board state.
This is far better than the "120 of 226" figure in the brief — that count included done-markers,
which have no board file at all.

### 1.5 `check_inert_code` green is unreliable

Per the standing caveat, the detector runs GREEN on gateway modules that are constructed and
stored but never invoked. Its green must not be read as proof for WORK-GATE-UNIVERSAL Gate B.
This is exactly INERT-INSTANCE-DETECT's premise, which remains valid.

---

## PART 2 — RE-VERIFICATION OF PAST RETIREMENTS (fixed instrument)

Ran `bash fleet/verify-merged.sh <id>` read-only over all **174** markers in `fleet/state/done/`.
`retire-done.sh` was NOT run.

| bucket | count |
|---|---|
| VERIFY, carries `merged:` proof | 73 |
| VERIFY, no proof line (verified via board branch/PR) | 63 |
| **NO-VERIFY, no proof at all (bare timestamp)** | **36** |
| NO-VERIFY despite carrying proof | 2 → **both false negatives, see below** |

### 2.1 Markers that now VERIFY but were previously held → RETIRABLE

**136 of 174** markers verify under the fixed instrument. This includes the whole class the
handoff called out as permanently un-retirable (rig-repo tickets verified against the product
repo). The 5 board-DONE tickets in §1.1 are confirmed retirable.

### 2.2 Phantoms — NONE FOUND

Two markers failed the batch sweep while carrying merge proof, which is the REPO-DECL-CENTRAL
shape. **Both are false negatives of the sweep, not phantoms.** Re-run individually they return
RC=0:

- **ENV-REGISTRY-WIRE** — `merged:#87`. `bash -x` trace confirms the repo-aware path works end to
  end: reads `repo: charon-private` → `repo_resolve` → `/home/stack/charon-private` +
  `Nnyan/charon-private` → `gh pr view 87` → `mergedAt=2026-07-16T01:18:24Z` → RC=0. Rig PR #87
  IS merged at `01b4060`. (Product #87 is an unrelated CLOSED PR — the exact cross-repo collision
  the old instrument fell into.)
- **EVAL-TAXONOMY-ALIGN** — `merged:f83810b`. That sha exists in the **rig** and is contained in
  `origin/master`; it is not a valid object in the product repo.

Cause of the batch false negatives: transient `gh` failures under the tight 174-call loop, not a
logic defect (`gh api rate_limit` showed core 4982/5000, graphql 4748/5000 afterwards — no
sustained exhaustion). **Conclusion: `verify_merged` is genuinely fixed. No committed work is
missing behind a lying marker.**

### 2.3 The real danger class — 36 unverifiable bare markers

All 36 NO-VERIFY markers share two properties: **no `merged:` proof line AND no board file at
all**. They are unverifiable by construction — there is no `repo:` to resolve and no sha/PR to
check. The fixed instrument cannot rescue them; only archaeology can.

```
ACTION-PIN-POLICY  ACTUALS-LEDGER  ADR-0015  BRIDGE-HARDEN  CLIENT-CONNECT-GUI
CONSOLE-PROVIDER-MGMT  CWD-CONFIG  DIFFICULTY-SCHEMA  DRAIN-ROUTING  DS-PLAN-REVIEW
DTC-1 DTC-2 DTC-3 DTC-4 DTC-5 DTC-7 DTC-8-TEST-PATTERNS  FALLBACK-PROVIDER
HANDOFF-PIPEFAIL  INC-401-FAILOVER  OBS-CAPTURE  ORCH-ROUTE  PREFLIGHT
PROXY-FAILOVER-FIX  PUBLIC-CLEAN-LINT  REQUEST-NORMALIZER  RFL-1  SETUP-KEY-UX
SR-1 SR-2 SR-4 SR-5 SR-5b SR-7 SR-8  WORK-CONVERGE-REVIEW
```

Note this is a **superset** of the brief's list (SR-1/2/5/5b/7/8, SETUP-KEY-UX) — SR-4 and 28
others share the shape. Several are money/trust-path (ACTUALS-LEDGER, DRAIN-ROUTING,
PROXY-FAILOVER-FIX, INC-401-FAILOVER, SR-5/5b pricing) and their "done" status rests on nothing
but a timestamp. Proposed: **MARKER-PROOF-BACKFILL** (see Part 4).

### 2.4 REPO-DECL-CENTRAL — the phantom is RECOVERABLE

Already corrected on rig master by `0f9d02f`. Confirmed here that the **code is not lost**:
branch `feat/repo-decl-central` exists, 1 commit ahead of master, **532 insertions / 9 deletions**
across 7 files (incl. `fleet/retire-done.sh` +7 and a new 191-line
`fleet/tests/repo-decl-central.test.sh`). It was built and never landed. It is landable.

---

## PART 3 — RE-CHECK OF THE PROPOSED WORK POOL (handoff §3)

Critically, **5 of the 8 proposed items were BUILT since the harvest and now sit in open PRs** —
they are no longer "proposed work" and must not be re-ticketed or re-claimed:

| item | status now |
|---|---|
| GH-SEAM-CHOKEPOINT | **STILL NEEDED, SCOPE GREW** — 32 sites/13 files, not 15/8 (§1.3). Guard script absent. Blocked on GITHUB-LIMITS-HARDENING (#101). |
| INERT-INSTANCE-DETECT | **STILL NEEDED** — premise intact; detector still blind to construct-but-never-invoke. Blocked on CAPABILITY-ACTUALS-DEADREF-CLEANUP (prod #164). |
| SELFCHECK-CYCLE-GATE | **BUILT — rig PR #113 open** |
| METER-DOC-RECONCILE | **BUILT — prod PR #174 open** |
| FT-LIMITS-GROQ-RECONCILE | **BUILT — rig PR #116 open** |
| AVAILABILITY-WRITETHROUGH | **STILL NEEDED** — no ticket, no PR, no branch. The only §3 item with zero motion. |
| HANDOFF-ROOT-ARCHIVE | **BUILT — rig PR #114 open** |
| STAGE-DEMUX | **BUILT — rig PR #115 open**. Blocks BENCH-OOB-GRADING. |

The handoff's "tier depth is the bottleneck / frontier 0, economy 0 ready" diagnosis is therefore
**stale** — the refill happened. The bottleneck has moved from *authoring* work to *landing* it.

---

## PART 4 — UNTICKETED WORK SWEEP

All items below were code-confirmed by direct read. Verdicts: 9 CONFIRMED, 1 PARTIAL,
1 NOT-AS-STATED (with a new defect found in its place).

### 4.1 Confirmed unticketed defects

| # | proposed id | verdict | evidence |
|---|---|---|---|
| 1 | **LAND-PUSH-HEAD-REF** | CONFIRMED | `fleet/land-push.sh:69` — `git -C "$REPO" push origin "$BRANCH"`. `$BRANCH` is a *refname*, so git resolves `refs/heads/<name>`, never HEAD. With HEAD detached or on another branch (the main tree is detached at `522c147` **right now**) it pushes a stale ref and exits 0. Nothing in lines 1-68 compares `$BRANCH` to HEAD. |
| 2 | **LAND-SH-BRANCH-F-RC** | CONFIRMED | `fleet/land.sh:11` is `set -uo pipefail` — **no `-e`**. `:150` `git branch -f "$BRANCH" HEAD && echo …` — on failure the `&&` only suppresses the echo; there is no `exit`. Control falls through to `:154` `git push origin "$BRANCH"`, pushing the **stale** same-named local ref; `:160-181` then verifies `state=MERGED` — of the wrong commit — and prints DONE. This is how `522c147` was silently merged today. |
| 3 | **LAND-WORKTREE-HELD-BRANCH** | CONFIRMED (empirically) | `git branch -D feat/coverage-meta-gate` → `error: cannot delete branch … used by worktree at '/home/stack/wt/coverage-meta-gate'`. `git branch -f` carries the same worktree lock, so `land.sh:150` can never move a worktree-held branch — and per #2 it does not abort. With **63 live worktrees** this is the common case, not the edge case. |
| 4 | **LEAK-GUARD-UNCONDITIONAL-D** | **PARTIAL** | `fleet/leak-guard.sh:45` `git -C "$charon" branch -D "$branch" 2>/dev/null \|\| true` **is** unconditional at that point and does erase the per-ref reflog. But it is not reached unguarded: `:34-37` returns 2 when `$npmarker` exists. `:46` recreates off `$base_ref`. Work is orphaned only when the needs-push marker was never written or was cleared — **and `fleet/state/needs-push/` is currently EMPTY, so the guard is presently vacuous for every branch.** Ticket the vacuity, not the unconditional-delete framing. |
| 5 | **COMMIT-ACTOR-STAMP** | CONFIRMED | `git config user.name`=`sim`, `user.email`=`sim@sim`. `grep -rn 'GIT_AUTHOR\|GIT_COMMITTER\|user\.name' fleet/**/*.sh` hits **only test fixtures** (all `t@t`). Neither `land.sh`, `land-push.sh`, `fleet-droid.sh` nor `charon-run.sh` sets any author env, though `fleet-droid.sh:288` has `$DROID`/`$id` in scope and uses them for brief/log paths. Droid, sub-agent and manager commits are indistinguishable in git history. |
| 6 | **RETIRE-DONE-REPO-UNAWARE** | NOT-AS-STATED → **new defect** | `done.sh:161` does call `retire-done.sh "$id"`, but it is **single-ticket, not a sweep**: `retire-done.sh:39-40` `ONLY_ID="${1:-}" … DONE_MARKERS=("$DONE/$ONLY_ID")`, `retire_safe()` `:28-33` HOLDS any non-merge-verified marker, worktree removal `:74` goes through `safe_worktree_remove`. **The real bug: `retire-done.sh:64` hardcodes `CHARON="/home/stack/code/charon"` and `:71` derives `wt="$CHARON-fleet-$id"`, so `repo: charon-private` tickets (worktrees at `/home/stack/charon-private-wt/<ID>`) are silently never cleaned.** Same root cause as the just-fixed VERIFY-MERGED-REPO-AWARE — the repo-awareness fix did not reach this file. |
| 7 | **SESSIONSTART-PUSH-ADVICE** | CONFIRMED — hook is **out-of-repo** | Not `fleet/hooks/session-start.sh` (that only prints an ahead count at `:83`). `/home/stack/.claude/settings.json` `hooks.SessionStart` registers `bash /home/stack/v5/docs/tools/check_push_status.sh`, which at `:102` prints `git -C $path push origin $branch_name` and at `:94` `pull --rebase … && push …`. `$branch_name` derives from the resolved upstream, so on the detached main tree it advises `push origin master` — compounding #1 exactly as `HANDOFF-2026-07-16.md:194,214` records. **Fix lives outside both repos** — operator action. |
| 8 | **CAPTURE-TIMEOUT-RACE** | CONFIRMED — currently RED | Ran it: `32 passed, 1 failed` — `FAIL: timeout kill (rc=124) -> NO capture row`. `fleet/tests/capture-wiring.test.sh:135` asserts no row; `fleet/charon-run.sh:165` on the too-slow branch does `cap "$M" "FAIL" "BLOCK" …`. The stub emits stderr before exiting so "output observed" is true and the model-attributable branch fires. **Already ticketed** as CAPTURE-WIRING-TIMEOUT-FIX (rig PR #119) — not unticketed. |
| 9 | **VALIDATE-BOARD-WORKTREE-BLIND** | CONFIRMED | `.gitignore:10` `fleet/state/*` (confirmed via `git check-ignore -v`). `validate_board.sh:70-71` builds `done_ids` from `glob.glob(fleet/state/done/*)`; `:201-202` `is_done()` stats `state/done/<t>`; `:272` iterates `("claims","submitted","done")`. In a worktree that dir does not exist → every done ticket reads live → false WCI-redundancy / orphan-marker REDs. |
| 10 | **FT-LIMITS-TSV-GITIGNORED** | CONFIRMED | `git check-ignore -v fleet/state/FREE-TIER-LIMITS.tsv` → `.gitignore:10`. The file has **no** `!` un-ignore line, unlike the 5 exceptions at `.gitignore:12,16,19,22` (`ROADMAP.tsv`, `REDS-CORPUS.md`, `RULE-SYNC-REGISTER.tsv`, `CONFIG-SOURCES.tsv`). A plain `git add` no-ops silently → empty PR. Directly threatens rig PR #116 (FT-LIMITS-GROQ-RECONCILE), whose `owns:` is that exact file. |
| 11 | **UNLANDED-WORK-REQUARANTINE** | CONFIRMED — **mechanism differs from the brief** | Quarantine marker is real: `fleet/state/loop-guard/COVERAGE-META-GATE` = `count=3 threshold=2 quarantined=2026-07-19T01:43:00Z`; `claim.sh:114` `build_set "$LG_SET" "$STATE/loop-guard"` makes claim.sh skip it. But the re-trip path is **worktree-create, not zero-commit no-op**: `leak-guard.sh:45` `branch -D` fails (worktree-held, per #3) → `:46` `git worktree add "$wt" -b "$branch"` fails on an existing branch → `return 1` → `fleet-droid.sh:255-258` releases and calls `loop-guard.sh record`. Two claims → quarantine, forever, no path back except manual `loop-guard.sh clear`. **Nothing anywhere checks whether the branch already carries complete unlanded commits.** |

### 4.2 The quarantine class is larger than one instance

7 tickets are currently loop-guard quarantined, all with reason `repeated zero-commit re-claims`:

```
API-DECOMPOSE-CYCLE-FIX  COVERAGE-META-GATE  DEDUP-GRAPHS-LEDGERS  LAUNCH-PLAN-GATE
PRICING-LIMITS-CHECKER   PROVIDER-CATALOG-REFRESH  SESSION-CTX-PROPAGATE
```

**API-DECOMPOSE-CYCLE-FIX is quarantined while holding an open product PR (#170), and
PRICING-LIMITS-CHECKER while PRICING-LIMITS-CHECK-SH holds rig PR #93.** The guard is punishing
tickets whose work is already authored and in review — confirming this is a class defect, not an
instance. 5 of the 7 have no board file at all (stale quarantine entries that will never clear).

### 4.3 Additional unticketed defects implied by the handoff + evidence

Sourced from `fleet/HANDOFF-2026-07-16.md` and the 6 reports in
`fleet/session-notes/2026-07-16-evidence/` (`audit-harvest.md`, `bench-provisional-deepdive.md`,
`pr-audit.md`, `product-clear.md`, `review-104.md`, `rig-clear.md` — 1473 lines).

| proposed id | finding |
|---|---|
| **LIVE-TREE-BRANCH-GUARD** | `HANDOFF:216-220` — branching inside `/home/stack/charon-private` flipped the board under a running droid mid-session (PRICE-REFRESHER reverted to `parked: true`). The tree is **right now** at detached HEAD `522c147` with 5 droid tabs reading it. No guard exists; it is a documented rule only. |
| **BOARD-FIELD-PARSE-SSOT** | `HANDOFF` §4.1 — board-field predicates re-parsed per consumer and drift. `parked` was 4 copies, wrong in 4; `tier`/`depends_on`/`owns`/`note` carry identical exposure. `_lib.sh`'s own header already promised to prevent this. Check SSOT-DRIFT-GATE (#97) as the home first. |
| **PARK-CONVENTION-UNIFY** | `HANDOFF` §4.2 — two competing park mechanisms: `.md.parked` rename (correct-by-construction, never broke) vs the `parked:` field (needs N implementations, broke 4/4). Converge on the rename; keep the field for the *reason* only. |
| **CLAUDE-RESERVED-ROUTING** | `HANDOFF` §4.3 — nothing expresses "not for SG droids, but DO work it via Claude". `parked` is the only lever and it means *nobody* works it, which a Claude-reserved ticket must never be. This gap is why an SG droid built #107. |
| **VACUOUS-ASSERT-DETECTOR** | `HANDOFF` §4.4 + `review-104.md:96` — #101 (19/19), #103 (40/40), #104's `/dev/null` assert, `test_capture_pipeline.py:122/165` all pass green while the real path is broken. No detector for always-true assertions / fixture-only coverage. |
| **GATEWAY-HOST-SSOT** | `audit-harvest.md:163` — 9 fleet files hardcode `10.0.1.60`, violating [[no-hardcoded-cross-boundary-paths]]. |
| **MARKER-PROOF-BACKFILL** | §2.3 — 36 done-markers are bare timestamps with no board file; several on the money path. Backfill proof or re-open. |
| **AUTO-MERGE-DISABLED** | `HANDOFF:227` — auto-merge is off on SLOP-Platform/charon, so every land needs a manual post-gate merge. This is what makes the #1/#2 silent-success bugs dangerous rather than cosmetic. Operator/repo-settings action. |
| **WORKTREE-SPRAWL-REAP** | 63 worktrees / ~62 unlanded branches. Every one is a live instance of #3 (unlandable via `land.sh`) and #11 (unclaimable via `fleet-droid.sh`). |

### 4.4 `feat/coverage-meta-gate` @ `e7aaeea` — landability

Exactly 1 commit ahead of `origin/master`: *"feat(fleet): coverage meta-gate — every mechanizable
rule must be a gate (§11 teeth)"*. Diff vs master: **394 insertions, 0 deletions, 0 modifications
to existing code** — `.gitignore` (+3), `fleet/checks/rule-coverage.sh` (+173, new),
`fleet/state/RULE-REGISTRY.tsv` (+90, new), `fleet/tests/rule-coverage.test.sh` (+128, new).
Ticket declares `repo: charon-private` and `owns:` exactly those three new files.

**Complete, additive-only, zero conflict surface.** Two caveats: `land.sh` cannot land it (§4.1 #3
— worktree-held branch, and #2 means it would silently push the wrong thing), and
`fleet/state/RULE-REGISTRY.tsv` falls under `.gitignore:10` (§4.1 #10) — it is committed on the
branch so it survives, but any follow-up edit needs `git add -f`.

---

## PART 5 — READY TO LAND

### 5.1 PRODUCT — `SLOP-Platform/charon`

| PR | verdict | detail |
|---|---|---|
| **174** meter docs | ✅ **MERGE-READY** ⚠️adversarial (money path) | Gate+wheel GREEN, CLEAN. Comment/docstring-only in `proxy.py:308-598`; no functional edit. `forwarder.py` does pass `provider=route.label`; readers at `forwarder.py:532`, `gateway.py:477`. Ships a doc-drift guard asserted on reader-count first, so it can't be satisfied by deleting readers. |
| **172** graceful degrade | ⚠️ **NEEDS-ADVERSARIAL-REVIEW** | Gate GREEN/CLEAN, but **203 lines of live money-path code** (`balance.py` +132, `failover.py` +57, `router.py` +14) under a title reading "resolve ruff I001/F401 issues in test file". Title/diff mismatch — not reviewable as labelled. |
| **171** price refresher | 🔴 **DO-NOT-MERGE — silent money-path revert** | `gateway.py:419` **reverts the energy-billed metering fix** landed by `da600d2` (#167): restores `obs.usage is not None and …` gating, recording **$0** for providers with no `usage` object (NeuralWatt shape). Also **deletes** `tests/test_gateway_nontoken.py` (68 lines, on master) — the regression guard for that exact bug. **CI is green only because the guard was removed.** Branch predates #167. Fix: rebase, drop the `gateway.py` hunk and the test deletion, re-run. Also 3579 lines in one new file. |
| **170** arch cycle fix | 🔴 **DO-NOT-MERGE — phantom cycle** | Gate **RED** (`arch: 1 violation`) — the PR's own fix makes the gate fail. |
| **169** flowchart | 🟡 **NEEDS-FIX (1 line)** | Gate RED on `public-clean`. Docs-only, zero product risk. Scrub the offending line in `docs/CHARON-FLOWCHART.md`. |
| **164** inert cleanup | 🟡 **NEEDS-FIX — re-run, but flake is a class** | Failure is `FileNotFoundError: /tmp/pytest-of-stack/pytest-53` at `pytest_asyncio/plugin.py:924` — the self-hosted runner's tmpdir was reaped mid-run. Environmental, not a code defect. But it's runner-hygiene (tmp reaper vs long runs), so a bare re-run may re-flake. |
| **161** roadmap HTML | 🔴 **DO-NOT-MERGE — boundary violation** | Gate RED at `docs/review-log/WEB-ROADMAP-GENERATOR.md:5` (rig name `charon-private` leaked into the public product repo). Deeper: the whole doc describes **fleet-rig** work (`fleet/roadmap-html.sh`, `end-session.sh`, a hardcoded artifact UUID) and does not belong in the product repo at all — [[product-vs-build-rig-boundary]]. Move to the rig; close here. |
| **135** FT catalog seed | 🔴 **DO-NOT-MERGE — prior "3-line fix" verdict WRONG** | `tests/test_provider_response_contract.py` fails for **three** presets (`featherless`, `github_models`, `ollama_cloud`), each needing a declared raw-shape wire fixture, plus `assert len(providers.PRESETS) == len(_KNOWN_KEYS)` → `29 == 26`. That is 3 hand-written wire fixtures + a known-keys update. The contract test is working as designed: it refuses to let presets ship un-exercised. |
| **86** dependabot | 🔴 **DO-NOT-MERGE — prior "rebase fixes it" verdict WRONG** | `public-clean` flags dependabot's **new** 40-char SHA pins as `hex token shape (>=40 chars)` (`ci.yml:29,30,69,70`, `heavy.yml:25,26`). Master is green only because its pins are *older* 40-char SHAs predating the rule — the rule fires on **changed lines only**. Rebasing re-introduces the same shapes. **This is a gate bug and it will block every future dependabot PR until fixed.** Real fix: allowlist `uses: <action>@<sha>` in `tools/check_public_clean.py`. |

#### #170 prior-verdict re-confirmation — 2 of 3 claims TRUE

| claim | verdict | evidence |
|---|---|---|
| `ast.walk` makes the cycle fake | ✅ **TRUE — and it is the merge blocker** | `tools/check_arch.py:277` (master) **and the PR's replacement** both keep `for node in ast.walk(tree):` — the PR does **not** fix it. Proof: `config/__init__.py:32` is module-level, but `keyprobe.py:41 from .. import providers` and `providers.py:297 from . import config` are **both function-scoped** — no runtime cycle. The PR's own doc admits "All three edges are function-scoped (deferred)" while still reporting them. |
| hardcodes `state_dir=".charon"` over `api.DEFAULT_STATE_DIR` | ✅ **TRUE** | `src/charon/decompose.py:308`, duplicating `src/charon/api.py:32`. Selective, too: `parallel.py:197` still uses `api.DEFAULT_STATE_DIR`. |
| deletes 182 lines of product tests | ❌ **FALSE — misattributed** | #170 touches exactly 3 files (`docs/review-log/API-DECOMPOSE-CYCLE-FIX.md`, `decompose.py`, `check_arch.py`). Zero test files. The claim belongs to **#171**, which deletes `tests/test_gateway_nontoken.py`. |

Bonus: the `decompose→api` cycle #170 exists to fix is **also** phantom — `api.py:320` is function-scoped; only the forward edge was module-level. Correct fix: make `_scan_module_level_imports` walk `tree.body` (with `if TYPE_CHECKING` handling) instead of `ast.walk`; the `decompose.py` and graph-builder edits then become unnecessary.

### 5.2 never-Anthropic scope calls left open by #173 — all three still in master

| item | location | verdict |
|---|---|---|
| `WIRE_ANTHROPIC` / `translate.py` / preset | `providers.py:31`, `forwarder.py:22,207`, `proxy_server.py:188`, `translate.py:13,66,82,99` | ✅ **OUT-OF-SCOPE-OK** — explicitly carved out in the rule's own SSOT at `providers.py:44-47`: the ban is on *selecting* an Anthropic route, not on wire-protocol support. These describe **how** to speak a wire and select nothing. SR-6 prompt-cache is built on them. |
| `tier resolve --executor anthropic` | `cli.py:831-848` | ✅ **OUT-OF-SCOPE-OK, hygiene note** — user explicitly names the executor; nothing auto-selects. **But** `_is_anthropic()` at `cli.py:831` returns `True` for **unknown model ids** (fall-through at `:836`), and it is a bespoke vendor-string match that bypasses `providers.is_anthropic_route`. Harmless today; fold into the SSOT predicate. |
| `recommend._heuristic_rank` | `recommend.py:244-273`, esp. `:257` (`"claude-3.5","claude-3-5","claude-4"` → `high`) | ⚠️ **NEEDS-GUARD (defence in depth)** | It is a classifier and invokes nothing, so out-of-scope by the stated rationale — **but** its output is `TierRecommendation("high", [...claude ids...])`, which becomes tier membership, which is a selection input. Reachability is currently blocked at the *selector* (`recommend.py:89` composes `is_anthropic_route`, FAIL-ON-REVERT guarded by `tests/test_recommend.py:328`), not here. Only `recommend.py:89` and `decompose_planner.py:336` call the predicate today. A Claude id sitting in a persisted "high" tier is a config-level landmine if a future selector forgets the predicate. |

### 5.3 Product work-item re-validation (Part 3 detail)

- **METER-DOC-RECONCILE** — **ALREADY-BUILT / IN-FLIGHT** = PR #174, gate-green and CLEAN. Do not re-scope. Side finding: `fleet/board/METER-MODEL-PROVIDER.md.parked` is a Wave-2 ticket whose premise is **dead** (the 8 write sites already shipped) — retire or rescope.
- **INERT-INSTANCE-DETECT** — **STILL NEEDED.** `tools/check_inert_code.py` exits `OK` purely because every finding is dispositioned in `tools/inert-code-disposition.json`, mostly under `keep-detector-false-positive-module-unreachable-cascade`. The modules with **zero src call sites** yet green: `context_shaper` (315 L), `pricing_limits_checker` (528 L), `tool_repair` (420 L), `quota` (638 L), `cache` (70 L), `lifecycle` (649 L), plus `engine/reconcile` (215 L) and `engine/semantic_proof` (471 L). **~2.6k lines of product code with no production caller, blanket-excused at *module* granularity.** Also `charon.capability.actuals` is dispositioned but the file no longer exists — the stale ref #164 cleans up.
- **AVAILABILITY-WRITETHROUGH** — **STILL NEEDED, greenfield.** No availability store, no write-through, no persist/flush path anywhere in `src/charon/`. Only `available*` symbol is `intake.py:281 available_adapters()`, unrelated.

---

### 5.4 RIG — `Nnyan/charon-private`

| PR | files | +/- | verdict | trust path |
|---|---|---|---|---|
| **90** gate-creation-standardize | 5 | +599/-0 | ✅ **MERGE-READY** — best of the batch; every branch red-proofed | no |
| **113** selfcheck-cycle-gate | 3 | +983/-0 | ✅ **MERGE-READY** — real static analysis, load-bearing tests | no |
| **115** stage-demux | 3 | +717/-4 | ✅ **MERGE-READY** — call site genuinely wired, tests fail-on-revert | ⚠️adversarial |
| **119** capture-timeout-fix | 2 | +30/-3 | 🟡 NEEDS-FIX — uncalibrated `>100` char threshold, positive branch untested. Add an rc=124 + >100-char test asserting a capture row **is** enqueued | ⚠️adversarial |
| **118** sync-schedule | 2 | +19/-1 | 🟡 NEEDS-FIX — wires a latent branch-clobber into every scan. `sync-checkouts.sh:27` `checkout master` → `checkout "$cur"` | no |
| **116** ft-limits-groq | 3 | +450/-0 | 🟡 NEEDS-FIX — ships a `deepseek-v4-pro-groq` row for a model Groq does not publish; duplicate llama-3.1-8b rows with conflicting `context_cap` | ⚠️adversarial |
| **114** handoff-root-archive | 3 | +251/-138 | 🟡 NEEDS-FIX — the "staleness checker" lives only inside its own test and never runs against the real HANDOFF.md. Hoist into `fleet/checks/` | no |
| **105** assign-dispatch-pick | 2 | +177/-1 | 🟡 NEEDS-FIX — **confirmed** | ⚠️adversarial |
| **103** droid-lifecycle-reap | 5 | +766/-6 | 🟡 NEEDS-FIX — **confirmed data-loss path, reproduced** | no |
| **101** github-limits-hardening | 5 | +547/-10 | 🟡 NEEDS-FIX — **confirmed invalid flag** | no |
| **97** ssot-drift-gate | 5 | +765/-0 | 🟡 NEEDS-FIX — `--jq '.state'` runs against an **array**, always errors → every board ticket false-flagged. Use `.[0].state` + `--state all` | ⚠️adversarial |
| **62** session-end-push-gate | 4 | +406/-1 | 🟡 NEEDS-FIX — committed `.pyc` build artifact; test A5 missing a `$` → passes unconditionally | no |
| **47** land-sh-postmortem | 3 | +337/-0 | 🟡 NEEDS-FIX — audit contradicts its own headline count (15 vs 24 scripts) | no |
| **107** bench-provisional-scoring | 4 | +585/-0 | 🔴 **DO-NOT-MERGE** — abandoned-droid artifact: 4 files, all docs, **zero implementation**. Merging marks a trust-path ticket landed with no code | ⚠️adversarial |
| **104** memory-index-compaction | 4 | +573/-0 | 🔴 **DO-NOT-MERGE** — destroys the memory index | no |
| **96** reachability-gate | 5 | +531/-0 | 🔴 **DO-NOT-MERGE** — claims tests + registry wiring; diff has neither. `PATTERNS_MED` never looped, allowlist inert | no |
| **95** work-gate-universal | 4 | +622/-0 | 🔴 **DO-NOT-MERGE** — Gate B assert cannot fail (bare `(green\|ok)` matches "tokens"/"look"), test cannot fail, zero wiring | no |
| **93** pricing-limits-check | 4 | +355/-0 | 🔴 **DO-NOT-MERGE** — mixes $/1M-tokens with $/month in one column; gitignored baseline → regenerates itself, exits 0 forever | ⚠️adversarial |

#### Rig prior-verdict re-confirmation — 4 of 5 upheld, 1 partly false

- **#101 UPHELD.** `gh pr list -r` → `unknown shorthand flag: 'r'` (verified live; `-q` is `--jq`, `-R` is `--repo`). In `gh-cache.sh:_gh_merged_files_tsv` the failed call makes the `if` false → `rm -f "$cf.tmp"` → cache never written → `merged_prs_touching_file` always empty → owns-match always negative. Fix `-r`→`-q` is correct. **Two things the prior review missed:** every test sets `GH_MERGED_FILES_FIXTURE`, which short-circuits the function *before* the gh call — the suite is green because the fixture stubs out the exact broken line; and the PR body's "SAME gh call / SINGLE batched call" is contradicted by the diff (two `gh pr list` invocations, two cache files, and `_gh_merged_tsv` fetches `files` only to discard it). Also ships `large-file-guard.sh` **completely unwired**.
- **#103 UPHELD, reproduced.** In a throwaway repo with an unresolvable `origin/master`, `git log --oneline "origin/master..work" 2>/dev/null | wc -l` returns **0** → unique=0 → CLEAN branch → `git branch -D` deleted a branch with real commits; `git branch -d` refused the same delete. Fix: guard `rev-parse --verify "$BASE_REF^{commit}"`, fail **safe** (preserve) on failure, and use `-d` not `-D`. Tests do build a real bare origin, so the happy path is covered — the hazard case simply is not tested.
- **#104 UPHELD on substance, debris claim STALE.** Measured against the real index: 20,100 bytes > the 17,408 threshold (hook fires), **0** entries match the pure-pointer regex, **118** match the "leaked detail" regex → all 118 summaries truncated to bare `- [Title](file.md)`. No backup (`mv -f "$TMP" "$INDEX_PATH"`) so it is irreversible. The `/dev/null/should-not-be-touched` assert is vacuous — `/dev/null` is a char device, ENOTDIR makes creation impossible, so `[ ! -e … ]` is always true. **But the 128-file / 277k-line `graphify-out/` claim is FALSE at current head:** 4 files, +573/-0, zero graphify hits. Mitigating: not auto-wired — though the review log's stated next step is wiring it into SessionStart.
- **#105 UPHELD exactly.** The swap sits in `main()` (`assign.py:528`), the single CLI entry point; `assign.sh` is `exec python3 …/assign.py "$@"`, so the SESSION-MANAGER path is un-gated too — directly contradicting the PR body. Proposed fix is right: `args.candidates` exists (`assign.py:478`) and is the correct discriminator.
- **#107 UPHELD.** Launcher auto-commit after the droid exited without doing the work. All 4 files are docs plus a `.gitignore` un-ignore; zero implementation.

#### Cross-PR conflicts to sequence around

- **#104 and #107 both add `fleet/board/REVIEWER-DOGFOOD-REDS.md` as a new file (41 lines each)** — guaranteed conflict. Both are launcher auto-commit PRs.
- **#97, #96, #93, #47 all edit the same `.gitignore` block** — pairwise conflicts; #47 is cut from older master.
- **#90 vs #96 is a semantic conflict:** #90's meta-gate REDs any `fleet/checks/*.sh` lacking a red-proof test, and #96 ships exactly that. Landing #96 after #90 turns the meta-gate red.
- **Six PRs (95, 96, 97, 62, 104, and #101's suite) share ONE failure mode:** tests that cannot fail, or fixtures stubbing the path under test. That is the [[gates-must-actually-run]] directive failing at scale — one class, not six bugs. Pairs with §4.3 **VACUOUS-ASSERT-DETECTOR**.

---

## PART 6 — OPTIMIZED RE-SEQUENCE

### 6.0 The sequencing constraint that dominates everything

**Nothing should be landed until the land tooling is fixed.** §4.1 items #1/#2/#3 mean `land.sh` and
`land-push.sh` can silently push the wrong ref, report success, and merge a wrong commit — which is
exactly what produced `522c147` today. With 63 worktrees, item #3 makes this the *common* path.
Merging the three MERGE-READY PRs through the current tooling risks repeating the incident.

So Wave 0 is a hard gate, and it is **Claude-reserved** (destructive, ref-mutating, and it is the
instrument every later wave depends on — the same reasoning that made VERIFY-MERGED-REPO-AWARE
manager-built).

### 6.1 Waves

Collision-free by `owns:`; ~5 droid tabs; W-numbers are hard gates, letters run concurrently.

| wave | id | owns (collision key) | who | notes |
|---|---|---|---|---|
| **W0-a** | **LAND-SAFETY-FIX** | `fleet/land.sh`, `fleet/land-push.sh` | 🔵 Claude | Folds §4.1 #1+#2+#3 into ONE ticket — same two files, same root cause. Push HEAD not the refname; honour `branch -f` rc; detect worktree-held branches. Pre-existing reds fold in here. |
| **W0-b** | **RETIRE-DONE-REPO-UNAWARE** | `fleet/retire-done.sh` | 🔵 Claude | §4.1 #6. Destructive (worktree removal). Disjoint file from W0-a → runs concurrently. |
| **W0-c** | **BOARD-STALE-RECONCILE** | `fleet/board/*.md`, `fleet/state/done/` | 🔵 Claude | Retire the 10 landed tickets (§1.1); repoint the 4 false-premise tickets (§1.2); clears the 5 stale quarantine entries (§4.2). Unblocks FT-WIRE-QUOTA + METER-KWH-USD-FIX by killing a dead dep. |
| **W0-d** | **LEAK-GUARD-VACUITY** | `fleet/leak-guard.sh` | 🔵 Claude | §4.1 #4 — `needs-push/` is empty so the guard is vacuous for every branch. Destructive path. |
| **W1-a** | land rig **#90** → **#113** → **#115** | `fleet/checks/*`, `fleet/benchmark/grader-daemon.py` | 🔵 Claude | **Order matters**: #90's meta-gate must precede anything adding `fleet/checks/*.sh`. #115 unblocks BENCH-OOB-GRADING. #115 is trust-path → adversarial sign-off before merge. |
| **W1-b** | land prod **#174** | `src/charon/proxy.py` | 🔵 Claude | Money-path docs truth; gate-green + CLEAN. Adversarial sign-off. |
| **W1-c** | **PUBLIC-CLEAN-SHA-ALLOWLIST** | `tools/check_public_clean.py` | 🟢 SG droid | Gate bug from #86: allowlist `uses: <action>@<sha>`. **Blocks every future dependabot PR** until landed. Then #86 merges. |
| **W1-d** | **MARKER-PROOF-BACKFILL** | `fleet/state/done/` (read), new `fleet/checks/marker-proof.sh` | 🟢 SG droid | §2.3 — 36 bare markers, several money-path. Backfill proof or re-open. Mechanize as a gate so the shape can't recur. |
| **W2-a** | fix+land **#101** | `fleet/gh-cache.sh`, `fleet/done.sh`, `fleet/checks/large-file-guard.sh` | 🟢 SG droid | `-r`→`-q`, **plus a non-fixture cache test** (the suite is green only because fixtures stub the broken line). Wire `large-file-guard.sh` or ticket it explicitly. **Unblocks GH-SEAM-CHOKEPOINT + DONE-SH-INTEGRITY-FIX.** |
| **W2-b** | fix+land **#103** | `fleet/fleet-droid.sh`, `fleet/reap-orphans.sh`, `fleet/foreman.sh` | 🔵 Claude | Data-loss path → manager-built. Fail-safe base check + `-d` not `-D`, at BOTH call sites. |
| **W2-c** | fix+land **#105** | `fleet/capability/assign.py` | 🟢 SG droid + ⚠️adversarial | Gate on `args.candidates`. Ranking path. |
| **W2-d** | fix+land **#118** | `fleet/preflight.sh`, `fleet/hooks/session-start.sh` | 🟢 SG droid | `checkout master`→`checkout "$cur"`. |
| **W2-e** | fix+land **#119** | `fleet/charon-run.sh` | 🟢 SG droid + ⚠️adversarial | Add the positive rc=124 test. Folds the §4.1 #8 red. |
| **W2-f** | fix+land **#169**, re-run **#164** | `docs/`, product tests | 🟢 SG droid | One scrubbed line; one CI re-run. Cheap wins. |
| **W3-a** | **UNLANDED-WORK-REQUARANTINE** | `fleet/leak-guard.sh`, `fleet/fleet-droid.sh`, `fleet/claim.sh`, `fleet/loop-guard.sh` | 🔵 Claude | §4.1 #11 — CLASS fix: check for complete unlanded commits before quarantining. **Depends on W0-a+W0-d** (same files) and on W2-b (`fleet-droid.sh`). Recovers 7 quarantined tickets. |
| **W3-b** | land `feat/coverage-meta-gate` @ `e7aaeea` | 3 new files, zero conflict surface | 🔵 Claude | Additive-only, 394 insertions, 0 deletions. **Blocked only by W0-a** (worktree-held branch). Note `RULE-REGISTRY.tsv` needs `git add -f`. |
| **W3-c** | land `feat/repo-decl-central` | `fleet/handoff.sh`, `retire-done.sh`, `handoff-check.sh`, `land-needs-push.sh` | 🔵 Claude | §2.4 — 532 lines already built, never landed. **Depends on W0-b** (`retire-done.sh` collision). |
| **W3-d** | **FT-LIMITS-TSV-GITIGNORED** | `.gitignore` | 🟢 SG droid | §4.1 #10 — add the `!` un-ignore line. **Must precede #116**, whose `owns:` is that exact file, or #116 lands empty. Serialize all `.gitignore` work here (#97/#96/#93/#47 all touch that block). |
| **W3-e** | fix+land **#116** | `fleet/state/FREE-TIER-LIMITS.tsv` | 🟢 SG droid + ⚠️adversarial | Drop the unpublished `deepseek-v4-pro-groq` row; reconcile duplicate llama-3.1-8b `context_cap`. After W3-d. |
| **W3-f** | fix+land **#114**, **#62**, **#47** | `HANDOFF.md`, `fleet/end-session.sh`, audit doc | 🟢 SG droid | Hoist the staleness checker into `fleet/checks/`; drop the `.pyc`; fix the `$`; reconcile 15-vs-24. #47 needs a rebase (cut from old master). |
| **W3-g** | fix+land **#97** | `fleet/checks/msot-drift.sh` | 🟢 SG droid + ⚠️adversarial | `.[0].state` + `--state all`. After W3-d (`.gitignore`). Candidate home for **BOARD-FIELD-PARSE-SSOT** — fold rather than proliferate. |
| **W4-a** | **VACUOUS-ASSERT-DETECTOR** | new `fleet/checks/vacuous-assert.sh` | 🔵 Claude | §4.3 — the class behind 6 PRs. Depends on W1-a (#90's gate-creation standard is its home). |
| **W4-b** | rebuild **#95**, **#96** | `fleet/checks/work-gate.sh`, `no-unreachable-paths.sh` | 🟢 SG droid | Rebuilds, not patches. **After W4-a**, which is the detector that catches exactly their defect. #96 after #90. |
| **W4-c** | rebuild **#93** | `fleet/pricing-limits-check.sh` | 🟢 SG droid + ⚠️adversarial | Money path. Separate $/1M-token and $/month columns; un-gitignore the baseline. |
| **W4-d** | rebuild **#170** | `tools/check_arch.py` | 🟢 SG droid | Correct fix: walk `tree.body` (+`TYPE_CHECKING`) instead of `ast.walk`; revert `decompose.py` entirely; keep `api.DEFAULT_STATE_DIR`. |
| **W4-e** | rebuild **#171** | `src/charon/gateway.py`, `tests/test_gateway_nontoken.py` | 🔵 Claude + ⚠️adversarial | **Silent money-path revert** — manager-built. Rebase onto master, drop the `gateway.py` hunk and the test deletion. |
| **W4-f** | **#172** full adversarial review | `balance.py`, `failover.py`, `router.py` | 🔵 Claude + ⚠️adversarial | 203 lines of money-path code under a mislabelled title. Re-review against the diff. |
| **W4-g** | rebuild **#135** | product presets + contract tests | 🟢 SG droid | 3 wire fixtures + known-keys update (NOT a 3-line fix). |
| **W4-h** | move **#161** to rig; close on product | rig `fleet/roadmap-html.sh` | 🟢 SG droid | Boundary violation. |
| **W5** | **GH-SEAM-CHOKEPOINT** (rescoped), **INERT-INSTANCE-DETECT**, **AVAILABILITY-WRITETHROUGH**, **PROJECT-MEMBERSHIP-GATE**, **ADR0016-DEPLOY-PRICED-COMPLETENESS** | see §1.3/§3 | mixed | The genuine remaining feature work. GH-SEAM **rescope to 32 sites/13 files first**. INERT-INSTANCE-DETECT after prod #164. |

**Never scheduled to an SG droid, ever:** anything in the 🔵 Claude column. Per [[sg-never-anthropic]],
SG droid work must not route through Claude/Anthropic models — and conversely, destructive
ref-mutating and money-path rebuild work is manager-built ([[claude-reserved-tickets-manager-builds]]).

### 6.2 Concurrency shape (5 tabs)

- **W0** saturates ~4 manager sub-sessions; droid tabs idle or take W1-c/W1-d.
- **W2** is the widest droid wave — 6 disjoint tickets, 5 of them droid-suitable.
- **W3** must serialize on `.gitignore` (W3-d first) and on the W0 file set.
- **W4** is 8 tickets but 3 are Claude-reserved money-path, so ~5 droid slots stay full.

### 6.3 Standing observations

1. **The bottleneck moved.** The handoff's "frontier 0 / economy 0 ready → tabs idle" is stale: 5 of
   the 8 proposed §3 items were built and now sit in open PRs. The constraint is no longer authoring
   work — it is **landing** it, and the land tooling is the thing that is broken.
2. **Green is not proof, at scale.** Six rig PRs and one product PR are green because a fixture stubs
   the path under test, an assert cannot fail, or a guard test was deleted (#171). This is one class.
3. **Repo-unawareness was not fully fixed.** `verify_merged` is genuinely repo-aware now (traced
   end-to-end), but `retire-done.sh:64` still hardcodes the product path. The fix did not reach every
   consumer — which is the same shape as the `parked:` four-copies bug.
