repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/coverage-meta-gate-rederive
depends_on:
substrate: N/A
substrate-novel: |
  No third-party tool enforces "every mechanizable MANAGER-OPERATING-RULES rule must be a wired
  gate" — this is a project-specific meta-invariant over our own rule set + gate registry. Closest
  external prior art does NOT cover it. coverage.py/linters measure CODE-line coverage, not rule to
  gate coverage; policy engines (OPA/Semgrep) enforce individual patterns, not completeness of the
  rule to gate mapping. The mediastack enforcement_coverage.py we port is our OWN prior art, not
  external substrate. Novel slice = the registry-driven rule to gate reconciliation.
landed: PR #140 — re-derived onto master (stranded feat/coverage-meta-gate abandoned); manager-verified gate GREEN + test 13/13
owns: fleet/checks/rule-coverage.sh, fleet/state/RULE-REGISTRY.tsv, fleet/tests/rule-coverage.test.sh
serial_justified: rule-coverage.sh and RULE-REGISTRY.tsv are one checker+its-own-schema unit (the
  mediastack enforcement_coverage.py reference pairs a script with the data file it audits) — the
  script's row-classification logic is written against the TSV's exact column schema; two concurrent
  writers risk the checker and the registry disagreeing on what a row means.
ds: |
  ## Dependencies & sequence
  depends_on: (none) — self-contained port. Establishes fleet/state/RULE-REGISTRY.tsv; the KS31
  tool-adapters (SEMGREP/GITLEAKS/BANDIT/VULTURE) each append their row after landing.
  wave: strong — the R0.1 anchor; land before the tool-adapters.
accept: |
  MECHANIZE §11 ("every rule that CAN be a gate MUST be a gate"). PORT the reference impl mediastack/tools/enforcement_coverage.py
  (+ its SSOT test) — TOOL-FIRST, do NOT rebuild. DO: fleet/state/RULE-REGISTRY.tsv — one row per MANAGER-OPERATING-RULES rule,
  classified mechanized(<gate>) | guidance(<why>) | GAP. fleet/checks/rule-coverage.sh — RED if any mechanizable rule is left
  GAP/advisory; run in preflight/CI. Would have auto-caught this session's advisory GAPs (decompose-sizing, E2E-wired, base-integrity).
  FAIL-ON-REVERT (fleet/tests/rule-coverage.test.sh): mark a mechanizable rule as GAP -> gate RED; revert -> passes -> test fails.
