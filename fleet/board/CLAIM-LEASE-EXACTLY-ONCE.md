repo: charon-private
tier: strong
difficulty: 4
priority: 0
work_class: rig-meta
branch: feat/claim-lease-exactly-once
owns: fleet/lease-enqueue.sh, fleet/tests/lease-exactly-once.test.sh
depends_on: FAKTORY-ADOPT, WORK-LEASE-GATE
real-dep: FAKTORY-ADOPT — the exactly-once claim is wired ON the Faktory reserve/ack substrate; the client/worker must exist before the enqueue-chokepoint can call them. dep-kind: build.
real-dep: WORK-LEASE-GATE — leak #1 (manager-sub bypass) is closed by the lease gate refusing un-leased work; this ticket wires the enqueue path INTO that gate. dep-kind: build.
source: CLAIM-INTEGRITY-EVAL verdict (RED LINE P0, operator-approved 2026-07-24, eeth-koth). Closes the re-claim/double-claim class at the mechanism level. Full eval: fleet/state/CLAIM-INTEGRITY-EVAL.md
note: |
  The exactly-once wiring that binds Faktory (substrate) + WORK-LEASE-GATE (enforcement) into ONE
  lease-with-ack claim. Closes ALL THREE re-claim paths [[claim-integrity-no-reclaim-red-line]]:
  1. SINGLE ENQUEUE CHOKEPOINT — claim.sh becomes the SELECTOR only; the winning ticket is handed to
     fleet/lease-enqueue.sh, the ONLY path that starts work, enforced by WORK-LEASE-GATE's
     write-boundary (a commit for a ticket with no live reservation is REFUSED → closes leak #1,
     the manager-sub bypass). ⚠️ MUST acquire the lease at DISPATCH, not just pre-commit — else two
     builders can both BUILD (wasted cycles) even though only one can commit (operator-added nit).
  2. IDEMPOTENT ENQUEUE — the wrapper refuses to PUSH a ticket-id that already has a live
     reservation/claim (OSS Faktory does NOT dedup PUSHes; unique_for is Enterprise). LOCKED mechanism
     (DEDUP-AT-STORE-EVAL, 2026-07-24): reuse the ALREADY-OWNED `flock` on state/lock (same primitive as
     claim.sh:207) as the dedup mutex, guarding a check-and-PUSH inside lease-enqueue.sh keyed on a durable
     `state/enqueued/<ticket-id>` marker — check + act both inside the held lock → atomic, no TOCTOU. NO
     second daemon (reusing Faktory's embedded Redis socket is DISQUALIFIED-unsafe: Faktory owns that store
     exclusively, app writes risk crashing its RDB). Multi-host upgrade path (documented, NOT now): swap the
     flock for a tiny standalone Valkey `SET id token NX EX ttl` — 1-line mutex swap, contract unchanged.
     Do NOT build a second lock (WORK-LEASE-GATE crit 1). Full: fleet/state/DEDUP-AT-STORE-EVAL.md.
  3. ATOMIC TERMINAL VIA ACK — replace the submitted→done marker hand-off: worker ACKs on a
     merge-verified delivery (keep done.sh's merge proof as the pre-ack gate); ACK is the atomic
     retire → closes leak #2 (no delivered-but-claimable window) and leak #3 (ACKed job durably
     un-fetchable across restart via RDB). reserve_for + dead-only reap-orphans.sh cover crash/zombie.
accept: |
  4-case fail-on-revert proof (mandatory):
  (a) two sessions cannot both hold the same ticket's reservation;
  (b) a manager-sub commit for an un-reserved ticket is REFUSED;
  (c) an ACKed ticket cannot be re-fetched after a Faktory container restart;
  (d) a double-enqueue of the same ticket-id creates exactly ONE job.
  Revert the wrapper/gate → each fixture regresses → test RED.
scope: |
  The exactly-once claim wiring only. Substrate = FAKTORY-ADOPT; enforcement = WORK-LEASE-GATE;
  dedup mechanism = DEDUP-AT-STORE-EVAL. This ticket binds them + the 4-case proof. No meaning
  until both deps land.
ds: |
  ## Dependencies & sequence
  P0 (RED LINE). depends_on FAKTORY-ADOPT + WORK-LEASE-GATE (both must land first). Sequence:
  STALE-CLAIM-RECONCILE (hygiene) → FAKTORY-ADOPT + WORK-LEASE-GATE → this. dep-kind: build.
