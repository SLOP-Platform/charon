# EVAL-CONTROL-GATE-FIX — review log fragment

**Ticket:** EVAL-CONTROL-GATE-FIX (tier: strong, work_class: bugfix, priority: 0)
**Branch:** `fix/eval-control-gate-unsatisfiable`
**Audited root defect:** the EVAL-PROMOTION-GATE control-panel gate
(`grades.py:651-654` product path; here `split_ok` in
`src/charon/capability/grades.py`) required a per-ref MUST-PASS control
`strong-control` with ≥3 rows, but `strong-control` had **0 rows in the entire
ledger** and control models never run against real ticket refs → `split_ok`
was ALWAYS `False` → EVERY live row excluded → **0 grades for all 6 models**.
The gate was STRUCTURALLY UNSATISFIABLE on the live lane. [[charon-eval-system-
under-repair]] [[gates-must-actually-run]]

## Change

Implemented the **documented no-control→admit fallback** the gate's docstring
already promised (but the old code did a hard `continue` instead). The fix
admits a ref's live rows when ZERO control rows exist for it at all — flagged
`provisional`/`uncontrolled` (the gate's integrity intent is preserved: the
row did NOT pass real control-panel validation). Where controls DO exist, the
≥3 threshold and the partial-controls exclusion are unchanged.

**Files (single claim, no outside-`owns:` edits):**
- `src/charon/capability/grades.py` — `split_ok` no-control→admit branch +
  `_is_fallback_admit` detector + `grade_refs` flags fallback admits; added
  public `MIN_CONTROL_COUNT` alias (resolved an `__all__` `F822` ruff error).
- `tests/test_control_gate_fix.py` — 10 fail-on-revert tests pinning the
  fallback (no-control ref admits flagged not dropped; 6 live models grade;
  ≥3 controls pass clean; partial controls still exclude; failed controls
  don't admit fallback; gate-disabled stays clean; mixed-ref run; filter
  helpers; `summarize` reports provisional admits not excluded).

## Accept / chose this design over alternatives

- **Alternative considered — disable the gate.** Rejected by the ticket spec:
  *preserve the control-panel integrity where controls DO exist; only add the
  missing no-control fallback.* With the fallback the gate's presence still
  bites a ref that has partial (1–2) controls or a failed `strong-control`
  row (see `test_partial_controls_below_threshold_still_exclude` and
  `test_failed_control_rows_do_not_count_toward_threshold`).
- **Alternative considered — seed `strong-control` rows.** Out of scope here
  (tracked as separate follow-up `MODEL-GRADE-PRESEED`): the fix unblocks
  grading NOW without coupling to a cold-start seeding land. Seeding is
  *still wanted* to lift provisional rows to clean; it just isn't the blocker.

## Verification (gate kept green)

- `PYTHONPATH=src python3 -m pytest -q` → full suite **2275 passed, 3 skipped,
  1 xfailed, 1 xpassed** (plus the 10 new tests); the targeted file alone → 10
  passed.
- `ruff check` → all checks passed (after the `MIN_CONTROL_COUNT` alias fix
  for `F822` undefined name in `__all__`).
- `mypy src tests` → no issues in the two changed files.
- `tools/check_boundary.py src` → boundary OK (no host-project references).
- `tools/check_version.py` → reports stale local editable metadata
  (`pyproject=0.6.0 installed=0.3.1`, "Not failing outside CI"); did NOT run
  `pip install -e` (forbidden by the launcher rules).

## Completion self-check

- [x] `grades.py` returns >0 grades on the live lane — a no-control ref now
  produces a flagged grade (`test_no_control_ref_admits_flagged_not_dropped`,
  `test_no_control_admits_all_six_live_models_flagged`).
- [x] Fail-on-revert: re-introducing the hard `continue` (no-control ref →
  dropped) fails `test_no_control_ref_admits_flagged_not_dropped` and
  `test_no_control_admits_all_six_live_models_flagged`.
- [x] Gate integrity preserved where controls exist (≥3 passes clean;
  partial/failed controls still exclude).
- [x] Scope self-check: only `src/charon/capability/grades.py` + this
  fragment + `tests/test_control_gate_fix.py` changed (all in `owns:`).