# DTC-2 — shared HTTP test infrastructure

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `tests/conftest.py` + `tests/test_shared_http.py` (new). These
test-only files are DISJOINT from every other backlog ticket → safe to run CONCURRENTLY with all
other Wave-1 tickets.

## Why
Seven test files (`test_setup_web.py`, `test_connect.py`, `test_connect_gui.py`,
`test_console_provider_mgmt.py`, `test_routing_proxy.py`, `test_gateway.py`,
`test_gateway_tiers.py`) each define their own mock HTTP upstream server using the same pattern:
a `http.server.HTTPServer` + `RequestHandler` in a background thread, with identical boilerplate for
setup/teardown, request logging, and per-route response stubbing. This creates ~200 lines of
duplicated code, makes all tests slower to write, and means any improvement to the mock (thread
safety, error injection, response assertion helpers) must be replicated 7 times. Consolidating into
shared `conftest.py` fixtures is a pure test infrastructure improvement — zero risk to production
code.

## What to build
- Define reusable pytest fixtures in `tests/conftest.py`:
  - A `mock_http_server` fixture that starts a configurable HTTP server in a background thread,
    returns the server + base URL, and tears down cleanly after the test.
  - A `mock_http_client` fixture that provides a pre-configured `urllib.request` opener pointed at
    the mock server.
  - Request-logging and response-stubbing helpers as thin wrappers over `http.server`.
- Add `tests/test_shared_http.py` that exercises the fixtures themselves (smoke test: can start,
  respond, log, and stop).
- Migrate ONE existing test file (`test_routing_proxy.py`) to use the shared fixtures as proof
  that the pattern works. Remove duplicated inline mock server code from that file.
- Target: eliminate ~200 lines of duplicated mock server boilerplate across 7 files (this ticket
  only does 1 migration as proof; the remaining 6 files are a separate follow-on ticket).

## Acceptance
- `PYTHONPATH=src python3 -m pytest -q tests/test_shared_http.py` passes.
- `test_routing_proxy.py` migrated to use shared fixtures; full suite still GREEN.
- The shared fixtures are documented: parametrize a test with different route tables, verify each
  gets a correctly-configured mock.
- No src/ files touched.

## CONSTRAINTS
Own ONLY: `tests/conftest.py`, `tests/test_shared_http.py`. Read-only on `test_routing_proxy.py`
being migrated — only remove its duplicated inline mock server code; do NOT change test assertions
or add new coverage. Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/DTC-2.md`. BACKLOG (parked).

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
