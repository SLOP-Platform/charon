repo: charon-private
tier: strong
difficulty: 4
priority: 1
work_class: rig-meta
branch: feat/faktory-adopt
owns: fleet/faktory/faktory-client.sh, fleet/faktory/faktory-worker.sh, fleet/faktory/README.md, fleet/state/FAKTORY-ADOPT.md
serial_justified: client + worker + durability proof are ONE coherent substrate adoption — splitting risks a half-wired store (worker without client, or unproven durability). Adopt atomically.
depends_on:
source: EVAL — Faktory ADOPT-PARTIAL (TRIAL-FAKTORY, 2026-07-24) + CLAIM-INTEGRITY-EVAL verdict (operator-approved 2026-07-24, eeth-koth). Faktory reserve/ack IS the claim-lease substrate.
note: |
  Adopt Faktory as the ONE durable job/lease substrate (already EXECUTED-verified on 4-LOM,
  ~15MB single container, embedded Redis-protocol RDB at /root/.faktory/db/). Replaces the
  loop-guard DLQ AND becomes the claim-lease store for CLAIM-LEASE-EXACTLY-ONCE. Do NOT stand up
  a second substrate — this is the sole one. See [[claim-integrity-no-reclaim-red-line]].
accept: |
  - Faktory server running durably on 4-LOM with the RDB volume mount proven to survive container
    recreation (TRIAL-FAKTORY §1/§6 pattern: -v ...:/root/.faktory).
  - A thin shell client wrapper (faktory-client.sh) exposing push / reserve / ack / fail over the
    Faktory protocol, and a shell worker (faktory-worker.sh) that reserves a job, runs the
    charon-run.sh-shaped payload, and ACKs on success / FAILs on error.
  - fail-on-revert tests: a reserved job is invisible to a second reserve; an ACKed job is gone;
    a FAILed/expired job requeues after reserve_for.
  - EVAL-REGISTRY already carries the ADOPT-PARTIAL row; this ticket is the WIRING of that verdict.
scope: |
  Substrate adoption only: server + client wrapper + worker + durability proof. The exactly-once
  claim semantics (idempotent enqueue, lease-as-claim) are CLAIM-LEASE-EXACTLY-ONCE (depends on this).
interface_contract: |
  ## ANCHOR — faktory-client.sh CLI (CLAIM-LEASE-EXACTLY-ONCE codes against THIS; do not drift).
  fleet/faktory/faktory-client.sh <cmd> [args]; exit 0 success / non-zero failure:
    push    --queue Q --jobtype T --jid <ticket-id> --arg <json>  # enqueue; prints jid
    reserve --queue Q [--timeout S]                               # FETCH one; prints job JSON {jid,args} or empty+rc1 if none
    ack     --jid <id>                                            # terminal success; job durably GONE (survives restart)
    fail    --jid <id> [--msg M]                                  # terminal fail; requeues per reserve_for
    info    --jid <id>                                            # prints state, rc1 if absent (used by T1's idempotent-enqueue check)
  Payload: jobtype "charon-run", args = the charon-run.sh invocation. reserve_for default 1800s.
  Durability: ACKed jid MUST NOT be re-fetchable after container recreation (RDB volume mount).
ds: |
  ## Dependencies & sequence
  P1. No prereq. Prereq FOR CLAIM-LEASE-EXACTLY-ONCE (T1) and the loop-guard-DLQ replacement.
  Coordinate: this is the SAME Faktory stack the claim-integrity eval converges on — one adoption.
  T1 (CLAIM-LEASE-EXACTLY-ONCE) codes against `interface_contract` above IN PARALLEL; only T1's final
  integrated e2e proof (real Faktory) serializes after this lands.
