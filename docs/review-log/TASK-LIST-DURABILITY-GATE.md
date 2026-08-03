# TASK-LIST-DURABILITY-GATE — review-log fragment

Ticket: TASK-LIST-DURABILITY-GATE
Class: rig-meta — boundary assertion (design of record; builds nothing)
Date: 2026-08-02
Branch: feat/task-list-durability-gate

## Deliverable (in `owns:`)

- `fleet/state/TASK-LIST-DURABILITY-GATE.md` — Assertion A spec (design of record).
  Consumed by `SESSION-CLOSE-COMPLETENESS-GATE` as its "HARNESS TASKS HAVE A DURABLE
  HOME" assertion (that board names this ticket as the assertion owner). The spec
  fixes, normatively: the two RED conditions (R1 no-export, R2 unmapped-OPEN-task),
  the input contract (`TASK_DURABILITY_TASK_LIST` + line format + statuses), the
  three durable-home resolutions (live board stem, live pending.sh action, explicit
  `[DROPPED — reason]`), the non-vacuity rule (R1 absence = RED, empty export =
  GREEN), the `fleet/end-session.sh` wiring point, and the six fail-on-revert
  assertions the build ticket must carry.

## What I did (and did not) do

- Wrote the spec only. The ticket's `owns:` line is exactly the two files above;
  `substrate: N/A` + substrate-novel ("Nothing is built; the novel slice is the
  BOUNDARY ASSERTION") confirm this is a design ticket, so NO check script,
  NO `fleet/end-session.sh` edit, NO test file was created — those belong to the
  umbrella build ticket (SESSION-CLOSE-COMPLETENESS-GATE owns
  `fleet/checks/session-close-completeness.sh` + its test).
- Removed a leftover untracked `fleet/task-durability-check.sh` found in the
  worktree — it was a prior attempt's off-scope artifact (not in this ticket's
  owns), so it was deleted rather than committed, keeping the diff exactly to scope.

## Design decisions grounded in the repo

- **The two stores already exist and are adopted** — `fleet/pending.sh` (labels
  A–Z then #N, `pending.sh:22-27`) and `fleet/board/` (live `<ID>.md`, parked
  `<ID>.md.parked`). The harness task list is the one ephemeral store.
- **R1 (no export) is RED, R2 (unmapped open task) is RED** — satisfies
  GATE-CREATION-STANDARD S2 non-vacuity. Absence of evidence must not pass; the
  close gate must not be a registered-but-never-executing cron job.
- **Parked board ids and retired operator labels are NOT durable homes** — a parked
  ticket is shelved, a retired label no longer exists; both would be gaming holes.
- **Empty export is GREEN** — the session's own "I have zero open tasks"
  declaration, distinct from never exporting at all.

## Verified

- Board: 146 live `.md` + 45 `.parked` in `fleet/board/` (parked-exclusion is
  real and observable).
- `fleet/state/*` is gitignored; the spec file is force-added (sibling design
  docs in `fleet/state/`, e.g. UNIFIED-RECONCILIATION-GATE-DESIGN.md, are tracked
  the same way).
- `fleet/end-session.sh:225-259` is the Phase-2 close path where the assertion
  must refuse before the commit/CLOSED print.

## Fail-on-revert note

Not executable here by design (nothing is built in this ticket). The six
assertions in spec §6 fix the exact RED/GREEN seeds the umbrella's committed test
must prove — including the direction "revert the gate wiring -> close passes",
which is what pins the wiring rather than the prose.
