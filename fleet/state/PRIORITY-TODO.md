# ⛔⛔ START HERE — THE VERY FIRST THINGS THE NEXT SESSION DOES ⛔⛔

**Operator directive, 2026-08-01 session close. Do these BEFORE anything else in this file.
Launch them in TABS. They are one causal chain: the work-loss class recurs every session because
its fixes keep being lost to the class itself.**

| # | item | state at close | why first |
|---|---|---|---|
| **0** | **RESCUE: push the 47 local-only branches** | 96 commits exist ONLY on this box | non-destructive, reversible, one call each. Do this BEFORE building anything — the last two sessions built the fix and lost it |
| **1** | `feat/stranded-work-detect-v2` | 1 unique commit, **NO remote** | the stranded-work detector is itself stranded |
| **2** | `feat/session-end-push-gate-v2` | 3 unique commits, **NO remote** | the push gate was built and never pushed; roadmap still says `not-started` |
| **3** | `HANDOFF-NAME-ALLOCATOR` | **archived + DONE, still broken** | verify the FIRING LAYER — a fix marked complete that never fixed it |
| **4** | `SESSION-END-GATE-REPAIR` | **LIVE, UNCLAIMED** | ticketed, never scheduled; `end-session.sh` aborts before its work-loss check EVERY run |
| **5** | **Adopt a tool to run the gate CONTINUOUSLY in the background** | nothing exists | a close-gate never fires when a session dies on a token limit, crashes, or is killed — which is most of them. **LAUNCH THIS IN A TAB FIRST, IN PARALLEL WITH 0** — it is research and does not block |
| **6** | **GATE DEFECT blocking a real push** | `fix/shared-namespace-contention` cannot be pushed | `land-push` refuses it as *"code owned by NO live board ticket"* — but the ticket IS on origin/master (`f8266ef`) and owns exactly those 4 files. **A gate that blocks legitimate work is how `--force` habits start.** Same stale-base class as RIG-CI-BASE-DEFAULT-BRANCH (fixed today for a different scope) |

### Ordering rationale — why RESCUE is 0 and the gate is not

Asked directly at close: *"should #5 be the FIRST action?"* **No — but launch it in parallel.**

- **0 is the only IRREVERSIBLE item.** 96 commits exist on one disk. A failure or a stray
  `reset --hard` loses them permanently. The gate protects FUTURE work; it does nothing for the 96
  already at risk.
- **Cost asymmetry:** rescue is ~47 pushes, minutes. The gate is an adopt-trial plus wiring, hours.
  Doing the cheap irreversible thing first is strictly correct.
- **This exact ordering is what the last two sessions got wrong** — they built the fix first, then
  lost it to the class (§L). Rescue-then-build breaks that loop; build-then-rescue repeats it.
- **BUT item 5 is INVESTIGATION, so it is not sequential.** Launch it in a tab immediately,
  concurrently with the rescue. Nothing about it blocks, and by the time rescue and items 1-4 are
  done the adopt-verdict should be ready to wire.

Net: **0 and 5 start together; 5 finishes last.**

### Item 5 — the requirement, stated properly
A session-close gate is structurally insufficient: **the sessions that lose work are the ones that
never reach their close.** This session came within a token limit of exactly that. So the check must
run on a CADENCE, independent of any session's lifecycle.

Investigate ADOPT-FIRST (per §0 doctrine — do NOT hand-roll a daemon first):
- the rig already runs **monit** (`fleet/watchdog/*`) — the cheapest candidate, already adopted
- systemd user timers / cron
- a git hook (`post-commit` / `pre-push`) for the commit-time half
- `fleet/watchdog/discover-services.sh` + `generate-monit-config.sh` already exist and may take it

It must cover **ALL** loss classes (the narrow "ahead of upstream" check is exactly what missed 96
commits): branches ahead of remote · **branches with NO upstream at all** · dirty worktrees ·
stashes · detached HEADs. And it must FAIL LOUD — see §J, where the existing gate is marked done and
silently never fires.

### Also at the head of the queue
- **`fix/shared-namespace-contention` — REVIEWED, PUSH BLOCKED.** 25 commits ahead of its remote;
  24 are master merges, the real work is tip `6e8247b` (split claim from check, idempotent re-claim,
  orphan reap, namespaced scratch) + `fleet/tests/scratch-namespace.test.sh`. 88 files, +2209.
  `land-push` REFUSES with *"touches CODE owned by NO live board ticket"* for
  `fleet/claim-jedi-name.sh`, `fleet/spawn-worker.sh` and both tests — **but
  `fleet/board/SHARED-NAMESPACE-CONTENTION.md` IS on origin/master (f8266ef) and owns exactly those
  four files.** So this is a GATE DEFECT, not a real ownership gap — almost certainly the branch's
  own stale copy of the board being read, the same stale-base class as RIG-CI-BASE-DEFAULT-BRANCH.
  Diagnose the gate; do NOT `--force` past it.

---

# PRIORITY TODO — OUTSTANDING WORK (authored 2026-08-01, session saba-sebatyne)

> **THIS FILE IS THE CARRY-FORWARD LIST.** It exists because the recurring failure is not bad work
> — it is good work that gets FORGOTTEN between sessions. Operator directive 2026-08-01:
> *"I want ALL these findings made DURABLE so the next sessions can NOT miss it."*
>
> **RULES FOR THE NEXT SESSION:**
> 1. Read this file at start. It is referenced from SESSION-HANDOFF-saba-sebatyne.md.
> 2. Do NOT delete an item. Mark it `[DONE <sha/PR>]` or `[DROPPED — reason]`. An item that just
>    vanishes is the failure this file prevents.
> 3. Items 1-5 are ALREADY APPROVED by the operator. They do not need re-litigating — they need
>    doing, and each must be DOGFOODED, not merely switched on.

---

## A. TOP 5 TOOL ENABLEMENTS — APPROVED, NOT STARTED

Source of truth + measurements: `fleet/state/TOOL-UTILIZATION-AUDIT.md`.
Only ~20% of installed tool capability is switched on. Operator: *"we tend to turn on a small
selection and then the other stuff gets forgotten or rots"* — so do ALL FIVE, and gate each.

| # | action | measured payoff | status |
|---|---|---|---|
| A1 | `preview = true` in `[tool.ruff.lint]` | **12 defects** inside families we ALREADY select, 7 auto-fixable | TODO |
| A2 | `extend-select = ["S","BLE","ARG","C90"]` | **184** findings, **3 HIGH-severity security** | TODO |
| A3 | mypy `check_untyped_defs` + `warn_unreachable` + `warn_return_any` | **176 real bugs**. SKIP `disallow_untyped_defs` (1952 = churn) | TODO |
| A4 | `shellcheck -o all` on the rig | **15 error-level** findings invisible today | TODO |
| A5 | `graphify affected` (blast-radius) | graph built by 114 `update` sites, query has **0** invocations | TODO |

Each needs: enable → burn down or explicitly baseline → **fail-on-revert test** → wire into a gate
so it cannot rot back off. A2 relates to ticket `RUFF-SEC-RULES-ON` (already minted).

---

## B. MONEY PATH — P0, and the picture CHANGED today

- **B1. `CATALOG-REFRESH-PERSIST`** — CLAIMED + RUNNING in a tab as of session end. Bar was raised
  to fully-wired + dogfooded (persist to disk, cadence observable, propagate to EVERY consumer,
  fail-loud, gate). **Verify it actually landed; do not trust the claim marker.**
- **B2. `SPEND-METRIC-TRUSTWORTHY`** — RE-SCOPE APPROVED but NOT YET APPLIED to the ticket.
  **Finding:** opencode already has per-session cost + token accounting via
  `GET http://127.0.0.1:<port>/api/session`. Measured 2026-08-01: **$1.3372 real spend across 50
  sessions** while the gateway reported `usage.cost_usd = $0.000226`. The gateway meter is fiction
  in BOTH directions (a prior session saw it inflate to a fictional ~$223 via a fabricated
  `est_cost` floor). **Re-scope from "fix the gateway counter" to "ingest the number that already
  exists".** A worker on this was running at session end.
- **B3. PR #207 `FORWARDER-COST-ORDER-FALLBACK` — BOUNCED** (comment posted). It is a strict no-op:
  the live catalog has **10 of 861 models priced**, so the sort key is degenerate; the chain is
  already sorted with the identical key at startup; and `proxy_server.py:674` full-sorts by EWMA
  latency immediately after, discarding cost order (reproduced: openrouter 6x costlier tried
  first). Also ships a FALSE claim that an unpriced leg "sorts last" — the 1000 sentinel equals a
  blended $10/M model, so priced legs above it get demoted BELOW unpriced ones.
  **Consequence: `PRICE-REFRESHER` is the money-path critical path, NOT the ordering ticket.**
  Cost ordering over an unpriced catalog cannot work no matter how correct the sort.
- **B4.** `minimax-m3-free` billed **$0.1542** and **$0.1009** despite `-free` in its name — likely
  a withdrawn free tier, i.e. catalog rot, not a billing bug. Covered by B1.

---

## C. THE 13 "TICKETED BUT STILL INERT" + 10 NEVER-TICKETED

Operator made these HIGH PRIORITY, to be pushed through like the PR backlog.
Full dispatch queue with per-item blockers: see the triage in the session handoff.

**Launched and running at session end:** `LITELLM-CAPABILITY-ADOPTION` (covers 3 items by
disposition), `BASH-INERT-COVERAGE`, `DEADCODE-TOOLS-WIRE`, `PRICE-REFRESHER`.

**BIGGEST UNLOCK — 4 stranded `state/submitted/` markers block 4 of the 13.** One
(`PRICE-REFRESHER`) was pure orphan and has been cleared. These four have LIVE remote branches =
real stranded PRs. Land or close them:
`PRICING-LIMITS-CHECK-SH` (@d4ac0ef) · `REACHABILITY-GATE` (@ea7e1c5) ·
`INERT-WIRING-ENFORCEMENT-DURABLE` (@bbb8421) · `CI-SUITES-CANARY`.

**Three need REOPEN, not a claim** — tickets minted 2026-08-01:
- `GW-CUTOVER-REOPEN` — the **whole litellm plane is merged, marked done, and has ZERO production
  importers**. `GW-CUTOVER-LIVE-WIRE` is in `state/done/` as merged #181; `grep -rn litellm_plane
  src/` finds only a tools/ script and tests. Largest single instance of the built-but-inert class.
- `RUFF-SEC-RULES-ON` — both BANDIT tickets closed green while `pyproject.toml:52` never gained
  `S`/`BLE`. (See also A2 — same work.)
- `GATE-INTEGRITY-C` — **NOT a bug**: `preflight.sh:802-806` documents `scan … || true` as a
  deliberate advisory ramp "until it has ridden a few PRs". It has. Live run: 37 findings, 1 new /
  36 baseline. A scheduled promotion coming due.

**Other confirmed-inert, unfixed:** `reachability-gate` is registered in `tools/gates.json:224-228`
with an enforcer file that **does not exist** — the registry emits a GREEN RECEIPT for an absent
gate. 16 `|| return 0` fail-open guards in preflight.sh. `ActualsLedger`, `pricing_limits_checker.py`
(528 lines), `stale-check.sh`, `reuse-check.sh` — all zero callers.

**Orphaned test suites — worse than first reported:** **91 suites declare themselves red-proofs but
are absent from `CI_SUITES`**, against a ratchet floor of 88, **and the count is RISING**.
Approved approach: **D+B** — (D) gate the INFLOW first so new unregistered suites are blocked, then
(B) ratchet the existing 91 down in batches, folding triage into each batch. `BASH-INERT-COVERAGE`
was running and may overlap; let it land first.

---

## D. WIRING / ENFORCEMENT

- **D1. `WIRING-DONE-CONTRACT`** — APPROVED, ticket NOT yet minted. Make wiring a mechanized
  DONE-CONTRACT rather than a mechanized action: a ticket cannot reach DONE unless its code is
  proven reachable from a real entrypoint (graphify call graph + inert-check + plane-canary,
  fail-closed). Deliberately NOT an auto-wirer — code generation into a money path that can be
  silently wrong is a worse version of the problem.
- **D2. `import-linter` adopt-test** — APPROVED, not started. Test it against REAL cases from the
  13 inert items, not fixtures.
- **D3. KS29 / KS30** — remain `designed` on the roadmap. Decide from what D1 catches in its first
  week rather than as a design bet.
- **D4.** Dead-code tools do NOT answer the wiring question. Measured: vulture flags `litellm_plane`
  with 7 hits at confidence 60 but **0 at confidence 80** (the recommended tuning would blind us to
  the one case that mattered); neither vulture nor deadcode ever says "this module has no
  importers". Confidence measures PROVABILITY, not IMPORTANCE. Do not tune confidence up; use
  `exclude` + a whitelist ratchet **generated only AFTER known inertness is fixed**, or it freezes
  the bugs in permanently.

---

## E. PIPELINE / RIG DEFECTS (from the 10-defect chain)

- **E1.** `AUTO-DONE-ON-MERGE-MISS` — FIXED, committed `9b69739`, **NOT pushed** (branch
  `fix/auto-done-on-merge-miss`, 83 commits behind master, needs update-branch).
  Root cause was NOT what #339 assumed: `reconcile-merged.sh` was **repo-blind** — `REPO_SLUG` came
  from the product checkout only, so all **196 `repo: charon-private` tickets** were structurally
  unreachable. #339's own file `reconcile-board-pr.sh` was a REINVENTION that never fired.
  **PR #339 should be CLOSED, not merged.** 19/19 tests, 11 FAIL on revert.
- **E2.** PR #346 `REVIEWER-TAB-POOL` — **BOUNCED** (comment posted). It would make the pool review
  NOTHING: switches B1 to a `CHARON-AUTHOR-DROID` PR-body marker that **0 of 16 PRs carry and no
  code writes**, with fail-closed skip. All five known review-pool defects untouched, one worsened.
- **E3.** PR #342 — **BOUNCED** (comment posted). The drift-correction PR reintroduces drift on rows
  stamped `aligned`.
- **E4.** `review-pool.sh` five defects, ALL still open: done-marker on INFRA failure (permanently
  retires PRs — 16 hit this today, quarantined to `fleet/state/review-quarantine-saba/`) ·
  stale model chain · `--wait/--retries` never parsed · `queue_gen` not idempotent/unlocked ·
  GraphQL burn. `PR-QUEUE-REST-ETAG` is BUILT (40/40 tests, 8-way red-proof, zero-quota steady
  state) and the CUTOVER into `review-pool.sh` is now IN SCOPE and approved — **not yet done**.
- **E5.** `work-lease.sh` never searches the worktree's own board despite its doc saying it does.
- **E6.** `retire-done.sh` archives working-tree-only; retirement is one `git reset` from vanishing.
- **E7.** `end-session.sh` is built-but-inert on master (R-G). Outside any ticket's owns.

---

## F. OPERATOR ACTIONS (need the human)

- **F1.** `charon-bot` PAT — APPROVED. The account EXISTS but all 16 open PRs show
  `user.login = Nnyan`, so GitHub refuses `request-changes` on our own PRs and B1 cannot key on
  `user.login` (it is a constant matching no droid id). Needs a PAT + collaborator access on both
  repos.
- **F2. DURABILITY GAP:** `MANAGER-OPERATING-RULES.md` (which now carries §14) is loaded at
  SessionStart from **`/home/stack/code/charon/.claude/settings.local.json`** — a machine-local,
  typically untracked file. The doctrine is durable in git; the LOADING of it is not. A fresh clone
  or another box will not load it. `fleet/hooks/session-start.sh` has ZERO references to it.
  **Harden into the tracked hook.**
- **F3.** Ledger corrections require the `bench-grader` user (read-only to manager sessions BY
  DESIGN). Template: `fleet/state/scorecard-correct-saba-20260801.sh`.

---

## G. DECIDED THIS SESSION — DO NOT RE-LITIGATE

- **Session comms:** opencode's HTTP control plane is ADOPTED (2026-07-26, verified post-doctrine).
  MCP was rejected as a control plane on a proven capability gap. **The bespoke session-bridge
  (3,073 LOC) was slated for retirement on 2026-07-26 and is STILL dual-running** — ~10 sidecars,
  3 daemons (one stale since Jul 26), an SSH tunnel, MCP entries in both client configs, and 12 rig
  scripts still reading the bridge DB proven to show 2 of 8 workers. **Finish the retirement.**
  All 4 comms verdicts are now registered in EVAL-REGISTRY.
- **TUI workers:** use `POST /api/session` to reset context per ticket — no respawn needed, keeps
  bridge visibility. Headless droids already get a fresh session per ticket (`opencode run` is
  one-shot); only TUI workers accumulate.
- **Model grading:** prelim leaderboard seed → superseded by REAL-WORK grades → promotion/demotion.
  ONE design, not two. Grading IS live (7 of 8 models graded); the audit claiming otherwise is
  stale. Grades must key on **model × provider** — speed is mostly a provider property, quality is
  model × provider (quantization, hardware, hidden prompts). Ticket `GRADE-MODEL-PROVIDER-PAIR`
  was claimed and running. `BROKER-BARE-TIER-LEGS` is HELD UNMERGED pending it.
- **Catalog is LIVE DATA** — see MANAGER-OPERATING-RULES.md §14. Model names rot, free status rots,
  and EVERY static list must be API-refreshed at EVERY consumer.

---

## H. HOUSEKEEPING

- `MEMORY.md` index is at 173 lines, over the 140 target — compaction deferred.
- 3 stale claims held by dead droids (this session's own manager-built work):
  `BROKER-BARE-TIER-LEGS`, `LAUNCHER-GATE-SETE-KILL`, `PR-QUEUE-REST-ETAG`. The reaper correctly
  HOLDS rather than releasing them (committed but not merge-proven). Retire once merged.
- `rig-ci` is RED on every open PR. Root cause identified: **`fleet/state/*` is gitignored, so
  files the gates depend on (`tier-drift-red.txt`, `service-registry.tsv`) never reach the CI
  checkout.** Not yet fixed — this is why the merge gate has effectively been off.
- 5 pre-existing tickets had unparseable YAML frontmatter (fixed). `BOARD-FRONTMATTER-GATE` is
  built (61 assertions, 4-way red-proof) to catch it at WRITE time; **committed, not pushed**.

---

## I. STARTUP FRICTION — what cost time THIS session, so it does not cost the next one

Operator directive 2026-08-01: *"use all your session start-up issues as a guide to make sure the
friction you had is not carried forward."* Each item below is real, measured, and fixable.

**I1. The handoff was unreadable in one pass.** `SESSION-HANDOFF-tenel-ka.md` was **1,286 lines /
~58,000 tokens** against a 25,000-token read cap. It had to be paged and grepped, and the
machine-generated state (worktree lists, PR dumps, roadmap) dwarfed the human-authored part.
→ **FIX:** keep the hand-written brief SHORT and put generated state behind a pointer. The
next session should read `fleet/state/PRIORITY-TODO.md` (this file) FIRST — it is the carry-forward
list — and treat the handoff as provenance, not as the task list.

**I2. Ticket→code chicken-and-egg cost ~6 round trips per ticket.** The substrate gate rejects in
sequence, one reason per push: missing `substrate:` → missing D&S → unparseable YAML → tool has no
EVAL-REGISTRY row → row is `drifted` and needs `substrate-retest:` → registry row may not land in
the SAME push as the ticket citing it ("not self-service") → `substrate:` tool name must not appear
in the ticket's own `owns:`. Each cost a full validate+push cycle.
→ **FIX:** author tickets with ALL of these present from the start:
`substrate:` (≥60 chars of real reasoning, or `N/A` + `substrate-novel:`), a
`## Dependencies & Sequence` section, block scalars (`key: |`) for ANY prose containing `: ` or a
backtick, and land any new EVAL-REGISTRY row in a SEPARATE, EARLIER push.

**I3. `work-lease` refuses a worktree whose branch maps to no board ticket** — so the ticket must
land on master BEFORE the code can be committed. Not a bug, but it must be sequenced deliberately:
mint + push the ticket first, then create the worktree.

**I4. `board-lock` pins a base sha.** Any plain-`git` commit on master (e.g. a doctrine edit) moves
HEAD under the lock and the next board commit refuses with `BASE MOVED UNDER THE BOARD LOCK`.
→ **FIX:** `board-lock.sh release <session> && board-lock.sh acquire <session>`. Also note
non-board commits on master need `board-hygiene` or `land:` in the message or work-lease refuses.

**I5. GitHub GraphQL quota was exhausted (5,000/hr) in under an hour** by 7 reviewer tabs, which
also blocked `gh pr review` and `land-push`'s CI verification. REST core sat untouched at 5000/5000.
→ **FIX:** `fleet/pr-queue.sh` (REST + ETag, zero-quota steady state) is BUILT and pushed; the
cutover into `review-pool.sh` is approved and pending. Until then keep reviewer tabs at
`REVIEW_POOL_WAIT=300` and no more than 1-2.

**I6. `rig-ci` is RED on EVERY open PR**, so the merge gate is effectively off and every merge is a
judgement call. Root cause found: **`fleet/state/*` is gitignored**, so files the gates require
(`tier-drift-red.txt`, `service-registry.tsv`) never reach the CI checkout. NOT yet fixed.

**I7. Name-pool burn.** Every `handoff.sh` / `handoff-check.sh` invocation allocates a Jedi name and
leaves a stub, burning names without a real session (operator action #19). Pool is ~69.

**I8. `end-session.sh` is self-blocking** (operator action #20): it creates its own target file,
then its allocator refuses the name as in-use, so it aborts BEFORE the work-loss check every run.
`SESSION-END-GATE-REPAIR` was claimed by a tab this session — verify whether it landed.

**I9. A sub-agent reported a file path it never wrote.** The tool-utilization audit was reported at
a scratchpad path that did not exist; the content survived only because it was in the manager's
context. → **FIX:** ALWAYS verify a sub's claimed deliverable exists and is non-empty before
relying on it, and prefer writing durable artifacts into `fleet/state/` (with a `.gitignore`
negation) rather than `/tmp`.

**I10. `/tmp` scratchpad does not survive.** Anything a session needs to carry forward must be in
the repo with a `!fleet/state/<file>` negation in `.gitignore` — `fleet/state/*` is blanket-ignored.

---

## J. SESSION-END SELF-BLOCKING — HIT AGAIN 2026-08-01, ESCALATE

**Operator, at session close: *"we keep hitting this stub file exists / self-blocking defect every
session end — is it scheduled to be FIXED?"* Answer: ticketed, NOT scheduled, and one prior fix is
already marked DONE while the defect persists.**

Measured at THIS session's close:

| ticket | state | reality |
|---|---|---|
| `SESSION-END-GATE-REPAIR` | **LIVE, UNCLAIMED** | ticketed, never scheduled |
| `SESSION-CLOSE-COMPLETENESS-GATE` | LIVE, unclaimed | blocked on the above |
| `HANDOFF-NAME-ALLOCATOR` | **archived + DONE** | **and the allocator STILL BLOCKS** — another merged-but-inert instance |

**The defect, reproduced live:** `handoff.sh` with `SESSION=saba-sebatyne` refused —
*"that name is already in use (live file present)"* — because the session's own 29-byte claim-marker
stub `fleet/SESSION-HANDOFF-<name>.md` is in `claim-jedi-name.sh`'s exclusion set. `end-session.sh`
hits the identical shape: it CREATES its target file, then calls `handoff.sh`, whose allocator sees
that 0-byte file and refuses. **The one gate meant to prevent work loss at session close aborts
before it runs its work-loss check, every single time.**

**J1. Fix the allocator to EXEMPT the caller's own target file** (or have `end-session.sh` write to
a temp path and `mv` into place). Both `end-session.sh` and `handoff.sh` are affected — fix the
allocator, not one call site, or the other keeps failing.

**J2. Verify `HANDOFF-NAME-ALLOCATOR`'s "DONE" claim.** It is archived with a done marker and the
symptom is still live. Either it fixed a different sub-case or it never fired — check the FIRING
LAYER, not the ticket state. This is the class the whole session was about.

**J3. Until J1 lands, session close MUST do the work-loss check by hand.** This session did:
```
git worktree list --porcelain | awk '/^worktree /{print $2}' | while read w; do ... done
```
**It found real stranded work** (see K), which is exactly what the broken gate would have missed.

**J4. Name-pool burn (operator action #19) is the same root.** Every `handoff.sh` /
`handoff-check.sh` invocation allocates a name and leaves a stub, burning names without a real
session. Same allocator, same exclusion-set behaviour.

---

## K. STRANDED WORK FOUND AT SESSION CLOSE — verify before assuming lost or safe

- **`fix/shared-namespace-contention` is 25 COMMITS AHEAD of its remote** (remote branch exists;
  PR #345 is open). This is the largest single body of unpushed work on the box. **Verify what those
  25 commits contain and land or explicitly drop them.** Do not assume PR #345 represents them.
- `fix/auto-done-on-merge-miss` — 1 commit ahead, unpushed (see E1).
- Rig master had 36 dirty files at close — mostly untracked board/archive churn and this session's
  in-flight worktrees; not lost, but not clean either.
- ~16 rig worktrees carry 1-4 dirty files each; several belong to tabs that were still running.
  **Re-run the work-loss check at the START of the next session** — tabs kept working after this
  handoff was written, so this list is a floor, not a ceiling.

---

## L. ⛔ ROOT/CLASS: 96 UNPUSHED COMMITS ON 47 LOCAL-ONLY BRANCHES — AND THE FIX IS ITSELF STRANDED

**Operator, 2026-08-01: *"we hit this most end of session (look at the last 3) but we never fix it
in a mechanical way to stop the ROOT/CLASS and not do whack-a-mole."* Measured at this close:**

```
charon-private:  25 local-only branches carrying 38 unpushed commits
charon:          22 local-only branches carrying 58 unpushed commits
TOTAL:           47 branches / 96 commits that exist ONLY on this box
```
(Excludes `backup/*`. "Local-only" = NO upstream ref at all — never pushed, not merely behind.)

**WHY IT RECURS — the fixes for this class were BUILT and then LOST TO THIS CLASS:**

| branch | unique commits | remote |
|---|---|---|
| `feat/stranded-work-detect-v2` | 1 | **NONE** |
| `feat/session-end-push-gate-v2` | 3 | **NONE** |

The stranded-work detector is stranded. The session-end push gate was built and never pushed.
`SESSION-END-PUSH-GATE` still reads `not-started` on the roadmap. Each session rediscovers the
problem, builds a fix, and loses the fix the same way — that IS the whack-a-mole.

Single largest at-risk item: **`feat/cwd-config` — 26 unique commits, never pushed.**

### L1. THE MECHANICAL FIX — do this INSTEAD of another manual sweep

A session-close gate is necessary but NOT sufficient, because a gate that is itself an unpushed
local branch does nothing. Required, in this order:

1. **RESCUE FIRST, before building anything.** Push all 47 local-only branches to remote (they cost
   nothing parked there and are then recoverable from any box), or explicitly delete the ones that
   are genuinely dead. Do NOT build the gate first — the last two sessions did and the gate was lost.
2. **Land `feat/session-end-push-gate-v2` and `feat/stranded-work-detect-v2` IMMEDIATELY.** They
   already exist. Landing them is cheaper than rebuilding them a fourth time.
3. **The gate must cover ALL loss classes, not just "ahead of upstream"** — that narrow check is why
   this was missed repeatedly. The full set, all measured at this close:
   - branches AHEAD of their remote (found: `fix/shared-namespace-contention` **25 commits**)
   - branches with **NO upstream at all** (found: 47 / 96 commits — the class that kept being missed)
   - uncommitted dirty worktrees (~16 rig worktrees, 1-4 files each)
   - stashes (1 in the rig)
   - detached-HEAD worktrees (2 in the rig)
4. **Run it on a CADENCE, not only at close.** A session that ends abruptly, hits a token limit, or
   crashes never reaches its close gate. A timer/preflight leg catches what a close gate cannot.
5. **FAIL LOUD and BLOCK.** `end-session.sh` currently aborts before its work-loss check every run
   (see §J) — so today the gate exists, is marked done, and never fires. Verify the FIRING LAYER.

### L2. Why "just push everything" is the right first move
These branches are already on disk. Pushing is non-destructive and reversible, costs one API call
each, and converts an invisible single-point-of-failure into recoverable remote state. Triage can
happen later at leisure. Losing 96 commits to a disk failure or a stray `reset --hard` cannot be
undone at all. **Rescue is cheap; reconstruction is not.**
