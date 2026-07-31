# SESSION — CONFIRM-FIRST: six gateway modules with zero invocation sites (wire or retire)

**Model:** a NON-ANTHROPIC model through the Charon gateway. Never Claude/Anthropic.
Graded sample, work_class `design-review`.
**You are INVESTIGATING. Do NOT change product code. Do NOT retire anything.**

## FIRST ACTS
0. **Claim your session name MECHANICALLY — do not invent one.** Names collide when models pick
   them; use the allocator (atomic, claim-before-build):
   ```
   NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"
   echo "claimed: $NAME"
   ```
   Then `session-bridge_register(session_id="<the claimed NAME>", name="DEAD GATEWAY MODULES confirm",
   repo="charon", ticket="DEAD-GATEWAY-MODULES", status="in-progress", model="<your model>")`.
   **Never reuse a name you see on the board — those sessions are LIVE.**
   Then `session-bridge_update` every ~5 min as a HEARTBEAT (600s lease, else you are purged).
1. Read the construction site: `git -C /home/stack/code/charon show HEAD:src/charon/gateway.py | sed -n '250,300p'`
   That checkout is the MANAGER's — read only, never edit or branch there.

## THE CLAIM TO CONFIRM OR REFUTE
Six modules are constructed at `src/charon/gateway.py:258-296` and reportedly have **ZERO invocation
sites**:

    RequestInspector · SessionAffinity · Observability
    SpeculativeExecutor · ConsensusRouter · VirtualKeyManager

The operator has approved retiring dead ones **but requires confirmation first**, because three of
those names — `SpeculativeExecutor`, `ConsensusRouter`, `SessionAffinity` — describe ROUTING
behaviour that someone may believe is live. Retiring a module that is actually load-bearing, or
leaving inert code that people think is protecting them, are both real failures.

## WHY YOU MUST NOT PATTERN-MATCH
**A zero-hit grep is NOT evidence a thing is unused.** Invocation survives renaming, aliasing,
re-export, dynamic dispatch, registry lookup, config-driven construction, and `getattr`. This exact
error was made twice in this project today. Use the owned tooling and READ the call sites:
- `graphify explain "<ClassName>"` and `graphify path "<A>" "<B>"` — the code graph is refreshed at
  session start and is the right tool for "is X reachable".
- `tools/check_inert_code.py` — purpose-built for built-but-dead detection. Run it and report output.
- Then open the construction site and follow the object: is it stored on the server, passed anywhere,
  read by any handler, referenced in config, or exposed on an endpoint?

## FOR EACH OF THE SIX, PRODUCE A VERDICT
Exactly one of:
- **LIVE** — it is invoked. Show the path from a request to the module. Retiring it would break X.
- **INERT-RETIRE** — constructed, never used, and nothing depends on its existence. Say what removing
  it would change (should be: nothing) and how you proved nothing calls it — naming the tool and the
  evidence, not just "no grep hits".
- **INERT-WIRE** — it is dead but SHOULD be live: it implements something the system claims to do.
  This is the important category. If `ConsensusRouter` or `SpeculativeExecutor` is dead while docs,
  ADRs, or config imply the behaviour exists, that is a silent capability gap, and retiring it would
  quietly delete an intended feature. Say what it was meant to do and where that intent is recorded.

For each, also answer: **does anything in docs/ ADRs/ config/ the console claim this behaviour is
active?** A user-visible claim backed by dead code is the worst outcome of the three.

## RULES
- **Do NOT edit `src/charon/gateway.py`.** It is owned by TWO live tickets (GATEWAY-NONTOKEN-METERING,
  WIRE-GRADING-PRIOR-LIVE) and two parked ones. You would be a third concurrent writer.
- **Do NOT delete or retire any module.** You produce a ruling; the operator disposes.
- You own ONE output file (below). No other file may be modified.
- Every verdict: `file:line` + the tool and evidence that produced it + what breaks if wrong.
- State explicitly what you verified by RUNNING vs by READING.
- If a module is ambiguous, say AMBIGUOUS and explain — a wrong RETIRE verdict deletes working code.

## REPORT BACK
Write to `/home/stack/charon-private/fleet/handoff-notes/DEAD-GATEWAY-MODULES-RULING.md`.
Your reply: file path + <=10 lines — the six verdicts one line each, and flag loudly any module in the
INERT-WIRE category (dead code implementing a behaviour we claim to have).

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
