repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: ci-infra
branch: feat/throughput-expectation-alarm
depends_on:
owns: fleet/checks/throughput-expectation.sh, fleet/tests/throughput-expectation.test.sh, fleet/state/THROUGHPUT-EXPECTATION-ALARM.md, docs/review-log/THROUGHPUT-EXPECTATION-ALARM.md
serial_justified: |
  One expectation model with one alarm path. Split, you get a producer-liveness check and an
  artifact check that disagree about what "working" means.
substrate: N/A
substrate-novel: |
  Every INPUT exists and stays adopted — board ready/claimed counts, claim markers, git commit
  times, gh PR creation times, loop-guard records, the launcher's per-ticket outcome. Nothing new
  is measured. The novel slice is the EXPECTATION: what SHOULD have been produced by now, given
  what was available to work on.
accept: |
  THE GAP, stated precisely. `FLEET-STATUS-BOARD` (queue #7) verifies that CHECKS still run —
  registry, heartbeat, bidirectional meta-check. It does NOT verify that WORK still happens.
  A fleet where every check is green and nothing is being produced looks perfectly healthy to it.
  That was the literal state for hours on 2026-08-02.
  THREE SUB-SHAPES of "something stopped working, nothing announced it". FSB covers only the first:
    (a) a CHECK stops running        -> crontab wiped, detector silent 8h        -> FSB catches
    (b) a WORKER stops producing     -> reviewer pool at ZERO; droids claiming and no-op'ing
                                        (8 tickets quarantined)                  -> NOTHING catches
    (c) an ARTIFACT stops appearing  -> the next-session bootstrap vanished while
                                        the gate still exited 0                  -> NOTHING catches
  Heartbeats prove a process is ALIVE. Only an EXPECTATION proves it is doing anything.
  Done contract:
  1. (b) THROUGHPUT EXPECTATION: given N claimable tickets and M live tabs, the fleet should
     produce >= 1 commit-or-PR per interval. ZERO production for X while work was AVAILABLE is an
     alarm, not silence. Must distinguish "no work to do" (fine) from "work available and nothing
     produced" (alarm) — that distinction is the whole ticket.
  2. (c) ARTIFACT ASSERTIONS: for each producer that exists to emit something (close gate ->
     bootstrap + handoff; reviewer -> verdict; droid -> commit or an explicit release reason),
     assert the ARTIFACT, never the exit code. A producer that exits 0 having produced nothing is
     a silent partial success.
  3. Register both in FLEET-STATUS-BOARD's CHECK-REGISTRY so they inherit the bidirectional
     meta-check — the alarm must not itself become something that silently stops.
  4. Escalate via `pending.sh add --key` (keyed upsert, no row-spam).
  5. FAIL-ON-REVERT, both: seed claimable work with all tabs no-op'ing and prove the alarm FIRES;
     seed a producer that exits 0 with no artifact and prove it FIRES. Remove each and prove it
     goes quiet. Report verbatim.
  MEASURED CONTEXT: 2026-08-02 the board read healthy, tabs read busy, checks read green, and
  throughput on affected tickets was ZERO — discovered only because the operator asked why nothing
  was landing.

## Dependencies & Sequence

P0. Pairs with FLEET-STATUS-BOARD (#7) — that one watches the WATCHERS, this one watches the WORK.
Land FSB's registry first if they land together, so these two register into it rather than becoming
two more unregistered checks. Independent of ZERO-COMMIT-SPIN (#1): that ticket fixes ONE instance
of (b); this one DETECTS the whole class, including the next instance nobody has found yet.
