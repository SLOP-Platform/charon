# DTC-1 — gate registry + self-validator

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `tools/gates.json` + `tools/check_gate_registry.py` ALREADY BUILT.
No file overlap with any other ticket → runs CONCURRENTLY with all Wave-1 tickets. Confirm files exist
and the checker passes clean.

## Why
`tools/gates.json` is the machine-readable register of every active validation rule (gates, checks,
structural rules, CI steps). The checker (`tools/check_gate_registry.py`) validates that every rule
has a living enforcer, that no two rules cover the same domain, and that `@covers:` annotations in
tool files match the registry. This is the source of truth for Rule 5 and Rule 6 — before writing any
new test or gate, consult this registry.

## What to build
- ALREADY BUILT. Verify:
  - `tools/gates.json` exists and contains entries for all existing gates
  - `tools/check_gate_registry.py` exists and passes clean (`python3 tools/check_gate_registry.py`)

## Acceptance
- `python3 tools/check_gate_registry.py` exits 0 with "check_gate_registry: OK"
- `tools/gates.json` is valid JSON and contains at least 10 gate entries
- All gate entries have id, domain, and enforcer fields

## CONSTRAINTS
Own ONLY: `tools/gates.json`, `tools/check_gate_registry.py`. Already built — confirm, don't create.
Stdlib core only; gate GREEN. Conventional commits; review note → `docs/review-log/DTC-1.md`.

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
