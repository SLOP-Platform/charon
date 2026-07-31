# DTC-3 — meta-tests: no-secrets + auth parametrized

## Dependencies & sequence
**depends_on: DTC-2 — Wave 1, after DTC-2.** Depends on DTC-2 for the shared HTTP test fixtures
in `conftest.py` (needs a running gateway test server). Owns only `tests/test_no_secrets.py` (new) +
`tests/test_auth_meta.py` (new). DISJOINT from every other backlog ticket → safe once the shared
fixtures land.

## Why
Fifteen-plus tests scattered across the test suite check that specific response bodies, CLI outputs,
or log lines do not contain a hardcoded token or API key. Seven-plus tests verify that specific write
endpoints reject unauthenticated requests with 401. Each of these tests is a point fix: it catches
exactly one surface × one secret pattern or one endpoint. Adding a new endpoint means writing new
tests — and forgetting means a regression goes undetected. Two property-based meta-tests that
enumerate every surface/endpoint from a centralized list are more robust, less code, and catch
future leaks automatically. Together they replace 22+ individual tests.

## What to build
- **`tests/test_no_secrets.py`** — single parametrized test:
  - Define `_KNOWN_SECRET_PATTERNS`: regex patterns for gateway tokens, upstream API keys, bearer
    tokens (>32 chars of `[A-Za-z0-9+/=]`), and any literal token values used in test fixtures.
  - Enumerate output surfaces: every HTTP response body from the gateway (`/v1/models`,
    `/v1/chat/completions`, `/charon/*` endpoints), CLI stdout/stderr from `charon --help` and
    dry-run modes, and any log files written during test setup.
  - Assert: for every `<surface, body>` pair, zero regex matches against any pattern in
    `_KNOWN_SECRET_PATTERNS`.
- **`tests/test_auth_meta.py`** — single parametrized test:
  - Define `_WRITE_ENDPOINTS`: list of `(method, path)` tuples for every Charon write endpoint
    (POST/PUT/DELETE at paths under `/charon/`). Derive from the actual route table if possible,
    or maintain as an explicit list near route definitions.
  - For each `(method, path)`, send unauthenticated request and assert 401.
- Once both tests pass, REMOVE the 22+ individual "no token" and "auth" tests from other test
  files (since these meta-tests cover them all).

## Acceptance
- `PYTHONPATH=src python3 -m pytest -q tests/test_no_secrets.py tests/test_auth_meta.py` passes.
- All 22+ subsumed individual tests removed; full suite still GREEN.
- Introducing a deliberate secret leak causes the no-secrets test to fail with a clear message.
- Adding a new write endpoint to the list without auth middleware causes the auth test to fail.
- No src/ files touched.

## CONSTRAINTS
Own ONLY: `tests/test_no_secrets.py`, `tests/test_auth_meta.py`. Read-only on the other test files —
only remove "no token" and auth assertions subsumed by the meta-tests; do NOT change any other test
logic. Must use the shared fixtures from DTC-2 (`conftest.py`). Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/DTC-3.md`. BACKLOG (parked).

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
