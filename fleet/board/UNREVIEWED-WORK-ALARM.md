repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 0
branch: feat/unreviewed-work-alarm
depends_on:
owns: fleet/checks/unreviewed-work.sh, fleet/tests/unreviewed-work.test.sh
serial_justified: |
  ONE alarm and its regression suite. The check without the suite is an unproven gate; the suite
  without the check has nothing to assert. The wiring is the point of the ticket — an alarm with
  no invocation site is the exact defect it exists to catch.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree.
source: |
  Operator question 2026-07-31: "why did you not do what you said you would do (monitor them,
  review them, then close them)? How can we mechanize so this doesn't keep happening?" Rec accepted.
note: |
  ## THE FAILURE THIS CLOSES
  Three P0 fixes finished and then sat unreviewed and unlanded for ~4 days while their worker tabs
  idled. One of the three was actively WRONG (a regression that reported the fleet IDLE while three
  workers ran). The manager had said it would monitor and land them, then ended its turn — a session
  cannot wake itself, so nothing resumed. Relying on an agent's stated intention is not a mechanism.

  ## THE DATA ALREADY EXISTS — THAT IS THE POINT
  `fleet/fleet-idle.sh` has always printed an "unlanded commits awaiting review" section, and it
  listed 23 branches while this was happening. A passive list that nobody is obliged to act on is
  not a control. The fix is to turn existing data into an AGED ALARM, not to collect new data.

  ## WHAT TO BUILD
  A check that goes RED on: branch has commits not in master, AND no live worker owns it, AND age
  exceeds a threshold. Surface it where the operator and every session already look (SessionStart /
  preflight), with the age and the branch named.

  REUSE, DO NOT REBUILD: `fleet/reconcile-stale-claims.sh` (landed PR #273) already has the
  dead-vs-live worker predicate and a stale threshold. `fleet/fleet-idle.sh` already enumerates
  unlanded branches. Do NOT introduce a second notion of liveness — the bridge also computes
  `stalled`/`stall_seconds`. Compose the existing three; write as little new code as possible.

  ## GUARDS
  - Advisory-vs-blocking is a real decision: a RED that blocks all work on 23 pre-existing branches
    would get disabled, and a gate that gets disabled is a gate that does not run. Propose the
    threshold and the escalation, and say which existing branches would fire on day one.
  - Fail closed on "cannot determine", but never so loudly that the alarm is noise.

D&S — Deps & Sequence:
  - Depends on: nothing. reconcile-stale-claims.sh and fleet-idle.sh are landed in master.
  - Blocks: nothing structurally; it is the guard that prevents finished work from being stranded.
  - Sequence: independent of the bridge migration and the research lanes.
