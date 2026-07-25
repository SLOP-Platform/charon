repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: ci-infra
branch: fix/rig-reds-disposition
depends_on:
owns: fleet/state/reviews/RIG-REDS-DISPOSITION-agen-kolar.md
source: 2026-07-24 landing-queue investigation — fleet/land.sh runs the full rig gate and REFUSES on
  any red, so the rig's persistent RED checks are a hard stop on every rig land.
priority-why: |
  P:0 — this is the CURRENT KEYSTONE and the only ticket on the board that unblocks other work by
  existing. fleet/land.sh runs the full gate and refuses to land on a red, so while the rig gate has
  standing reds NOTHING lands in the rig: ~21 built-but-unmerged branches are queued behind these 10
  checks. Every other rig ticket, including the P:0 gate work, terminates at a land that cannot run.
  A blocker that gates the entire landing queue is exactly the top band; it is not P:2 because it is
  not merely "large blast radius", it is the serial predecessor of every rig merge.
note: |
  STATE: a sub-session is working this branch RIGHT NOW in the worktree
  /home/stack/charon-private-wt/RIG-REDS. The ticket is created PRE-EMPTIVELY because the work-lease
  commit hook refuses any worktree branch that maps to no board ticket, and that session will hit the
  refusal the moment it commits.
scope: |
  ONE-TIME DISPOSITION of the rig gate's persistent RED checks — the standing reds that block every
  rig `land.sh` and therefore the whole landing queue (~21 built-but-unmerged branches).

  METHOD: every red is ATTRIBUTED to exactly one of four classes, then fixed or ticketed. No red is
  stepped around, muted, or de-scoped:
    - genuinely broken       -> the check is right and the code is wrong: FIX the code.
    - slow-or-concurrency    -> the check is racing another runner / timing out: fix the race or the
                                bound; a flake is a defect, not weather.
    - obsolete               -> the check asserts a contract that no longer exists: RETIRE the check
                                with the reason recorded (never silently delete).
    - environmental          -> the failure is host/tooling state, not code: fix the environment or
                                make the check fail-closed with an actionable message.

  COUNT: 10. This number is BASELINED against a pristine `git archive HEAD` tree, deliberately, because
  the earlier counts were wrong for two different reasons — 9 was stale (taken before later checks
  landed) and 12 was concurrency-inflated (parallel runners in a shared checkout failing each other).
  Any future count must be taken the same way or it is not comparable.
accept: |
  - fleet/state/reviews/RIG-REDS-DISPOSITION-agen-kolar.md: one row PER RED with (a) the check, (b) the
    reproduction command, (c) the attributed class from the four above, (d) the disposition — fixed
    here / retired here / ticket id raised — and (e) for a "fixed" row, the evidence it now passes.
    A red with no class or no disposition is an INCOMPLETE deliverable, not a finding.
  - NON-VACUOUS: the disposition doc must account for ALL 10 baselined reds. A doc that dispositions
    zero reds, or that reports "no reds found" without the pristine-tree baseline command and its
    output, FAILS acceptance — silence is never a pass.
  - PROVEN BY EXECUTION, not by claim: re-run the gate on a pristine `git archive HEAD` tree and show
    the red count going 10 -> 0 (or 10 -> N with each remaining N carrying a ticket id and a reason it
    is legitimately deferred). A green claimed from the working checkout is not evidence — that is the
    concurrency inflation that produced the bogus count of 12.
  - FAIL-ON-REVERT: each red fixed as "genuinely broken" lands with its own red-proof — revert the fix
    and the corresponding check goes RED again. Reds classed "obsolete" land with the retirement
    reason recorded in the disposition doc, so a future session cannot mistake the deletion for drift.
  - END STATE: `bash fleet/land.sh` on the rig is no longer refused by a standing gate red, i.e. the
    landing queue can actually drain. This is the ticket's real acceptance test.
  - bash fleet/validate_board.sh stays GREEN.
ds: |
  ## Dependencies & sequence
  depends_on: NONE — and deliberately so. This ticket is the SERIAL PREDECESSOR of the rig landing
  queue, not a dependent of it; adding any dep would put the keystone behind the very work it
  unblocks. Wave-1, claim immediately, run to done before the queue is drained.

  OWNS IS SCOPED CONSERVATIVELY, ON PURPOSE. The set of test/check files this work will repair is NOT
  KNOWN until each red is attributed, so `owns:` claims only the one file that is certainly this
  ticket's own deliverable: fleet/state/reviews/RIG-REDS-DISPOSITION-agen-kolar.md. Declaring a
  speculative file list would create phantom owns-collisions across half the board and block tickets
  this one is supposed to unblock. PER-RED FIXES ARE SPLIT OUT: each "genuinely broken" red that needs
  more than a local repair gets its OWN ticket with its OWN owns set, raised from the disposition doc.

  CONTENDED SURFACES THE WORKING BRANCH ALREADY TOUCHES (declared here so the contention is visible to
  the next session even though it is not claimed in `owns:`):
  - fleet/checks/rig-ci-scope.sh — live owners HANDOFF-GATE-NONBYPASSABLE and TIER-BALANCE (both
    append to CI_SUITES). Merge-order only: append, never rewrite the list, so the three edits compose.
  - fleet/tests/assign-dispatch.test.sh — live owner FLEET-DEMAND-BROKER (in review). Coordinate before
    editing; if the repair is more than a flake fix, raise it as a sub-ticket against that owner.
  - fleet/gate.sh, fleet/tests/capture-wiring.test.sh, fleet/tests/promotion-gate.test.sh,
    fleet/tests/submit-checkin.test.sh, fleet/tests/w0b-harden.test.sh — NO live board owner
    (verified 2026-07-24 against every `owns:` line); safe to repair in place.

  CONCURRENCY SAFETY: run the baseline in an ISOLATED pristine tree (`git archive HEAD`), never in a
  shared checkout — a second runner in the same tree is what inflated the count to 12.
