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
