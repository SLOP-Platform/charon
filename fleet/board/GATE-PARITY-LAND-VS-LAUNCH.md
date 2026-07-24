repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: rig-meta
branch: fix/gate-parity-land-vs-launch
owns: fleet/checks/gate-parity.sh, fleet/tests/gate-parity.test.sh
serial_justified: The land-gate parity check and its control-plane fail-on-revert canary are one
  invariant — a check that asserts "everything that lands is launchable" is only trustworthy shipped
  with the fixture proving it REDs a lands-but-unlaunchable ticket; inseparable.
depends_on:
source: 2026-07-23 deadlock RCA — the strong pool deadlocked; keystone SUBSTRATE-FIRST-OWNS-BASE-REF landed unlaunchable (no serial_justified) then spun claim->no-op->release and was loop-guard-quarantined
note: |
  CLASS root cause of the deadlock: the LAND gate (validate_board.sh:387-399) treats the
  parallelizability gate as an ADVISORY (WCI, non-blocking), while the LAUNCH path
  (launch-plan.sh:168, fleet-droid.sh:316-336) enforces the SAME gate HARD (refuses launch). So a ticket
  can pass land, then be refused at claim/launch, spin zero-commit, and get loop-guard-quarantined —
  wedging it (and re-REDing the board). Recurs: GRACEFUL-DEGRADE, HANDOFF-NAME-ALLOCATOR, SUBSTRATE.
  ROOT PRINCIPLE: land-gate MUST be >= launch-gate — nothing lands that the launcher would refuse.
  [[sg-never-deadlocks]] [[gates-must-actually-run]]
accept: |
  - fleet/checks/gate-parity.sh: at LAND time (wired into validate_board / land.sh), re-run EVERY
    launch-refusal predicate the launcher applies (start with parallelizability-gate; make the set
    explicit + extensible) and FAIL HARD (RED, exit non-zero) if a board ticket would be refused at
    launch. A ticket that passes this can be launched. Fail-CLOSED: an unrunnable predicate => RED.
  - CONTROL-PLANE FLOW-CANARY (the missing analog of fleet/flow-canary.sh, which only canaries the
    gateway DATA plane): fleet/tests/gate-parity.test.sh SEEDS each control-plane fault and proves RED-
    then-GREEN, mirroring flow-canary.test.sh's hermetic seed→assert→revert pattern:
      (F1) a ticket that PASSES validate_board but the launcher REFUSES (splittable-serial, no
           serial_justified) => gate-parity RED; add serial_justified => GREEN.
      (F2) (stretch/compose with STUCK-TICKET-LOUD) a ticket that lands and cannot be claimed for ANY
           reason is surfaced LOUD, never silently parked.
    GREEN-is-not-proof: each case must go RED on the seeded fault and GREEN on revert.
  - Wire gate-parity.sh into the land path (validate_board scan and/or land.sh pre-condition) so it
    actually FIRES — not a built-but-inert check. Prove it fires (e2e: land a splittable-unjustified
    fixture ticket => blocked).
  - bash fleet/validate_board.sh GREEN on the real board (all live tickets already justified).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — gate code that gates landing;
    manager gates. Fix root cause, not symptoms.
scope: |
  Close the land-vs-launch parity gap so no ticket lands that the launcher refuses — the durable fix for
  the deadlock class. Ships WITH the control-plane flow-canary that would have caught it. Composes with
  STUCK-TICKET-LOUD (visibility) and LAUNCHER-CRASH-PARTIAL-DETECT (marker/quarantine rollback).
ds: |
  ## Dependencies & sequence
  P0, no build prereq. New file (fleet/checks/gate-parity.sh) — disjoint owns; wiring into
  validate_board/land.sh is a one-line anchor (coordinate, do not rewrite those files). Build via
  manager sub (deadlock-clearing, [[sg-never-deadlocks]]).
