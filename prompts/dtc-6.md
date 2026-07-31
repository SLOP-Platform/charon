# DTC-6 — parametrize sweep for test files

## Dependencies & sequence
**depends_on: DTC-2, DTC-3 — Wave 2.** Depends on DTC-2 (shared HTTP fixtures in conftest.py) and
DTC-3 (meta-tests replacing 22+ individual tests) so the new shared infrastructure and meta-tests are
in place first. Owns `test_fence.py`, `test_failover.py`, `test_decompose.py`. These files are
DISJOINT from all Wave-1 tickets → safe once dependencies land.

## Why
Several test files have pattern-repeating test functions where 5-10 nearly-identical test bodies
differ only in a policy name, failover scenario, or decompose variant. These are maintenance drag:
changing the assertion logic means editing N copies, and adding a new variant means copying the
entire function. Converting to `@pytest.mark.parametrize` collapses N redundant functions into 1,
makes the test matrix explicit and self-documenting, and ensures new variants get tested
automatically.

## What to build
- Convert pattern-repeating test functions to `@pytest.mark.parametrize`:
  - `tests/test_fence.py`: 7 separate per-policy test functions → 1 parametrized test with a
    policy-name parameter list
  - `tests/test_failover.py`: collapse redundant failover-scenario tests into parametrized form
  - `tests/test_decompose.py`: collapse redundant decompose-variant tests into parametrized form
- Mechanical conversion only — no test assertion changes, no new coverage.
- Ensure parametrized test names are readable: `pytest --collect-only -q` should show each
  parameter value as a distinct test case.

## Acceptance
- `PYTHONPATH=src python3 -m pytest -q tests/test_fence.py tests/test_failover.py tests/test_decompose.py` passes.
- Each file shows the same number of test cases collected before and after (same coverage, fewer
  function definitions).
- Full test suite still GREEN.
- No src/ files touched.

## CONSTRAINTS
Own ONLY: `tests/test_fence.py`, `tests/test_failover.py`, `tests/test_decompose.py`. Mechanical
conversion only — do NOT change assertions, add new tests, or touch other files. Must use shared
fixtures from DTC-2 where applicable. After DTC-3 lands, ensure no "no token" or auth tests remain
in these files (they're subsumed by the meta-tests). Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/DTC-6.md`. BACKLOG (parked).

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
