repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: rig-meta
branch: feat/claim-integrity-tool-adopt
owns: fleet/state/CLAIM-INTEGRITY-EVAL.md
depends_on:
source: operator RED LINE 2026-07-24 — re-claim/double-claim of tickets is unacceptable and keeps happening (SUBSTRATE, gate-parity, wire-graphify, FAKTORY-TRIAL, KSF this session)
note: |
  RED LINE [[claim-integrity-no-reclaim-red-line]]: CG does NOT work if any path lets a ticket be
  re-claimed or double-claimed. Recurring class this session: manager-sub builds bypass claim/submit
  markers; done-but-not-retired tickets stay claimable; pool restart re-offers done work. Needs a
  MECHANIZED, class-level guarantee — exactly-once / lease-with-ack / idempotent claim — NOT per-incident
  patches.
accept: |
  - ADOPT-FIRST investigation (this ticket is the eval; a follow-up builds the winner). Evaluate BY REAL
    capability (not README skim) external tools that guarantee claim integrity: job queues with
    visibility-timeout + explicit ack (Faktory — already ADOPT-PARTIAL, river, BullMQ, SQS), Temporal
    task-queue leases, DB advisory locks (Postgres), etcd/consul leases. For each: does it make
    double-claim and re-claim-of-done STRUCTURALLY IMPOSSIBLE (not just detected-after)?
  - Compare to our OWN owned tools: claim.sh flock + priority ladder, WORK-LEASE-GATE, LAUNCHER-CRASH-
    PARTIAL-DETECT (marker rollback), POOL-PAUSED, submit/claim/done markers. Where do they LEAK (the
    manager-sub-bypass path; done-not-retired; restart re-offer)? Adopt-vs-extend verdict + EVAL-REGISTRY row.
  - Deliverable = the eval + a recommended mechanism that closes EVERY re-claim path (incl. manager-sub
    builds must claim, done must retire atomically on delivery, restart must not re-offer). For OPERATOR
    REVIEW before the build ticket is spawned.
scope: |
  Adopt-first eval of a claim-integrity mechanism (the RED-LINE class fix). Investigation + recommendation;
  the build is a follow-up. Composes with FAKTORY-ADOPT (its DLQ/lease may BE the substrate).
ds: |
  ## Dependencies & sequence
  P0 (operator RED LINE). No prereq. Likely overlaps FAKTORY-ADOPT (Faktory's reserve/ack IS a claim-lease)
  — coordinate: the executor's lease may be the mechanism, making this eval + FAKTORY-ADOPT one stack.
