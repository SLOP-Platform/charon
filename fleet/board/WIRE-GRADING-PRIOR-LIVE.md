repo: charon
tier: frontier
priority: 0
difficulty: 3
work_class: money-path
branch: feat/wire-grading-prior-live
gateway-py-handoff: |
  2026-07-26 — SW-STATIC-LEGS-RETIRE added ~11 lines to src/charon/gateway.py (load_config, approx
  :229-234) WITHOUT owning that file. Operator decision 31(a): landed anyway because the change is
  ADDITIVE (an explicit operator-intent filter for `enabled: false`, moved out of the routing-policy
  compiler where it was a silent membership drop) and does not rewrite anything this ticket touches.
  ROOT CAUSE: the SW-STATIC-LEGS-RETIRE brief forbade proxy.py and forwarder.py by name but omitted
  gateway.py, so the session had no stop-check to hit. Manager error, not session error.
  ACTION FOR THIS TICKET: rebase onto the landed change; do NOT assume gateway.py matches the version
  you started from. If the filter placement conflicts with your work, it is REVERSIBLE — the 11 lines
  are self-contained in load_config and the behaviour they preserve (/charon/disable honouring
  enabled: false) has test coverage in tests/test_static_legs_retired.py.
owns: src/charon/gateway.py, tests/test_grading_prior_wire.py
depends_on: GATEWAY-NONTOKEN-METERING
real-dep: GATEWAY-NONTOKEN-METERING — merge-order only: both edit the gateway.py god-file (contended); sequence after the in-flight metering PR to avoid a land conflict. dep-kind: build.
source: SG-readiness review 2026-07-24 — the industry-benchmark preflight PRE-GRADE + real-work update
  is BUILT (grades_import.py, #186) but INERT: the live gateway builds a bare empty CapabilityMatrix
  (gateway.py:493), seed_matrix() is imported NOWHERE in src/, and reconcile_with_real() has ZERO callers.
  So SG routes with no pre-grade and no real-work update — a direct hit on "SG does good work."
note: |
  Wire the two ALREADY-BUILT+TESTED halves of grades_import.py into the LIVE gateway [[charon-silent-downgrade-leak]]:
  1. SEED: at gateway.py:493 call seed_matrix() (the cold-start external-benchmark prior — curated
     aider-polyglot/LMArena/models.dev table, decaying weight 0.5, confidence<1.0) instead of the bare
     CapabilityMatrix(). Day-1 the router then has an industry-grounded prior.
  2. UPDATE: connect the real-work outcome path to reconcile_with_real() (grades_import.py:277 — real
     outcome REPLACES the prior, never blends) so grades improve as models do real work. The real-outcome
     LOOP is unblocked by EVAL-CONTROL-GATE-FIX (#191) — coordinate.
  This is the SG-quality core: route to trusted, well-graded models from day 1, self-correcting on real work.
accept: |
  - gateway.py:493 seeds the matrix from seed_matrix() (prior loaded at startup; assert non-empty matrix).
  - real-work outcomes flow into reconcile_with_real() (find/instrument the forwarder outcome path);
    a graded model's live success/failure updates its grade (prior -> real override).
  - fail-on-revert test: revert the seed wiring -> matrix empty -> a known-weak model is no longer
    pre-filtered -> RED; revert the update wiring -> real outcome does not change the grade -> RED.
  - ADVERSARIAL REVIEW (reviewer != builder) — money/routing path; a mis-wired grade routes work wrong.
scope: |
  WIRING only of the existing grades_import halves into gateway.py + the outcome path. Does NOT rebuild
  grades_import (already merged #186) or change the curated benchmark table. Composes.
ds: |
  ## Dependencies & sequence
  P0 (top SG-readiness "do good work" gap). Coordinate with EVAL-CONTROL-GATE-FIX (#191, unblocks the
  real-outcome loop). Both halves are written+tested; this is the un-orphaning wire.
