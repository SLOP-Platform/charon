repo: charon-private
tier: strong
difficulty: 2
work_class: ci-infra
branch: feat/reachability-audit-land
owns: fleet/state/REACHABILITY-AUDIT.md
depends_on: REACHABILITY-GATE
accept: |
  LAND the reachability audit as the design artifact of its gate ticket and wire it in.
  `fleet/state/REACHABILITY-AUDIT.md` (222 lines) is the PART-1 audit deliverable for the
  EXISTING ticket `fleet/board/REACHABILITY-GATE.md` — its own header names that ticket.
  It has sat UNTRACKED across multiple sessions; `.gitignore` already carries the negation
  (`!fleet/state/REACHABILITY-AUDIT.md`) so it is meant to be tracked.

  CODE-CONFIRMED FACTS (do not re-derive; verify before editing):
  - The audit used the operator's code-map tool `graphify` (not blind grep) and found the
    root instance of the MODEL-PREFLIGHT wall: `fleet/benchmark/grader-daemon.py` hardcodes
    `/home/stack/...` paths that the OOB grader user `bench-grader` (uid 999, not in group
    `stack`) cannot traverse — `/home/stack` is `drwxr-x--- stack:stack`.
  - REACHABILITY-GATE.md already lists `fleet/state/REACHABILITY-AUDIT.md` in its `owns:`
    and orders audit-then-gate (its `serial_justified` / `ds` note).

  DO:
  1. Commit REACHABILITY-AUDIT.md as REACHABILITY-GATE's PART-1 design artifact (the file
     is authored analysis — TRACK it, do NOT gitignore).
  2. Wire the audit's findings into REACHABILITY-GATE's PART-2 contract + PART-3 gate build:
     the confirmed grader-daemon.py hardcoded-path root instance becomes the first
     FAIL-ON-REVERT case for `fleet/checks/no-unreachable-paths.sh`, and the audit matrix
     scopes the gate's allowlist.

  ACCEPT: REACHABILITY-AUDIT.md is git-tracked; REACHABILITY-GATE's gate build references
  the audit's matrix + the grader-daemon.py root instance as its seed test case.
scope: |
  Cross-boundary path-reachability hygiene. This is the committing + wiring half of the
  audit-then-gate ordering already baked into REACHABILITY-GATE. [[no-hardcoded-cross-boundary-paths]]
  [[charon-deploy-drift-lessons]] [[gates-must-actually-run]]
ds: |
  ## Dependencies & sequence
  depends_on: REACHABILITY-GATE — this ticket lands the audit that REACHABILITY-GATE's PART-3
  gate is scoped from; they share the same design artifact (REACHABILITY-GATE `owns:` lists
  REACHABILITY-AUDIT.md too). Sequence: land the audit (this ticket) → REACHABILITY-GATE
  PART-3 builds the gate from it. File-adjacent but not colliding: this ticket only commits
  the .md; the gate ticket writes the check script. Coordinate so both do not stage the .md.
  wave: reachability gate.
