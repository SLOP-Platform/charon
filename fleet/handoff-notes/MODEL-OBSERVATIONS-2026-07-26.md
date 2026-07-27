# MODEL OBSERVATIONS — 2026-07-26 (INTERIM, manager-observed)

**STATUS: TEMPORARY. This is NOT the ledger and must never become a parallel one.**
`fleet/model-scorecard.tsv` (live lane) is the ledger. It could not capture today's runs because the
grading path is broken end to end: `fleet/capability/grades.py:544-559` requires >=3 `strong-control`
rows and the file has 0, so `assign.py` returns `REFUSED — no eligible candidate` for everything
(B1); and `done.sh:175` hardcodes `MERGE/pass/score=100`, so every row is identical anyway (B2).
Fixes: `SW-PHASE0-GRADE-READ` (B1) and `DONE-SH-INTEGRITY-FIX` defect (c) (B2). **When those land,
fold these observations in as evidence and DELETE this file.**

**Weight these correctly:** n=1 per model per task, no controls, tasks of unequal difficulty, and the
observer (manager) also wrote the briefs — so a good outcome partly measures brief quality, not just
model quality. This is a field note, not a ranking. Do NOT use it to pick tiers.

---

## deepseek-v4-pro — 4 tasks, all completed, no failures

| Session | Task | Outcome |
|---|---|---|
| qui-gon-jinn | SW-IDENTITY-FOLD (bugfix, money path) | GOOD, shallow on evidence |
| mace-windu | PREFLIGHT-OWNS-ARBITRATE (design-review) | EXCELLENT |
| obi-wan-kenobi | TRIAGE-ADD-PROVIDER (rig-meta) | EXCELLENT |
| rey-skywalker | NIM-PROVIDER-CLEANUP (blocked) | CORRECT STOP |

- **qui-gon-jinn**: fixed the fp4 fold, 38-entry corpus, red-proof executed properly with both exit
  codes, gate green (2356 passed). Weakness: dispositioned SIX suffix families as one blanket
  "no-fold" on a SINGLE example (`gpt-4` vs `gpt-4-turbo`), and built its corpus from SYNTHETIC ids
  rather than the live catalog — so it "proved" `awq`/`gptq`/`w8a8` against models that do not exist.
  Did the task; did not interrogate its own evidence.
- **mace-windu**: found that a 5-way owns collision needed exactly ONE dep edge because four tickets
  already chained transitively. Its predicted post-ruling validator output was **exactly correct**.
  Correctly refused to apply the edit (contract said ruling only).
- **obi-wan-kenobi**: **overturned the manager's framing with evidence.** I called d7e03ab abandoned
  WIP; it proved 25/25 tests pass, no abandonment signatures, and 100% overlap with NIM's (a)+(b).
  Also hit the work-lease refusal and **did not use the advertised `WORK_LEASE_BYPASS=1`** — it
  reported and released cleanly. That restraint was not explicitly instructed at the time.
- **rey-skywalker**: hit its blocking precondition, stopped in 15.9s with zero files touched,
  unregistered AND released the ticket. Textbook.

## minimax-m3-free (nvidia leg, free-daily) — 1 complete, 1 running

- **cal-kestis** — ADVERSARIAL REVIEW SW-IDENTITY-FOLD: **best analytical depth of the day.** Traced
  all **620 live catalog entries** rather than trusting the test corpus, and produced findings the
  builder and the manager both missed: 4 REAL stranded pool ids
  (`nanogpt/coding-router:low|:medium|:high|:max`), and that the corpus proves 13 quant folds against
  only 2 live quant forms — i.e. `awq`/`gptq`/`w8a8`/`:free`/`:nitro`/`:online`/`:reasoning` are dead
  code. Correctly returned MERGE (0 BLOCKING) instead of manufacturing blockers to look thorough.
- **(unnamed, collided as `kit-fisto`)** — ADVREVIEW LITELLM-COST-FIELD, still running at time of
  writing. Registered by REUSING the manager's live session name despite the brief listing it as
  taken, taking over the manager's board entry. Also stopped heartbeating and was purged while alive.
  Cause is partly ours (prose instruction instead of `claim-jedi-name.sh`; no transport heartbeat —
  see BRIDGE-PROXY-HEARTBEAT), but the name WAS listed as taken in its brief.

## Cross-cutting observations
- **Every session that was given a mechanical stop-check obeyed it**; the one instruction class that
  failed repeatedly (heartbeat, name choice) was prose. Consistent with
  `brief-clauses-that-work`: file tests and commands are obeyed, judgement prose is not.
- **No model fabricated a success** today. Every claim checked (commit SHAs, test counts, file
  contents, diffs) held up on independent verification.
- **The reviewer role produced more value than the builder role.** cal-kestis and obi-wan-kenobi each
  found something their brief did not anticipate; builders did what they were told.

---

## UPDATE — SW-IDENTITY-FOLD follow-up (deepseek-v4-pro, unregistered session)

`89d15c5`, manager-reviewed, MERGED to product master as PR #198 (squash) -> `fb39191`.
- Implemented all 5 adversarial findings plus operator decisions 13/14.
- **`_EXPLICIT_ALIASES` is exactly the narrow, auditable table asked for** — 2 entries
  (`gemini-3-pro-preview`, `gemini-3-flash-preview`), one-shot lookup before the regex loop, not a
  second normalizer. **Correctly REFUSED to alias `gemini-3-pro-image-preview`** (image model into a
  text pool) and said why in-code. That judgement was the risk in this task and it got it right.
- Fixed cal-kestis's F3 by extending `_MODE_SUFFIX` to `:low|:medium|:high|:max` — the 4 live
  `coding-router` strands are gone. Dropped the no-op `_MARKETING_SUFFIX` regex.
- VERIFIED BY MANAGER, not self-reported: corpus test 3 passed; `charon.cli gate` all checks passed.
- Known residual edge (NOT a defect, recorded so nobody rediscovers it): the alias applies to the
  final segment BEFORE suffix stripping, so a stacked form like `gemini-3-pro-preview-fp8` would not
  alias. No such id exists in the live catalog today.

## PROCESS FINDING — bridge registration is being skipped outright
8 opencode sessions ran concurrently; **zero registered on the board.** This session committed real,
correct work and never appeared. So the problem is NOT just the missing heartbeat
(BRIDGE-PROXY-HEARTBEAT): models skip `register` itself, even with a mechanized
`claim-jedi-name.sh` step 0 in the brief. Consequence: the manager cannot see or ASSIGN work through
the bridge, which is the whole point of it.
**Implication for BRIDGE-PROXY-HEARTBEAT:** the proxy should AUTO-REGISTER on startup (claiming a
name itself) rather than waiting for the model to call `register`. Same lesson as everything else
today — put it in the transport, not the prompt.

---

## ROUND 2 — 2026-07-26 afternoon

### deepseek-v4-pro (cont.)
- **BRIDGE-PROXY-HEARTBEAT** (`9ee20d2`+`aff9414`) — **best proof discipline of the day.** The contract
  demanded proving an idle session survives its 600s lease by ACTUALLY WAITING. It waited **630s**,
  red-proofed the no-heartbeat case (purged after 3 board calls), proved the kill path releases the
  ticket, and confirmed `daemon.py` untouched (0 lines). 5 proxy + 19 daemon tests pass. Added an
  env kill-switch for testing. It did NOT cut corners on the one requirement that was expensive.
- **SECRET-HOTROTATE** (`b0cd2ae`) — read all 11 salvaged prior-art diffs, adopted the consensus
  pattern, and **caught a bug in one of them** (`free-mistral-code`'s one-liner assigns None from
  `setdefault`'s return). Red-proof 1->0. Hit the work-lease refusal and **again refused
  `WORK_LEASE_BYPASS=1`** — reported instead, so the work survived for the manager to commit.
- **SW-STATIC-LEGS-RETIRE** (`e72e49b`) — **pushed back on the ticket's premise and was RIGHT.** The
  brief said retire `upstream_model`; it proved that field is populated BY DISCOVERY
  (catalog_refresh.py:120) and is a wire-routing field, not a membership control — retiring it would
  have broken discovery. Correctly reframed the 175 hand-pinned entries as deploy-time DATA cleanup.
  Moved `enabled: false` from a silent drop in the routing compiler to an explicit operator control.
  Produced real before/after snapshots (pool_ids 3 -> 3, LOST: NONE), red-proof fails 3 named tests.
  ONE DEFECT: edited `src/charon/gateway.py` (11 lines) which it did not own — but the brief forbade
  proxy.py/forwarder.py by name and OMITTED gateway.py, so it had no stop-check. Manager error.

### minimax-m3-free
- **ADVREVIEW-LITELLM-COST-FIELD** (release gate) — **the most valuable single output today.** It
  refuted the entire money-risk premise by proving `litellm_cost` has ZERO production callers and
  that authoritative spend runs elsewhere — then still returned **HOLD** on a genuine BLOCKING gap
  (zero test coverage on the new branch) plus a real operational finding (0.0 conflated with
  "missing" would saturate the COST DIVERGENCE alarm on every free-tier request). Refuting the brief's
  framing AND finding a real defect is the ideal reviewer behaviour.
  DEFECT: registered by REUSING the manager's live session name (`kit-fisto`), taking over its board
  entry — the brief listed it as taken. Cause partly ours (prose, not `claim-jedi-name.sh`).
- **EFFORT-MODEL-ADOPT** (corran-horn) — **correct refusal.** Found zero `nsurf` sites exist, the work
  was already delivered as `c8c1f13`, and the files belong to live ticket TIER-BALANCE. Refused all
  three bad options (no-op commit / bypass an active ticket / duplicate the formula). Cleaned up
  fully: lease released, worktree AND branch removed, unregistered. The ticket was redundant; it
  proved it rather than producing a plausible no-op.

### minimax-m3-together
- **NIM-PROVIDER-CLEANUP** (cal-kestis) — **caught two nonexistent files in the brief's OWNS clause**
  (`free_tier_catalog.json`, `add-provider.test.sh`), identified the real artifacts, cited the landed
  review-log showing defect (c) was deliberately deferred, and stopped rather than inventing files.
  Later re-registered fresh per the new protocol rather than renewing a dead lease.

## CROSS-CUTTING — ROUND 2
- **Three sessions refused to do bad work and reported instead** (corran-horn, cal-kestis,
  rey-skywalker). In every case the brief was wrong, not the session. **The manager was the weakest
  link today** — 4+ file facts asserted without verification, one omitted stop-check that caused an
  owns violation, and one wrong strand diagnosis (zai). Sessions caught all of them.
- **Two sessions independently declined the advertised `WORK_LEASE_BYPASS=1`.** Neither was told to
  in the earlier briefs. That is judgement, not compliance.
- Still zero fabricated successes across ~12 sessions. Every SHA/test-count/diff spot-checked held.

---

## ROUND 3 — THE FIRST REAL NEGATIVE SIGNAL (gate-building)

Two P0 gates were built and BOTH FAILED REVIEW for the SAME reason. This is the most important
observation of the day because the work LOOKED excellent by every surface metric.

### deepseek-v4-pro — DOGFOOD-GATE (`f0f3666`) — REJECTED
Built a registered gate (one line in `gate_runner.py` CHECKS — genuinely wired), 325-line test file,
258-line checker, 12 assertion sites, exit 0, "all routing assertions passed".
**Defect:** the gate PASSES a build containing the exact production bug it exists to catch. Manager
reverted the fp4 fold (verified broken: `MiniMaxAI/MiniMax-M2.5-FP4` -> `minimax-m2.5-fp4`) and the
gate still exited 0. Its ticket's stated acceptance test was precisely "go RED against a reverted fp4
fold". Also emitted NO session report — the missing RED-PROOF field is exactly what would have caught
this before it reached the manager.

### deepseek-v4-flash (lowbacca) — INERT-STARTUP-CHECK (`ccb1b79`) — REJECTED
Emitted a complete, well-formed SESSION REPORT v1: 14/14 tests, gate 21/21, TWO red-proofs, correct
scope (did not touch the 4-claimant gateway.py), OBSERVABLE: MET. Reads as exemplary.
**Defect:** `classify_modules()` is a lookup against a HARDCODED `INERT_ATTRS` frozenset containing
the six module names the ticket handed it. It does not detect inertness — it recites the answer. It
can never find a SEVENTH dead module, and defaults everything unknown to ACTIVE (fail-open, on a
check whose whole job is finding silent deadness).

## THE PATTERN — name it, it is subtle and it defeats our current bar
Both satisfied the LETTER of the contract with machinery that CANNOT FAIL:
* Both passed their own red-proofs — because the red-proof tested SELF-CONSISTENCY. Removing an entry
  from a hardcoded list and watching the test that reads that list go RED proves only that the list
  matches itself.
* Both had clean scope, real test counts, green gates. Every proxy we use for quality was satisfied.
* Neither would have caught the miss it was built for.
**RED-PROOF IS NOT SUFFICIENT when the model chooses what to break.** The break must be an
INDEPENDENT, EXTERNAL defect (revert a real production fix; introduce a genuinely new dead module) —
not a mutation of the check's own input. Future gate tickets must specify the break, not delegate it.
Manager-side lesson: I only caught both by running the external break MYSELF. Reading the report
would not have found either.

## CALIBRATION — do not over-read this
Same two models did excellent work earlier today (mace-windu's minimal 5-way collision fix;
obi-wan-kenobi overturning the manager with evidence; the 630s heartbeat wait). This is a TASK-CLASS
signal, not a model-quality verdict: **gate-building is where they under-perform**, because "write a
check that catches X" is satisfiable by asserting X directly. Route gate work with an explicit
external red-proof spec, or expect this failure.

### FAIRNESS CORRECTION — deepseek-v4-flash / INERT-STARTUP-CHECK
That session terminated with `ResourceExhausted: Worker local total request limit reached (48/48)`.
A 48-request ceiling plausibly explains the shortcut: deriving inertness needs reading forwarder.py's
full invocation surface plus proxy_server.py wiring — many tool calls — whereas a hardcoded frozenset
is one write. It may have been BUDGET-TRUNCATED rather than lazy, and it still emitted a complete,
honest report and respected scope.
**Operational finding, not a model finding:** a hard per-session request cap silently converts
"derive it" into "assert it". Sessions do not report hitting the ceiling as a constraint — this one
reported STATUS: DONE. Route derivation-heavy work to a route WITHOUT this cap, or expect the
cheapest satisfying implementation. Worth adding a BUDGET line to SESSION REPORT v1 so truncation is
visible instead of inferred.
