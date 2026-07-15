repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/eval-promotion-gate
depends_on: EVAL-TAXONOMY-ALIGN, EVAL-GRADER-PROVISION, EVAL-PIPELINE-CONSOLIDATE
dep-kind: build
serial_justified: F10 (synthetic promote gate) and F13 (live-row gate) are the SAME control-panel discrimination rule applied to both write paths; they must share one implementation or the live path keeps its no-gate hole.
owns: fleet/benchmark/promote.py, fleet/capability/grades.py, fleet/tests/promotion-gate.test.sh
accept: |
  Review F10 + F13: promotion/trust has two holes. F10 — promote.py:144-163 promotes on between-model SPREAD>=15 (per-model
  MEAN, K>=2), which measures whether two models DIFFER, not whether the task separates GOOD from BAD; two mediocre N=1
  models promote a non-diagnostic unit; a real {100,0} split (mean 50, spread 0) is wrongly rejected. F13 —
  finalize/live rows write stage=active and grades.py trusts them IMMEDIATELY (grades.py:176,198,350), so a single (F4)
  budget-breaching run shifts the pick with no discrimination gate — the provisional→active care taken for synthetic
  units does NOT exist on the live path.
  DO:
  - ONE control-panel discrimination gate (from EVAL-GRADER-PROVISION's controls): a task/unit counts toward a grade
    ONLY IF the designated MUST-PASS control PASSES it AND the MUST-FAIL control FAILS it, N>=3 each (PREFLIGHT-DESIGN-V2
    §3). promote.py keys on THIS split, not raw spread (keep spread as a secondary sanity check only). Raise K.
  - Apply the SAME gate to the LIVE path: a source=live row for a task counts only after that task has passed the control
    split (or require N>=MIN_N + control split before any live row for that task is admitted to a grade). Removes the
    "single live run shifts the pick" hole. Coordinate with grades.py's admission (shared surface with EVAL-TAXONOMY-ALIGN
    — rebase onto it, never concurrent).
  FAIL-ON-REVERT (fleet/tests/promotion-gate.test.sh): a unit where the MUST-FAIL control also passes is NOT promoted
  (revert → spread-only promotes it → test fails); a {100,0} real-split unit (spread 0 by mean) IS promoted via the
  control split; a live task with no control split does NOT count toward a grade until it earns one.
