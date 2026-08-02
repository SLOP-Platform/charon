repo: charon-private
tier: strong
priority: 2
difficulty: 3
work_class: ci-infra
branch: fix/substrate-owns-word-boundary
depends_on:
owns: docs/review-log/SUBSTRATE-OWNS-WORD-BOUNDARY.md
serial_justified: |
  Single defect, single surface. Nothing to parallelise.
substrate: N/A
substrate-novel: |
  No tool adopted. The mechanism already exists and is misconfigured or mis-wired; the novel
  slice is the correction plus the assertion that keeps it corrected.
accept: |
  fleet/checks/substrate_first_gate.py matches the substrate: tool name against owns: paths by
  SUBSTRING. Measured 2026-08-02: 'substrate: cron' false-matched the owned path
  fleet/checks/stranded-work-cron.sh. Worked around by rewording to 'crontab', but it will misfire
  on any short tool name (jq, gh, sed, uv, ruff). Match on a path/word boundary. Low severity, but
  it silently pushes authors toward contorted tool names to appease a gate.

## Dependencies & Sequence

No inbound deps. Independent of the P0 lanes; disjoint owns.
