# EVAL-PROMOTION-GATE — Review Log

## Ticket
EVAL-PROMOTION-GATE (review F10 + F13): one control-panel discrimination
gate applied to BOTH write paths — the synthetic provisional-unit path
(benchmark/promote.py) and the live-row admission path (capability/
grades.py). The v1 spread-only rule (between-model spread >= 15 with
K >= 2) measured whether two models DIFFER, not whether the task
separates GOOD from BAD. The fix: a MUST-PASS / MUST-FAIL control
panel (PREFLIGHT-DESIGN-V2 §3 — `deepseek-v4-flash` MUST-FAIL control
+ a strong MUST-PASS control, N >= 3 each) decides trust; the v1
spread is retained as a secondary sanity check only. The same gate
runs on the live path so a single budget-breaching live run can't
shift the pick anymore (F13 hole).

## The problems (F10 + F13, restated)
F10 — promote.py:144-163 promoted on between-model SPREAD >= 15
(per-model MEAN, K >= 2), which measured whether two models DIFFER,
not whether the task separates GOOD from BAD. Two mediocre N=1 models
differing by noise (each scoring 60) got spread = 0 and were
(correctly) rejected — but a real {100, 0} per-run split (mean 50
each, spread 0 by mean) was wrongly rejected as saturated; meanwhile
two mediocre N=1 models at {60, 80} promoted a non-diagnostic unit.
The v1 rule also has K = 2 (too weak to distinguish signal from a
coin flip).

F13 — `finalize_live_capture` enqueues `--stage active` (dogfood-eval.sh:155)
and grades.py trusted `source=live` + `stage=active` immediately
(grades.py:176, 198, 350). So a single dogfood run moved the
capability grade the moment it landed. Combined with F4
(budget-violating clean run injects a MERGE score=100), this shifted
the pick with no discrimination gate. The provisional -> active
care taken for synthetic units (F10) did NOT exist on the live
path.

## What was done (files owned by this ticket)
- `fleet/benchmark/promote.py` — the v2 control-panel gate
  (`control_panel_split` + `evaluate_gate_v2`) keys on the per-unit
  MUST-PASS / MUST-FAIL control split (CONTROL_N = 3,
  MUST_PASS_MIN = 80, MUST_FAIL_MAX = 20, defaults mirror
  PREFLIGHT-DESIGN-V2 §3 and item-bank/manifest.tsv's calibration
  anchor columns). The v1 (bool, str) `evaluate_gate` signature is
  preserved as a thin wrapper around `evaluate_gate_v2` so legacy
  callers (capability/selftest.py + benchmark/test-quality-gate.py)
  keep working unchanged. Backward-compat: when a unit has no rows
  on EITHER control (a pre-v2 unit that was promoted under the v1
  protocol and has never been re-run on the controls), the gate
  falls back to the v1 spread check — the FAIL-ON-REVERT test
  documents this as "v1 fallback, no control data" in the dry-run
  reason. units.tsv is now a 6-col schema (adds `control_pass` /
  `control_fail` columns with sane defaults
  `strong-control` / `deepseek-v4-flash`); save_units back-fills
  defaults so a 4-col legacy file round-trips cleanly.

- `fleet/capability/grades.py` — applies the SAME control-panel gate
  to the live path (F13 fix). `ScorecardGradesProvider._control_panel_for(ref)`
  computes the per-ref control split (cached per-provider for
  _rows_for efficiency); `_rows_for(..., require_control_panel=True)`
  (the new default) excludes a `source=live` row whose `ref` has no
  passing control split. `require_control_panel=False` is the
  backward-compat path for analysis / smoke tooling that wants to
  see un-controlled rows (the "do we have a control row at all yet?"
  diagnostic). The control-panel constants
  (`CONTROL_PASS_MODEL = "strong-control"`,
  `CONTROL_FAIL_MODEL = "deepseek-v4-flash"`,
  `CONTROL_N = 3`, `MUST_PASS_MIN = 80`, `MUST_FAIL_MAX = 20`)
  mirror promote.py's, and `VERDICT_SCORE_FROM_GATE` (with
  `VERDICT_SCORE` as the verdict-only fallback) resolves a row's
  non-numeric score for the per-control mean calculation. The score
  column takes precedence when numeric (the OOB grader fills it in
  with a value when it has one; verdict+gate fallback handles the
  gate=pass+verdict=FIXES partial-credit bucket the dogfood-eval
  path produces).

- `fleet/tests/promotion-gate.test.sh` — the FAIL-ON-REVERT test.
  Four hermetic scenarios drive the REAL promote.py + REAL
  grades.py (not reimplemented) against fixture scorecards / units
  in a mktemp dir; a revert on EITHER path flips the corresponding
  scenario RED. Stage 1 (a): broken MUST-FAIL is NOT promoted.
  Stage 2 (b): a clean {100, 0} per-run split IS promoted via the
  control split. Stage 3 (c): F13 — a live task with no control
  split does NOT count toward a grade (and
  `require_control_panel=False` re-admits the row, the analysis-
  path backstop). Stage 4 (d): a unit with a clean control split
  IS promoted even when the field is narrow (the secondary spread
  check is a backstop, not the primary gate).

## What was NOT done (out of `owns:`)
- `fleet/capability/selftest.py` (60+ assertions) and
  `fleet/capability/testdata/scorecard-fixture.tsv` (its hand-crafted
  fixture) assert the PRE-F13 contract — they don't include
  control-panel rows for the refs they exercise, so the F13 gate
  (on by default per the ticket's intent) makes the selftest
  return None for every grade and the 60+ assertions turn RED.
  This is INTENTIONAL behavior, not a regression: the F13 hole
  the ticket explicitly fixes IS "a single live run shifts the
  pick" — the old selftest cannot exercise that hole because its
  fixture predates the control-panel protocol. A future ticket
  (likely a follow-up EVAL-* reconciliation) should add
  control-panel rows to the selftest fixture and update the
  assertions; that's its owns, not this one.
- The pytest gate (75 tests, the actual join-prompt gate) is GREEN.
  The selftest.py failure is OUTSIDE that gate.
- The product-side `assign.py` consumer does not need changes
  (it calls `grades.grade()` which uses `_rows_for()` with the
  new defaults). The control-panel gate is on by default; no
  consumer needs to opt in.
- The OOB grader substrate (grader-daemon.py, bench-grader user,
  $KEYS/preflight/) is unchanged. The item-bank runner's
  `_enqueue_capture` (which writes source=live rows from the
  control-aware pipeline) is unchanged. The control-panel gate
  CONSUMES the control rows those paths already write.

## Coordination with sibling tickets
- **EVAL-TAXONOMY-ALIGN** (merged dep, owns `fleet/capability/grades.py`
  in part): this ticket rebases onto it. The control-panel gate
  operates on the per-ref scorecard data TAXONOMY-ALIGN's
  `_canonical_of()` resolves; the `work_class` query path is
  untouched. The selftest.py selftest being affected by the F13
  gate is an unavoidable cross-ticket impact: TAXONOMY-ALIGN
  added the canonical-vocabulary allow-list, and this ticket adds
  the control-panel allow-list on top. The next EVAL-* ticket
  should add control rows to the selftest fixture as a
  TAXONOMY/CONTROL reconciliation.
- **EVAL-GRADER-PROVISION** (merged dep, owns the OOB grader
  substrate): the controls this ticket relies on
  (`strong-control`, `deepseek-v4-flash`) are exactly the ids
  GRADER-PROVISION's `bench-grader` substrate is configured to
  grade. The control-panel gate consumes those rows; the
  substrate is unchanged.
- **EVAL-PIPELINE-CONSOLIDATE** (merged dep, owns the adaptive
  item-bank runner): the runner's `_enqueue_capture` already
  writes a single source=live row per (model, work_class) with
  the control rows pre-collected (the runner climbs the per-skill
  difficulty ladder starting with the MUST-PASS control and
  marks the unit saturated when the MUST-FAIL control fails it).
  This ticket's F13 gate validates the runner's output: a live
  row produced by the runner always has a measured control split
  (the runner placed the controls first), so the gate admits
  runner-produced rows. Pre-runner legacy rows (dogfood-eval
  source=live rows from before EVAL-PIPELINE-CONSOLIDATE landed)
  are still excluded — which is correct: those rows had no
  control evidence by construction.

## Known caveats / open follow-ups
- The control-panel gate applies per-`ref` (task id), not per-
  work_class. A unit that is part of a task and shares a `ref`
  with other units gets a single control-panel verdict. This is
  intentional (the F13 hole is "a single live run shifts the
  pick"; gating on the per-ref run is the minimal hole-closer)
  but a future ticket may refine to per-(ref, work_class) if
  evaluation traffic warrants.
- The `VERDICT_SCORE_FROM_GATE` table assumes a single canonical
  mapping. Edge cases (gate=pending, gate=skip, custom gates)
  fall back to `VERDICT_SCORE` and then to None (excluded from
  the per-control mean). The OOB grader contract
  (grader-daemon.py) is the only writer of these cells; the
  contract is "verdict in {MERGE, FIXES, BLOCK} and gate in
  {pass, fail}", so the table covers all production cases.
- The selftest.py failure (60+ assertions RED) is the largest
  visible side effect of this ticket and is OUTSIDE the pytest
  gate. The launcher should mention it in the PR description so
  the reviewer knows it's an intentional contract change, not a
  regression.
