repo: charon-private
tier: economy
difficulty: 2
work_class: rig-meta
branch: feat/foreman-wire
owns: fleet/preflight.sh, fleet/tests/test_foreman_wire.sh
serial_justified: One small wiring of foreman into the existing preflight surface + its test; nothing independent to parallelize.
depends_on:
note: |
  foreman.sh (claimability + composition monitor, confirm-first, blast-radius-aware) is built + tested
  but runs only when the manager invokes it. Wire it to run AUTOMATICALLY and notify LOUDLY (operator:
  "monitor the pools and tell you loudly if work isn't seen/being claimed"): add a `foreman` step to
  preflight.sh scan that runs `foreman.sh` (report-only, never --fix in preflight) and surfaces its
  STARVE/COLLISION verdict prominently in the operator-actions output. Non-blocking (advisory) — it
  REPORTS, the manager acts.
accept: |
  - preflight.sh scan runs foreman.sh and prints its verdict line ([STARVE]/[COLLISION]/[OK]) in the
    surfaced operator actions; a starving tier or a live collision shows LOUDLY (not buried).
  - preflight NEVER runs foreman --fix (report-only there; acting stays a manager decision).
  - fleet/tests/test_foreman_wire.sh: a fixture where a tier starves -> preflight scan output contains
    the loud STARVE surface; a fed+clean board -> no false alarm. Fail-on-revert.
