repo: charon-private
tier: strong
priority: 1
difficulty: 3
work_class: rig-meta
branch: fix/land-push-worktree-state
depends_on:
owns: docs/review-log/LAND-PUSH-WORKTREE-STATE.md
serial_justified: |
  Single defect, single surface. Nothing to parallelise.
substrate: N/A
substrate-novel: |
  No tool adopted. The mechanism already exists and is misconfigured or mis-wired; the novel
  slice is the correction plus the assertion that keeps it corrected.
accept: |
  MEASURED 2026-08-02: fleet/land-push.sh:59 reads the AUTONOMOUS lever from $FLEET/state/, but
  fleet/state/ is gitignored so every LINKED WORKTREE has an empty state dir and the lever always
  reads OFF — a sub-session was blocked from landing while the lever was ON in the main checkout.
  WORK-LEASE-WORKTREE-RESOLVE already solved this exact class via git rev-parse --git-common-dir;
  land-push never got the same treatment. Sweep for other $FLEET/state/ readers with the same
  assumption. Fail-on-revert covering the worktree case.

## Dependencies & Sequence

No inbound deps. Independent of the P0 lanes; disjoint owns.
