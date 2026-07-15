repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/eval-derived-budgets
depends_on: EVAL-TAXONOMY-ALIGN, LEG-PREFLIGHT-CANARY
dep-kind: build
real-dep: LEG-PREFLIGHT-CANARY produces LEG-RANK.tsv (per-leg tok_s) that the token/tok_s budget-normalization half consumes; the p95 half can proceed without it, but the full ticket needs it.
serial_justified: the derivation module + its calibration data + the design-doc write are one cohesive change; budgets are meaningless split from the taxonomy they key on.
owns: fleet/benchmark/budget-derive.py, fleet/state/PREFLIGHT-DESIGN-V2.md, fleet/tests/budget-derive.test.sh
accept: |
  Review F8 (folds operator ask #1): the rung/latency budgets (3/6/10 min, 480/900s) are ARBITRARY round numbers
  contradicted by the observed 20s–538s spread (RFL-3 field jammed 497-499 vs the 480 ceiling). Replace with DERIVED
  budgets. Depends on EVAL-TAXONOMY-ALIGN (budgets are per canonical work_class).
  DO:
  - budget-derive.py: compute a budget per (work_class × difficulty) from the OBSERVED completion-time distribution of
    KNOWN-GOOD models (read model-scorecard.tsv time_s + dogfood-eval result-card wall_s). Budget = p95 of good-model
    completion + margin (state the rule). Normalize for leg speed: express the task budget in TOKENS (or expected
    output size), and derive the wall-clock ceiling per run as tokens / the leg's measured tok_s from R0 (LEG-RANK) —
    so a fast leg and a slow leg on the SAME task get fair, different wall-clocks instead of one flat number.
  - Write the derived budgets + the derivation rationale into PREFLIGHT-DESIGN-V2.md (replaces the arbitrary numbers).
    Feeds EVAL-LATENCY-GATE's DETAIN threshold and EVAL-PIPELINE's rungs.
  FAIL-ON-REVERT (fleet/tests/budget-derive.test.sh): given a fixture time distribution, the derived budget == p95+margin
  (revert the derivation → it returns the hardcoded 480 → test fails); a leg with 2x tok_s gets ~½ the wall-clock ceiling
  for the same token budget (proves normalization, not a flat number).
