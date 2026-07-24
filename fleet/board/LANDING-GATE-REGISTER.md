repo: charon-private
tier: economy
difficulty: 1
priority: 0
work_class: rig-meta
branch: feat/landing-gate-register
owns: fleet/tests/landing-plane-canary-registration.test.sh
real-dep: PLANE-CANARY-REGISTRY seeds the "landing" plane's registry row this ticket's test
  verifies, and creates fleet/plane-canary-registry.tsv itself (the file the test reads) — a
  genuine build prereq.
depends_on: PLANE-CANARY-REGISTRY
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 3 "P6 landing/merge-gate" spec +
  "PROPOSED TICKET LIST" row 9.
note: |
  PARTIAL plane (design doc Phase 3, #6) — fleet/checks/substrate-first-gate.sh +
  fleet/checks/gate-parity.sh already exist and already have their own fault-seed tests
  (fleet/checks/substrate-first-gate.test.sh, fleet/tests/gate-parity.test.sh) that already prove
  RED->GREEN. Per the design doc, this is a REGISTER-ONLY plane: no new build. Registry row
  already seeded (PLANE-CANARY-REGISTRY, plane=landing, canary_script=
  fleet/checks/substrate-first-gate.sh, dogfood_test=fleet/tests/substrate-first-gate.test.sh).
  This ticket's only genuine deliverable is a small reconciliation-coverage regression test that
  the registration ITSELF doesn't silently drift (e.g. if substrate-first-gate.sh or its test is
  ever renamed/moved without updating the registry row) — a real fail-on-revert test, not a
  no-op ticket. [[gates-must-actually-run]]
accept: |
  - fleet/tests/landing-plane-canary-registration.test.sh: asserts the "landing" row in
    fleet/plane-canary-registry.tsv resolves to canary_script + dogfood_test paths that (a)
    actually exist on disk, and (b) the dogfood_test, when run, exits 0 (proving
    substrate-first-gate.test.sh + gate-parity.test.sh are genuinely passing today, not just
    referenced). This is registered as the "landing" plane's own supplementary coverage.
  - fail-on-revert test: rename/move fleet/checks/substrate-first-gate.sh in a scratch fixture
    copy of the registry (not touching the real file) so the registry row no longer resolves ->
    assert this test goes RED ("landing row unresolvable"); revert -> GREEN.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — this is coverage-proof for
    the landing/merge-gate plane (substrate-first-gate.sh + gate-parity.sh, the gates that refuse
    a bad land); manager gates, PR does NOT merge on the builder's self-report.
scope: |
  Registration-coverage confirmation only. Does NOT modify substrate-first-gate.sh or
  gate-parity.sh (both reused exactly as-is, both already fault-seed-proven by their own
  existing tests) and does not add new landing-gate logic.
ds: |
  ## Dependencies & sequence
  depends_on PLANE-CANARY-REGISTRY only (the row it verifies is seeded there). Disjoint owns
  from every other gap-canary ticket in this wave — parallelizable.
