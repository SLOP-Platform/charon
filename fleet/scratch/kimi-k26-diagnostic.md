# kimi-k2.6 benchmark diagnostic — 2026-07-06

## What's anomalous

`kimi-k2.6` / **S5** (greenfield-feature) is the sole outlier in an otherwise clean
7-row run (S0-S4, S6 all MERGE/100 or expected partial credit, times/costs in line
with the model's normal profile — e.g. S0 112.9s/$0.027 vs gpt-5.4's 24.1s/$0.141,
just a slower/cheaper model, nothing wrong there).

S5 ledger row: `score=60  time_s=0.6  cost_usd=0.000000  corrections=0`, reason
`ambiguities_named=0/4; files_touched=0; explicit_defer=True`.

That combination is triply wrong versus every other section/model:
- **time_s=0.6s** — 30-180x faster than any other section for this model (next
  fastest is S2 at 20.2s).
- **cost_usd=0.000000** — the *only* $0.00 row for kimi-k2.6; confirmed by
  `cost_start_usd` in meta.json being **identical** between S5 (1.237304) and S6
  (1.237304) — literally zero dollars metered during the entire S5 attempt.
- **ambiguities_named=0/4** despite the saved `RESPONSE.md` being a well-structured,
  fully honest scoping doc that explicitly lists all 4 ambiguity topics (exhausted
  definition, per-model/tier/global, free/paid ordering, config location) plus 4
  numbered open questions — arguably *better* structured than gpt-5.4's answer,
  which scored 3/4 and 100.

**Re-running the (unmodified) grader against the current worktree confirms this
directly**: `python3 graders/s5.py --worktree runs/kimi-k2.6/S5/worktree --baseline
fixtures/sections/s5` now returns `score=100, ambiguities_named=4/4` — not the
`60 / 0/4` recorded in the ledger, on the exact same files. The regex logic in
`graders/s5.py` (unchanged since it was authored on 2026-07-05, single commit
`15edf24`, never touched since) is not at fault — it scores the saved content
correctly right now.

**mtime smoking gun**: `meta.json` (containing the frozen final_score) predates
`RESPONSE.md`'s last write by **37 seconds** for kimi-k2.6/S5 (meta 22:43:19,
RESPONSE.md 22:43:56). The same **exact 37s** gap, same direction, appears on
**glm-5.2/S5** (meta 22:38:36, RESPONSE.md 22:39:13) — which shows the identical
anomaly signature (`score=60, ambiguities_named=0/4`, near-zero cost `$0.001141`,
time `5.1s`). Both healthy runs checked (gpt-5.4/S5, hy3-preview-or/S5) show the
opposite, expected ordering — RESPONSE.md written **before** meta.json (~5s
earlier) — i.e. write-then-grade, as designed.

## Ranked hypotheses

1. **(Most likely) Harness/driver race — grading fired before the model's file
   write was flushed to disk.** `run.sh --grade` / `bench.sh grade` is a
   human/droid-triggered step (per run.sh's own header: "when the model's
   attempt is ready, grade it with..."). For kimi-k2.6 and glm-5.2's S5 leg, the
   driving automation appears to have called `--grade` the instant the model's
   turn/message looked done, while a trailing tool-call (the actual `RESPONSE.md`
   write) was still in flight — the grader then read an empty-or-partial file
   (0 ambiguity hits, 0 cost/time accrued because the gateway hadn't posted the
   spend yet either), and 37s later the real content landed, too late to matter.
   Evidence: identical 37s late-write gap on both affected models, both scoring
   the exact "a_ok-but-not-all/d_ok-true" partial-credit band (60) that S5's
   grader emits for "no ambiguities found but defer language present" — consistent
   with grading near-empty text that still contained a stray `?` or "TBD"-like
   token satisfying `DEFER_RE` but nothing else. Re-grading the *current* file
   gives 4/4 and 100, ruling out a model-quality or grader-logic problem.
2. **Cost/time accounting quirk, downstream of #1.** `cost_start_usd` identical
   S5→S6 for kimi-k2.6 shows the global cost meter hadn't incremented at all
   when the grade fired — reinforcing that the *entire* S5 attempt (generation +
   write) happened after finalization, not that kimi got a free/flat-rate route.
   Not a gateway-routing bug in the "wrong provider" sense; it's a symptom of #1.
3. **Model genuinely underperformed / dodged.** Ruled out — the actual saved
   RESPONSE.md is a strong, honest, well-scoped answer (arguably better than
   gpt-5.4's). Not the cause.
4. **Grader regex bug.** Ruled out — re-running the unmodified grader against
   the final content scores it correctly (4/4, 100); the regexes for all 4
   topics do match kimi's phrasing.
5. **Gateway routing/provider issue specific to kimi-k2.6.** No evidence in
   the other 6 sections (normal, if slow, cost/time profile) or in S5 itself
   (no error, no timeout marker, no dropped-route signature) — only the
   race-condition pattern.

## Bottom line / action

This is not a kimi-k2.6 model problem and not a grader bug — it's a **run-harness
premature-grade race** that also hit glm-5.2's S5 leg (same run session,
2026-07-06 evening). The recorded 60/0-4 rows for both models understate their
actual S5 performance; re-grading the untouched worktrees now yields the correct
scores. Fix belongs in the driver (bench.sh/droid automation): don't call
`--grade` until the worktree's mtime has been stable for N seconds (or the
driving agent's process has fully exited), not just "message looks done."
Recommend: manually re-grade kimi-k2.6/S5 and glm-5.2/S5 from the untouched
worktrees and correct the ledger rows, then patch the "ready to grade" trigger
before running any more models through S5.

---

# CONTAMINATION SCOPE (harness-bug sweep)

Confirmed root cause (from operator run output): a HARNESS bug, two facets —
(1) `bench.sh` timeout uses a **stale `start_ts` not reset on resume** → forced
score=0 with time_s ≈ 91,700s (~25h); (2) runs are **keyed by bare model name**,
so a resume reuses a prior model's stale state dir and inherits its NAME.

## Method
For every `benchmark/runs/<model>/S*/meta.json` I compared `start_ts` (clock
origin) vs the meta.json write-mtime (when the grade actually landed) and vs
`timebox_sec`, and cross-checked every `bench` row in model-scorecard.tsv.

## Contamination table

| Scorecard rows | Flag(s) | Verdict |
|---|---|---|
| **deepseek-v4-pro — S0..S6 (ALL 7)** | start_ts=**Jul-5 21:09:01** frozen identically across all 7 sections; graded **Jul-6 22:37-22:40** → time_s **91,701–91,875s** (>> 180-720s timeboxes); **score=0 all sections**, cost=`-`, verdict BLOCK/INVALID | **DISCARD** |
| gpt-5.4 — S0..S6 | start_ts fresh (each within ~15-40s of its grade mtime, 20:41-20:43); time_s 15-42s, all < timebox | **TRUST** |
| glm-5.2 — S0..S6 | start_ts fresh (22:36-22:38); time_s 7-428s, all < timebox | **TRUST** (see S5 caveat) |
| hy3-preview-or — S0..S6 | start_ts fresh (22:38-22:44); time_s 22-106s, all < timebox | **TRUST** |
| kimi-k2.6 — S0..S6 | start_ts fresh (22:38-22:43); time_s 0.6-113s, all < timebox | **TRUST** (see S5 caveat) |
| big-pickle — S0 | not finalized (final_score=None); **not in scorecard** — run in progress | N/A (incomplete) |

## The deepseek-v4-pro rows are the ONLY contaminated scorecard rows.
All 7 carry every flag: all-sections-0, absurd time_s (~25h), stale start_ts a
full day older than the grade. Critically, the **worktrees contain REAL Jul-6
work** — `deepseek-v4-pro/S0/worktree/gateway/providers.py` differs from the
fixture (a genuine fix) and `deepseek-v4-pro/S5/worktree/RESPONSE.md` is a
complete, competent scoping+implementation doc written Jul-6 22:38 — yet the
whole run was zeroed by the stale-timeout. This confirms **facet #2**: a model
actually ran on Jul-6 into the deepseek-named dir (which was first created Jul-5
21:09) and the run inherited the "deepseek-v4-pro" name. **The recorded model
name is therefore untrustworthy** — per the operator, the chart said
deepseek-v4-pro but kimi-k2.6 was the model being driven. So these 7 rows are
both mis-scored (facet #1) AND possibly mislabeled (facet #2): DISCARD outright;
do not attribute them to deepseek-v4-pro.

Note: there is currently **no trustworthy benchmark data for deepseek-v4-pro at
all** — its only rows are these contaminated ones.

## Clean / trustworthy recent rows
- **gpt-5.4 (all 7)** — the validated Frontier baseline; pristine.
- **glm-5.2 (all 7)**, **hy3-preview-or (all 7)**, **kimi-k2.6 (all 7)** — fresh
  start_ts, in-timebox times, sensible cost curves. Trustworthy as *scores*.

### Two S5 caveats (a DIFFERENT, second bug — not the contamination bug)
`kimi-k2.6/S5` (60, 0.6s, $0.00) and `glm-5.2/S5` (60, 5.1s, $0.001) are
understated by the **premature-grade race** documented in the first section
above (grade fired ~37s before RESPONSE.md was flushed). start_ts is fresh
(so NOT the stale-timeout contamination), but the *score* is wrong — re-grading
kimi's untouched worktree now yields 4/4 → 100. Treat both S5=60 cells as
suspect-low and re-grade; every other cell for those two models is solid.

## Bottom line
- **DISCARD:** all 7 `deepseek-v4-pro` bench rows + drop the deepseek-v4-pro dir's
  authority (stale start_ts + name-inheritance; real work thrown away).
- **RE-GRADE (understated, separate S5 race):** kimi-k2.6/S5 and glm-5.2/S5.
- **TRUST:** every other bench cell for gpt-5.4, glm-5.2, hy3-preview-or, kimi-k2.6.
- **Harness fixes:** reset `start_ts` on resume/re-grade; key run state by
  (model, run-id/timestamp) not bare model name; gate `--grade` on worktree
  mtime stability (fixes the S5 race too).

---

# MINIMAX-M3 + BIG-PICKLE (post-scan follow-up)

Coordinator reported both "just finished." **On disk, neither produced a
finalized, scored result** — there is nothing in model-scorecard.tsv for either.

## minimax-m3 — NO DATA (neither TRUST nor DISCARD; escalate)
- **No `benchmark/runs/minimax-m3/` dir exists.** No meta.json, no worktree, no
  scorecard row anywhere. The only "minimax" hits in the fleet tree are model-
  catalog mentions in planning docs (MODEL-ROLE-EVALUATION.md, HANDOFF, etc.),
  not run artifacts.
- Nothing landed under the name `minimax-m3`. All six existing run dirs
  (gpt-5.4, glm-5.2, deepseek-v4-pro, hy3-preview-or, kimi-k2.6, big-pickle)
  have an internal `meta.json "model"` field that **matches their dir name**, so
  there is no visible collision victim where minimax silently wrote under
  another model's name either.
- **Verdict: no result to trust or discard — the run never persisted.** This is
  itself the facet-#2 failure mode (a run that produced no correctly-named
  state). ACTION for coordinator: if minimax-m3 was really driven, its output
  was not saved under that key — re-run it cleanly after the keying fix; do NOT
  expect to recover a hidden minimax result from the current dirs.

## big-pickle — INCOMPLETE / INERT (not contaminated, but not a result)
- Only **S0** exists; `meta.json` has `"finalized": false`, **no `final_score`,
  no final_time, no final_cost** → never graded, **not in the scorecard**.
- start_ts = 1783402877 = **Jul-6 22:41:17, fresh** — does NOT match the Jul-5
  21:09:02 (1783310942) deepseek collision stamp, and is within seconds of its
  dir mtime. **No stale/shared-start_ts contamination; did not collide with the
  stuck deepseek run.**
- No absurd time_s, no all-0/INVALID row (there's no row at all).
- Worktree is **inert**: `diff -rq` vs the S0 fixture shows **no changes** (only
  pyc/cache), and `gateway/providers.py` still carries the fixture's own
  19:35:27 mtime — the model never edited anything; the section was prepared but
  never actually driven to a fix.
- **Verdict: no scorecard row to DISCARD; the run is simply incomplete + inert.**
  Nothing to trust either. Re-run big-pickle from scratch (all 7 sections) after
  the harness fix.

## Premature-grade (37s-late-write) sweep — ALL cells, all models
Ran the facet-(e) check across every model/section, not just S5. **Only two
cells** show RESPONSE.md written >3s after meta.json:
- `glm-5.2/S5` (+37s) and `kimi-k2.6/S5` (+37s) — the two already flagged.
No other section for any model (incl. minimax-m3/big-pickle, which have no
RESPONSE at all) carries the signature. The premature-grade race is contained to
those two S5 cells; the re-grade list is unchanged.

## Net for these two models
- **minimax-m3:** DISCARD/absent — no persisted result; re-run.
- **big-pickle:** incomplete + inert (S0 only, unfinalized, no diff); not
  contaminated, not a usable result; re-run.
- Neither collided with the Jul-5 21:09 deepseek stuck run (big-pickle start_ts
  is fresh; minimax left no state to collide).
- Re-grade list unchanged: still only kimi-k2.6/S5 and glm-5.2/S5.
