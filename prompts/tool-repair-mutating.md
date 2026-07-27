# TOOL-REPAIR-MUTATING — Fix the allow_mutating NO-OP gate

## Context
The tool_repair module's `allow_mutating` flag is currently a NO-OP — it repairs mutating
tool calls regardless of the flag's value (HANDOFF-2026-07-04-v2 §3). MUST be fixed BEFORE
tool_repair is wired into the proxy.

## Fix
Add an `is_mutating` marker to the tool-call schema so the `allow_mutating` flag can
short-circuit: when `allow_mutating=False` and the tool call is mutating, skip repair
(pass through unchanged). When `allow_mutating=True` or the call is non-mutating, repair
normally.

The tool_repair.py module + tests already exist on `feat/tool-repair` (local commit
e06b193). This ticket may resolve by either:
(a) landing that branch's content via PR (preferred — it also has quota.py), or
(b) cherry-picking just the mutating-gate fix.

## Dependencies & sequence
No depends_on. Small, self-contained in tool_repair.py.

## Gate
`PYTHONPATH=src python3 -m pytest tests/test_tool_repair.py -v -q ; ruff check ; mypy src
tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`

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
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
