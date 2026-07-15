repo: charon-private
tier: strong
difficulty: 4
work_class: ci-infra
branch: feat/ssot-drift-gate
depends_on: EVAL-TAXONOMY-ALIGN
real-dep: EVAL-TAXONOMY-ALIGN — this gate ENFORCES the taxonomy SSOT that TAXONOMY-ALIGN defines; it cannot drift-check a canonical that does not yet exist.
owns: fleet/checks/msot-drift.sh, fleet/tests/msot-drift.test.sh, fleet/state/SSOT-REGISTRY.tsv
accept: |
  ENFORCE the SSOTs we already declared (see fleet/state/MSOT-BLAST-RADIUS-AUDIT.md: 9 MSOTs, 4 DIVERGED). This is the
  "one framework wrapper for all single-sources-of-truth, NOT a god-file" the operator asked for. TOOL-FIRST reference already
  exists: the audit flags pricing_limits_checker.py (canonical-file + reader + drift-diff) — GENERALIZE it, don't build new.
  DO:
  - fleet/state/SSOT-REGISTRY.tsv: one row per canonical fact -> its ONE owning file + the reader files that must agree.
  - fleet/checks/msot-drift.sh: FAIL LOUD (non-zero, no pipe-mask) if any reader diverges from its owning file. Converge the
    diverged MSOTs it does NOT hand to another ticket: tier->model membership (model_catalog.py tier_hint vs tier-models.tsv),
    model-id normalization (detect_model.py vs proxy._normalize_model_id), board-state vs GitHub PR-state.
  - Taxonomy convergence is OWNED by EVAL-TAXONOMY-ALIGN (hence the dependency); this gate ENFORCES it, never redefines it.
  FAIL-ON-REVERT (fleet/tests/msot-drift.test.sh): introduce a deliberate reader divergence -> gate RED; revert the gate -> passes -> test fails.

reuse: per-fact SSOTs already ticketed (REPO-DECL-CENTRAL = repo paths; DEDUP-GRAPHS-LEDGERS = actuals/graphs) — this gate COMPOSES them via SSOT-REGISTRY.tsv, it does NOT re-own their facts. TOOL-FIRST base = PRICING-LIMITS-CHECKER pattern.
