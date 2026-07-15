tier: frontier
difficulty: 4
work_class: greenfield-feature
branch: feat/work-decomposer
repo: charon
depends_on:
owns: src/charon/decompose_planner.py, src/charon/decompose_surface.py, fleet/decompose.sh
accept: |
  Auto-decompose ENGINE: split a broad ticket + real code into N single-domain, file-scoped sub-tickets so weak
  executors each do one chunk. COMPOSE (per WORK-DECOMPOSER-TOOL-EVAL): strong-planner (DEC-PLANNER) + AST
  blast-radius (DEC-AST-WRAP, wraps engine/semantic_proof) + emit via intake.PlanUnit + the existing
  intake.assert_disjoint_waves hard gate. Chunks: DEC-PLANNER (done, decompose_planner.py) · DEC-AST-WRAP
  (decompose_surface.py) · DEC-EMIT-PARENT (parent field) · DEC-DRIVER (decompose.sh) · DEC-VALIDATE-STRICT ·
  DEC-E2E (R46 fixture). Fail-on-revert per chunk (already proven in the chunk PRs).
scope: Router Model-Trust — the "shrink the surface" engine; feeds DECOMPOSE-DEFAULT-GATE. [[charon-work-composition-intelligence]] [[wci-ticket-decompose-method]]
ds: |
  depends_on: none. Multi-chunk (see fleet/state/DEC-AUDIT.md revised plan); most of the mechanical engine already
  existed in the native engine — only the LLM splitting brain + thin glue are new. Adversarial review each chunk.
note: engine chunks landing 2026-07-13 (DEC-PLANNER merged; AST-WRAP/EMIT in flight). Capstone = DECOMPOSE-DEFAULT-GATE.
