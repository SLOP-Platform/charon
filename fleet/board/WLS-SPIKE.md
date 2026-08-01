repo: charon-private
tier: frontier
priority: 0
difficulty: 4
work_class: design-review
branch: eval/wls-spike
owns: fleet/state/WLS-SPIKE-TRIAL.md
serial_justified: One executed adopt-trial producing one verdict document; splitting it yields half a trial, which is desk research.
substrate: N/A
substrate-novel: |
  This ticket IS the substrate evaluation — it exists to ANSWER an adopt-vs-build question, not to
  build. Its whole output is an executed trial + an EVAL-REGISTRY verdict. Marking it N/A is not a
  novelty claim; there is simply no "tool to adopt in order to evaluate tools".
depends_on:
note: |
  ROADMAP.tsv:184 has carried this as "R0 LEAD: adopt-first spike of the work-loop-integrity stack
  (ao first, then Omnigent/Windmill/Archon) — durable fix for the built-but-not-wired/stale/
  gate-decay class" — QUEUED, never minted as a board ticket, therefore never claimable.

  THE COST OF THE HAND-ROLL, MEASURED 2026-08-01:
    fleet/claim.sh + release.sh + reconcile-stale-claims.sh + reap-orphans.sh + work-lease.sh
    + loop-guard.sh  =  1,719 LOC
  re-implementing atomic dequeue, leases and orphan recovery. Measured outcome of that
  implementation: of 25 tickets worked, 6 reached DONE, 3 got a PR, 4 stayed claimed and 12 fell
  back to READY — a 24% end-to-end success rate.

  WHAT A BROKER GIVES OFF THE SHELF: atomic dequeue (collisions impossible by construction),
  VISIBILITY TIMEOUT (a dead worker's item auto-requeues — deletes the reaper AND the stale-claim
  reconciler), retries with backoff, and a dashboard.

  SCOPE BOUNDARY — read this before proposing a design. Push-vs-pull does NOT remove the hard part;
  it removes CONTENTION. You still need dead-worker detection, which is precisely what a visibility
  timeout provides and what we hand-rolled badly. And the TAB LIFECYCLE (open a Windows-Terminal
  tab when work exists and none is free; close idle tabs) is genuinely rig-local — NO broker does
  WSL/WT tabs. That thin layer is the novel slice worth owning; everything under it is not.

  DELIVERY-GUARANTEE WARNING — do not repeat a known mistake. OSS Faktory has NO exactly-once
  execution, yet CLAIM-LEASE-EXACTLY-ONCE was recorded as coding against it. VERIFY the delivery
  guarantee each candidate ACTUALLY provides (at-most-once / at-least-once / effectively-once) from
  its source or a live trial — never from its README. Something in the rig may already depend on a
  guarantee that never existed.
accept: |
  - An EXECUTED trial, not desk research (registry rule AP-12: rejecting a RUNNABLE candidate
    requires an executed trial). Candidates in order: ao, then Windmill, Temporal, River, Archon,
    Omnigent. Faktory is already adopted for dispatch — re-test it under this lens rather than
    assuming it.
  - For EACH candidate actually run: the delivery guarantee VERIFIED (source or trial, not README),
    whether a dead worker's item genuinely auto-requeues, and how the tab lifecycle would attach.
  - A migration sketch naming which of the 1,719 LOC each candidate DELETES. A candidate that
    deletes nothing is not solving this problem.
  - Verdicts appended to fleet/state/EVAL-REGISTRY.md in a SEPARATE commit from this ticket (the
    registry is not self-service), each with an honest `alignment` and a resolvable evidence-link.
  - REJECTIONS MAY NOT cite "adds a dependency", "second runtime", "we already own X", or
    "solo box" — §0 abolished those on 2026-07-20 and the registry classes them as drift markers.
    Name a specific measured cost or do not reject.
  - Output: fleet/state/WLS-SPIKE-TRIAL.md with commands run and raw output counted.

## Dependencies & Sequence

- **depends_on: (none).**
- **Sequence: AFTER GRADE-MODEL-PROVIDER-PAIR.** That ticket has a data-loss clock (every run
  writes a provider-blind ledger row that cannot be reconstructed); this one does not degrade while
  it waits. Operator-approved order, 2026-08-01.
- **Blocks / unblocks:** unblocks the collision/stale-claim class wholesale, and is the
  prerequisite for any push-dispatch or tab-manager work — building a tab manager against the
  current claim model would be rework.
- **owns-collision:** none — output is a new state doc. Any resulting MIGRATION is a separate
  ticket and will collide heavily with the claim machinery; do not start it inside this spike.
