repo: charon
tier: strong
difficulty: 1
work_class: refactor
branch: feat/capability-actuals-deadref-cleanup
owns: src/charon/decompose_sizing.py, tools/check_inert_code.py, tools/inert-code-disposition.json
depends_on:
dep-kind:
work_class_note: doc/tooling hygiene only — no behavior change.
note: |
  OBSERVED 2026-07-15: PR #160 (DEDUP-ACTUALS-DELETE, merged, "delete dead ActualsLedger/
  ActualRow module") deleted ``src/charon/capability/actuals.py`` and
  ``tests/test_actuals_ledger.py`` from origin/master (confirmed: file absent after
  ``git pull``). Three references to the now-deleted module survive:
  - src/charon/decompose_sizing.py:32,54 — docstring/comment prose naming
    ``capability.actuals``/``ActualsLedger`` as a still-pending calibration source.
  - tools/check_inert_code.py:13 — an example line in its own docstring naming
    ``capability/actuals.py::ActualsLedger`` as a worked example.
  - tools/inert-code-disposition.json:14,18 — whitelist entries for
    ``charon.capability.actuals.ActualRow`` / ``charon.capability.actuals.ActualsLedger`` that
    now name a module that doesn't exist.
accept: |
  Remove all three stale references: reword decompose_sizing.py's docstring/comment to drop the
  dead pointer (or replace with whatever DID replace the actuals-ledger calibration path, if one
  exists — do not invent one), replace check_inert_code.py's example with a still-live example,
  and delete the two dead whitelist entries from inert-code-disposition.json.
  FAIL-ON-REVERT: a grep-based test (or extend an existing check_inert_code selftest) asserting
  no `capability.actuals` / `ActualsLedger` / `ActualRow` string survives in
  decompose_sizing.py, check_inert_code.py, or inert-code-disposition.json. Revert any one
  cleanup -> the grep test fails.
scope: |
  Pure cleanup, no runtime behavior change. Product repo, difficulty 1. Low risk; safe to run
  concurrently with anything not touching these exact 3 files.
ds: Now — no owns collision found; trivial, no dependencies.
