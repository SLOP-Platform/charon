repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/coverage-meta-gate
depends_on:
owns: fleet/checks/rule-coverage.sh, fleet/state/RULE-REGISTRY.tsv, fleet/tests/rule-coverage.test.sh
serial_justified: rule-coverage.sh and RULE-REGISTRY.tsv are one checker+its-own-schema unit (the
  mediastack enforcement_coverage.py reference pairs a script with the data file it audits) — the
  script's row-classification logic is written against the TSV's exact column schema; two concurrent
  writers risk the checker and the registry disagreeing on what a row means.
accept: |
  MECHANIZE §11 ("every rule that CAN be a gate MUST be a gate"). PORT the reference impl mediastack/tools/enforcement_coverage.py
  (+ its SSOT test) — TOOL-FIRST, do NOT rebuild. DO: fleet/state/RULE-REGISTRY.tsv — one row per MANAGER-OPERATING-RULES rule,
  classified mechanized(<gate>) | guidance(<why>) | GAP. fleet/checks/rule-coverage.sh — RED if any mechanizable rule is left
  GAP/advisory; run in preflight/CI. Would have auto-caught this session's advisory GAPs (decompose-sizing, E2E-wired, base-integrity).
  FAIL-ON-REVERT (fleet/tests/rule-coverage.test.sh): mark a mechanizable rule as GAP -> gate RED; revert -> passes -> test fails.
