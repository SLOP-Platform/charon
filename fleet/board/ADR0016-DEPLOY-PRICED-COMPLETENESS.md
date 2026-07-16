repo: charon
tier: strong
difficulty: 3
work_class: money-path
branch: feat/adr0016-priced-completeness-guard
owns: src/charon/routing_policy/cost_rank.py, tests/test_priced_completeness.py
serial_justified: One deploy-safety guard on the cost-selection path + its test; cohesive money-path change.
depends_on:
note: |
  ADVERSARIAL REVIEW FINDING (adversarial-delete-static-rank.md, this session) — MONEY EXPOSURE.
  DELETE-STATIC-RANK's landed CODE is sound, but its mandated deploy step (purge cost_rank from the
  live 4-LOM /data/models.json) is UNSAFE as-is: any model lacking cost_input/cost_output silently
  collapses to the fixed 1000 fallback (cost_rank.py:88-89, pools.py:136), tie-broken by config-insert
  order -> can route to a PRICIER provider. The operator override that could correct a bad derived
  order was removed (routing_policy/__init__.py:117), and NOTHING guarantees priced-completeness.
  DO NOT purge cost_rank on 4-LOM until this guard exists.
accept: |
  - A PRICED-COMPLETENESS preflight: fails LOUD (or holds the cost_rank purge) if ANY live model lacks
    cost_input/cost_output — so no model can silently collapse to the 1000 fallback. Names the offenders.
  - Either restore a safe operator-override path OR prove the derived order is correct for every priced model.
  - tests/test_priced_completeness.py: a model missing pricing -> guard FAILS (fail-on-revert); fully-priced
    catalog -> passes. Prove a missing-price model does NOT get selected over a cheaper priced one.
  - charon.cli gate GREEN.
