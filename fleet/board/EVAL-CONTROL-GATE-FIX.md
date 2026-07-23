repo: charon-private
tier: strong
difficulty: 3
work_class: bugfix
priority: 0
branch: fix/eval-control-gate-unsatisfiable
depends_on:
owns: fleet/state/EVAL-CONTROL-GATE-FIX.md
work_class_note: |
  ROOT DEFECT of "grades.py returns 0 grades" (ranking-pipeline audit 2026-07-23). The EVAL-PROMOTION-GATE
  control-panel gate (product `src/charon/capability/grades.py:651-654`, require_control_panel=True) requires
  a per-ref MUST-PASS control `strong-control` with ≥3 rows — but `strong-control` has **0 rows in the entire
  ledger** and control models never run against real ticket refs, so split_ok is ALWAYS False and EVERY live
  row is excluded → 0 grades for all 6 models (they DO have real live rows if the gate is off). The gate is
  STRUCTURALLY UNSATISFIABLE on the live lane. [[charon-eval-system-under-repair]] [[gates-must-actually-run]]
accept: |
  Make the promotion gate satisfiable on the live lane WITHOUT weakening its integrity intent, so real live
  rows produce grades. The audit found the fix is ALREADY DESIGNED but not coded:
  1. **Implement the documented "no-control → admit" fallback** — grades.py:651-654 docstring PROMISES a
     no-control-present → admit-with-caveat path, but the code does a hard `continue` instead. Implement the
     fallback the docstring already specifies (admit the live row, flagged provisional/uncontrolled), so a
     ref that has no seeded control doesn't silently drop every model.
  2. Verify: run the grading module on the live ledger → it now returns grades for the 6 live models
     (provisional where uncontrolled), not 0. Fail-on-revert test: a live row with no matching control MUST
     produce a (flagged) grade, not be excluded.
  3. Do NOT just disable the gate — preserve the control-panel integrity where controls DO exist; only add
     the missing no-control fallback. Note whether seeding `strong-control` rows is still wanted as a
     separate follow-up (it is, but this fix unblocks grading now).
  COMPLETION SELF-CHECK: if grades.py still returns 0 on the live ledger, INCOMPLETE.
scope: |
  Fix the structurally-unsatisfiable EVAL-PROMOTION-GATE control-panel gate (implement the documented
  no-control→admit fallback) so live rows produce grades instead of 0. The #1 unblock for real ranking.
ds: |
  ## Dependencies & sequence
  - depends_on: none. owns the fix to grades.py's gate logic (product code — coordinate the cross-repo land).
  - unblocks: real per-model ranking; pairs with MODEL-GRADE-PRESEED (day-1 prior) — this fixes the LOOP,
    pre-seed fixes the COLD-START. Both wanted.
