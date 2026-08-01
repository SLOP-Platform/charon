# Charon Fleet — Session Handoff — tenel-ka

## Bootstrap (copy-paste into the next session)

```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-tenel-ka.md then flip to fleet mode.
```

---

# ⛔ READ THIS FIRST — THE ONE THING THAT EXPLAINS EVERYTHING BELOW

**MEASURED 2026-08-01: the work pipeline has a 24% end-to-end success rate.**
Of 25 tickets worked: 6 reached DONE, 3 got a PR, 4 stayed claimed, **12 fell back to READY** —
silently redone by another tab or stranded on disk.

That is not one bug. It is **TEN defects in one chain**, and ANY ONE strands the work. Do not
treat the symptoms as incidents the way the last two sessions did — they are one broken pipeline:

| # | Defect | State |
|---|---|---|
| 1 | Gate runs INSIDE the worktree -> stale board -> false RED -> publish skipped | HALF-FIXED (#338 merged for land-push; `rig-ci-scope.sh` substrate check STILL broken) |
| 2 | Gate RED -> launcher silently skips publish | unticketed |
| 3 | `release.sh` (11 lines) drops the claim over COMMITTED work | RELEASE-PRESERVES-WORK P0 |
| 4 | Ticket -> READY -> another tab redoes it (duplicate work) | same root as 3 |
| 5 | `fleet-droid.sh:1403` writes to `gate-results/` and mkdirs it on :1405 — under `set -e` this kills the WHOLE TAB | dir created as stopgap; ordering bug REMAINS |
| 6 | Claim markers never expire; `heartbeat` == `claimed` on every marker, never refreshed | CLAIM-LIVENESS-BINDING P0 |
| 7 | F2 auto-done-on-merge does not fire -> merged work reads unfinished | AUTO-DONE-ON-MERGE-MISS, PR #339 |
| 8 | `needs-push` has NO reader in `handoff.sh`/`report.sh` -> dies at session end | in RELEASE-PRESERVES-WORK |
| 9 | `--delete-branch` on an UNCONFIRMED merge deletes the remote branch | FORCE-PUSH-SAFETY-GATE P0 |
| 10 | `$FLEET`/`gate-results` path bugs -> silent report loss | BRIEF-ABSOLUTE-PATHS P1 |

**With 10 failure points in series a clean pass is unlikely BY CONSTRUCTION. 24% is what that
looks like.** Fixing these beats starting anything new.

---

# LESSONS THIS SESSION PAID FOR (do not re-learn these)

1. **A mechanism existing is not a mechanism running.** SEVEN things were built, merged, marked
   DONE, and structurally incapable of firing: F2 auto-done, SESSION REPORT v1, Faktory's lease
   chokepoint, REVIEWER-TAB-POOL's `reviewer!=builder` guard, the loop-guard infra exemption,
   CI-SUITES-CANARY's ratchet, and the catalog refresher's write-back. **Always check the FIRING
   LAYER, never the ticket state.**
2. **Reuse-check before minting — I got burned twice.** ASSIGN-DETERMINISTIC-SELECTOR was minted
   P0 to build a selector `claim.sh` ALREADY HAD (full documented ladder at :67-74).
   REVIEWER-TAB-POOL was nearly rebuilt on frontier tier when attempt #2 had already MERGED.
   `FREE-TIER-LIMITS.tsv` already had every limit, researched 10 days earlier.
3. **Verify the metric before escalating on it.** I told the operator money was burning at
   ~$45/hr from `spent_usd`. It is PHANTOM-INFLATED — the gateway's own docstring records it
   inflating to a "fictional ~$223" via a fabricated `est_cost` floor. Real spend was ~$20.
4. **A gate refusing you is usually right.** `land-push` refused a `--force` 20 times in a row
   correctly; on the 20th, local held 24 MASTER commits and the remote held the ONLY copy of a
   905-line fix. Forcing would have destroyed it.
5. **Two-dot diffs lie.** Always `master...branch`.
6. **Fail-closed without a resolution path = permanent limbo.** `reconcile-stale-claims.sh`
   correctly refuses to clear claims over unlanded work; nothing then LANDS that work, so
   SW-IDENTITY-FOLD sat 135h holding 2 commits and blocking a money P0.

---

# PRIORITY ORDER (operator-approved 2026-08-01 — use this, it supersedes older framings)

1. **Operator asks** — they hold context the rig does not.
2. **Unblocking power** — how many things does landing this release. *Evidence:* PR #205 was a
   2-file test fix that unblocked the ENTIRE product repo; the `priority:` backfill was a trivial
   edit that released 30 tickets stuck up to 22 days. Neither ranks high on any other axis.
3. **Criticality and blast radius as ONE axis** — in this codebase they are the same thing.
4. **Cost, as tie-break only.**
**Risk is NOT a rung.** Money-path danger means adversarial review (a GATE), never queue-jumping.
Band criteria are mechanized in `fleet/state/PRIORITY-LADDER.md` (P:0 FLEET-STOPPED and SCARCE,
P:1 UNBLOCKER, P:2 HIGH-CONSEQUENCE, P:3 STANDARD, P:4 QUICK-WIN, P:5 DEFERRED).

---

# THE RUNNING LIST — 13 ITEMS, CARRIED FORWARD (this is the thread; do not drop it)

Ranked by the order above, not by discovery order.

| # | Item | Ticket? |
|---|---|---|
| 1 | **Fix the 10-defect pipeline chain above** — start with RELEASE-PRESERVES-WORK + CLAIM-LIVENESS-BINDING (both P0, READY, unclaimed) | yes |
| 2 | **Session-close gates — START HERE.** `end-session.sh` is thorough but has TWO defects: it SELF-BLOCKS (creates its own target file, then its allocator refuses the name — aborts before the work-loss check EVERY run) and NOTHING INVOKES IT (no SessionEnd hook). Plus a meta-gate so untracked commitments cannot survive a close. | **SESSION-END-GATE-REPAIR (P0) + SESSION-CLOSE-COMPLETENESS-GATE (P0)** |
| 3 | **`mkdir` ordering at `fleet-droid.sh:1403`** — kills whole pool tabs under `set -e`; this is why pools drain below P0 | NO TICKET |
| 4 | **Land the PR backlog** — 20 open (14 rig + 6 product). #116 needs only a rebase (16/16 real fail-on-revert tests). #263 NEEDS-WORK (`ledger_decay` wired NOWHERE, money-path intended). | partial |
| 5 | **PR-AUTOMATION-EVAL verdict** (aider / pr-agent vs our hand-rolled 830-line `review-pool.sh`) — minted, landed, NEVER CLAIMED | yes |
| 6 | **`$FLEET` brief resolution** — BRIEF-ABSOLUTE-PATHS P1 | yes |
| 7 | **Never-dispatched detector** — extend `stranded-work.sh` (it covers finished-but-stranded, NOT never-started) | NO TICKET |
| 8 | **GATE 4 memory verdicts** — LETTA-REVIEW.md + MEMORY-LAYER-REVIEW.md commissioned, completed, **NEVER READ. Survived 3 sessions now.** `grep -c Letta EVAL-REGISTRY` = 0 | NO TICKET |
| 9 | **4 dropped GATE 3 tickets** — SPAWN-VIA-CAPABILITY, ENGINE-CONVERGE, PRICING-FEED, ORCHESTRATION-RE-RUN. Approved 07-31, still unstaged. **PRICING-FEED's operator-only content exists ONLY in the satele-shan handoff** (Price-Per-Token MCP, MCP-first shape, multi-source-over-SSOT). | NO TICKET |
| 10 | **Exactly-once alarm** — OSS Faktory has NO exactly-once execution, yet CLAIM-LEASE-EXACTLY-ONCE was recorded as coding against it. Something may depend on a guarantee that never existed. | NO TICKET |
| 11 | **Code diagram / PR #169** — draft since 2026-07-19, operator-requested. CODE-MAP-MERMAID (P0) is claimed. | yes |
| 12 | **Diff-scope `rig-ci-scope.sh`'s substrate check** — #338 fixed land-push only; this gate has the identical stale-worktree flaw and produced a FALSE "code owned by NO ticket" RED | NO TICKET |
| 13 | **Restart gateway after config changes** — pools/limits load at STARTUP; disk edits are inert until restart, and the running process REWRITES `spend.json` (it clobbered a cap back to 0.0) | yes |

**5 of 13 have NO board ticket — they live only here. TICKET THEM OR THEY DIE.**
(Was 7. Items 2 and 12 were ticketed at session close as SESSION-END-GATE-REPAIR and
SESSION-CLOSE-COMPLETENESS-GATE — both P0, both READY, unclaimed.)

**SESSION-CLOSE-COMPLETENESS-GATE is the one that stops this recurring**: it makes "a session may
not close with untracked commitments" a real exit code instead of a habit. Until it lands, this
list is protected only by whoever remembers to read it.

---

# MONEY PATH — 5 P0s, all READY, all unclaimed

- **FORWARDER-COST-ORDER-FALLBACK** — `forwarder.py:531` orders by METERED SPEND and falls back to
  arbitrary STATIC order when the meter is empty. Per-provider spend is NEVER populated, so the
  reorder NEVER fires. `pools.py:136` sorts correctly but the money path does not call it.
- **PARK-REARM-FUNDED-PROVIDER** — a 402 on ONE leg parked ALL of OpenRouter while it still served
  traffic; no re-arm fired; `/data/balance.json` does not exist.
- **SPEND-METRIC-TRUSTWORTHY** — `spent_usd` is phantom-inflated (fabricated `est_cost` floor on
  `unpriced` completions) AND the cap cannot be set without a restart. **Do NOT set a cap while
  the number is fiction — a $50 cap against a fictional $88 bricks the gateway.**
- **CATALOG-REFRESH-PERSIST** — the refresher polls EVERY provider every 6h and **holds results in
  memory only**; it never writes back to `models.json`. That is why Zen's free list rotated
  unnoticed and 647 of 859 entries have no price.
- **FREE-TIER-QUOTA-ROUTING** — free legs must be chosen by REMAINING QUOTA, not cost. Limits
  already exist in `fleet/state/FREE-TIER-LIMITS.tsv` with **ZERO rig consumers**; the gateway's
  `/data` has no limits file at all.

**Provider state as of session end:** OpenRouter EXHAUSTED (-$0.15). Chains now lead with DIRECT
legs, verified `provider=direct`: `minimax-m2.5-go`, `deepseek-v4-flash-ds`, `deepseek-v4-pro-ds`,
`gpt-oss-120b-groq`, `free-groq`, `free-cerebras`, plus Zen free `laguna-s-2.1-free` /
`ling-3.0-flash-free` / `big-pickle`. opencode-go was wired this session (it had NO base_url and NO
key_env; shares OPENCODE_ZEN_KEY, base `https://opencode.ai/zen/go/v1`).
**`deepseek-v4-flash-go` still fails** — model-version restriction on Zen/Go, not credentials.

---
# Charon Fleet — Session Handoff (2026-08-01T07:20:08Z) — tenel-ka

> **Per-session handoff.** Each session writes: `SESSION-HANDOFF-$SESSION.md`.
> No collisions. Next session reads ALL: `SESSION-HANDOFF-*.md`.

**Date:** 2026-08-01
**Session:** tenel-ka

---

## Bootstrap (copy-paste into next session)

```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-tenel-ka.md — you are the fresh Charon fleet MANAGER, carry it out, then flip to fleet mode.
```

### Context discipline (always on)
See MANAGER-OPERATING-RULES.md §9 (token-economy is DEFAULT) and §13 (startup budget gate). Key: auto-compact ON; sub-sessions write/don't-dump; read big docs in slices once; keep-alive = light heartbeat folded into real work, NOT a 4-min wakeup loop.

---

## Provenance (anti-clobber — verify this matches the session/filename before trusting this handoff)

**Session:** tenel-ka
**Generated:** 2026-08-01T07:20:08Z
**Product HEAD:** e4a70f0 — current with origin/master
**Rig HEAD:** 40cdcbb — current with origin/master

---
<!-- GENERATED-STATE v1 (do not hand-edit) generated=2026-08-01T07:20:11Z -->
### Generated state (truth-of-record — machine-queried, do NOT hand-edit)

> Generated by fleet/handoff.sh from LIVE queries at handoff time. A session physically
> cannot hand-assert facts here — regenerate to refresh. `UNAVAILABLE` lines mean the
> query (gh / git remote) was down at generation, NOT that the thing is absent.

**origin/master SHA (git ls-remote, machine-parseable):**

origin-master product = e4a70f054ac109d1088d50ddd50d0022c4823296  # SLOP-Platform/charon
origin-master rig = 40cdcbb879b42364034699aa0f6c3932b2c3a51a  # Nnyan/charon-private

**Open PRs — product (SLOP-Platform/charon):**
- #206 fix(SW-IDENTITY-FOLD): fold quantization/variant model-id spellings into one pool identity [draft=false] head=fix/sw-identity-fold (CI-unverified until checked)
- #203 fix(discover): match namespaced catalog prices [draft=true] head=feat/catalog-completeness (CI-unverified until checked)
- #193 feat(bench): out-of-band grading — grader-daemon + spool, bench.sh loses grading powers (#26) [draft=true] head=feat/bench-oob-grading (CI-unverified until checked)
- #169 docs(flowchart): add printable Charon end-to-end Mermaid map (operator request) [draft=true] head=docs/charon-flowchart (CI-unverified until checked)
- #135 chore(FT-CATALOG-SEED): launcher auto-commit — droid exited without committing (review for completeness) [draft=false] head=feat/ft-catalog-seed (CI-unverified until checked)
- #86 ci: bump the github-actions group across 1 directory with 6 updates [draft=false] head=dependabot/github_actions/github-actions-911e50acf6 (CI-unverified until checked)

**Open PRs — rig (Nnyan/charon-private):**
- #346 fix(review-pool): B1 fail-closed on UNKNOWN author + adversarial review boundary + real-id test [draft=false] head=feat/reviewer-tab-pool (CI-unverified until checked)
- #345 fix(shared-namespace-contention): split claim check from claim, idempotent same-holder, orphan reap, namespaced scratch [draft=false] head=fix/shared-namespace-contention (CI-unverified until checked)
- #343 BRIDGE-MIGRATE-DROID-CLIENT: migrate droid-bridge.sh off proxy.py onto session-ctl.sh [draft=false] head=feat/bridge-migrate-droid-client (CI-unverified until checked)
- #342 EVAL-REGISTRY: re-derive verdicts for 6 router candidates under B/C lens, 2026-07-31 [draft=false] head=design/router-substrate-reeval (CI-unverified until checked)
- #341 feat(unreviewed-work): add aged-unreviewed-work alarm (UNREVIEWED-WORK-ALARM) [draft=false] head=feat/unreviewed-work-alarm (CI-unverified until checked)
- #340 refactor: gate-registry extraction — collapse 9x duplicated ensure_open/close into sha [draft=false] head=feat/preflight-gate-registry (CI-unverified until checked)
- #339 fleet: wire reconcile-board-pr to auto-close submitted on merge [draft=false] head=fix/auto-done-on-merge-miss (CI-unverified until checked)
- #335 docs(review-log): add RETIRE-FINAL-E2E-REVIEW per-ticket fragment [draft=false] head=chore/retire-final-e2e-review (CI-unverified until checked)
- #334 fix(loop-guard): wire --reason at all record call sites in fleet-droid.sh [draft=false] head=fix/loop-guard-reason-wire (CI-unverified until checked)
- #320 eval(runtime-inert-detection): rank OTel FastAPI #1 for per-route runtime inert detection [draft=false] head=eval/runtime-inert-detection (CI-unverified until checked)
- #317 feat(ci): add CI_SUITES_CANARY with staleness ratchet [draft=false] head=feat/ci-suites-canary (CI-unverified until checked)
- #287 board-hygiene: archive RECONCILE-GATE-WIRED (PR #285 landed by worker) + SHARED-NAMESPACE-CONTENTION ticket [draft=false] head=board/namespace-contention (CI-unverified until checked)
- #263 feat(routing): add exponential half-life decay for model-signal ledger (ROUTER-LEDGER-DECAY) [draft=false] head=feat/router-ledger-decay (CI-unverified until checked)
- #116 test(ft-limits): mechanize marker + malformed + tracking detector [draft=false] head=feat/ft-limits-groq-reconcile (CI-unverified until checked)

**Branches ahead of upstream + uncommitted work (stranded-work signal):**
- product /home/stack/code/charon [master]: 0 commit(s) ahead of origin/master, 5 file(s) uncommitted
- product /home/stack/charon-wt/LITELLM-CAPABILITY-ADOPTION [design/litellm-capability-adoption]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- product /home/stack/charon-wt/LITELLM-COST-FIELD-TEST [fix/litellm-cost-field-test]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/charon-wt/SECRET-HOTROTATE [fix/secret-hot-rotation]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/charon-wt/SW-IDENTITY-FOLD [fix/sw-identity-fold]: 2 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/charon-wt/SW-STATIC-LEGS-RETIRE [feat/sw-static-legs-retire]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/charon-wt/order-a [feat/ordering-cost-primary]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- product /home/stack/code/charon-fleet-DIFF-COVER-FIX [feat/diff-cover-mutmut-adopt]: no-upstream commit(s) ahead of <none>, 1 file(s) uncommitted
- product /home/stack/code/charon-fleet-FORWARDER-COST-ORDER-FALLBACK [fix/forwarder-cost-order-fallback]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon-fleet-GATEWAY-GRADE-ORDER-MVP [feat/gateway-grade-order-mvp]: 2 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon-fleet-INERT-INSTANCE-DETECT [feat/inert-instance-detect]: 4 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon-fleet-PYLINT-UNUSED-ARGS [feat/pylint-unused-args]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon-fleet-router-ledger-decay [feat/router-ledger-decay]: 2 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon-wt-CONTRIB-HOOKS [docs/contributing-hook-install]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon-wt-GW-CUTOVER [feat/gw-cutover-live-wire]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon-wt-LITELLM-WIRE [fix/litellm-order-precall]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon-wt-RUFF-SEC [fix/ruff-security-rules]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon-wt-meter-kwh [fix/meter-kwh-usd]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- product /home/stack/code/charon/.claude/worktrees/agent-a4294af67f9d41d80 [feat/wire-tool-repair]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- product /home/stack/code/charon/.claude/worktrees/agent-a4896ad6d2bfe5d06 [feat/gateway-litellm-live-wire]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private [master]: 0 commit(s) ahead of origin/master, 5 file(s) uncommitted
- rig /home/stack/charon-private-wt-baseline: DETACHED HEAD
- rig /home/stack/charon-private-wt/AUTO-DONE-ON-MERGE-MISS [fix/auto-done-on-merge-miss]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/BANDIT-PREEXISTING-FINDINGS [fix/bandit-preexisting-findings]: 0 commit(s) ahead of origin/fix/bandit-preexisting-findings, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/BOARD-WRITE-LOCK [fix/board-write-lock]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/BRIDGE-MIGRATE-DROID-CLIENT [feat/bridge-migrate-droid-client]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/CLAIM-LADDER-HEALTH [feat/claim-ladder-health]: 0 commit(s) ahead of origin/feat/claim-ladder-health, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/CLAIM-LIVENESS-BINDING [fix/claim-liveness-binding]: 0 commit(s) ahead of origin/master, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/CLAIM-RECONCILE-INERT [fix/claim-reconcile-inert]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/CODE-MAP-MERMAID [feat/code-map-mermaid]: 0 commit(s) ahead of origin/master, 4 file(s) uncommitted
- rig /home/stack/charon-private-wt/DOGFOOD-SCORECARD-TIMESTAMP-FIX [fix/dogfood-scorecard-timestamp-collision]: 0 commit(s) ahead of origin/fix/dogfood-scorecard-timestamp-collision, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/FAKTORY-REINVESTIGATE [eval/faktory-reinvestigate]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/FN-MEMORY-RETIRE-ADOPT [feat/fn-memory-retire-adopt]: 0 commit(s) ahead of origin/feat/fn-memory-retire-adopt, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/INVENTORY-TABLE [feat/inventory-table]: 0 commit(s) ahead of origin/feat/inventory-table, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/KSF-LOAD-BEARING [feat/ksf-load-bearing]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/LOOP-GUARD-INFRA-FAULT-EXEMPT [fix/loop-guard-infra-fault-exempt]: 0 commit(s) ahead of origin/fix/loop-guard-infra-fault-exempt, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/LOOP-GUARD-REASON-WIRE [fix/loop-guard-reason-wire]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/NIM-PROVIDER-CLEANUP [fix/nim-provider-cleanup]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/NS-CONTENTION [board/ns-contention-v2]: 0 commit(s) ahead of origin/master, 2 file(s) uncommitted
- rig /home/stack/charon-private-wt/PREFLIGHT-GATE-REGISTRY [feat/preflight-gate-registry]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/PREFLIGHT-OWNS-ARBITRATE [fix/preflight-owns-arbitrate]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/REAPER-APPLY-WIRING [fix/reaper-apply-wiring]: 0 commit(s) ahead of origin/fix/reaper-apply-wiring, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/RECONCILE-BOARD-PR-DONE [feat/reconcile-board-pr-done]: 0 commit(s) ahead of origin/feat/reconcile-board-pr-done, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/RELEASE-PRESERVES-WORK [fix/release-preserves-work]: 0 commit(s) ahead of origin/master, 2 file(s) uncommitted
- rig /home/stack/charon-private-wt/RETIRE-FINAL-E2E-REVIEW [chore/retire-final-e2e-review]: 2 commit(s) ahead of origin/master, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/REVIEW-DISPENSATION-CANARY [feat/review-dispensation-canary]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/REVIEWER-TAB-POOL [feat/reviewer-tab-pool]: 4 commit(s) ahead of origin/master, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/RIG-BRANCH-16-DEEPDIVE [fix/rig-branch-16-deepdive]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/ROUTER-SUBSTRATE-REEVAL [design/router-substrate-reeval]: no-upstream commit(s) ahead of <none>, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/SHARED-NAMESPACE-CONTENTION [fix/shared-namespace-contention]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/STALE-CLAIM-RECONCILE [feat/stale-claim-reconcile]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/SUBSTRATE-GATE-V2 [feat/substrate-first-gate-v2]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/SW-PHASE0-GRADE-READ [fix/sw-phase0-grade-read]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/TICKET-LIFECYCLE-CANARY [feat/ticket-lifecycle-canary]: no-upstream commit(s) ahead of <none>, 1 file(s) uncommitted
- rig /home/stack/charon-private-wt/UNREVIEWED-WORK-ALARM [feat/unreviewed-work-alarm]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- rig /home/stack/charon-private-wt/VERIFY-MASTER: DETACHED HEAD
- rig /home/stack/charon-wt-AVAIL-EMPTY [fix/availability-empty-snapshot]: 1 commit(s) ahead of origin/master, 0 file(s) uncommitted
- rig /home/stack/wt/coverage-meta-gate [feat/coverage-meta-gate]: no-upstream commit(s) ahead of <none>, 0 file(s) uncommitted
- (clean if no bullets above)
<!-- /GENERATED-STATE -->

---

## Done / committed@SHA

> Latest 5 SHAs on master (rig + product). Edit only to highlight commits the next session must NOT regress.
```
rig master HEAD:    40cdcbb
rig master subject: Merge pull request #349 from Nnyan/board/freetier-discovery
product master HEAD:    e4a70f0
product master subject: merge: bring autoland-default-branch fix onto ambient-coupled-tests (resolves deadlock) (#205)

--- last 5 rig master commits ---
40cdcbb Merge pull request #349 from Nnyan/board/freetier-discovery
acaf5a3 board-hygiene: FREE-TIER-QUOTA-ROUTING consumes the EXISTING limits SSOT + requires API discovery
7dc1946 Merge pull request #348 from Nnyan/board/catalog-freetier-final
e38ab12 board-hygiene: operator-action #18 (opencode-go credential — now RESOLVED, shared Zen key wired)
259788e board-hygiene: add minimax-m2.5-go to strong/frontier chains (opencode-go now wired with shared Zen key, verified provider=direct)

--- last 5 product master commits ---
e4a70f0 merge: bring autoland-default-branch fix onto ambient-coupled-tests (resolves deadlock) (#205)
f87d4ae land: SW-INV-SW2-GATE — INV-SW2 assertions (external red-proof verified)
6ab6035 land: INERT-STARTUP-CHECK — derived inertness, finds unseen dead modules (external red-proof verified)
d6267c3 land: DOGFOOD-GATE — e2e gate that fails on a broken fold (external red-proof verified)
34669e9 DOGFOOD-GATE: assert observable pool effects so the gate fails on a broken fold
```

---

## Next-action / in-flight

> Auto-emitted machine state is under `## Auto-generated state` below. Fill `### Manager's first actions` terse (numbered, one file/script per item).

### Manager's first actions (priority order — fill below)

1. <first action — the smallest thing that lets the next session start safe>
2. <second>
3. <third>

---
---

## Gotchas (avoid re-discovering / DENIED)

> Auto-surfaced from reds.tsv open reds matching gotcha markers. Fill session-specific below.

- `git push` is DENIED to the manager (settings deny-list; verbal authority does NOT override it). The operator pushes.
- <session-specific gotcha 1>
- <session-specific gotcha 2>

---

## session-bridge (auto — live board)

> Live `~/.charon/session-bridge.db` snapshot at handoff time.

```
NAME                           REPO        STATUS      TICKET                       LAST_SEEN
KSF load-bearing refactor — pl charon      in-progress KSF-LOAD-BEARING             2026-08-01T06:27:11
wire vulture+deadcode into CI  charon      in-progress DEADCODE-TOOLS-WIRE          2026-08-01T06:26:36
RELEASE-PRESERVES-WORK: releas charon      in-progress RELEASE-PRESERVES-WORK       2026-08-01T06:12:30
```
> Coordination: review the board above for collisions/blockers before claiming work. If blocked, surface in `blockers=` on `register()`. If inheriting a timed-out session, pick a NEW Jedi name.

---

## Auto-generated state
### Active worktrees (`git worktree list`)
```
/home/stack/code/charon                                            e4a70f0 [master]
/home/stack/charon-wt/DOGFOOD-GATE                                 34669e9 [feat/dogfood-gate]
/home/stack/charon-wt/INERT-STARTUP-CHECK                          37dc42f [feat/inert-startup-check]
/home/stack/charon-wt/LITELLM-CAPABILITY-ADOPTION                  0cd6b6d [design/litellm-capability-adoption]
/home/stack/charon-wt/LITELLM-COST-FIELD-TEST                      d79ac77 [fix/litellm-cost-field-test]
/home/stack/charon-wt/SECRET-HOTROTATE                             b0cd2ae [fix/secret-hot-rotation]
/home/stack/charon-wt/SW-IDENTITY-FOLD                             89d15c5 [fix/sw-identity-fold]
/home/stack/charon-wt/SW-INV-SW2-GATE                              51fd29a [feat/sw-inv-sw2-gate]
/home/stack/charon-wt/SW-STATIC-LEGS-RETIRE                        e72e49b [feat/sw-static-legs-retire]
/home/stack/charon-wt/order-a                                      16dbdc2 [feat/ordering-cost-primary]
/home/stack/code/charon-fleet-AUTOLAND-DEFAULT-BRANCH-FIX          a38ffd9 [fix/autoland-default-branch]
/home/stack/code/charon-fleet-BENCH-OOB-GRADING                    cae48b4 [feat/bench-oob-grading]
/home/stack/code/charon-fleet-CATALOG-COMPLETENESS                 c68c632 [feat/catalog-completeness]
/home/stack/code/charon-fleet-DIFF-COVER-FIX                       404881d [feat/diff-cover-mutmut-adopt]
/home/stack/code/charon-fleet-FORWARDER-COST-ORDER-FALLBACK        be71807 [fix/forwarder-cost-order-fallback]
/home/stack/code/charon-fleet-GATEWAY-GRADE-ORDER-MVP              1de389b [feat/gateway-grade-order-mvp]
/home/stack/code/charon-fleet-INERT-INSTANCE-DETECT                ed62c6f [feat/inert-instance-detect]
/home/stack/code/charon-fleet-PYLINT-UNUSED-ARGS                   4cd13c3 [feat/pylint-unused-args]
/home/stack/code/charon-fleet-UNIFIED-PLANE-CANARY-FRAMEWORK       6782236 [feat/unified-plane-canary-framework]
/home/stack/code/charon-fleet-router-ledger-decay                  82f677a [feat/router-ledger-decay]
/home/stack/code/charon-wt-CONTRIB-HOOKS                           f7c0426 [docs/contributing-hook-install]
/home/stack/code/charon-wt-GW-CUTOVER                              064d197 [feat/gw-cutover-live-wire]
/home/stack/code/charon-wt-LITELLM-WIRE                            4b9d401 [fix/litellm-order-precall]
/home/stack/code/charon-wt-RUFF-SEC                                f4605c3 [fix/ruff-security-rules]
/home/stack/code/charon-wt-meter-kwh                               d6e6973 [fix/meter-kwh-usd]
/home/stack/code/charon/.claude/worktrees/agent-a4294af67f9d41d80  af8d795 [feat/wire-tool-repair]
/home/stack/code/charon/.claude/worktrees/agent-a4896ad6d2bfe5d06  5ebe5c0 [feat/gateway-litellm-live-wire]
/home/stack/code/charon/.claude/worktrees/agent-ab00727b804e8f8db  a18a005 [feat/public-clean-enforce]

/home/stack/charon-private                                      40cdcbb [master]
/home/stack/charon-private-wt-baseline                          649c3a6 (detached HEAD)
/home/stack/charon-private-wt-preflight                         5c8c1de [fix/DROID-CLIENT-PREFLIGHT-PATH]
/home/stack/charon-private-wt/4LOM-CANARY                       0c6b9e6 [feat/4lom-canary-service]
/home/stack/charon-private-wt/ASSIGN-DETERMINISTIC-SELECTOR     b7ed456 [feat/assign-deterministic-selector]
/home/stack/charon-private-wt/AUTO-DONE-ON-MERGE-MISS           ec73a0d [fix/auto-done-on-merge-miss]
/home/stack/charon-private-wt/BANDIT-PREEXISTING-FINDINGS       8320b58 [fix/bandit-preexisting-findings]
/home/stack/charon-private-wt/BASH-INERT-COVERAGE               4c4b710 [feat/bash-inert-coverage]
/home/stack/charon-private-wt/BOARD-WRITE-LOCK                  6ef1fb1 [fix/board-write-lock]
/home/stack/charon-private-wt/BOUNCE-1                          017339d [feat/bounce-1-egress-canary-realsut]
/home/stack/charon-private-wt/BRIDGE-MIGRATE-DROID-CLIENT       1c83142 [feat/bridge-migrate-droid-client]
/home/stack/charon-private-wt/CI-SUITES-CANARY                  1a4ff9f [feat/ci-suites-canary]
/home/stack/charon-private-wt/CLAIM-LADDER-HEALTH               f85a2ac [feat/claim-ladder-health]
/home/stack/charon-private-wt/CLAIM-LIVENESS-BINDING            64443f2 [fix/claim-liveness-binding]
/home/stack/charon-private-wt/CLAIM-RECONCILE-INERT             4921a6e [fix/claim-reconcile-inert]
/home/stack/charon-private-wt/CODE-MAP-MERMAID                  4c4b710 [feat/code-map-mermaid]
/home/stack/charon-private-wt/DIFF-COVER-MUTMUT-ADOPT           87f39ef [feat/diff-cover-mutmut-adopt]
/home/stack/charon-private-wt/DOGFOOD-SCORECARD-TIMESTAMP-FIX   4608592 [fix/dogfood-scorecard-timestamp-collision]
/home/stack/charon-private-wt/FAKTORY-REINVESTIGATE             5590d75 [eval/faktory-reinvestigate]
/home/stack/charon-private-wt/FLEET-DEMAND-BROKER               4f33f87 [feat/FLEET-DEMAND-DRIVEN-ROUTING-avail-cap]
/home/stack/charon-private-wt/FN-MEMORY-RETIRE-ADOPT            338e145 [feat/fn-memory-retire-adopt]
/home/stack/charon-private-wt/FORGE-PRIMARY-GITEA               128605a [feat/forge-primary-gitea]
/home/stack/charon-private-wt/INERT-WIRING-ENFORCEMENT-DURABLE  bbb8421 [fix/inert-wiring-enforcement-durable]
/home/stack/charon-private-wt/INVENTORY-TABLE                   bcc2a15 [feat/inventory-table]
/home/stack/charon-private-wt/ISSUE-BOARD-SURFACE               42b3904 [feat/issue-board-surface]
/home/stack/charon-private-wt/KS29-DISCOVERY-LEG                f69a524 [feat/ks29-discovery-leg]
/home/stack/charon-private-wt/KSF-LOAD-BEARING                  9bd8eb2 [feat/ksf-load-bearing]
/home/stack/charon-private-wt/LAND-GATE-RIG-SUITE               506caa1 [fix/land-gate-rig-suite]
/home/stack/charon-private-wt/LENS-REGISTRY-AND-REPORT          128605a [feat/lens-registry-and-report]
/home/stack/charon-private-wt/LOOP-GUARD-INFRA-FAULT-EXEMPT     a833991 [fix/loop-guard-infra-fault-exempt]
/home/stack/charon-private-wt/LOOP-GUARD-REASON-WIRE            ba73658 [fix/loop-guard-reason-wire]
/home/stack/charon-private-wt/META-GATE-CALLSITE                a92019d [feat/meta-gate-callsite-enum]
/home/stack/charon-private-wt/NIM-PROVIDER-CLEANUP              ad92a5d [fix/nim-provider-cleanup]
/home/stack/charon-private-wt/NS-CONTENTION                     f8266ef [board/ns-contention-v2]
/home/stack/charon-private-wt/PREFLIGHT-GATE-REGISTRY           825ce7f [feat/preflight-gate-registry]
/home/stack/charon-private-wt/PREFLIGHT-OWNS-ARBITRATE          aff4996 [fix/preflight-owns-arbitrate]
/home/stack/charon-private-wt/PRICE-TRACKED-INVENTORY-AUTOSWAP  dc4087a [feat/price-tracked-inventory-autoswap]
/home/stack/charon-private-wt/REAPER-APPLY-WIRING               c32badf [fix/reaper-apply-wiring]
/home/stack/charon-private-wt/RECONCILE-BOARD-PR-DONE           54e0f5d [feat/reconcile-board-pr-done]
/home/stack/charon-private-wt/REGISTRY-META-CATALOG             78dd0c7 [feat/registry-meta-catalog]
/home/stack/charon-private-wt/RELEASE-PRESERVES-WORK            4c4b710 [fix/release-preserves-work]
/home/stack/charon-private-wt/RETIRE-FINAL-E2E-REVIEW           0fe3a98 [chore/retire-final-e2e-review]
/home/stack/charon-private-wt/REVIEW-DISPENSATION-CANARY        ffe9d26 [feat/review-dispensation-canary]
/home/stack/charon-private-wt/REVIEWER-TAB-POOL                 55e9dd1 [feat/reviewer-tab-pool]
/home/stack/charon-private-wt/RIG-BRANCH-16-DEEPDIVE            e75155f [fix/rig-branch-16-deepdive]
/home/stack/charon-private-wt/ROUTER-LEDGER-DECAY               779d918 [feat/router-ledger-decay]
/home/stack/charon-private-wt/ROUTER-SUBSTRATE-REEVAL           19bd5bf [design/router-substrate-reeval]
/home/stack/charon-private-wt/RUNTIME-INERT-DETECTION           de8dbcb [eval/runtime-inert-detection]
/home/stack/charon-private-wt/SG-ISSUE-CONTROL-PLANE            b9d314b [feat/sg-issue-control-plane]
/home/stack/charon-private-wt/SHARED-NAMESPACE-CONTENTION       6e8247b [fix/shared-namespace-contention]
/home/stack/charon-private-wt/STALE-CLAIM-RECONCILE             092a419 [feat/stale-claim-reconcile]
/home/stack/charon-private-wt/STRANDED-WORK-DETECT              b94c26d [feat/stranded-work-detect]
/home/stack/charon-private-wt/SUBSTRATE-GATE-V2                 c182d7e [feat/substrate-first-gate-v2]
/home/stack/charon-private-wt/SW-PHASE0-GRADE-READ              dd28aed [fix/sw-phase0-grade-read]
/home/stack/charon-private-wt/TICKET-LIFECYCLE-CANARY           5c608db [feat/ticket-lifecycle-canary]
/home/stack/charon-private-wt/TIER-BALANCE                      c98c5bc [feat/tier-classifier]
/home/stack/charon-private-wt/UNREVIEWED-WORK-ALARM             104f4ba [feat/unreviewed-work-alarm]
/home/stack/charon-private-wt/VERIFY-MASTER                     ec34714 (detached HEAD)
/home/stack/charon-private-wt/WATCHDOG-RESTART-VERIFY           a23fce3 [feat/watchdog-restart-cmds-verify]
/home/stack/charon-private-wt/WCI-TEETH                         300e9a4 [feat/wci-contention-teeth]
/home/stack/charon-private-wt/WORK-LEASE-RESOLVE                5d951e8 [fix/work-lease-worktree-resolve]
/home/stack/charon-wt-AVAIL-EMPTY                               2a17fc3 [fix/availability-empty-snapshot]
/home/stack/wt/coverage-meta-gate                               e7aaeea [feat/coverage-meta-gate]
```
### In-flight charon-run jobs (CHARON_RUN_RESULT)
```
dogfood-RFL-3-minimax-m2.7-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-free-mistral-code-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-gemma-4-31b-cb-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-deepseek-v4-flash-20260715T001840Z  ->  SUCCESS model=deepseek-v4-flash
dogfood-RFL-3-glm-5.2-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-kimi-k2.6-20260715T001840Z  ->  SUCCESS model=kimi-k2.6
dogfood-RFL-3-minimax-m3-together-20260715T001840Z  ->  EXHAUSTED
dogfood-RFL-3-deepseek-v4-pro-20260715T001840Z  ->  SUCCESS model=deepseek-v4-pro
```
### Provider-exhaustion-ledger tail (`provider-exhaustion-ledger.tsv`)
```
ts	job	model	event	note
2026-08-01T07:15:37Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-08-01T07:15:37Z	out	my-model	leg-fault-failover	rc=124; budget=1800s; no output observed before the timeout -- leg/infra hang, not a model verdict
2026-08-01T07:15:37Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-08-01T07:15:37Z	out	my-model	too-slow-failover	rc=124; budget=1800s; model streamed output but did not finish -- latency-is-a-failure-class, model-attributable
2026-08-01T07:15:37Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-08-01T07:15:37Z	out	my-model	infra-fault-failover	rc=3; provider/local/infra symptom (5xx/reset/refused/deadline/db-lock/timeout/opaque) -- not a model verdict
2026-08-01T07:15:37Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-08-01T07:15:37Z	out	my-model	error-failover	rc=1; non-limit, non-infra failure (genuine model-attributable result)
2026-08-01T07:15:37Z	out	my-model	ALL-EXHAUSTED	every model failed over; POOL TOO THIN -> consider adding providers
2026-08-01T07:15:37Z	fleet-droid	band:strong	cost-cap-config-invalid	work_class=routing: SPILL_UP_COST_CEILING absent/malformed in /home/stack/charon-private/fleet/state/TIER-CANON.md — cost spill-up disabled (fail closed)
```
### Git
```
master

?? .coverage
?? .coverage.Tardis.pid3585032.XZxsxeWx.He0d2GOVTEYh
?? .coverage.gateway-test
?? .coverage.overhead
?? coverage.json

--- last 10 commits ---
e4a70f0 merge: bring autoland-default-branch fix onto ambient-coupled-tests (resolves deadlock) (#205)
f87d4ae land: SW-INV-SW2-GATE — INV-SW2 assertions (external red-proof verified)
6ab6035 land: INERT-STARTUP-CHECK — derived inertness, finds unseen dead modules (external red-proof verified)
d6267c3 land: DOGFOOD-GATE — e2e gate that fails on a broken fold (external red-proof verified)
34669e9 DOGFOOD-GATE: assert observable pool effects so the gate fails on a broken fold
37dc42f INERT-STARTUP-CHECK: derive inertness from the invocation surface, not a hardcoded list
51fd29a SW-INV-SW2-GATE: build the gate + red-proof its assertions
ccb1b79 INERT-STARTUP-CHECK: build the gate + red-proof its assertions
f0f3666 DOGFOOD-GATE: build the gate + red-proof its assertions
9659998 land: release v0.6.1
```
### Open PRs (raw — see GENERATED-STATE block above for the authoritative list)
```
[{"headRefName":"fix/sw-identity-fold","number":206,"state":"OPEN","title":"fix(SW-IDENTITY-FOLD): fold quantization/variant model-id spellings into one pool identity"},{"headRefName":"feat/catalog-completeness","number":203,"state":"OPEN","title":"fix(discover): match namespaced catalog prices"},{"headRefName":"feat/bench-oob-grading","number":193,"state":"OPEN","title":"feat(bench): out-of-band grading — grader-daemon + spool, bench.sh loses grading powers (#26)"},{"headRefName":"docs/charon-flowchart","number":169,"state":"OPEN","title":"docs(flowchart): add printable Charon end-to-end Mermaid map (operator request)"},{"headRefName":"feat/ft-catalog-seed","number":135,"state":"OPEN","title":"chore(FT-CATALOG-SEED): launcher auto-commit — droid exited without committing (review for completeness)"},{"headRefName":"dependabot/github_actions/github-actions-911e50acf6","number":86,"state":"OPEN","title":"ci: bump the github-actions group across 1 directory with 6 updates"}]
```
### Gate
```
test: FAIL worker-lifecycle.test.sh (killed (no exit status recorded — child died before writing .rc))
test: FAIL worktree-leak-guard.test.sh (killed (no exit status recorded — child died before writing .rc))
cat: /tmp/tmp.AYRyWLKSZW/shellcheck.rc: No such file or directory
```
### Roadmap (canonical — fleet/report.sh)
```
CHARON FLEET ROADMAP
====================

PROJECT 1 — ROUTER

  Wave 1 — sense (meter)
    ✅  Done  R1                         meter-model-provider                 real per-call cost sensor
    ✅  Done  R4                         meter-wire                           wire real cost into decisions
    ✅  Done  R5                         cost-rank-auto                       sort pools by metered cost
  Wave 2 — decide (brain)
    ✅  Done  R2                         router-core                          price-sorted order + smart failover
    ✅  Done  R3                         capability-matrix                    which providers serve what + quirks
    ✅  Done  R7                         capability-engine                    one brain for routing
    ✅  Done  R8                         latency-signal                       fail over slow providers
  Wave 3 — class-fix (wiring & test discipline)
    🟠  now   R43                        wiring-audit                         sweep gateway for built-but-inert features → wired/inert matrix — audit delivered (WIRING-AUDIT-MATRIX.md), PR #20 still DRAFT (not merged)
    🟣  next  R44                        dogfood-gate                         e2e merge-gate: real-config request asserts observable effects
    🟣  next  R45                        inert-startup-check                  startup self-check: active vs inert optional components (fail-loud)
  Wave 3a — foundation & balance
    ✅  Done  R46                        balance-wire                         construct BalanceTracker from gateway config (un-deads R4 record_spend) — merged PR #95 (b5d7948), verified live in gateway.load_config/_build_balance_tracker + test_gateway.py FAIL-ON-REVERT
    🟣  next  R47                        live-api-balance                     neuralwatt adapter + TTL poller + wire balance into routing
    ✅  Done  R12                        drain-routing                        route to drain credit first — merged PR #95 (b5d7948), forwarder.py funding-class reorder + balance.py drain accounting
    ✅  Done  R11                        drain-then-park                      spend prepaid credit then pause — merged PR #95 (b5d7948), sole-leg guard (forwarder.py _is_sole_leg) + funding-class re-arm table (balance.py park/unpark) + tests/test_drain_then_park.py
  Wave 3b — quick wins
    🟣  next  R14                        meter-session-tag                    attribute spend to a session
    🟣  next  R16                        graceful-degrade                     throttle+alert+auto-recover on refill
    🟣  next  R26                        catalog-reconcile-gpt5               reconcile catalog with live routing
    🟣  next  R30                        rfl-3                                image-aware provider routing filter
    ✅  Done  R15                        free-tier-order                      adversarial best-order given exact limits
    ✅  Done  R17                        pricing-limits-checker               verify limits+pricing, alert on change
  Wave 3c — bigger
    🟣  next  R10                        free-tier-quota-spill                spill when a tier caps
    🟣  next  R13                        pools-simplification                 cut the pool sprawl
  Wave 3d — deferred (not dropped)
    🟤  next  R9                         work-routing-to-charon               route fleet work through gateway
    🟣  next  R18                        provider-probe-fix                   fix provider key probe validation
  Wave 4 — provider integration
    🟣  next  R19                        provider-url-helper                  unify provider URL construction helper
    🟤  next  R20                        openrouter-flakiness-fix             flatten openrouter wrapped error fields
    🟤  next  R21                        longcat-provider                     add longcat provider integration
    🟤  next  R22                        cooldown-fix3                        audit cooldown retry-after edge cases
    🟤  next  R23                        provider-flatrate                    add flat-rate cheap providers
    🟤  next  R24                        sr-12                                restore opencode-zen provider preset
  Wave 5 — catalog & pricing
    🟤  next  R25                        catalog-sync-drift                   sync catalog and detect drift
    🟤  next  R27                        catalog-search-curate                search and curate model catalog
    🟤  next  R28                        nanogpt-primary-review               review nanogpt primary routing policy
  Wave 6 — RFL console
    🟣  next  R29                        rfl-5                                optional context compaction for long chats
    🟤  next  R31                        rfl-2                                chat playground and served-model view
    🟤  next  R32                        rfl-4                                console limit editor with hot-reload
  Wave 7 — SR routing
    🟣  next  R33                        sr-4                                 fix smart-routing doc inaccuracies
    🟣  next  R34                        sr-3                                 cache correctness and status counters
    🟤  next  R35                        gateway-routing-decompose            tracked gateway routing decompose trigger
    🟤  next  R36                        zen-drift-cleanup                    clean live zen model config drift
    🟤  next  R37                        sr-6-phase2                          bidirectional openai anthropic translation
    🟤  next  R38                        gpt5-pool-reorder                    reorder live gpt-5 pool order
  Wave 8 — capability & quality
    🟣  next  R39                        workclass-taxonomy                   classify tasks into work classes
    🟤  next  R40                        explore-promote                      risk-gated model explore and promote
    🟤  next  R41                        bench-oob-grading                    out-of-band benchmark grading integrity
    🟤  next  R42                        pff-p2                               opt-in cross-model substitution
  Model-Trust
    ✅  Done  DETENTION-REDLINE          detention-redline                    scorecard block-rate excludes a model from a work_class chain
    ✅  Done  WORK-DECOMPOSER            work-decomposer                      strong planner splits a broad change into single-domain sub-tickets
    ✅  Done  MODEL-PREFLIGHT            model-preflight                      OOB-graded battery screens a candidate model on our failure modes
    ✅  Done  PROVIDER-CATALOG-REFRESH   provider-catalog-refresh             auto model<->provider mapping on a schedule (wired)
    ✅  Done  ADD-PROVIDER-MECHANIZE     add-provider-mechanize               one-command gateway provider add
    ✅  Done  DECOMPOSE-EFFORT-AXIS      decompose-effort-axis                effort axis on the decompose gate (EFFORT-WIRE+ESTIMATOR merged)
    ✅  Done  MODEL-LIFECYCLE            model-lifecycle                      fresh-install onboard + scheduled keep-fresh orchestrator — merged PR #117 (69c115d)

PROJECT 2 — BRIDGE

  Wave A — substrate
    ✅  Done  B1                         phase-0-1-substrate                  lay the bridge foundation
  Wave B — active bridge
    🟣  next  B2                         phase-2-active                       push notifications across sessions
    ⚪  next  B3                         roci-coordinator                     run a durable session coordinator
    🟤  next  B8                         durable-bridge-phase-2               bridge daemon watch and renewal
  Wave C — portable engine
    🟣  next  B5                         obol-adr-0008                        one portable orchestration store
    🟣  next  B6                         work-engine-d10                      move the work engine in-tree
    🟣  next  B7                         work-converge-review                 one modular work tool (SLOP+Charon)
  Wave D — ranking
    🟤  next  B4                         benchmark-v2                         rank models by real outcomes
  Wave E — durable bridge & writeback
    🟤  next  B9                         dsgn-writeback                       design ticket write-back sink

PROJECT 3 — FLEET

  Wave A — droid isolation
    ✅  Done  F1                         worktree-leak-guard                  stop droid work leaking into main
    ✅  Done  F2                         auto-done-on-merge                   close tickets when PRs merge
    ✅  Done  F3                         needs-push-gate                      block exit with unpushed work
  Wave B — session gates
    ✅  Done  F4                         end-session-gate                     require clean board before exit
    ✅  Done  F5                         checkin-in-submit                    check in on every submit
    ✅  Done  F6                         deploy-key-derive                    derive deploy keys, never hardcode
    ✅  Done  F7                         board-correctness                    keep the board state valid
  Wave C — done validation
    ✅  Done  F8                         refuse-unverified-done               reject unmerged work as complete
    ✅  Done  F9                         done-unmerged-red                    flag unmerged tickets claiming completion
    ✅  Done  F10                        retire-done-ordering                 retire finished tickets in order
  Wave D — gate & reporting
    ✅  Done  F20                        report-renderer                      one canonical fleet status report
    ✅  Done  F21                        gate-exclude-goldens                 drop benchmark fixtures from the gate
    ✅  Done  F22                        done-close-archived                  record merge-proof on archived tickets
    ✅  Done  F24                        fleet-gate-repoint                   gate runs fleet tests not product ones
    ✅  Done  F27                        access-check                         probe+report host access at boot
    ✅  Done  F44                        web-roadmap-generator                self-refreshing web roadmap from ROADMAP.tsv
  Wave H — board & gate
    🟣  next  F45                        project-audit-gate                   fact-audit + re-sequence at project/wave start
    🟣  next  F30                        difficulty-schema                    enforce difficulty field on tickets
    🟣  next  F31                        wire-mocklint-enforce                enforce fabricated-mock lint in gate
    🟣  next  F43                        project-membership-gate              gate: new tickets fold into a project
    🟤  next  F32                        board-reds-triage                    triage pre-existing board reds
    🟤  next  F33                        workclass-backfill-review            review low-confidence workclass backfills
    🟣  next  F46                        parallelizability-gate               launch-time gate: block launching a splittable effort (size>=M AND >1 independent surface per owns/collision-map) as a single SERIAL job without --serial-justified=<reason>; mechanizes the wall-clock rule NOW in the rig
  Wave E — automation brains
    🟡  next  F11                        work-optimizer                       COMPOSE (not rebuild): wire F46 parallelizability-gate (merged, fleet PR #37) + decompose-sizing's makespan N* (product feat/decompose-sizing) into one launch-time scheduler; absorbs F12's auto-close-on-completion step; see WCI-CONSOLIDATION.md
    🟤  next  F12                        auto-close                           FOLDED into F11 (auto-close-on-completion is F11's final scheduler step, not a separate brain) — most of this is ALSO already covered live by F2 auto-done-on-merge (done); see WCI-CONSOLIDATION.md
    🟤  next  F13                        recurrence-auditor                   FOLDED — the concrete recurring-defect classes are now owned by REACHABILITY-GATE (cross-boundary hardcoded paths) + test_gate_registry_execution.py (orphaned gates, PR #119); generalized brain = Keystone KS21/KS29. No standalone scope remains; see WCI-CONSOLIDATION.md
    🟤  next  F14                        detector-lifecycle                   FOLDED — detector/gate freshness now covered by test_gate_registry_execution.py's fail-loud wiring proof (PR #119) + Keystone KS29 registry-primitive drift-check when built; see WCI-CONSOLIDATION.md
  Wave F — session lifecycle
    🟠  now   F23                        session-end-deploy                   auto-update 4-LOM at session close
    🟡  next  F28                        startup-context-diet                 cut startup context and token cost
    🟣  next  F16                        autonomous-ttl                       time-box unattended runs
    ⚪  next  F19                        bridge-unregister-trap               unregister the bridge on exit
    🟣  next  F47                        no-dark-work                         register every session on the bridge + pickup-gate so no session runs dark and no report strands
  Wave G — quality & hygiene
    🟣  next  F15                        worktree-cleanup                     clean up orphaned worktrees
    ✅  Done  F17                        scorecard-auto-append                record model scores automatically
    ✅  Done  F18                        auto-log-model-lies                  log models that claim false success
    🟣  next  F25                        repo-decl-central                    declare product vs fleet repo once
    🟣  next  F26                        shellcheck-clean                     make fleet scripts shellcheck-clean
    ✅  Done  F29                        post-gateway-wci-decompose           surgical gateway decompose: module-registry (PR #100/085e74f) + config-package (PR #99/6460ace) + providers-data (PR #98/5135e2e) — all 3 slices merged, unblocked Router W4-8
  Wave I — CI & actions
    🟣  next  F34                        docker-smoke-cleanup                 fix docker smoke cleanup trap
    🟣  next  F35                        sr-11                                mechanize actions version bumps
    🟤  next  F36                        sr-10                                enforce single-producer deploy hygiene
    🟤  next  F37                        test-exercises-change-guard          pre-push hook and fail-on-revert guard
  Wave J — handoff & doctrine
    🟣  next  F38                        handoff-mechanize                    mechanize handoff generation and checking
    ✅  Done  F39                        handoff-pipefail                     fix masked gate failure in handoff
    🟤  next  F40                        coordinator-doctrine-rollout         roll out coordinator doctrine v2
  Wave K — review policy
    🟤  next  F41                        atc                                  final adversarial audit of build waves
    🟤  next  F42                        frontier-review-policy               design frontier review policy spec
  Rig fixes
    ✅  Done  LAND-SH-SAFE-SYNC          land-sh-safe-sync                    land.sh sync must never destroy an uncommitted working tree — merged PR #24 (40ffdba)

PROJECT 4 — SECURITY

  Wave A — scrub & enforce
    ✅  Done  S1                         email-scrub                          remove operator email from repo
    ✅  Done  S2                         enforce-public-clean                 keep private info out of repo
    🟠  now   S4                         scrub-name+name-guard                remove leaked name, block its return
  Wave B — preflight & history
    🟣  next  S5                         guard-pre-flight                     catch secret leaks before push
    ⚪  next  S3                         history-purge                        erase secrets from git history
  Wave C — secrets & guardrails
    🟤  next  S6                         secret-hotrotate                     hot-rotate secrets without restart
    🟤  next  S7                         push-guard-gitc-harden               harden destructive git -C bypass
    🟡  next  SEC-SBX                    subagent-worktree-sandbox            P2: confine subagent writes to their own worktree — close the instruction-is-not-a-boundary escape (2026-07-22)
    🟡  next  SEC-BND                    bandit-preexisting-findings          clear 3 pre-existing MEDIUM bandit findings (diff-scoped gate misses them) — fix or justified nosec

PROJECT 5 — BACKLOG

  Wave A — grader & keys
    🟣  next  K3                         grader-secfix                        harden the grader against tampering
    ✅  Done  K3S                        grader-real-shell-fix                kill live shell=True injection at real.py:54 — the site the reconcile does NOT own (RANK-0 / P1)
    🟣  next  K4                         bench-oob-reds-replay                grade models on past failures
    🟤  next  K7                         chutes-commandcode-keys              get missing provider API keys
  Wave B — product UX
    🟣  next  K8                         tool-repair-mutating                 fix mutating tool-repair behavior
    🟤  next  K9                         gui-svelte-build                     rewrite console as svelte spa
    🟤  next  K10                        ux-polish                            batch first-run ux polish nits
    🟤  next  K11                        tier-recs                            setup wizard model recommendations
    🟤  next  K12                        cwd-config-verify                    verify blocked acp config path
  Wave C — connect & dogfood
    🟤  next  K13                        connect-omp-wsl                      fix omp config on wsl connect
    🟤  next  K14                        dogfood                              end-to-end out-of-tree dogfood run
    🟤  next  K15                        ohmypi-assess                        research omp integration feasibility
  Wave D — benchmark remnants
    🟤  next  K16                        bench-reds-replay                    replay real reds as benchmark tasks
    🟤  next  K17                        dtc-6                                parametrize repeating test functions

PROJECT 6 — KEYSTONE

  Wave A — foundation
    ✅  Done  KS1                        mvp-core                             stdlib core + 3 gates + module contract + reuse-check + verify-self (built/reviewed/fixed/verified)
    ✅  Done  KS2                        doctrine-gates                       no_vacuous/no_skip_game/no_pipe_mask/fail_loud/leak_guard (mechanize green-is-not-proof)
    🟣  next  KS8                        coverage-goal                        coverage_ssot tracks % + classifies every rule mechanized/guidance/GAP; FAIL on mechanizable-rule-with-no-gate; goal=100% where logical
  Wave B — capability
    🟣  next  KS3                        graphify-real                        real Graphify integration + `ksf module add graphify` (full pillar B)
    🟡  next  KS3W                       wire-graphify-freshness              wire the orphaned graphify-freshness gate into preflight so the product code map stays fresh automatically
    🟣  next  KS4                        inert-code-gate                      catch UNREGISTERED-inert via AST reachability (the real BalanceTracker case; NO half-measure)
  Wave C — apply & deploy
    🟣  next  KS5                        live-charon-dogfood                  point KSF at LIVE Charon as the final dogfood; surface real inert/dead code
    🟣  next  KS6                        deploy-github                        GitHub-clean (leak_guard) + push; decide repo home
  Wave D — propagate
    🟣  next  KS7                        slop-integration                     analyze+plan KSF adoption into SLOP/mediastack; reconcile with ms-enforce
  Wave E — gate library (pluggable, per-project logical)
    🟣  next  KS9                        lens-test-integrity                  static-only-is-a-gap + dead-code + test-behavior-not-structure + mutation-testing
    🟣  next  KS10                       lens-no-duplicate-impl               one-canonical-path / no duplicate implementations (structural anti-rediscovery)
    🟣  next  KS11                       lens-design-deep-modules             complexity cap + deep-modules / interface-simplicity (APoSD pillar D)
    🟣  next  KS12                       lens-code-quality                    type-discipline + lint/format clean (conditional: typed lang)
    🟣  next  KS13                       lens-security                        secrets-scan (gitleaks) + SAST (bandit/semgrep)
    🟣  next  KS14                       lens-supply-chain                    dependency-pin + CVE scan (trivy/pip-audit); pin CI actions/images
    🟣  next  KS15                       lens-robustness                      fresh-install/zero-data-never-500 + idempotency + test-independence (random order)
    🟣  next  KS16                       lens-artifact-integrity              hermetic standalone build+install+health + deterministic/reproducible build (deploy proof)
    🟣  next  KS17                       lens-change-discipline               ADR/decision-record (-> state-store) + migration-discipline (if DB) + surface-boundary
    🟣  next  KS18                       lens-anti-god-file                   file/module size caps (shrink-only ratchet) + god-file/contention detector (too-many-owners = decompose trigger) + single-responsibility; module-per-capability = feature-level decomposition
    🟣  next  KS19                       lens-fragility                       detect/block fragile code: hardcoded-single-entity, bare-except/error-swallow, brittle-parse-where-structured, known-bad-revert-patterns, over-mocking-internals, flaky sources (time/random/net), generic-500-on-known-condition
    🟣  next  KS20                       lens-anti-accretion                  gates are META-invariants over classes, registry-driven (add data not code); forbid per-instance gate proliferation; scale by registry entries (open-seam/anti-accretion) MUST RUN ON KSF ITSELF (dogfood) alongside size-cap(gate files) + single-entity-hardcode, so KSF cannot mint hardcoded/narrow/monolith/unwired gates without going RED
    🟣  next  KS21                       lens-code-tension                    structural tension proxies (cheap, meta): multiple-source-of-truth / single-canonical-owner; composition-conflict (same data re-ordered by multiple passes = the R8/R2 shape); config-vs-reality drift; incomplete-stub-in-done-surface. Deep semantic contradictions stay with adversarial review, NOT a fuzzy find-all-bugs gate
    🟣  next  KS22                       lens-firing-layer                    every registered/enforced gate/tool MUST be invoked in a real firing layer (CI/Makefile/pre-commit); wired-but-never-run = RED (meta-meta over the gate set). Both audits flagged it
    🟣  next  KS23                       lens-verification-delta              a SUCCESS/done claim requires a NON-EMPTY diff AND a test that fails on revert (revert-hunk-must-go-red); catches trust-the-report / unverified success
    🟣  next  KS24                       lens-drift                           declared != reality drift: config/catalog/pools vs live provider state; deployed artifact vs source checksum; dead/stale entries. Registry-driven (add a drift-check spec) ALGORITHM = desired-vs-observed reconciliation (k8s/Terraform pattern): content-hash/checksum, set-diff/bidirectional, subset/schema-conformance, graph-reachability, staleness-probe(TTL). = the registry primitive's discovery/drift leg (KS29)
    🟣  next  KS25                       lens-ai-judgment                     first-class INDEPENDENT adversarial-review layer for the semantic residue gates can't mechanize (contradictions-in-meaning, design quality, blast-radius). Findings are GATED (must resolve); silence is NEVER a pass (green-is-not-proof). DToC for high-blast. Two-owner firewall: reviewer != builder; dev-time judgment separate from any runtime agent. Generalizes SLOP-AI-Agent aspiration + Charon work-engine quality-brain
    🟣  next  KS28                       consolidate-pattern-guard            collapse the pattern-scanning gates (leak_guard, no_pipe_mask + KS13 security, KS19 fragility, revert-patterns) into ONE registry-driven pattern_guard meta-gate: one enforcer, patterns = data rows (pattern/severity/scope). Retire the hardcoded-pattern scripts. Dogfoods KS20 anti-accretion. Build all future pattern lenses as registry rows, not scripts
    🟣  next  KS31                       component-tool-adapters              KSF gate-plugins are thin ADAPTERS over best-in-class INDUSTRY tools (ruff/mypy/bandit/gitleaks/semgrep/vulture/radon/mutmut/hypothesis/schemathesis/trivy/pip-audit/actionlint/hadolint/shellcheck/sqlfluff) + the meta-layer (registry-wire, red-proof, firing, coverage, fail-loud). NEVER reimplement a tool. Each = a fully-supported plug-in working once enabled. Map KS9/11/12/13/14/15 to specific tools. Custom gates ONLY for novel classes tools don't cover (inert/verification-delta/drift/firing-layer/code-tension/grounding). Charon currently uses only 3 of ~15 (ruff/mypy/pip-audit) -> adoption flows through KS5 apply-to-Charon
    🟣  next  KS32                       build-vs-adopt-gate                  TOOL-FIRST gate: adding CUSTOM implementation for a new class requires a tool-eval record (best-in-class candidate + REAL test vs actual cases + verdict wrap/reject-because-X); missing record OR custom-when-a-tool-fits = RED. The tool-ecosystem analog of reuse-check. Registry-assisted (per-class tool registry).
  Wave F — agent grounding
    🟣  next  KS26                       component-agent-onboarding           mechanically ASSEMBLE a per-app agent GROUNDING bundle from live KSF artifacts: architecture+purpose one-pager, code-graph map (what exists + what it does), built-inventory+decisions (state-store), rules + role/job-description, how-to-learn (reconcile-first + lesson-ledger), how-to-ask-for-help (bridge/escalation). Freshness/drift-gated (map==code or the agent trains on lies). Role-filterable (runtime vs dev). Loaded at reconcile-first. Thin packaging over existing artifacts, NOT model fine-tuning. Portable per app (SLOP/Charon/future). This is what makes a 'dumb' agent competent
    🟣  next  KS27                       component-work-orchestration         DEFAULT-to-fan-out work planner: given an effort, auto-compute collision-free chunks (WCI: dedup->contention-axis->waves) from owns/surface + worktrees, launch one agent per chunk; SERIAL = explicit opt-out. The work-engine layer; mechanizes the wall-clock rule so it can't be forgotten
    🟣  next  KS29                       component-registry-primitive         ONE registry PRIMITIVE: declare a registry (schema+scope) -> auto conformance gate (entries valid) + discovery gate (fail-closed on unknown that should be in it) + drift check, for free. Instances: bad-patterns, config/thresholds, entrypoints(auto-derived), decisions, rules/doctrine, catalog/providers, lessons/reds. The single way to make a single-source-of-truth (mediastack registry+conformance-leg+discovery-leg, generalized)
    🟣  next  KS30                       enforcement-spine                    the 'gate of gates': ONE `ksf enforce` entry composing rule-registry(KS29) + coverage-SSOT(KS8: every rule mechanized-or-explicit-guidance, no silent GAP) + gate-runner + firing-layer(KS22, every mechanized rule actually runs) + fail_loud (any violation/unwired = non-zero, never masked). Knows the rules, verifies none are broken, fails LOUD. Runs on KSF itself (dogfood) + any target project. Guarantees the MECHANIZED set; pure-judgment rules explicitly flagged guidance -> judgment layer(KS25)+human. Must NEVER pretend to enforce a judgment rule (fake-green)

PROJECT 7 — FOUNDATION

  Wave A — memory
    🟣  next  FN1                        memory-store-adopt                   adopt basic-memory MCP store over memory/ + kill whole-dump hook + migrate ~50 notes
    🟣  next  FN2                        bitemporal-decay                     shared valid-from/until+last-referenced decay for memory facts AND model-signal ledgers (fixes routing-brain decay, gap B2)
    🟣  next  FN3                        curation-pass                        scheduled dedup/conflict-flag/decay-to-archive; approval-gated (borrow /sleep + bd compact)
  Wave B — research-gate
    🟣  next  FN4                        research-gate                        mechanized research protocol: reuse-check-first + evidence-over-prose + registry(dedup/staleness->update) + completeness gate
  Wave C — anti-accretion
    🟣  next  FN5                        registry-sweep                       audit product+rig+KSF for smart-registry candidates -> apply KS29 primitive (kills collision/accretion classes); F29 registry = candidate #1

PROJECT 8 — FLEET

  session-reliability
    🔵  next  SESSION-CTX-PROPAGATE      sub-agent context propagation        sub-agents inherit session context via PreToolUse hook (built feat/session-ctx-propagate, needs land)
    🟡  next  WLS-SPIKE                  workloop-stack-spike                 R0 LEAD: adopt-first spike of the work-loop-integrity stack (ao first, then Omnigent/Windmill/Archon) — durable fix for the built-but-not-wired/stale/gate-decay class
    🟡  next  BASE-INTEGRITY-GATE        base-integrity launch gate           refuse building a ticket on a base missing its prereqs (root cause of wrong-base bug)
    🟡  next  COVERAGE-META-GATE         rule-coverage meta-gate (§11)        port mediastack enforcement_coverage; every gate-able rule must be a gate
    🟡  next  WORK-GATE-UNIVERSAL        decompose-sizing + E2E-wired gates   mechanize work-discipline across inline/subsession/detached/tab
    🟡  next  ENV-REGISTRY-WIRE          live env-registry at session start   surface CG-PROVIDERS to sessions/sub-agents; kill env-spelunking
    🟡  next  SSOT-DRIFT-GATE            SSOT drift merge-gate                converge diverged MSOTs incl board-vs-roadmap; msot-drift.sh
    ✅  Done  STRANDED-WORK-AUDIT        stranded near-done work audit        recover 18 built-unmerged items + FN #49-53
    🟡  next  SESSION-END-PUSH-GATE      session-end commit+push gate         refuse session close on uncommitted OR unpushed work (found this session)
  leg-followups
    🟡  next  LEG-F6-REALPATH-TEST       close vacuous F6 fail-on-revert      exercise the real urllib pin path

PROJECT 9 — SECURITY

  leg-followups
    🟡  next  LEG-SANDBOX-HARDEN         leg-preflight sandbox isolation      close cred-exfil vector (ns/seccomp) in canary exec

Totals:  ✅ done=47  🔵 in-review=1  🟠 building=3  🟡 queued=14  🟣 designed=71  🟤 parked=43  ⚪ not-started=3
```
### Board
```

  CHARON-FLEET STATUS @ 2026-08-01T07:21:52Z

  KEY SERVICES (registry-driven; fleet/watchdog/)
  == watchdog: CLEAN ==

  DROIDS (live tabs)        TIER    UPTIME    WORKING-ON
  (no droid tabs running)

  BOARD
  ID     TIER    STATE     BRANCH                 HELD-BY / NOTE
  ADR0016-DEPLOY-PRICED-COMPLETENESS strong  PR-OPEN   feat/adr0016-priced-completeness-guard 388h31m ago
  API-DECOMPOSE-CYCLE-FIX economy PR-OPEN   feat/api-decompose-cycle-fix 383h02m ago
  ASSIGN-DETERMINISTIC-SELECTOR strong  ready     eval/assign-selector-delta -
  ASSIGN-DISPATCH-PICK-FIX strong  PR-OPEN   feat/assign-dispatch-pick-fix 385h13m ago
  AUTO-DONE-ON-MERGE-MISS strong  ready     fix/auto-done-on-merge-miss -
  AUTOLAND-DEFAULT-BRANCH-FIX economy PR-OPEN   fix/autoland-default-branch 7h21m ago
  BALANCE-CANARY strong  DONE      feat/balance-canary    -
  BANDIT-PREEXISTING-FINDINGS strong  DONE      fix/bandit-preexisting-findings -
  BASH-INERT-COVERAGE strong  ready     feat/bash-inert-coverage -
  BENCH-OOB-GRADING frontier PR-OPEN   feat/bench-oob-grading 202h27m ago
  BRIDGE-MIGRATE-DROID-CLIENT strong  NEEDS-PUSH feat/bridge-migrate-droid-client committed, NO PR — land-needs-push.sh BRIDGE-MIGRATE-DROID-CLIENT
  BRIEF-ABSOLUTE-PATHS economy blocked   fix/brief-absolute-paths needs SESSION-REPORT-WIRE, LOOP-GUARD-REASON-WIRE
  CAPABILITY-ACTUALS-DEADREF-CLEANUP economy DONE      feat/capability-actuals-deadref-cleanup -
  CAPTURE-WIRING-TIMEOUT-FIX strong  PR-OPEN   feat/capture-wiring-timeout-fix 315h59m ago
  CATALOG-COMPLETENESS strong  PR-OPEN   feat/catalog-completeness 6h02m ago
  CATALOG-REFRESH-PERSIST strong  blocked   fix/catalog-refresh-persist needs SW-STATIC-LEGS-RETIRE
  CG-LAN-OPEN-UI strong  PARKED    feat/cg-lan-open-ui    unclaimable — see note:
  CHARON-FLOWCHART strong  PR-OPEN   docs/charon-flowchart  383h54m ago
  CI-SUITES-CANARY strong  PR-OPEN   feat/ci-suites-canary  3h05m ago
  CLAIM-LADDER-HEALTH strong  DONE      feat/claim-ladder-health -
  CLAIM-LIVENESS-BINDING strong  ready     fix/claim-liveness-binding -
  CODE-MAP-MERMAID strong  ready     feat/code-map-mermaid  -
  CREATION-GATE-DECOMPOSE-WIRE strong  blocked   feat/creation-gate-decompose-wire needs PROJECT-MEMBERSHIP-GATE, PRIORITY-CONSOLIDATION, CLAIM-LIVENESS-BINDING
  DEADCODE-TOOLS-WIRE strong  ready     feat/deadcode-tools-wire -
  DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD strong  PR-OPEN   feat/decomposer-route-through-switchboard 385h03m ago
  DEGRADE-ALERT strong  DONE      feat/degrade-alert     -
  DIFF-COVER-MUTMUT-ADOPT strong  ready     feat/diff-cover-mutmut-adopt -
  DISCOVERY-APPROVAL-WIRE strong  blocked   feat/discovery-approval-wire needs DISCOVERY-QUEUE, ADD-PROVIDER-MECHANIZE-COMPLETE
  DISCOVERY-CADENCE economy blocked   feat/discovery-cadence needs DISCOVERY-APPROVAL-WIRE
  DISCOVERY-DIFF strong  blocked   feat/discovery-diff    needs DISCOVERY-NORMALIZE
  DISCOVERY-NORMALIZE strong  ready     feat/discovery-normalize -
  DISCOVERY-QUEUE strong  blocked   feat/discovery-queue   needs DISCOVERY-DIFF
  DONE-SH-INTEGRITY-FIX strong  blocked   feat/done-sh-integrity-fix needs GITHUB-LIMITS-HARDENING, VERIFY-MERGED-REPO-AWARE
  EGRESS-KEY-CANARY strong  DONE      feat/egress-key-canary -
  EVAL-CONTROL-GATE-FIX strong  DONE      fix/eval-control-gate-unsatisfiable -
  FAILOVER-CANARY strong  DONE      feat/failover-canary   -
  FAKTORY-TRIAL strong  DONE      eval/faktory-trial     -
  FINAL-E2E-REVIEW frontier blocked   audit/final-e2e-review needs DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT
  FIX-PROVIDER-KEY-EXFIL strong  PARKED    fix/provider-key-exfil unclaimable — see note:
  FN-MEMORY-RETIRE-ADOPT economy DONE      feat/fn-memory-retire-adopt -
  FORCE-PUSH-SAFETY-GATE strong  ready     fix/force-push-safety-gate -
  FORWARDER-COST-ORDER-FALLBACK strong  ready     fix/forwarder-cost-order-fallback -
  FREE-TIER-QUOTA-ROUTING strong  blocked   feat/free-tier-quota-routing needs FT-LIMITS-GROQ-RECONCILE
  FT-CATALOG-SEED economy PR-OPEN   feat/ft-catalog-seed   409h57m ago
  FT-LIMITS-GROQ-RECONCILE economy PR-OPEN   feat/ft-limits-groq-reconcile 317h31m ago
  FT-WIRE-QUOTA strong  PARKED    feat/ft-wire-quota     unclaimable — see note:
  GATEWAY-GRADE-ORDER-MVP strong  ready     feat/gateway-grade-order-mvp -
  GATEWAY-LITELLM-ADOPT strong  PARKED    feat/gateway-litellm-adopt unclaimable — see note:
  GATEWAY-NONTOKEN-METERING strong  PR-OPEN   feat/gateway-nontoken-metering 387h49m ago
  GITEA-ACTIONS-CI-SPIKE strong  PARKED    spike/gitea-actions-ci unclaimable — see note:
  GITHUB-LIMITS-HARDENING strong  PR-OPEN   feat/github-limits-hardening 385h50m ago
  GW-BRIDGE-3-STREAMING-SSE strong  DONE      feat/gw-bridge3-streaming-sse -
  GW-BRIDGE-4-PARK-COOLDOWN strong  DONE      feat/gw-bridge4-park-cooldown -
  HANDOFF-GATE-NONBYPASSABLE strong  blocked   feat/handoff-gate-nonbypassable needs RECONCILE-WIRING, MERGE-DROP-RATCHET, REVIEWER-TAB-POOL
  HANDOFF-NAME-ALLOCATOR strong  DONE      feat/handoff-name-allocator -
  HANDOFF-ROOT-ARCHIVE economy PR-OPEN   feat/handoff-root-archive 371h24m ago
  INERT-INSTANCE-DETECT strong  NEEDS-PUSH feat/inert-instance-detect committed, NO PR — land-needs-push.sh INERT-INSTANCE-DETECT
  INERT-WIRING-ENFORCEMENT-DURABLE strong  PR-OPEN   fix/inert-wiring-enforcement-durable 204h37m ago
  INVENTORY-TABLE-SHARE strong  blocked   feat/inventory-table-share needs INVENTORY-TABLE, DISCOVERY-NORMALIZE
  INVENTORY-TABLE strong  DONE      feat/inventory-table   -
  KSF-LOAD-BEARING frontier ready     feat/ksf-load-bearing  -
  KSF-VENDOR-GATES strong  DONE      feat/ksf-vendor-gates  -
  LAND-SH-POSTMORTEM strong  PR-OPEN   audit/land-sh-postmortem 432h44m ago
  LAUNCHER-CRASH-PARTIAL-DETECT strong  blocked   feat/launcher-crash-partial-detect needs DROID-LIFECYCLE-REAP, SESSION-REPORT-WIRE, LOOP-GUARD-REASON-WIRE, BRIEF-ABSOLUTE-PATHS
  LITELLM-CAPABILITY-ADOPTION frontier NEEDS-PUSH design/litellm-capability-adoption committed, NO PR — land-needs-push.sh LITELLM-CAPABILITY-ADOPTION
  LITELLM-COST-FIELD-FIX economy DONE      fix/litellm-cost-field -
  LOOP-GUARD-INFRA-FAULT-EXEMPT strong  DONE      fix/loop-guard-infra-fault-exempt -
  LOOP-GUARD-REASON-WIRE economy ready     fix/loop-guard-reason-wire -
  MARKER-PROOF-MECHANIZE strong  blocked   feat/marker-proof-mechanize needs DONE-SH-INTEGRITY-FIX, GITHUB-LIMITS-HARDENING, FOREMAN-WIRE, REPO-MAP-CONVERGE, BENCH-OOB-GRADING
  MEMORY-INDEX-COMPACTION strong  PR-OPEN   feat/memory-index-compaction 385h44m ago
  METER-KWH-USD-FIX strong  DONE      feat/meter-kwh-usd-fix -
  MODEL-HARDCODE-PURGE strong  blocked   fix/model-hardcode-purge needs REVIEWER-TAB-POOL, CAPTURE-WIRING-TIMEOUT-FIX
  MODEL-PREFLIGHT frontier blocked   feat/model-preflight   needs BENCH-OOB-GRADING
  NO-LOCAL-MASTER-COMMITS strong  blocked   fix/no-local-master-commits needs SYNC-SCHEDULE
  ORDER-A-COST-PRIMARY-LAND strong  blocked   feat/ordering-cost-primary needs GW-CUTOVER-LIVE-WIRE, FORWARDER-COST-ORDER-FALLBACK
  OWN-TOOLS-CAPABILITY-AUDIT frontier ready     eval/own-tools-capability-audit -
  PARK-REARM-FUNDED-PROVIDER strong  blocked   fix/park-rearm-funded-provider needs SW-IDENTITY-FOLD
  PEAK-PRICING-AWARE strong  blocked   feat/peak-pricing-aware needs PRICING-LIMITS-CHECK-SH
  PLANE-CANARY-REGISTRY strong  DONE      feat/plane-canary-registry -
  PLANE-CANARY-WIRE strong  DONE      feat/plane-canary-wire -
  PR-AUTOMATION-EVAL strong  ready     eval/pr-automation     -
  PREFLIGHT-GATE-REGISTRY frontier NEEDS-PUSH feat/preflight-gate-registry committed, NO PR — land-needs-push.sh PREFLIGHT-GATE-REGISTRY
  PREFLIGHT-GATE-RUN-HELPER strong  blocked   feat/preflight-gate-run-helper needs WCI-CONTENTION-TEETH, SYNC-SCHEDULE, MARKER-PROOF-MECHANIZE, RECONCILE-WIRING, REPO-MAP-CONVERGE
  PREFLIGHT-OWNS-ARBITRATE strong  ready     fix/preflight-owns-arbitrate -
  PRICE-REFRESHER strong  PR-OPEN   feat/price-refresher   377h38m ago
  PRICE-TRACKED-INVENTORY-AUTOSWAP strong  PR-OPEN   feat/price-tracked-inventory-autoswap 204h56m ago
  PRICING-LIMITS-CHECK-SH strong  PR-OPEN   feat/pricing-limits-check-sh 387h29m ago
  PRODUCT-GRADES-STORE strong  PARKED    feat/product-grades-store unclaimable — see note:
  PROJECT-MEMBERSHIP-GATE economy PR-OPEN   feat/project-membership-gate 428h52m ago
  PYLINT-UNUSED-ARGS economy ready     feat/pylint-unused-args -
  REACHABILITY-AUDIT-LAND strong  blocked   feat/reachability-audit-land needs REACHABILITY-GATE
  REACHABILITY-GATE strong  PR-OPEN   feat/reachability-gate 387h17m ago
  REAPER-APPLY-WIRING strong  DONE      fix/reaper-apply-wiring -
  RECONCILE-BOARD-PR-DONE strong  DONE      feat/reconcile-board-pr-done -
  RECONCILE-GATE-WIRED strong  DONE      feat/reconcile-gate-wired -
  RECONCILE-HANDOFF-FRESHNESS strong  ready     feat/reconcile-handoff-freshness -
  RECONCILE-OWNS-TRACKED strong  DONE      feat/reconcile-owns-tracked -
  RECONCILE-WIRING strong  blocked   feat/reconcile-wiring  needs RECONCILE-BOARD-PR-DONE, RECONCILE-OWNS-TRACKED, RECONCILE-GATE-WIRED, RECONCILE-REVIEW-GATE, MARKER-PROOF-MECHANIZE
  RELEASE-PRESERVES-WORK strong  ready     fix/release-preserves-work -
  REPO-DECL-CENTRAL economy DONE      feat/repo-decl-central -
  REPO-MAP-CONVERGE strong  blocked   feat/repo-map-converge needs VERIFY-MERGED-REPO-AWARE, REPO-FIELD-REQUIRED, REPO-DECL-CENTRAL, SYNC-SCHEDULE, GH-SEAM-CHOKEPOINT
  RETIRE-FINAL-E2E-REVIEW strong  ready     chore/retire-final-e2e-review -
  REVIEW-DISPENSATION-CANARY strong  ready     feat/review-dispensation-canary -
  REVIEWER-TAB-POOL frontier ready     feat/reviewer-tab-pool -
  ROUTER-LEDGER-DECAY economy PR-OPEN   feat/router-ledger-decay 178h26m ago
  RUNTIME-INERT-DETECTION strong  PR-OPEN   eval/runtime-inert-detection 2h42m ago
  SECRET-HOTROTATE strong  NEEDS-PUSH fix/secret-hot-rotation committed, NO PR — land-needs-push.sh SECRET-HOTROTATE
  SESSION-END-PUSH-GATE strong  PR-OPEN   feat/session-end-push-gate 401h51m ago
  SHARED-NAMESPACE-CONTENTION strong  ready     fix/shared-namespace-contention -
  SINGLE-LEG-AUTOSWAP strong  ready     feat/single-leg-autoswap -
  SPEND-METRIC-TRUSTWORTHY strong  ready     fix/spend-metric-trustworthy -
  SSOT-DRIFT-GATE strong  PR-OPEN   feat/ssot-drift-gate   387h09m ago
  STOP-WORKER-GRACEFUL-EXIT strong  ready     fix/stop-worker-graceful-exit -
  STRANDED-WORK-AUDIT strong  ready     feat/stranded-work-detect -
  SW-IDENTITY-FOLD strong  NEEDS-PUSH fix/sw-identity-fold   committed, NO PR — land-needs-push.sh SW-IDENTITY-FOLD
  SW-STATIC-LEGS-RETIRE frontier NEEDS-PUSH feat/sw-static-legs-retire committed, NO PR — land-needs-push.sh SW-STATIC-LEGS-RETIRE
  SYNC-SCHEDULE economy PR-OPEN   feat/sync-schedule     317h06m ago
  TOOL-COMPOSITION-LAYER frontier ready     design/tool-composition-layer -
  WEB-ROADMAP-GENERATOR economy PR-OPEN   feat/web-roadmap-generator 385h35m ago
  WIP-CLOSE-GATE strong  blocked   feat/wip-close-gate    needs SESSION-END-PUSH-GATE
  WIRE-BRAIN-INTO-GATEWAY strong  PARKED    feat/wire-brain-into-gateway unclaimable — see note:
  WIRE-GRAPHIFY-FRESHNESS strong  DONE      fix/wire-graphify-freshness-gate -
  WORK-GATE-UNIVERSAL strong  PR-OPEN   feat/work-gate-universal 387h19m ago
  WORK-LEASE-GATE strong  DONE      feat/work-lease-gate   -
  WORKFLOW-E2E-AUDIT frontier ready     eval/workflow-e2e-audit -

  OPEN PRs (draft → operator merges)
  #206  fix/sw-identity-fold  [READY-TO-MERGE]
  #203  feat/catalog-completeness  [draft]
  #193  feat/bench-oob-grading  [draft]
  #169  docs/charon-flowchart  [draft]
  #135  feat/ft-catalog-seed  [READY-TO-MERGE]
  #86  dependabot/github_actions/github-actions-911e50acf6  [READY-TO-MERGE]
  (CI per PR:  gh pr checks <n> --repo SLOP-Platform/charon)

  SUMMARY  droids:0   ready:29  claimed:0  PR-open:30  done:27  blocked:25  parked:7

  (token/usage is NOT faked here — see Claude's own /usage. board.sh = the quick view.)

```
### Board validation
```
== validate_board ==
  INFO owns hand-off (dep-sequenced/historical, ok): /home/stack/charon-private/fleet/validate_board.sh <- CREATION-GATE-DECOMPOSE-WIRE PROJECT-MEMBERSHIP-GATE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/charon-run.sh <- CAPTURE-WIRING-TIMEOUT-FIX MODEL-HARDCODE-PURGE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/checks/rig-ci-scope.sh <- HANDOFF-GATE-NONBYPASSABLE REVIEWER-TAB-POOL
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/claim-jedi-name.sh <- HANDOFF-NAME-ALLOCATOR SHARED-NAMESPACE-CONTENTION
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/claim.sh <- CLAIM-LIVENESS-BINDING CREATION-GATE-DECOMPOSE-WIRE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/done.sh <- DONE-SH-INTEGRITY-FIX GITHUB-LIMITS-HARDENING MARKER-PROOF-MECHANIZE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/end-session.sh <- SESSION-END-PUSH-GATE WIP-CLOSE-GATE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/fleet-droid.sh <- BRIEF-ABSOLUTE-PATHS LAUNCHER-CRASH-PARTIAL-DETECT LOOP-GUARD-REASON-WIRE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/foreman-cadence.sh <- PLANE-CANARY-WIRE RECONCILE-WIRING
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/land.sh <- HANDOFF-GATE-NONBYPASSABLE RECONCILE-WIRING
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/preflight.sh <- MARKER-PROOF-MECHANIZE PLANE-CANARY-WIRE PREFLIGHT-GATE-REGISTRY PREFLIGHT-GATE-RUN-HELPER RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/review-pool.sh <- MODEL-HARDCODE-PURGE REVIEWER-TAB-POOL
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/state/FREE-TIER-LIMITS.tsv <- FREE-TIER-QUOTA-ROUTING FT-LIMITS-GROQ-RECONCILE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/state/REACHABILITY-AUDIT.md <- REACHABILITY-AUDIT-LAND REACHABILITY-GATE
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/tests/claim-jedi-name.test.sh <- HANDOFF-NAME-ALLOCATOR SHARED-NAMESPACE-CONTENTION
  INFO owns hand-off (all-done, ok): src/charon/capability/grades.py <- EVAL-CONTROL-GATE-FIX PRODUCT-GRADES-STORE
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/forwarder.py <- FORWARDER-COST-ORDER-FALLBACK FT-WIRE-QUOTA GATEWAY-LITELLM-ADOPT ORDER-A-COST-PRIMARY-LAND WIRE-BRAIN-INTO-GATEWAY
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/gateway.py <- CG-LAN-OPEN-UI FIX-PROVIDER-KEY-EXFIL FT-WIRE-QUOTA GATEWAY-NONTOKEN-METERING METER-KWH-USD-FIX
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/proxy.py <- PARK-REARM-FUNDED-PROVIDER SW-IDENTITY-FOLD
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/proxy_server.py <- CG-LAN-OPEN-UI GATEWAY-LITELLM-ADOPT ORDER-A-COST-PRIMARY-LAND
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/routing_policy/catalog_refresh.py <- CATALOG-REFRESH-PERSIST SW-STATIC-LEGS-RETIRE
  INFO owns hand-off (dep-sequenced/historical, ok): src/charon/secrets.py <- FIX-PROVIDER-KEY-EXFIL SECRET-HOTROTATE
  INFO owns hand-off (dep-sequenced/historical, ok): tools/check_inert_code.py <- CAPABILITY-ACTUALS-DEADREF-CLEANUP INERT-INSTANCE-DETECT
  INFO owns hand-off (dep-sequenced/historical, ok): tools/inert-code-disposition.json <- CAPABILITY-ACTUALS-DEADREF-CLEANUP INERT-INSTANCE-DETECT
  WARN tier-drift: API-DECOMPOSE-CYCLE-FIX declared=economy derived=strong :: middle band d2 refactor
  WARN tier-drift: ASSIGN-DISPATCH-PICK-FIX declared=strong derived=economy :: trivial single-surface rig-meta d2
  WARN tier-drift: BASH-INERT-COVERAGE declared=strong derived=economy :: trivial single-surface ci-infra d2
  WARN tier-drift: CAPABILITY-ACTUALS-DEADREF-CLEANUP declared=economy derived=strong :: middle band d1 refactor
  WARN tier-drift: CAPTURE-WIRING-TIMEOUT-FIX declared=strong derived=economy :: trivial single-surface rig-meta d2
  WARN tier-drift: CHARON-FLOWCHART declared=strong derived=economy :: docs d3
  WARN tier-drift: CI-SUITES-CANARY declared=strong derived=economy :: trivial single-surface ci-infra d2
  WARN tier-drift: DEADCODE-TOOLS-WIRE declared=strong derived=economy :: trivial single-surface ci-infra d2
  WARN tier-drift: DONE-SH-INTEGRITY-FIX declared=strong derived=economy :: trivial single-surface rig-meta d2
  WARN tier-drift: EGRESS-KEY-CANARY declared=strong derived=frontier :: security-critical path (ratchet: never trade capability)
  WARN tier-drift: FAILOVER-CANARY declared=strong derived=frontier :: money+ (livefwd=0 d4 effort13.3)
  WARN tier-drift: FINAL-E2E-REVIEW declared=frontier derived=strong :: middle band d3 ci-infra
  WARN tier-drift: FIX-PROVIDER-KEY-EXFIL declared=strong derived=frontier :: security-critical path (ratchet: never trade capability)
  WARN tier-drift: FN-MEMORY-RETIRE-ADOPT declared=economy derived=strong :: middle band d3 rig-meta
  WARN tier-drift: FORCE-PUSH-SAFETY-GATE declared=strong derived=economy :: trivial single-surface ci-infra d2
  WARN tier-drift: FREE-TIER-QUOTA-ROUTING declared=strong derived=frontier :: money+ (livefwd=0 d4 effort8.45)
  WARN tier-drift: FT-CATALOG-SEED declared=economy derived=strong :: money floor (d2 effort7.45)
  WARN tier-drift: FT-LIMITS-GROQ-RECONCILE declared=economy derived=strong :: money floor (d2 effort7.3)
  WARN tier-drift: FT-WIRE-QUOTA declared=strong derived=frontier :: money+ (livefwd=1 d4 effort12.6)
  WARN tier-drift: GATEWAY-GRADE-ORDER-MVP declared=strong derived=frontier :: money+ (livefwd=0 d5 effort13.6)
  WARN tier-drift: GATEWAY-LITELLM-ADOPT declared=strong derived=frontier :: money+ (livefwd=1 d5 effort16.6)
  WARN tier-drift: GW-BRIDGE-3-STREAMING-SSE declared=strong derived=frontier :: money+ (livefwd=1 d4 effort11.3)
  WARN tier-drift: GW-BRIDGE-4-PARK-COOLDOWN declared=strong derived=frontier :: money+ (livefwd=1 d4 effort11.3)
  WARN tier-drift: INERT-WIRING-ENFORCEMENT-DURABLE declared=strong derived=frontier :: review-class ratchet d3 (F11: capability never traded down)
  WARN tier-drift: KSF-LOAD-BEARING declared=frontier derived=strong :: middle band d4 refactor
  WARN tier-drift: LITELLM-COST-FIELD-FIX declared=economy derived=strong :: money floor (d1 effort6.3)
  WARN tier-drift: MEMORY-INDEX-COMPACTION declared=strong derived=economy :: trivial single-surface rig-meta d2
  WARN tier-drift: MODEL-PREFLIGHT declared=frontier derived=strong :: middle band d4 ci-infra
  WARN tier-drift: ORDER-A-COST-PRIMARY-LAND declared=strong derived=frontier :: money+ (livefwd=1 d3 effort10.75)
  WARN tier-drift: PR-AUTOMATION-EVAL declared=strong derived=frontier :: review-class ratchet d3 (F11: capability never traded down)
  WARN tier-drift: PREFLIGHT-GATE-REGISTRY declared=frontier derived=strong :: middle band d4 refactor
  WARN tier-drift: PRICE-REFRESHER declared=strong derived=frontier :: money+ (livefwd=0 d3 effort40.3)
  WARN tier-drift: PRICE-TRACKED-INVENTORY-AUTOSWAP declared=strong derived=frontier :: review-class ratchet d4 (F11: capability never traded down)
  WARN tier-drift: PRODUCT-GRADES-STORE declared=strong derived=frontier :: money+ (livefwd=0 d5 effort14.2)
  WARN tier-drift: PROJECT-MEMBERSHIP-GATE declared=economy derived=strong :: middle band d2 rig-meta
  WARN tier-drift: REACHABILITY-AUDIT-LAND declared=strong derived=economy :: trivial single-surface ci-infra d2
  WARN tier-drift: REPO-DECL-CENTRAL declared=economy derived=strong :: middle band d2 ci-infra
  WARN tier-drift: RETIRE-FINAL-E2E-REVIEW declared=strong derived=economy :: trivial single-surface rig-meta d1
  WARN tier-drift: REVIEW-DISPENSATION-CANARY declared=strong derived=economy :: trivial single-surface rig-meta d2
  WARN tier-drift: REVIEWER-TAB-POOL declared=frontier derived=strong :: middle band d4 rig-meta
  WARN tier-drift: ROUTER-LEDGER-DECAY declared=economy derived=strong :: money floor (d3 effort10.3)
  WARN tier-drift: RUNTIME-INERT-DETECTION declared=strong derived=frontier :: review-class ratchet d3 (F11: capability never traded down)
  WARN tier-drift: SECRET-HOTROTATE declared=strong derived=frontier :: security-critical path (ratchet: never trade capability)
  WARN tier-drift: WEB-ROADMAP-GENERATOR declared=economy derived=strong :: middle band d3 rig-meta
  WARN tier-drift: WIRE-BRAIN-INTO-GATEWAY declared=strong derived=frontier :: money+ (livefwd=1 d4 effort11.6)
  WARN tier-drift: WORKFLOW-E2E-AUDIT declared=frontier derived=strong :: middle band d4 rig-meta
  WARN owns-path-missing: ADR0016-DEPLOY-PRICED-COMPLETENESS owns 'tests/test_priced_completeness.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: ASSIGN-DETERMINISTIC-SELECTOR owns 'fleet/state/ASSIGN-SELECTOR-DELTA.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: AUTO-DONE-ON-MERGE-MISS owns 'fleet/checks/reconcile-board-pr.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: AUTO-DONE-ON-MERGE-MISS owns 'fleet/tests/auto-done-on-merge.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BASH-INERT-COVERAGE owns 'fleet/tests/bash-inert-coverage.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BENCH-OOB-GRADING owns 'benchmark/bench.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BENCH-OOB-GRADING owns 'benchmark/lib/grade_state.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BENCH-OOB-GRADING owns 'model-scorecard.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BENCH-OOB-GRADING owns 'benchmark/grader-daemon.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BENCH-OOB-GRADING owns 'benchmark/graders' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BENCH-OOB-GRADING owns 'benchmark/RUN-BENCHMARK.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BENCH-OOB-GRADING owns 'START-SESSION.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BENCH-OOB-GRADING owns 'preflight.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: BRIEF-ABSOLUTE-PATHS owns 'fleet/tests/brief-absolute-paths.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CATALOG-COMPLETENESS owns 'src/charon/providers/discover.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CATALOG-COMPLETENESS owns 'tests/test_catalog_completeness.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CATALOG-REFRESH-PERSIST owns 'tests/test_catalog_refresh_persist.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CHARON-FLOWCHART owns 'docs/CHARON-FLOWCHART.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CI-SUITES-CANARY owns 'fleet/tests/ci-suites-canary.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CLAIM-LIVENESS-BINDING owns 'fleet/tests/claim-liveness.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CODE-MAP-MERMAID owns 'fleet/code-map.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CODE-MAP-MERMAID owns 'fleet/tests/code-map.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: CREATION-GATE-DECOMPOSE-WIRE owns 'fleet/tests/test_creation_gate_decompose.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DEADCODE-TOOLS-WIRE owns 'tests/test_deadcode_tools.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DISCOVERY-APPROVAL-WIRE owns 'fleet/discovery/approval_wire.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DISCOVERY-CADENCE owns 'fleet/discovery/schedule.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DISCOVERY-DIFF owns 'fleet/discovery/offer_diff.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DISCOVERY-NORMALIZE owns 'fleet/discovery/normalize.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DISCOVERY-NORMALIZE owns 'fleet/state/discovery-inventory.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DISCOVERY-QUEUE owns 'fleet/discovery/queue.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: DISCOVERY-QUEUE owns 'fleet/state/discovery-review.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FINAL-E2E-REVIEW owns 'fleet/state/FINAL-E2E-REVIEW.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FORCE-PUSH-SAFETY-GATE owns 'fleet/tests/force-push-safety.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FORWARDER-COST-ORDER-FALLBACK owns 'tests/test_forwarder_cost_order.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FREE-TIER-QUOTA-ROUTING owns 'src/charon/routing_policy/free_tier.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FREE-TIER-QUOTA-ROUTING owns 'tests/test_free_tier_quota.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FREE-TIER-QUOTA-ROUTING owns 'fleet/state/FREE-TIER-LIMITS.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FT-CATALOG-SEED owns 'src/charon/routing_policy/free_tier_catalog.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FT-CATALOG-SEED owns 'tests/test_free_tier_catalog.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: FT-LIMITS-GROQ-RECONCILE owns 'fleet/tests/ft-limits-reconcile.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GATEWAY-GRADE-ORDER-MVP owns 'src/charon/capability/product_grades.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GATEWAY-GRADE-ORDER-MVP owns 'src/charon/routing_policy/grade_order.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GATEWAY-GRADE-ORDER-MVP owns 'tests/test_product_grades.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: GATEWAY-GRADE-ORDER-MVP owns 'tests/test_grade_order.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: HANDOFF-ROOT-ARCHIVE owns 'fleet/tests/handoff-root-staleness.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: INERT-INSTANCE-DETECT owns 'tests/test_inert_instance_detect.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: INERT-WIRING-ENFORCEMENT-DURABLE owns 'fleet/state/INERT-WIRING-ENFORCEMENT-DESIGN.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: INVENTORY-TABLE-SHARE owns 'fleet/discovery/inventory_writer.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: KSF-LOAD-BEARING owns 'fleet/state/KSF-CLASS-REGISTER.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: KSF-LOAD-BEARING owns 'fleet/state/KSF-LOAD-BEARING-PLAN.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: LAND-SH-POSTMORTEM owns 'fleet/state/LAND-SH-POSTMORTEM.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: LAUNCHER-CRASH-PARTIAL-DETECT owns 'fleet/tests/test_launcher_crash_partial.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: LITELLM-CAPABILITY-ADOPTION owns 'docs/adr/0021-litellm-capability-adoption.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: LITELLM-CAPABILITY-ADOPTION owns 'tests/test_litellm_capability_map.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: LOOP-GUARD-REASON-WIRE owns 'fleet/tests/loop-guard-reason-wire.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: MARKER-PROOF-MECHANIZE owns 'fleet/checks/marker-proof.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: MARKER-PROOF-MECHANIZE owns 'fleet/tests/marker-proof.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: MEMORY-INDEX-COMPACTION owns 'fleet/hooks/memory-compact.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: MODEL-HARDCODE-PURGE owns 'fleet/checks/no-hardcoded-model.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: MODEL-HARDCODE-PURGE owns 'fleet/tests/no-hardcoded-model.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: MODEL-PREFLIGHT owns 'fleet/state/PREFLIGHT-CANDIDATES.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: OWN-TOOLS-CAPABILITY-AUDIT owns 'fleet/state/OWN-TOOLS-CAPABILITY-AUDIT.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PARK-REARM-FUNDED-PROVIDER owns 'tests/test_park_rearm.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PEAK-PRICING-AWARE owns 'src/charon/routing_policy/pricing.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PEAK-PRICING-AWARE owns 'tests/test_peak_pricing.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PR-AUTOMATION-EVAL owns 'fleet/state/PR-AUTOMATION-EVAL.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PREFLIGHT-GATE-REGISTRY owns 'fleet/state/GATE-REGISTRY.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PREFLIGHT-GATE-REGISTRY owns 'fleet/tests/preflight-gate-registry.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PREFLIGHT-GATE-RUN-HELPER owns 'fleet/tests/preflight-gate-run.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PREFLIGHT-OWNS-ARBITRATE owns 'fleet/state/PREFLIGHT-OWNERSHIP-RULING.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PRICE-REFRESHER owns 'src/charon/routing_policy/price_refresher.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PRICE-REFRESHER owns 'tests/test_price_refresher.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PRICE-TRACKED-INVENTORY-AUTOSWAP owns 'fleet/state/PRICE-TRACKED-INVENTORY-AUTOSWAP-DESIGN.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PRICING-LIMITS-CHECK-SH owns 'fleet/pricing-limits-check.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PRICING-LIMITS-CHECK-SH owns 'fleet/state/provider-pricing-limits.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: PYLINT-UNUSED-ARGS owns 'tests/test_pylint_unused_args.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: REACHABILITY-GATE owns 'fleet/checks/no-unreachable-paths.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: RECONCILE-HANDOFF-FRESHNESS owns 'fleet/checks/reconcile-handoff-freshness.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: RECONCILE-HANDOFF-FRESHNESS owns 'fleet/tests/reconcile-handoff-freshness.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: RECONCILE-WIRING owns 'fleet/checks/reconcile-timer.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: RECONCILE-WIRING owns 'fleet/tests/reconcile-wiring.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: RELEASE-PRESERVES-WORK owns 'fleet/tests/release-preserves-work.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: REPO-MAP-CONVERGE owns 'fleet/checks/repo-map-single-home.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: REPO-MAP-CONVERGE owns 'fleet/tests/repo-map-converge.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: ROUTER-LEDGER-DECAY owns 'src/charon/routing_policy/ledger_decay.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: ROUTER-LEDGER-DECAY owns 'tests/test_ledger_decay.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: RUNTIME-INERT-DETECTION owns 'fleet/state/RUNTIME-INERT-DETECTION.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SHARED-NAMESPACE-CONTENTION owns 'fleet/tests/scratch-namespace.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SINGLE-LEG-AUTOSWAP owns 'fleet/single-leg-guard.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SPEND-METRIC-TRUSTWORTHY owns 'tests/test_spend_metric.py' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SSOT-DRIFT-GATE owns 'fleet/checks/msot-drift.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SSOT-DRIFT-GATE owns 'fleet/tests/msot-drift.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: SSOT-DRIFT-GATE owns 'fleet/state/SSOT-REGISTRY.tsv' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: TOOL-COMPOSITION-LAYER owns 'fleet/handoff-notes/TOOL-COMPOSITION-RESEARCH.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: WORK-GATE-UNIVERSAL owns 'fleet/checks/work-gate.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: WORK-GATE-UNIVERSAL owns 'fleet/hooks/pretooluse-work-gate.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: WORK-GATE-UNIVERSAL owns 'fleet/tests/work-gate.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: WORKFLOW-E2E-AUDIT owns 'fleet/state/WORKFLOW-E2E-AUDIT.md' does not exist (yet) — verify it is a to-be-created file or a typo
  WARN owns-path-missing: WORKFLOW-E2E-AUDIT owns 'fleet/tests/workflow-e2e.test.sh' does not exist (yet) — verify it is a to-be-created file or a typo
  WCI-ADVISORY justified-disjoint-dep (ok): DIFF-COVER-MUTMUT-ADOPT -> KSF-VENDOR-GATES (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): DISCOVERY-APPROVAL-WIRE -> DISCOVERY-QUEUE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): DISCOVERY-CADENCE -> DISCOVERY-APPROVAL-WIRE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): DISCOVERY-DIFF -> DISCOVERY-NORMALIZE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): DISCOVERY-QUEUE -> DISCOVERY-DIFF (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): FINAL-E2E-REVIEW -> MODEL-PREFLIGHT (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): INVENTORY-TABLE-SHARE -> INVENTORY-TABLE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): INVENTORY-TABLE-SHARE -> DISCOVERY-NORMALIZE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): MARKER-PROOF-MECHANIZE -> BENCH-OOB-GRADING (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): MODEL-PREFLIGHT -> BENCH-OOB-GRADING (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): NO-LOCAL-MASTER-COMMITS -> SYNC-SCHEDULE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): PEAK-PRICING-AWARE -> PRICING-LIMITS-CHECK-SH (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): RECONCILE-HANDOFF-FRESHNESS -> RECONCILE-GATE-WIRED (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): RECONCILE-WIRING -> RECONCILE-BOARD-PR-DONE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): RECONCILE-WIRING -> RECONCILE-OWNS-TRACKED (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): RECONCILE-WIRING -> RECONCILE-GATE-WIRED (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): REPO-MAP-CONVERGE -> REPO-DECL-CENTRAL (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): RETIRE-FINAL-E2E-REVIEW -> PLANE-CANARY-WIRE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): REVIEW-DISPENSATION-CANARY -> PLANE-CANARY-REGISTRY (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): SINGLE-LEG-AUTOSWAP -> INVENTORY-TABLE (marked real build/correctness prereq)
  WCI-ADVISORY justified-disjoint-dep (ok): SW-STATIC-LEGS-RETIRE -> SW-IDENTITY-FOLD (marked real build/correctness prereq)
  WCI-ADVISORY semantic: prompt-intent contradiction / hidden coupling is NOT machine-checked — eyeball overlapping or dep-linked tickets by hand.
  GREEN board structurally valid
```
### Foreman tier-health (auto)
```
--- foreman handoff ---

### Foreman tier-health (auto)

```
== FOREMAN: tier claimable depth ==
  [ok]     frontier: 5 claimable -> REVIEWER-TAB-POOL LITELLM-CAPABILITY-ADOPTION KSF-LOAD-BEARING TOOL-COMPOSITION-LAYER WORKFLOW-E2E-AUDIT
  [ok]     strong: 5 claimable -> CLAIM-LIVENESS-BINDING FORWARDER-COST-ORDER-FALLBACK SHARED-NAMESPACE-CONTENTION BRIDGE-MIGRATE-DROID-CLIENT CODE-MAP-MERMAID
  [LOW]    economy: 2 claimable -> LOOP-GUARD-REASON-WIRE PYLINT-UNUSED-ARGS -- almost empty, feed proactively
  (LOW-WATER tiers: economy -- top up before they starve)
== FOREMAN: non-claimable tickets (reason + blast radius) ==
  BRIEF-ABSOLUTE-PATHS           blocked on LOOP-GUARD-REASON-WIRE (real prereq -- build it)
  CATALOG-REFRESH-PERSIST        BLOCKED on SW-STATIC-LEGS-RETIRE, whose PR #199 is MERGED (unmarked) -> SAFE to done-mark (blast: unblocks CATALOG-REFRESH-PERSIST)
  CG-LAN-OPEN-UI                 PARKED (human hold) -- NOT auto-cleared; confirm still intended
  CREATION-GATE-DECOMPOSE-WIRE   blocked on PROJECT-MEMBERSHIP-GATE (real prereq -- build it)
  DISCOVERY-APPROVAL-WIRE        blocked on DISCOVERY-QUEUE (real prereq -- build it)
  DISCOVERY-CADENCE              blocked on DISCOVERY-APPROVAL-WIRE (real prereq -- build it)
  DISCOVERY-DIFF                 blocked on DISCOVERY-NORMALIZE (real prereq -- build it)
  DISCOVERY-QUEUE                blocked on DISCOVERY-DIFF (real prereq -- build it)
  DONE-SH-INTEGRITY-FIX          blocked on GITHUB-LIMITS-HARDENING (real prereq -- build it)
  FINAL-E2E-REVIEW               blocked on MODEL-PREFLIGHT (real prereq -- build it)
  FIX-PROVIDER-KEY-EXFIL         PARKED (human hold) -- NOT auto-cleared; confirm still intended
  FREE-TIER-QUOTA-ROUTING        blocked on FT-LIMITS-GROQ-RECONCILE (real prereq -- build it)
  FT-WIRE-QUOTA                  PARKED (human hold) -- NOT auto-cleared; confirm still intended
  GATEWAY-LITELLM-ADOPT          PARKED (human hold) -- NOT auto-cleared; confirm still intended
  GITEA-ACTIONS-CI-SPIKE         PARKED (human hold) -- NOT auto-cleared; confirm still intended
  HANDOFF-GATE-NONBYPASSABLE     blocked on RECONCILE-WIRING (real prereq -- build it)
  INVENTORY-TABLE-SHARE          blocked on DISCOVERY-NORMALIZE (real prereq -- build it)
  LAUNCHER-CRASH-PARTIAL-DETECT  blocked on LOOP-GUARD-REASON-WIRE (real prereq -- build it)
  MARKER-PROOF-MECHANIZE         blocked on DONE-SH-INTEGRITY-FIX (real prereq -- build it)
  MODEL-HARDCODE-PURGE           blocked on REVIEWER-TAB-POOL (real prereq -- build it)
  MODEL-PREFLIGHT                blocked on BENCH-OOB-GRADING (real prereq -- build it)
  NO-LOCAL-MASTER-COMMITS        blocked on SYNC-SCHEDULE (real prereq -- build it)
  ORDER-A-COST-PRIMARY-LAND      blocked on FORWARDER-COST-ORDER-FALLBACK (real prereq -- build it)
  PARK-REARM-FUNDED-PROVIDER     BLOCKED on SW-IDENTITY-FOLD, whose PR #198 is MERGED (unmarked) -> SAFE to done-mark (blast: unblocks PARK-REARM-FUNDED-PROVIDER)
  PEAK-PRICING-AWARE             blocked on PRICING-LIMITS-CHECK-SH (real prereq -- build it)
  PREFLIGHT-GATE-REGISTRY        blocked on MARKER-PROOF-MECHANIZE (real prereq -- build it)
  PREFLIGHT-GATE-RUN-HELPER      blocked on SYNC-SCHEDULE (real prereq -- build it)
  PRODUCT-GRADES-STORE           PARKED (human hold) -- NOT auto-cleared; confirm still intended
  REACHABILITY-AUDIT-LAND        blocked on REACHABILITY-GATE (real prereq -- build it)
  RECONCILE-WIRING               blocked on MARKER-PROOF-MECHANIZE (real prereq -- build it)
  REPO-MAP-CONVERGE              blocked on SYNC-SCHEDULE (real prereq -- build it)
  SW-STATIC-LEGS-RETIRE          BLOCKED on SW-IDENTITY-FOLD, whose PR #198 is MERGED (unmarked) -> SAFE to done-mark (blast: unblocks SW-STATIC-LEGS-RETIRE)
  WIP-CLOSE-GATE                 blocked on SESSION-END-PUSH-GATE (real prereq -- build it)
  WIRE-BRAIN-INTO-GATEWAY        PARKED (human hold) -- NOT auto-cleared; confirm still intended
== FOREMAN: composition health (collisions / decomposition) ==
  [ok] no live owns-collisions
== FOREMAN: remedies (provably-safe only) ==
  PROPOSE: done-mark merged dep SW-IDENTITY-FOLD (blast: unblocks its dependents)
  PROPOSE: done-mark merged dep SW-STATIC-LEGS-RETIRE (blast: unblocks its dependents)
== FOREMAN: orphan-claim reaper (dead-PID claims) ==
  reap-orphans: DRY-RUN (pass --apply to actually reap)
  reap-orphans: fleet=/home/stack/charon-private/fleet claims_dir=/home/stack/charon-private/fleet/state/claims
  
  DEAD+PRESERVE  SW-IDENTITY-FOLD  droid=strong-1837603 pid=1837603 branch=fix/sw-identity-fold unique=2 (work valuable — keep branch + worktree, flag for manager)
  
  reap-orphans: done (dry-run)
    live (untouched): 0
    dead+preserve:    1
    dead+clean:       0
  (reaper: live=0 dead-preserve=1 dead-clean=0)
  [ORPHAN] 1 dead-droid branch(es) with unmerged commits — manager: 'fleet/land-needs-push.sh <id>' per id (or re-run 'foreman.sh --fix' with reap-orphans confirmation).
== FOREMAN VERDICT: [OK] all tiers fed, no collisions, decomposition clean ==
```

### >>> PLANE-CANARY RED — declared control/money planes are UNGUARDED <<<

```
--- plane-canary surface (handoff) ---
════════════════════════════════════════════════════════════
 PLANE-CANARY reconcile — every declared plane must be
 wired + passing + fault-proven, or it is LOUD RED
 registry: /home/stack/charon-private/fleet/plane-canary-registry.tsv
════════════════════════════════════════════════════════════
  RED    plane 'data/serving': unwired canary — wired_in=[ci,preflight] but layer(s) [preflight] do NOT invoke flow-canary.sh/flow-canary.test.sh (FINAL-E2E-REVIEW phantom class; fail-closed)
  RED    plane 'failover': unwired canary — wired_in=[ci,preflight] but layer(s) [ci preflight] do NOT invoke failover-canary.sh/failover-canary.test.sh (FINAL-E2E-REVIEW phantom class; fail-closed)
  RED    plane 'egress-key': unwired canary — wired_in=[ci,preflight] but layer(s) [ci preflight] do NOT invoke egress-key-canary.sh/egress-key-canary.test.sh (FINAL-E2E-REVIEW phantom class; fail-closed)
  RED    plane 'review': unwired canary — wired_in=[preflight] but layer(s) [preflight] do NOT invoke reconcile-review-gate.sh/review-dispensation-canary.test.sh (FINAL-E2E-REVIEW phantom class; fail-closed)
  RED    plane 'lifecycle': unwired canary — wired_in=[preflight,ci] but layer(s) [preflight ci] do NOT invoke gate-parity.sh/ticket-lifecycle-canary.test.sh (FINAL-E2E-REVIEW phantom class; fail-closed)
  GREEN  plane 'landing': wired [ci], files present, proven (LANDING-GATE-REGISTER)
  RED    plane 'balance': unwired canary — wired_in=[preflight] but layer(s) [preflight] do NOT invoke balance-canary.sh/balance-canary.test.sh (FINAL-E2E-REVIEW phantom class; fail-closed)
  RED    plane 'config-ssot': unwired canary — wired_in=[preflight] but layer(s) [preflight] do NOT invoke config-ssot-gate.sh/config-ssot-gate.test.sh (FINAL-E2E-REVIEW phantom class; fail-closed)
  GREEN  plane 'map-freshness': wired [preflight,land], files present, proven (WIRE-GRAPHIFY-FRESHNESS)
  RED    plane 'reconciliation': unwired canary — wired_in=[preflight,timer] but layer(s) [timer] do NOT invoke reconcile-gate-wired.sh/reconcile-gate-wired.test.sh (FINAL-E2E-REVIEW phantom class; fail-closed)

████ PLANE-CANARY reconcile: RED — a declared plane is unwired / proofless / uncovered (see RED lines) ████

████████████████████████████████████████████████████████████████████████
████ PLANE-CANARY RED: 8 of 10 DECLARED PLANES HAVE NO TRUSTWORTHY CANARY
████ RED planes: data/serving failover egress-key review lifecycle balance config-ssot reconciliation
████ Each is a declared control/money plane that is unwired, proofless,
████ or entirely uncanaried. It will break silently in production.
████ Detail:  bash fleet/plane-canary.sh reconcile
████████████████████████████████████████████████████████████████████████
```

```
### Parked tickets
```
ATC.md.parked
BENCH-REDS-REPLAY.md.parked
BOARD-REDS-TRIAGE.md.parked
CAPABILITY-ENGINE.md.parked
CATALOG-RECONCILE-GPT5.md.parked
CATALOG-SEARCH-CURATE.md.parked
CATALOG-SYNC-DRIFT.md.parked
CONNECT-OMP-WSL.md.parked
COOLDOWN-FIX3.md.parked
COORDINATOR-DOCTRINE-ROLLOUT.md.parked
COST-RANK-AUTO.md.parked
CWD-CONFIG-VERIFY.md.parked
DOGFOOD.md.parked
DSGN-WRITEBACK.md.parked
DTC-6.md.parked
DURABLE-BRIDGE-PHASE-2.md.parked
EXPLORE-PROMOTE.md.parked
FREE-TIER-QUOTA-SPILL.md.parked
FRONTIER-REVIEW-POLICY.md.parked
GATEWAY-CONTRACT-INJECT.md.parked
GATEWAY-ROUTING-DECOMPOSE.md.parked
GPT5-POOL-REORDER.md.parked
GUI-SVELTE-BUILD.md.parked
LONGCAT-PROVIDER.md.parked
METER-MODEL-PROVIDER.md.parked
METER-SESSION-TAG.md.parked
NANOGPT-PRIMARY-REVIEW.md.parked
OHMYPI-ASSESS.md.parked
OPENROUTER-FLAKINESS-FIX.md.parked
PFF-P2.md.parked
POOLS-SIMPLIFICATION.md.parked
PROVIDER-FLATRATE.md.parked
PUSH-GUARD-GITC-HARDEN.md.parked
RFL-2.md.parked
RFL-3.md.parked
RFL-4.md.parked
SECRET-HOTROTATE.md.parked
SR-10.md.parked
SR-12.md.parked
SR-6-Phase2.md.parked
TEST-EXERCISES-CHANGE-GUARD.md.parked
TIER-RECS.md.parked
UX-POLISH.md.parked
WORKCLASS-BACKFILL-REVIEW.md.parked
ZEN-DRIFT-CLEANUP.md.parked
```
### Live tickets (.md, not parked)
```
ADR0016-DEPLOY-PRICED-COMPLETENESS.md  tier=strong  depends_on=
API-DECOMPOSE-CYCLE-FIX.md  tier=economy  depends_on=
ASSIGN-DETERMINISTIC-SELECTOR.md  tier=strong  depends_on=
ASSIGN-DISPATCH-PICK-FIX.md  tier=strong  depends_on=
AUTO-DONE-ON-MERGE-MISS.md  tier=strong  depends_on=
AUTOLAND-DEFAULT-BRANCH-FIX.md  tier=economy  depends_on=
BALANCE-CANARY.md  tier=strong  depends_on=PLANE-CANARY-REGISTRY
BANDIT-PREEXISTING-FINDINGS.md  tier=strong  depends_on=
BASH-INERT-COVERAGE.md  tier=strong  depends_on=FIXTURE-BYPASS-GATE
BENCH-OOB-GRADING.md  tier=frontier  depends_on=STAGE-DEMUX
BRIDGE-MIGRATE-DROID-CLIENT.md  tier=strong  depends_on=
BRIEF-ABSOLUTE-PATHS.md  tier=economy  depends_on=SESSION-REPORT-WIRE, LOOP-GUARD-REASON-WIRE
CAPABILITY-ACTUALS-DEADREF-CLEANUP.md  tier=economy  depends_on=
CAPTURE-WIRING-TIMEOUT-FIX.md  tier=strong  depends_on=SALVAGE-STASH-CHARON-RUN
CATALOG-COMPLETENESS.md  tier=strong  depends_on=
CATALOG-REFRESH-PERSIST.md  tier=strong  depends_on=SW-STATIC-LEGS-RETIRE
CG-LAN-OPEN-UI.md  tier=strong  depends_on=
CHARON-FLOWCHART.md  tier=strong  depends_on=
CI-SUITES-CANARY.md  tier=strong  depends_on=MERGE-DROP-RATCHET
CLAIM-LADDER-HEALTH.md  tier=strong  depends_on=
CLAIM-LIVENESS-BINDING.md  tier=strong  depends_on=
CODE-MAP-MERMAID.md  tier=strong  depends_on=
CREATION-GATE-DECOMPOSE-WIRE.md  tier=strong  depends_on=PROJECT-MEMBERSHIP-GATE, PRIORITY-CONSOLIDATION, CLAIM-LIVENESS-BINDING
DEADCODE-TOOLS-WIRE.md  tier=strong  depends_on=
DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD.md  tier=strong  depends_on=
DEGRADE-ALERT.md  tier=strong  depends_on=
DIFF-COVER-MUTMUT-ADOPT.md  tier=strong  depends_on=KSF-VENDOR-GATES
DISCOVERY-APPROVAL-WIRE.md  tier=strong  depends_on=DISCOVERY-QUEUE, ADD-PROVIDER-MECHANIZE-COMPLETE
DISCOVERY-CADENCE.md  tier=economy  depends_on=DISCOVERY-APPROVAL-WIRE
DISCOVERY-DIFF.md  tier=strong  depends_on=DISCOVERY-NORMALIZE
DISCOVERY-NORMALIZE.md  tier=strong  depends_on=DISCOVERY-SOURCE-ADAPTERS
DISCOVERY-QUEUE.md  tier=strong  depends_on=DISCOVERY-DIFF
DONE-SH-INTEGRITY-FIX.md  tier=strong  depends_on=GITHUB-LIMITS-HARDENING, VERIFY-MERGED-REPO-AWARE
EGRESS-KEY-CANARY.md  tier=strong  depends_on=PLANE-CANARY-REGISTRY
EVAL-CONTROL-GATE-FIX.md  tier=strong  depends_on=
FAILOVER-CANARY.md  tier=strong  depends_on=PLANE-CANARY-REGISTRY
FAKTORY-TRIAL.md  tier=strong  depends_on=
FINAL-E2E-REVIEW.md  tier=frontier  depends_on=DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT
FIX-PROVIDER-KEY-EXFIL.md  tier=strong  depends_on=
FN-MEMORY-RETIRE-ADOPT.md  tier=economy  depends_on=
FORCE-PUSH-SAFETY-GATE.md  tier=strong  depends_on=
FORWARDER-COST-ORDER-FALLBACK.md  tier=strong  depends_on=
FREE-TIER-QUOTA-ROUTING.md  tier=strong  depends_on=FT-LIMITS-GROQ-RECONCILE
FT-CATALOG-SEED.md  tier=economy  depends_on=
FT-LIMITS-GROQ-RECONCILE.md  tier=economy  depends_on=
FT-WIRE-QUOTA.md  tier=strong  depends_on=FT-QUOTA-ENGINE, FT-CONFIG-SURFACE, FT-CATALOG-SEED, FAIL-LOUD-CONTRACT, FORWARDER-RECONCILE, PROVIDER-PROBE-FIX, GATEWAY-NONTOKEN-METERING
GATEWAY-GRADE-ORDER-MVP.md  tier=strong  depends_on=GW-CUTOVER-LIVE-WIRE
