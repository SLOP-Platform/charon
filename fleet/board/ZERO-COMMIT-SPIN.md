repo: charon-private
tier: strong
priority: 0
difficulty: 4
priority_note: RANKED #1 — see LIVE EVIDENCE section
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

## LIVE EVIDENCE 2026-08-02T15:40Z — THE WORK NEVER STARTS

Re-quarantined WITHIN MINUTES of being cleared: `droid=strong-2780986 count=3
quarantined=2026-08-02T15:40:28Z`. The spin is ACTIVE.

DECISIVE OBSERVATION — there is **NO session log and NO gate result** for this ticket:
  - `fleet/state/gate-results/*SPEND-METRIC*`  -> does not exist
  - `fleet/state/agent-logs/*SPEND-METRIC*`    -> does not exist
  - the SAME droid has a full, normal session log for another ticket:
    `fleet/state/agent-logs/strong-2780986-BASH-INERT-COVERAGE.txt` (real work, reading files)

So this is NOT "the model produced bad work". The session NEVER STARTS. The failure is between
CLAIM and SESSION-START, and it leaves no artifact — which is why it was invisible until the
guard counted to three.

HYPOTHESIS TO TEST FIRST (cheap, and it fits the data): **both spinning tickets are
`repo: charon` (PRODUCT) tickets claimed by a RIG-launched droid.** The same droid's runs record
holds SPEND-METRIC-TRUSTWORTHY and RESCUE-TRIAGE-PRODUCT — both product-repo. Suspect the
product worktree/repo resolution path (repo-registry.sh hardcodes
`/home/stack/code/charon-fleet-<id>`; a product ticket whose worktree lives elsewhere was already
observed today to break `land-needs-push.sh` for LITELLM-CAPABILITY-ADOPTION).
Second candidate: p0-worktree-setup refusing on a dirty/unpushed existing worktree — observed
today killing tabs outright with leak-guard refusals.

WHY THIS IS RANKED ABOVE VISIBILITY WORK: BOARD-VIEW-MISMATCH makes exclusion visible, but
visibility of nothing is still nothing. This defect means the fleet CLAIMS WORK AND PRODUCES
NOTHING while looking busy — measured today: 8 tickets, including P0s minted hours earlier, and
a near-zero throughput window that read as healthy.

ACCEPTANCE ADDITION: instrument the claim->session-start path so a no-op leaves an ARTIFACT
naming the refusal. A failure that writes nothing cannot be diagnosed after the fact, which is
the reason this survived long enough to quarantine 8 tickets.
