repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/eval-latency-gate
depends_on:
serial_justified: F1 (marker) and F4 (gate on the marker) are one cause→effect change across charon-run.sh + dogfood-eval.sh + the attribution lib; they must land together or the gate reads a marker that doesn't exist.
owns: fleet/charon-run.sh, fleet/benchmark/dogfood-eval.sh, fleet/benchmark/lib/dogfood-attribution.sh, fleet/tests/dogfood-latency-gate.test.sh
accept: |
  RESTORE latency-is-a-failure-class (review F1 + F4 + F-attr-2; see fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md).
  Today: dogfood-attribution.sh:41-46 greps for TIMEOUT strings charon-run NEVER emits; is_infra_fault treats rc=124
  as infra → every hang becomes 'provider-throttled'→RETRY, and dogfood-eval computes elapsed>=budget (dogfood-eval.sh:222)
  but NEVER gates on it (glm-5.2 RFL-3 ran 499s>480 → REVIEW-READY → eligible live MERGE). The budget is decorative.
  DO:
  - charon-run.sh: when the run is killed by the `timeout` wrapper (RC==124), emit a SELF-DESCRIBING marker to the
    out_log distinguishing (a) genuine too-slow (model streamed but didn't finish) from (b) hung/no-output leg. Make
    the exact string match what dogfood-attribution.sh greps (fix BOTH sides so the strings agree — the dead-code bug).
  - dogfood-attribution.sh: the rc=124 branches (41-46) must fire on the real marker; a too-slow with healthy leg →
    `too-slow`, a no-output hang → leg-fault (park, not model-blame). Fix any other mislabels noted in F-attr-2.
  - dogfood-eval.sh: BEFORE the REVIEW-READY branch (~line 240), add the wall-clock DETAIN — elapsed>=LATENCY_BUDGET_S
    AND attribution=too-slow → overall=DETAIN(latency) (finalize as BLOCK), NOT REVIEW-READY. A leg-fault timeout still
    parks the leg (never a model BLOCK). Keep the finalize/capture path from double-logging (F-finalize note).
  FAIL-ON-REVERT (fleet/tests/dogfood-latency-gate.test.sh, hermetic, stub opencode): a run that streams past budget →
  DETAIN(latency)/BLOCK, NOT REVIEW-READY (revert the gate → it passes → test fails); a no-output rc=124 hang →
  leg-fault (NOT a model BLOCK); a within-budget clean run → REVIEW-READY unchanged. Assert the charon-run marker string
  is exactly what the attribution grep matches (revert either side → the dead-code bug returns → test fails).
