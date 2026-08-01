repo: charon-private
tier: strong
priority: 2
difficulty: 2
work_class: rig-meta
branch: feat/assign-dispatch-pick-fix
owns: fleet/capability/assign.py
depends_on:
dep-kind:
work_class_note: MONEY-adjacent — a wrong pick routes real work/spend to the wrong model.
note: |
  OBSERVED 2026-07-15: fleet/tests/assign-dispatch.test.sh is RED against fleet/capability/assign.py
  (3 of 6 cases fail, confirmed by running the test):
  - a1: with live real-outcome data present, the resolved chain should promote the real-outcome
    pick (modelB) to the FRONT (expected 'modelB,modelA,modelC'); assign.py leaves it unchanged
    ('modelA,modelB,modelC') — the real-outcome signal is not being applied to reorder the chain.
  - d1: ``assign.py --print-model`` (the machine-readable single-id contract other scripts parse)
    prints EMPTY instead of the picked model id 'modelB'.
  - e1: with ``--candidates`` restricting the offered set to {modelA, modelC}, the picked model
    escapes that set (prints empty / an id outside the candidates) instead of staying within it.
  b1/c1 (static-chain fallback when no live data, and when no candidate has any live evidence)
  already PASS — the fallback path is correct; only the real-outcome-driven pick path is broken.
accept: |
  fleet/tests/assign-dispatch.test.sh (already exists, do not rewrite it — the fix must make THIS
  test green): assign.py's real-outcome pick (a) leads the resolved candidate chain when live
  scorecard data favors a non-first candidate, (b) ``--print-model`` emits ONLY the picked model
  id (no extra text) and nothing when refused/no-data (matches existing PASSING d2), (c) the pick
  never returns an id outside an explicit ``--candidates`` set.
  FAIL-ON-REVERT: `bash fleet/tests/assign-dispatch.test.sh` — currently 3 passed/3 failed; this
  ticket is done when it reports 6/6 passed. Revert the fix -> back to 3 failed.
scope: |
  Correctness fix on the rig's model-dispatch picker (which real work/spend is routed to).
  Rig-only, no product change. The test file itself is NOT owned/rewritten by this ticket — only
  the SUT (assign.py) changes to satisfy the existing contract.
ds: Now — rig-only, disjoint from other open tickets (no owns collision found). MONEY-adjacent:
  flag for adversarial review before land (real work gets routed off a wrong pick today).
