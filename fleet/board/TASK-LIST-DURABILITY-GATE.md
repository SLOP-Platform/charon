repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/task-list-durability-gate
depends_on:
owns: fleet/state/TASK-LIST-DURABILITY-GATE.md, docs/review-log/TASK-LIST-DURABILITY-GATE.md
serial_justified: |
  One assertion at one boundary. Splitting it ships a check that runs at close without the
  conversion path it is supposed to demand, which reds every session end for no gain.
substrate: N/A
substrate-novel: |
  Both durable stores already exist and are adopted — the board and fleet/pending.sh. The
  ephemeral store is the harness task list, which is outside the repo by construction. Nothing is
  built; the novel slice is the BOUNDARY ASSERTION that no open task may exist without a durable
  home.
accept: |
  THE HOLE: MANAGER-OPERATING-RULES sec.0 mandates BOTH the harness task list AND fleet/pending.sh,
  and is explicit that the harness list exists to survive mid-turn REDIRECTS — not sessions. It is
  session-scoped and writes nothing to the repo. Nothing checks the boundary, so any item left
  only there dies silently with the session.
  MEASURED 2026-08-02: the session closed with 24 harness tasks, 15 still OPEN. SIX had no board
  ticket and would have been lost — including LAUNCHER-LEAKGUARD-NONFATAL (5 tabs killed) and
  SPILL-UP-CEILING-SSOT (spill-up failing closed fleet-wide). They survived only because the
  operator asked the question.
  THE EVIDENCE PROBLEM: no prior session's task list can be inspected, because none survived. The
  absence of any artifact IS the finding — losses of this shape leave no trace to audit, which is
  why the class went unnoticed. Note the adjacent, worse shape already on record: a session was
  reminded ~20 times to use the task tool, used it ZERO times, and then failed to deliver work it
  had promised in prose.
  Done contract:
  1. At session close, ASSERT every OPEN harness task maps to a durable home — a board ticket id,
     a fleet/pending.sh operator action, or an explicit `[DROPPED — reason]`. Unmapped = RED.
  2. Wire it into fleet/end-session.sh, which today checks work-loss in GIT only (branches,
     commits, worktrees) and has no notion of an open task without a home.
  3. FAIL LOUD and name the unmapped items. A silent pass here is the same false-green family as
     a registered-but-never-executing cron job.
  4. Fail-on-revert: an open task with no durable home must RED the close; with the gate removed
     it must pass. Prove both.
  5. The reverse direction is NOT in scope — a board ticket need not appear in the harness list.
     The list is a working set; the board is the record.

## Dependencies & Sequence

P0. Depends on nothing. Should land BEFORE the next session accumulates its own list, or the
class repeats one more time. Pairs with FLEET-STATUS-BOARD (which makes checks visible) — this one
closes the boundary where work stops being tracked at all.
