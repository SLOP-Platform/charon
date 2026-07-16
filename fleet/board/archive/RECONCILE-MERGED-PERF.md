repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: fix/reconcile-merged-perf
owns: fleet/reconcile-merged.sh, fleet/tests/reconcile-merged.test.sh
depends_on:
note: |
  PERF (found by adversarial perf audit 2026-07-15, see fleet/state/PERF-AUDIT.md top row):
  `preflight.sh scan` takes 5m46s — root cause is reconcile-merged.sh's ticket_for_pr() doing
  O(merged-PRs × board+archive files) awk-subprocess-per-file (~43,800 awk spawns/run). SAME
  failure class as the pre-fix done.sh full-sweep bug. Fix at the CLASS level (index-once, not
  re-scan-per-item). DO NOT re-derive — the exact fix is in PERF-AUDIT.md.
accept: |
  ## Task (apply the PERF-AUDIT.md fix — reconcile-merged.sh:65-83 ticket_for_pr + :89-108 loop)
  - Build the board/archive `branch:`→id and `owns:`→id index ONCE in a single pre-pass BEFORE
    the `while read` PR loop (instead of re-scanning all ~181 board+archive files inside
    ticket_for_pr per PR).
  - Short-circuit: skip the board lookup for any PR whose branch is already covered by an existing
    state/done/* marker (pre-build a done-branch set once) — mirrors the done.sh single-id fast path.
  - Preserve identical OUTPUT/behavior (same ticket↔PR reconciliation results); only the algorithm changes.
  ## Accept
  - `time bash fleet/reconcile-merged.sh` drops from >2min (didn't finish) to single-digit seconds.
  - fleet/tests/reconcile-merged.test.sh: a fixture board+done set + fake merged PRs asserts the
    SAME reconciliation result as before (behavior-preserving), and completes fast.
  - bash -n fleet/reconcile-merged.sh; preflight.sh scan no longer dominated by this step.
  ## Dependencies & sequence
  depends_on: (none) — self-contained algorithmic fix in one script.
