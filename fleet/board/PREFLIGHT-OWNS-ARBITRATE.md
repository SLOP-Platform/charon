repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 1
branch: fix/preflight-owns-arbitrate
depends_on:
owns: fleet/state/PREFLIGHT-OWNERSHIP-RULING.md
serial_justified: |
  ONE arbitration producing ONE ruling artifact. This ticket deliberately owns NO code and NOT
  fleet/preflight.sh itself — taking ownership of the contended file would make it a sixth concurrent
  writer, which is the defect. Its output is the ordering decision; the edits happen inside the
  tickets that already own the file.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  The run IS a graded sample: record it into fleet/model-scorecard.tsv with the work_class above.
  One checkout, one agent — its OWN worktree, never a shared checkout.
source: |
  Operator decision 9b, 2026-07-26 (manager session kit-fisto). The RED is long-standing and was
  documented but never scoped as work (rig commit 57a3849 records it as a blocking pre-existing RED).
note: |
  ## THE RED (the board's only standing RED)
  `validate_board.sh` reports:
    owns-collision LIVE (no dep ordering): fleet/preflight.sh <- MARKER-PROOF-MECHANIZE
    PREFLIGHT-GATE-RUN-HELPER RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE
  FIVE live tickets claim `fleet/preflight.sh` with no dependency ordering between them. Whichever
  pair runs concurrently, the second writer clobbers or conflicts with the first. The collision pairs
  the validator names: MARKER-PROOF-MECHANIZE|PREFLIGHT-GATE-RUN-HELPER,
  PREFLIGHT-GATE-RUN-HELPER|RECONCILE-WIRING, PREFLIGHT-GATE-RUN-HELPER|REPO-MAP-CONVERGE,
  PREFLIGHT-GATE-RUN-HELPER|SYNC-SCHEDULE.

  ## WHY IT MATTERS BEYOND THE RED LINE
  A standing RED trains everyone to read RED as background noise. That is how the next REAL collision
  gets waved through [[never-ignore-preexisting-issues]]. It also blocks any clean "board is green"
  claim, so no gate can use board-green as a precondition.

  ## WHAT THIS TICKET DOES — ARBITRATE, DO NOT EDIT
  For each of the five, read the ticket and determine what it actually needs from preflight.sh. Then
  produce ONE ruling that resolves the collision by exactly one of these means per ticket:
  - **SEQUENCE IT** — add a `real-dep:` + `dep-kind: build` edge so the writers are ordered
    (PREFLIGHT-GATE-RUN-HELPER appears in 4 of the 4 named pairs and is the obvious anchor candidate —
    confirm or refute that from the tickets, do not assume it).
  - **NARROW THE OWNS** — the ticket does not really need the whole file; drop it from `owns:` with a
    stated reason.
  - **MERGE THE TICKETS** — two tickets are one change and should be one ticket.
  - **RETIRE IT** — the ticket is stale or already satisfied.
  Ownership churn is itself risky: a wrongly-dropped `owns:` re-creates the collision silently later.
  Every disposition must say what evidence it rests on.

  ## HARD CONSTRAINT
  Do NOT edit `fleet/preflight.sh`. Do NOT edit the five tickets' code. This ticket writes a ruling;
  the `depends_on:`/`owns:` line edits it prescribes are applied as a board-hygiene commit by the
  manager after the operator reads the ruling. Five live tickets are involved — silently rewriting
  another ticket's ownership is the kind of override that needs an operator in the loop
  [[adversarial-review-must-not-silently-override-operator]].
accept: |
  DONE-CONTRACT:
  - `fleet/state/PREFLIGHT-OWNERSHIP-RULING.md` exists with a per-ticket disposition for all FIVE
    tickets (sequence / narrow / merge / retire), each with the evidence it rests on.
  - The exact `depends_on:` / `owns:` line edits are written out verbatim, ready to apply — so
    applying the ruling is mechanical, not a second round of judgement.
  - A DRY-RUN proof: state which validator RED lines the ruling clears and which (if any) remain.
    Show the current `validate_board.sh` RED output and the predicted post-ruling output.
  - NON-VACUOUS: a ruling that dispositions fewer than five tickets is incomplete, not partial credit.
  - No edits to fleet/preflight.sh and no edits to the five tickets. A diff touching either is out of
    contract.

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately**, fully concurrent with the Switchboard wave — it
  owns one new state file and touches no contended surface.
- **Blocks:** any future gate that wants to use "board is green" as a precondition.
- **Wave:** parallel lane, any time.
- **Concurrency safety:** owns one NEW file; no live ticket owns it. Deliberately does NOT own
  fleet/preflight.sh — see serial_justified.
