repo: charon-private
tier: frontier
difficulty: 4
work_class: rig-meta
branch: feat/gate-creation-standardize
serial_justified: One cohesive meta-process (ledger + creation-standard + meta-gate) around gate quality; splitting fragments the standard.
owns: fleet/state/GATE-GAP-LEDGER.tsv, fleet/checks/gate-creation-standard.sh, fleet/GATE-CREATION-STANDARD.md, fleet/tests/test_gate_creation_standard.sh
depends_on:
note: |
  OPERATOR DIRECTIVE (cere-junda handoff): standardize HOW we create gates so we eliminate issues at a
  CLASS level, driven by the history of what green gates MISSED. Green-is-not-proof [[green-is-not-proof]]
  is the doctrine; this makes it a mechanized, self-updating process.
  RESEARCH FIRST: enumerate every case where a GREEN gate failed to detect a real issue — from this
  session (DELETE-STATIC-RANK gate-green but deploy money-exposure; the single-provider "stiffness" class
  with NO gate; the FOREMAN-WIRE commit that CLAIMED wiring the diff didn't contain = self-report-lie;
  check_catalog_case_quant built but wired into no gate; inert-gate non-determinism; config-siloing with no
  drift gate) + the review-logs (docs/review-log/*, fleet/state/*AUDIT*, prior handoffs). Extract the CLASS
  behind each miss, not the instance.
accept: |
  ## 1. GATE-GAP-LEDGER.tsv (durable, append-only, git-tracked)
  Row per green-gate-miss: date | gate(s) that passed | issue that shipped | ROOT CLASS | the gate
  improvement that would have caught it | status. Seed it from the RESEARCH above (historical misses).
  MUST be appended EVERY time a green gate later fails to detect an issue (wire a one-liner into the
  land/postmortem path + document the append step).
  ## 2. GATE-CREATION-STANDARD.md — the standardized checklist a NEW gate MUST satisfy
  Derived from the ledger's recurring classes + green-is-not-proof: red-proofed (demonstrably goes RED on a
  real failure), non-vacuous (can't pass on zero items), un-gamed (node-set can't silently shrink), not-inert
  (exercises WIRED production=test path), fail-loud (non-zero exit, no pipe-mask), + any class the ledger surfaces.
  ## 3. gate-creation-standard.sh — a META-GATE: a new/changed gate (a new check in gates.json / gate_runner /
  fleet/checks) must carry evidence it meets the STANDARD (a red-proof test) or RED. Wire advisory into
  validate_board first. fail-on-revert test. Compose existing lenses (anti-accretion) — do NOT mint per-instance scripts.
  ## 4. Verify the seeded ledger classes each map to a concrete standard item (traceability).
