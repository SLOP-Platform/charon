# DTC-5 — architecture layer audit tool

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `tools/check_arch.py` (new) + `tests/test_check_arch.py` (new).
New files with zero overlap against any other ticket → safe to run CONCURRENTLY with all other Wave-1
tickets.

## Why
Charon's architecture has invariants that are enforced by convention today but not by automation:
engine/ and gateway/ must be isolated from each other, the stdlib-only core must have zero third-party
imports, and no vendor/provider names may be hardcoded in engine/ or gateway/. A single check_arch.py
tool that validates these invariants catches regressions before they reach review, prevents circular
imports from creeping in, and keeps the codebase product-clean as it scales.

## What to build
- `tools/check_arch.py` — validates these architectural invariants:
  (a) `src/charon/engine/` never imports from `src/charon/gateway/` or `src/charon/proxy_server/`
  (b) `src/charon/gateway/` never imports from `src/charon/engine/`
  (c) No circular imports between any layers under `src/charon/`
  (d) The stdlib-only core (files under `src/charon/` that claim to be stdlib-only) has zero
      third-party imports
  (e) No vendor/provider names hardcoded in `src/charon/engine/` or `src/charon/gateway/`
      (product-clean — catch things like "openai", "anthropic", "google" as string literals)
- `tests/test_check_arch.py` — red-proof tests that prove the checker CAN fail:
  - Inject a forbidden import and verify the checker flags it
  - Verify clean codebase passes
  - Test each invariant (a)-(e) independently
- Exit 0 on pass, exit 1 on violation with clear path-and-line diagnostics.

## Acceptance
- `python3 tools/check_arch.py src` exits 0 on current codebase
- Each invariant (a)-(e) has a red-proof test that causes the checker to fail
- Introducing a forbidden import (e.g., `from ..gateway import foo` in an engine/ file) causes
  the checker to report the violation with the exact file and line
- No src/ files touched except what the checker validates

## CONSTRAINTS
Own ONLY: `tools/check_arch.py`, `tests/test_check_arch.py`. Read-only on `src/` — only scan, never
edit. Stdlib core only; gate GREEN (`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src
tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`). Conventional commits;
review note → `docs/review-log/DTC-5.md`. BACKLOG (parked).

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
