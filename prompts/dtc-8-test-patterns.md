# DTC-8 — test-pattern enforcement gate

## Dependencies & sequence
**depends_on: NONE — Wave 2.** Owns `tools/check_test_patterns.py` (new) + `tests/test_check_test_patterns.py` (new).
No file overlap with any other ticket → runs CONCURRENTLY with all other Wave-2 tickets.

## Why
Test quality drifts silently: functions lose docstrings, parametrization opportunities are missed,
duplicate function names cause silent coverage gaps, and bloated test bodies resist later refactoring.
An automated gate catches these before they accumulate. This complements the structural hygiene rules
(Rule 1–Rule 4) by enforcing test-specific patterns on every commit.

## What to build
- `tools/check_test_patterns.py` — scans `tests/test_*.py` for:
  (a) Duplicate test-function names within the same file (ERROR — module-level shadowing)
  (b) Missing docstring on test functions (WARNING — "class of bug" philosophy, Rule 5)
  (c) Parametrize ratio < 1 per 10 test functions (WARNING — encourages parametrization, Rule 7)
  (d) Test function body exceeding 50 lines (WARNING — suggests parametrization opportunity)
- `tests/test_check_test_patterns.py` — red-proof tests that prove the checker CAN fail:
  - Create a temp file with duplicate test function names and verify detection
  - Create a temp file with missing docstrings and verify the warning fires
  - Create a temp file with low parametrize ratio and verify the warning fires
  - Verify a clean file passes with no errors or warnings
  - Verify line-count warning on a >50-line test function
- Register the gate in `tools/gates.json` (domain: "test", id: "test-patterns").
- Exit 0 on clean (no errors), exit 1 on error violations. Warnings are printed but don't
  affect exit code unless `--strict` is passed.

## Acceptance
- `PYTHONPATH=src python3 -m pytest -q tests/test_check_test_patterns.py` passes
- Each check (a)-(d) has a red-proof test that triggers the checker
- `python3 tools/check_test_patterns.py tests/` exits 0 on the current codebase
  (warnings are printed but exit 0 since only duplicate names count as errors)
- Gate is registered in `tools/gates.json` with id, domain, enforcer, and invariant fields

## CONSTRAINTS
Own ONLY: `tools/check_test_patterns.py`, `tests/test_check_test_patterns.py`.
Stdlib core only (AST, pathlib, sys, re). Must register the gate in `tools/gates.json`
(add one entry). Gate GREEN (`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ;
python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/DTC-8-TEST-PATTERNS.md`.

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
