repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: rig-meta
branch: fix/zero-commit-spin
depends_on:
owns: fleet/state/ZERO-COMMIT-SPIN.md, docs/review-log/ZERO-COMMIT-SPIN.md
serial_justified: |
  One diagnosis across one shared failure mode; parallel lanes would each re-derive the same
  cause from a different ticket and disagree.
substrate: N/A
substrate-novel: |
  loop-guard.sh already DETECTS the spin and quarantines correctly. Nothing is built. The novel
  slice is the CAUSE — why droids claim work and produce zero commits.
accept: |
  MEASURED 2026-08-02: EIGHT tickets were quarantined by loop-guard for
  "repeated zero-commit re-claims (claim->no-op->release spin)" — BASH-INERT-COVERAGE,
  CLAIM-LIVENESS-BINDING, GATE-OWNERSHIP-FAILOPEN, PARK-REARM-FUNDED-PROVIDER,
  RECONCILE-HANDOFF-FRESHNESS, SPEND-METRIC-TRUSTWORTHY, STRANDED-WORK-AUDIT,
  TICKET-CHECK-SCOPE-SEMANTIC — including P0 tool-utilization tickets minted the same day.
  The guard is CORRECT; the question is why the droids no-op. Live evidence: after clearing,
  SPEND-METRIC-TRUSTWORTHY was RE-QUARANTINED within minutes, so the spin is ACTIVE, not stale.
  Consequence (loop-guard.sh:11-14 documents it): quarantined ids are silently skipped, so P0
  tabs drop past them to economy work with zero signal — the priority ladder starves.
  Done contract:
  1. Capture a FULL droid run on a quarantined ticket — brief, model chain, gate output, exit
     path — and state exactly where zero commits happen.
  2. Classify: infra fault (pool exhaustion, gateway reset, launcher refusal) vs model failure vs
     unactionable brief. loop-guard already has an INFRA-FAULT EXEMPTION via `--reason`; if these
     are infra, the launcher is failing to pass a reason and the exemption never fires.
  3. Fix the cause. Clearing quarantines without it just restarts the spin — proven today.
  4. Fail-on-revert covering the classification path.

## Dependencies & Sequence

P0, no inbound deps. Pairs with BOARD-VIEW-MISMATCH: that one makes exclusion VISIBLE, this one
removes the cause. Land either order.
