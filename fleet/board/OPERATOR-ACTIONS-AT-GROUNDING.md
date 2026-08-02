repo: charon-private
tier: economy
priority: 1
difficulty: 2
work_class: rig-meta
branch: fix/operator-actions-at-grounding
depends_on:
owns: fleet/hooks/session-start.sh, docs/review-log/OPERATOR-ACTIONS-AT-GROUNDING.md
serial_justified: |
  One print block in one hook. Nothing to split.
substrate: N/A
substrate-novel: |
  Nothing adopted or built — `pending.sh list` already exists and already formats the list. The
  novel slice is WHERE it is invoked: at grounding, unconditionally, rather than behind a noisy
  leg the session may never reach.
accept: |
  OPERATOR-DIRECTED 2026-08-02: the next session must surface the operator action list right after
  it grounds itself.
  MEASURED: `preflight.sh:909` DOES print the list — but that line sits BEHIND the reconcile-merged
  output, which ran to hundreds of lines on 2026-08-02 and starved every late leg; a 200s-capped
  preflight never reached it at all. And `fleet/hooks/session-start.sh` had ZERO references to
  pending.sh. **An action list the session does not see is an action list that does not exist** —
  operator action #15 (~10 commissioned review verdicts) went UNREAD for THREE sessions this way.
  Done contract:
  1. Print the list UNCONDITIONALLY and EARLY from the GIT-TRACKED session-start hook — tracked so
     a fresh clone or another box gets it (the F2 durability gap: doctrine is durable, its LOADING
     is not). DONE 2026-08-02, verified by running the hook.
  2. Guarded so it can NEVER block session boot; a `pending.sh` failure prints a WARN rather than
     failing silently.
  3. The session must REPORT it to the operator in its first substantive reply, not let it scroll
     past — and TRIAGE it, since most entries are stale. A noisy list is the mechanism by which the
     real entries get missed.
  4. Fail-on-revert: remove the block and prove a fresh session start no longer surfaces the list.

## Dependencies & Sequence

Lands FIRST and standalone. **FLEET-STATUS-BOARD's done-contract also wires into this same hook**
— it must take this file's ownership into account or declare a dependency edge, or the two collide
(the owns-overlap class). This ticket is small and immediate; FSB builds on top of it.
