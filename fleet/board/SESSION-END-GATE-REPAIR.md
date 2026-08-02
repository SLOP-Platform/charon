repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: rig-meta
branch: fix/session-end-gate-repair
depends_on:
owns: fleet/end-session.sh, fleet/tests/session-end-gate.test.sh
substrate: N/A
substrate-novel: |
  REUSES the gate that already exists and is already thorough. `fleet/end-session.sh` already
  refuses to close on a dirty tree, on commits that are on NO remote ("that is stranded work"),
  and fails closed when paths cannot be resolved — it covers the second repo too. Nothing about
  the CHECK needs building. Two defects stop it running: a self-collision, and no firing layer.
serial_justified: |
  Both defects sit on the same close path. Fixing the self-collision without wiring the hook gives
  a working gate nobody invokes; wiring the hook without fixing the collision fires a gate that
  always fails. Either alone leaves work-loss unguarded.
source: |
  Operator, 2026-08-01: "I need all session ends to review potential work loss in a mechanized way
  that can not be optional or bypassed." Then, at session close: "is the gate now fixed or
  ticketed to be fixed quickly?" — it was neither. This ticket is that fix.
note: |
  ## DEFECT 1 — THE GATE BLOCKS ITSELF (it can NEVER complete)
  Reproduced 2026-08-01 with `SESSION=tott-doneeta bash fleet/end-session.sh`:
  ```
    end-session: generating machine-state handoff -> fleet/SESSION-HANDOFF-tott-doneeta.md
    handoff.sh: SESSION=tott-doneeta refused by claim-jedi-name.sh — that name is already in use
                (live file present).
    end-session: WARNING — handoff.sh exited non-zero (rc=2): the GATE is RED.
  ```
  `end-session.sh` creates its target via shell redirection (leaving a **0-byte**
  `SESSION-HANDOFF-<SESSION>.md`), THEN calls `handoff.sh`, whose `claim-jedi-name.sh` allocator
  sees that very file and refuses the name as already in use. **The gate creates the condition
  that makes it fail.** It aborts BEFORE reaching its work-loss check every single time.
  Fix shape: write to a temp path and `mv` into place, or exempt the run's own target from the
  allocator's exclusion set. Do NOT weaken the allocator's no-reuse rule — that rule is correct
  and it is what stopped a name being reused this session.

  ## DEFECT 2 — NOTHING INVOKES IT (100% bypassable)
  Measured 2026-08-01:
    - `fleet/hooks/` contains: `commit-msg`, `pre-commit`, `session-start.sh` — **no session-end**.
    - `~/.claude/settings.json` hooks: `PreToolUse`, `SessionStart`, `SubagentStart` — **no
      SessionEnd**.
  So closing a session never runs it. That is why this session had to hand-rescue **19 branches**
  and why the manager ran the work-loss sweep manually at close — precisely the
  "a hand-run discovery is not a control" failure `stranded-work.sh`'s own header warns about
  [[dynamic-tools-never-on-demand]].

  ## WHAT IT MUST CATCH (the gate already implements these — do not rewrite them)
  Uncommitted work in either main checkout · commits on NO remote (stranded) · unresolvable paths
  (fail closed) · second-repo coverage. **ADD:** `fleet/state/needs-push/` entries must be
  surfaced at close — they are currently invisible to both `handoff.sh` and `report.sh`.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline, fixture repos:
    a. **Reproduce defect 1**: `end-session.sh` with a valid SESSION completes and REACHES its
       work-loss check (today it aborts at handoff generation). Revert the fix -> RED.
    b. a checkout with an unpushed commit -> close is REFUSED, naming branch and commit count.
    c. a fully clean checkout -> close SUCCEEDS (ANTI-OVER-BLOCK — a gate that never lets you
       close gets disabled, which is worse than no gate).
    d. a `needs-push` entry present -> surfaced at close, not silently passed.
    e. **Defect 2**: the gate is invoked by a real firing layer (SessionEnd/Stop hook) — prove it
       FIRES, not merely that it is configured. A configured-but-uninvoked gate is the inert class
       this whole ticket is about.
  Then dogfood: run against the live rig and report what it finds.

  ## RELATED — do not duplicate
  `SESSION-END-PUSH-GATE` is state=submitted with PR #62 CLOSED-not-merged. Read it FIRST and
  either fold this work into it or state why it is superseded. Do not build a third attempt at the
  same thing without checking [[no-rig-as-product-adopt-dont-handroll]].

## Dependencies & Sequence
  - Depends on: nothing. `end-session.sh` is uncontended.
  - HIGHEST-VALUE close-path fix: this session lost nothing only because leak-guard refused 19
    worktree deletions and the manager swept by hand. Neither is a control.

## SCOPE ADDITION 2026-08-02: THE GATE MUST EMIT THE NEXT-SESSION BOOTSTRAP

Fixing the allocator makes the close gate RUN. It does NOT make it PRODUCE its output. Those are
different failures and only the first was ticketed.

OBSERVED 2026-08-02, operator-reported: "session end process is no longer handing me the one-liner
next session prompt — I have to keep asking for it." Root cause: the copy-paste bootstrap block is
generated by `handoff.sh` / `end-session.sh`, and both ABORT before reaching it (the self-blocking
allocator this ticket fixes). The gate that carried the bootstrap broke, the bootstrap went with
it, and **nothing announced the loss** — the operator had to notice and ask, session after session.

Interim mitigation already in place: the bootstrap block now lives at the TOP of
`fleet/state/PRIORITY-TODO.md` so it survives a broken generator. **Remove that block only when
this ticket lands and the generator is PROVEN to emit it.**

Done contract additions:
 1. `end-session.sh` MUST emit the copy-paste bootstrap one-liner as part of a successful close,
    pointing at PRIORITY-TODO.md and naming the current #1 queue item.
 2. FAIL-ON-REVERT: break the emission and prove the close REDs. A close that "succeeds" while
    producing no bootstrap is a silent partial success — the same false-green family as a
    registered cron job that never executes.
 3. ASSERT THE OUTPUT, NOT JUST THE EXIT CODE. This ticket's whole lesson is that a gate can run
    to completion and still fail to deliver what it exists to deliver. Check the artifact.
