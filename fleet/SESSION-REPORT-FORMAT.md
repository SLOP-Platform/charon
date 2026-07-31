# SESSION REPORT FORMAT v1 — the mechanized handoff from a worker session to the manager

**Every session ends by emitting exactly this block.** Fixed fields, fixed order, one line each.
~16 lines. Machine-greppable, human-skimmable, and complete enough that the manager never has to go
digging in worktrees to find out what happened.

## THE BLOCK

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <path,path,...>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <one-line detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING, one line>
READ:         <what you concluded by READING only, one line>
BRIEF-ERRORS: none | <what the brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why (request cap, timeout, context)>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```

## WHY EACH FIELD EXISTS (every one is paid for by a real 2026-07-26 failure)

- **COMMIT** — the manager repeatedly had to inspect worktrees to discover work had been committed.
  Two completed tickets sat unnoticed for hours.
- **FILES + OWNS-OK** — a session edited `gateway.py` (4 claimants) because the brief forgot to
  forbid it. Self-declaring the owns check surfaces collisions at report time, not at merge time.
- **RED-PROOF (both exit codes)** — "a green you did not first make fail is not evidence." Reporting
  only the green run hides whether the test can fail at all.
- **OBSERVABLE** — THE most important field. Three tickets merged with done-contracts requiring proof
  on the LIVE gateway; none delivered it and nothing noticed. A session that cannot reach the live
  system must say DEFERRED and say why, so the debt is visible instead of assumed paid.
- **RAN vs READ** — separates verification from inference. Cheap to write, expensive to reconstruct.
- **BRIEF-ERRORS** — the highest-value field in practice. On 2026-07-26 sessions caught: two
  nonexistent files in an OWNS clause, a ticket whose work already existed, a wrong premise about
  `upstream_model`, and a command that could not run. **The brief is wrong more often than the
  session is.** Silence here loses that signal.
- **BUDGET** — added 2026-07-26. A session hit `ResourceExhausted: Worker local total request limit
  reached (48/48)` and reported `STATUS: DONE`. A hard per-session request ceiling silently converts
  "derive it" into "assert it": the cheapest satisfying implementation wins when budget is short, and
  nothing in the report says so. If you ran out of anything — requests, context, time — say
  TRUNCATED and name what you skipped. A shortcut you declare is a finding; one you hide is a defect.
- **BLOCKED-BY / NEXT** — turns a report into a dispatch decision without a follow-up round-trip.

## RULES
- Emit the block even when STATUS is BLOCKED or REFUSED — **especially** then. A session that
  correctly refuses bad work produces the most valuable report of all; a silent exit produces none.
- No diffs, no logs, no code in the block. Pointers only. Long-form goes to a handoff-note file and
  is referenced from NEXT.
- Never leave a field out. `n/a` with a reason is a valid value; absence is not.
- Do not pad. One line per field. If it does not fit on one line, it belongs in a handoff note.
