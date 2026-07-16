repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: fix/perf-audit-claim-decompose
owns: fleet/claim.sh, fleet/decompose.sh, fleet/tests/test_claim_decompose_perf.sh
serial_justified: One timed-audit + any O(n) fix across the two hot loop scripts; cohesive perf pass, not independently parallelizable.
depends_on:
note: The perf audit (PERF-AUDIT.md) could NOT time claim.sh/decompose.sh (they mutate live shared board/claim state, no dry-run). Add a --dry-run/throwaway-worktree timing path, measure both, and if either exceeds 5s or is O(board-size), apply the index-once fix (same class as done.sh/reconcile-merged). If already fast, record the measurement and close.
accept: |
  - Both timed in a throwaway worktree (no live-state mutation); PERF-AUDIT.md updated with measurements.
  - Any >5s / O(n-over-growing-set) path fixed to index-once + a fail-on-revert perf test; else documented fast.
