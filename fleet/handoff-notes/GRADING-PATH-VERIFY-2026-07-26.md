# Real-work grading path — read-only verification, 2026-07-26

## 1. The path (exact files)

RIG (all under /home/stack/charon-private/fleet):
- `fleet-droid.sh` — launcher; sets `CHARON_JOB_REF=<ticket>`, resolves the model chain from `tier-models.tsv`.
- `charon-run.sh:201` — runs opencode via `charon/<model>`; on rc=0 writes `state/model-used/<ref>` and enqueues a PROVISIONAL capture (`cap()` at :77).
- `capture/enqueue-capture.sh:36` — writes capture JSON into `${CAPTURE_SPOOL_DIR:-/var/lib/bench-grader/spool/req}`. Never writes the ledger.
- `benchmark/grader-daemon.py:731` — bench-grader-owned daemon; consumes spool, appends 16-col rows.
- `done.sh:151-193` — on verified merge, enqueues the FINAL capture `--stage active --actual-verdict MERGE --actual-gate pass --score 100`.
- `model-scorecard.sh` (cmd_append) — the ONE writer of the ledger.
- `model-scorecard.tsv` — THE ledger (live lane).
- `capability/grades.py` (ScorecardGradesProvider) -> `capability/assign.py` -> re-rank in `fleet-droid.sh:378-405` and `launch-plan.sh:56`.

Dogfood/Path-C (separate, operator-driven): `benchmark/dogfood-eval.sh` -> `benchmark/dogfood-to-scorecard.sh` (GENERATES an append script; emits stage=provisional only; never writes the ledger).

PRODUCT (/home/stack/code/charon/src/charon/capability): `scorecard.py` = freeze-ring artifact store (used by `lifecycle.py:316`, `decompose_effort.py:265`); `grades.py` / `grades_import.py` = capability matrix. NOT connected to the rig ledger.

## 2. Does it work?

Ledger writes: YES. `model-scorecard.tsv` mtime Jul 24 22:56 local; newest row date **2026-07-25** (LITELLM-COST-FIELD-FIX / minimax-m3-free). **64 rows**, all `source=live`, all `stage=active`. Dates: 16x 07-15, 29x 07-16, 15x 07-24, 4x 07-25. Daemon alive: pid 180289 `python3 .../benchmark/grader-daemon.py` (bench-grader). Spool res: 9264 files, newest Jul 24 22:57 (all stub selftest captures).

Ranking reads: **NO.** `python3 fleet/capability/assign.py <any-ticket>` returns
`REFUSED — no eligible candidate` for every ticket tried, and with explicit `--work-class ci-infra --candidates glm-5.2,minimax-m3-free,deepseek-v4-flash`. `GradesProvider().grade(m,'ci-infra')` returns `None` for all three.

## 3. What produces a graded row for model X

Run on the dev box, cwd /home/stack/charon-private/fleet:
- `bash fleet/fleet-droid.sh <frontier|strong|economy> --only <TICKET-ID> --wait 0`
  (model X must be head of that tier's chain in `tier-models.tsv`; no per-run force-model flag exists)
- then, after the PR merges: `bash fleet/done.sh <TICKET-ID>`

done.sh is what emits the `stage=active` row. Watch for its stdout line
`done.sh: scorecard FINAL enqueued for <id> (model=X, ref=<id> -> MERGE/pass).`
Verify: `grep <TICKET-ID> /home/stack/charon-private/fleet/model-scorecard.tsv`

## 4. BROKEN / INERT

**B1 (blocker) — rig control-panel gate drops every live row.**
`fleet/capability/grades.py:544-559`: `split_ok = pass_observed and fail_observed`, requiring >=3 rows for `CONTROL_PASS_MODEL="strong-control"` on the SAME ref. `grep -c strong-control model-scorecard.tsv` = **0**. `_rows_for` (:655-658) drops any live row whose ref lacks split_ok -> `grade()` -> None -> assign.py REFUSED. The no-control->admit fallback landed only in the PRODUCT copy (`/home/stack/code/charon/src/charon/capability/grades.py:149 _is_fallback_admit`, commit 0947401); `grep -c _is_fallback_admit fleet/capability/grades.py` = **0**. Rig copy never got the fix.

**B2 — the ledger has no discriminating signal.** `done.sh:175` hardcodes `--actual-verdict MERGE --actual-gate pass --score 100`. Verdicts: 63 MERGE / 1 BLOCK. `model-scorecard.sh render` shows 100% merge for 24 of 25 (model, work_class) cells. A "ranking" over this is a tie.

**B3 — efficiency columns never populated.** render's EFFICIENCY block shows `-` for mean_s / mean_$ / mean_corr for ALL 6 models. assign.py's tiebreakers (mean_cost_usd, mean_time_s, step 4) have zero data.

**B4 — product-side capability grading is test-only.** `grade_refs` and `reconcile_with_real` have no non-test callers (`grep -rn` over /home/stack/code/charon). `grades_import.py` has no file reads at all — `SEED_PRIOR` is hardcoded; nothing ever feeds it real outcomes.

**B5 — review nudge overdue.** `model-scorecard.sh --due`: "review is DUE — 64 rows (+32 new)". `state/last-scorecard-review` = `2026-07-07  rows=32`.

**B6 — assign.py re-rank is advisory-only** (`fleet-droid.sh:385`), so B1 fails silently: dispatch falls back to the static tier chain and nobody sees that real-outcome ranking is dead.
