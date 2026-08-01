repo: charon-private
tier: strong
difficulty: 2
priority: 0
work_class: rig-meta
branch: feat/config-ssot-canary-register
owns: fleet/tests/config-ssot-gate.test.sh
real-dep: PLANE-CANARY-REGISTRY seeds the "config-ssot" plane's registry row at the exact
  fleet/tests/config-ssot-gate.test.sh path this ticket owns, and its reconciliation leg is what
  this dogfood_test must satisfy to register as GREEN — a genuine build prereq.
depends_on: PLANE-CANARY-REGISTRY
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 3 "P8 config/SSOT-drift" spec +
  "PROPOSED TICKET LIST" row 8.
note: |
  PARTIAL plane (design doc Phase 3, #8) — fleet/checks/config-ssot-gate.sh already exists and
  already runs (advisory, via fleet/checks/gate-creation-standard.sh's BASELINE_CHECKS) but has
  NO fault-seed test proving it actually catches a real divergence. Promote it from
  advisory-untested to a REGISTERED, PROVEN plane canary — no new checker (reuse
  config-ssot-gate.sh as-is), align with fleet/board/SSOT-DRIFT-GATE.md's msot-drift.sh (a
  disjoint, complementary drift check — do not merge the two).
accept: |
  - fleet/tests/config-ssot-gate.test.sh: seed a manifest/reader divergence (e.g. a provider
    present in the git-tracked manifest but absent from a fixture "live" config reader output, or
    a base_url/key_env mismatch between the two) -> assert fleet/checks/config-ssot-gate.sh
    (unmodified, reused as-is) exits non-zero / reports the divergence. Correct the fixture ->
    GREEN. This IS the "config-ssot" plane's dogfood_test (registry row already seeded by
    PLANE-CANARY-REGISTRY at this exact path) — no separate registration edit needed.
  - fail-on-revert test: revert the seeded divergence fix -> RED again, proving the assertion
    isn't a tautology that passes regardless of manifest state.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — proves the config-SSOT gate
    (a security/drift-relevant check: provider base_url/key_env mismatches are exactly the shape
    the egress-key exfil class rides) actually catches a real divergence. Manager gates, PR does
    NOT merge on the builder's self-report.
scope: |
  Fault-seed test + plane registration only. Does not modify fleet/checks/config-ssot-gate.sh
  (reused as-is, "no new checker" per the design doc) and does not touch
  fleet/checks/gate-creation-standard.sh's advisory BASELINE_CHECKS wiring (a separate promotion-
  to-blocking question, out of scope here — this ticket proves the check WORKS, not that it
  blocks landing).
ds: |
  ## Dependencies & sequence
  depends_on PLANE-CANARY-REGISTRY only (registry row already seeded at this exact path).
  Disjoint owns from every other gap-canary ticket in this wave — parallelizable.
