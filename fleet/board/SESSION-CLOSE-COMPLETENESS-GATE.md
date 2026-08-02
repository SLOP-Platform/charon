repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/session-close-completeness-gate
depends_on: SESSION-END-GATE-REPAIR
real-dep: SESSION-END-GATE-REPAIR makes end-session.sh able to run at all (today it self-blocks); this gate is a new check ON that close path, so it must land second
owns: fleet/checks/session-close-completeness.sh, fleet/tests/session-close-completeness.test.sh
substrate: N/A
substrate-novel: |
  A meta-invariant over OUR OWN close path, board schema and marker dirs. Reuses every existing
  detector as an input — `validate_board.sh`, `stranded-work.sh`, `gate-integrity.sh`,
  `fleet/state/needs-push/`, `fleet/state/claims/`, `fleet/pending.sh`. It ADDS no detector; it
  asserts that a session cannot close while any of them has an unresolved finding.
serial_justified: |
  One assertion at one chokepoint. The individual detectors already exist and are separately owned.
source: |
  Operator, 2026-08-01: "session end needs a gate so that this (and all other issues we keep
  having) can't happen." Prompted by the manager recording TWO close-path defects in pending.sh
  and the handoff narrative WITHOUT minting board tickets — the same drop-on-close class the whole
  session was spent recovering from.
note: |
  ## THE CLASS — COMMITMENTS THAT DIE AT SESSION CLOSE
  Every recurring failure this session shares one shape: something REAL was identified, recorded
  somewhere non-durable, and lost when the session ended. Measured 2026-08-01:
  - **7 of 13** items on the manager's running list had NO board ticket — they existed only in
    session context and the handoff narrative.
  - The manager then added **2 MORE** untracked items at close (the end-session self-collision and
    the name-pool leak) — after having flagged the problem.
  - **GATE 4** (LETTA-REVIEW / MEMORY-LAYER-REVIEW verdicts) has now survived **THREE sessions**
    unread. `grep -c Letta EVAL-REGISTRY.md` = 0.
  - **4 operator-approved GATE 3 tickets** (SPAWN-VIA-CAPABILITY, ENGINE-CONVERGE, PRICING-FEED,
    ORCHESTRATION-RE-RUN) approved 2026-07-31 and STILL never staged; PRICING-FEED's
    operator-only content exists ONLY in one handoff file.
  - **41 of 350 tickets** were minted and NEVER dispatched; oldest 22 days.
  A note in a handoff is not a control. A ticket on the board is, because the pool can claim it.

  ## THE RULE — A SESSION MAY NOT CLOSE WITH UNTRACKED COMMITMENTS
  At close, RED on any of:
  1. **An open item on the session's running list with no board ticket.** This is the operator's
     "anything added to the list must first be ticketed" made mechanical rather than remembered.
  2. **Committed-but-unpushed work** anywhere (worktrees + both main checkouts), or a
     `fleet/state/needs-push/` entry that is unresolved and unmentioned in the handoff.
  3. **A claim marker with no live process** (phantom) — it will block dependents silently.
  4. **`validate_board.sh` RED** — never hand off a red board as green.
  5. **A handoff that does not pass `handoff-check.sh`.**
  6. **Unanswered `pending.sh` items** must be surfaced in the handoff, not merely present.

  ## HOW THE LIST IS MACHINE-READABLE (solve this first — it is the crux)
  The manager's running list currently lives in session context, which a gate cannot inspect.
  Options, in preference order: (a) require the handoff to carry a structured section the gate
  parses and cross-checks against `fleet/board/`; (b) a small on-disk list file the manager appends
  to, mirroring `pending.sh`'s append-only shape — **reuse `pending.sh`'s pattern rather than
  inventing a second store** [[no-rig-as-product-adopt-dont-handroll]]. Pick one and say why.
  If the list cannot be made machine-readable, the gate cannot enforce rule 1 — say so plainly
  rather than shipping a rule that silently checks nothing (that is the inert class).

  ## DO NOT
  - Do NOT make this unskippable-by-shouting. It must be a real exit code on the close path, wired
    to the same firing layer as SESSION-END-GATE-REPAIR — a warning that can be scrolled past is
    the advisory-gate pattern that decays.
  - Do NOT duplicate the detectors. Call `validate_board.sh`, `stranded-work.sh` and
    `handoff-check.sh`; do not re-implement their logic.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline, fixture board + repos:
    a. an open list item with no matching board ticket -> RED naming the item. Revert -> RED.
       **This is the defect that motivated the ticket.**
    b. committed-but-unpushed work in ANY checkout or worktree -> RED naming branch + count.
    c. a phantom claim (marker present, no live process) -> RED naming the ticket.
    d. a handoff failing `handoff-check.sh` -> RED.
    e. **ANTI-OVER-BLOCK**: a genuinely clean session closes GREEN. A gate that never permits a
       close will be bypassed within a day, which is worse than no gate.
    f. the gate FIRES on the real close path — prove it, do not merely register it.
  Then dogfood against this session's own end state and report what it would have caught.

D&S — Deps & Sequence:
  - After SESSION-END-GATE-REPAIR (that fixes the close path; this adds a check to it).
  - Composes with, and does not replace, WIP-CLOSE-GATE and SESSION-END-PUSH-GATE — read both
    before starting and fold rather than fork if they overlap.

## SCOPE EXTENSION 2026-08-02 (operator-directed): THE CLOSE GATE MUST COVER NON-GIT LOSS TOO

Operator: "can we make the session end gate cover things like this — make a session verify its
claims and save/ticket harness tasks?" Yes, and this ticket is the umbrella.

WHAT end-session.sh ASSERTS TODAY — all of it GIT-SHAPED: handoff exists (or regenerate),
handoff-check passes, no strandable work in second repos, stale-handoff guard. Every loss class it
knows about leaves a git artifact. The classes measured 2026-08-02 that it CANNOT see leave none.

THE ASSERTION LIST — a close is REFUSED unless every one passes, each naming what failed:

  A. HARNESS TASKS HAVE A DURABLE HOME  → owned by `TASK-LIST-DURABILITY-GATE` (minted 2026-08-02)
     Every OPEN harness task maps to a board ticket id, a fleet/pending.sh action, or an explicit
     `[DROPPED — reason]`. MEASURED: closed with 24 tasks / 15 open / SIX with no ticket. They
     survived only because the operator asked. No prior session's list can be inspected because
     none survived — that absence IS the evidence.

  B. THE SESSION VERIFIED ITS OWN CLAIMS  → the F9 rule, mechanized
     Every COMMAND written into the handoff must have been EXECUTED this session, with its result
     recorded. MEASURED: the first draft of the 2026-08-02 handoff carried two false claims —
     "a ppid of 1 = detached" (wrong; real detached tabs show a bash/timeout parent) and an
     inherited "monit is already adopted" (disproved by one `command -v`). An unverified procedure
     in a handoff is not guidance, it is a trap: the next session trusts it exactly as much as
     this one trusted the last.

  C. CADENCE LEG B  — every registered cron job has a FRESH heartbeat, not merely a crontab line.
     MEASURED: an 8-hour silent outage after a `| crontab` (missing `-`) replaced the table.

  D. NO INVISIBLE TICKETS  — `fleet/state/loop-guard/` is empty, or each entry is named with its
     reason. MEASURED: 8 tickets quarantined and invisible, including P0s minted the same day.

  E. NO STALE OPERATOR ACTIONS  — closed items retired. MEASURED: the list reached #33 and mostly
     closed, which is why action #15 went UNREAD for three sessions.

Done contract: implement A-E as named assertions in fleet/end-session.sh, each FAILING LOUD with
the specific unmet item. Fail-on-revert per assertion — seed the exact condition and prove the
close REFUSES. A close gate that passes silently is the same false-green family as a registered
cron job that never executes.

## Dependencies & Sequence

Depends on SESSION-END-GATE-REPAIR: the close path is self-blocking today (end-session.sh creates
its own target file, then the allocator refuses the name), so it ABORTS BEFORE any assertion runs.
Fix that first or every assertion added here is dead code. Assertion A is owned by
TASK-LIST-DURABILITY-GATE; land it independently and reference it here.
