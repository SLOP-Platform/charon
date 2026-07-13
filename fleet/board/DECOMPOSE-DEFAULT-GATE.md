tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/decompose-default-gate
repo: charon
depends_on: WORK-DECOMPOSER
real-dep: WORK-DECOMPOSER — this gate INVOKES the decomposer engine (DEC-PLANNER + AST-WRAP + emit) at intake; it cannot exist until that engine lands. True build prereq, not merge-order.
owns: src/charon/intake.py, tests/test_decompose_default_gate.py
accept: |
  Make decomposition the DEFAULT + MECHANIZED way work is created for Charon Gateway — so a broad/god-ticket can
  NEVER enter the board un-decomposed again (no more manual hand-splitting like 2026-07-13).
  DO: at INTAKE (new work item created), a work item whose change-surface exceeds a SINGLE-DOMAIN threshold
  (use the AST blast-radius from DEC-AST-WRAP: >1 module / crosses a wiring boundary / owns would span disjoint
  independence groups) is AUTOMATICALLY run through the decomposer (DEC-PLANNER) to emit disjoint single-domain
  sub-tickets, AND the gate REFUSES to admit the un-decomposed parent (fail-loud, actionable message) — reusing
  the existing `intake.assert_disjoint_waves` hard check but TRIGGERED AT CREATION, not just at plan time.
  Escape hatch: an explicit `single-domain: true` (or `no-decompose: <reason>`) on a ticket bypasses, recorded
  so it can't hide (like the detention override).
  FAIL-ON-REVERT (tests/test_decompose_default_gate.py): a fixture broad ticket (crosses 2 modules) submitted at
  intake is REJECTED unless decomposed; a genuinely single-domain ticket passes untouched; the bypass flag admits
  with the reason recorded. Revert the gate → the broad ticket is admitted un-decomposed → RED.
  GREEN-IS-NOT-PROOF: prove the gate fires on the REAL intake path (production==test path), not a side function.
scope: |
  The capstone that makes WORK-DECOMPOSER the DEFAULT work-creation path for Charon Gateway (operator directive
  2026-07-13: "this should be the default way work gets created"). [[decomposed-by-design-not-reactive]]
  [[charon-work-composition-intelligence]] [[charon-work-engine-vision]]
ds: |
  depends_on: WORK-DECOMPOSER (the engine it invokes). Sequence AFTER the DEC-* chunks land. co-owns intake.py
  with DEC-EMIT-PARENT (parent field) — sequence after that merges. Adversarial review (blast-radius: it gates ALL
  work creation).
note: capstone — auto-decompose + block-un-decomposed at intake, so manual decomposition never recurs.
