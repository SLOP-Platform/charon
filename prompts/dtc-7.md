# DTC-7 — automated security audit gate

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `tools/check_security.py` (new) + `tests/test_check_security.py`
(new). New files with zero overlap against any other ticket → safe to run CONCURRENTLY with all other
Wave-1 tickets.

## Why
Security anti-patterns accumulate silently: a bare `except:` swallowing errors, a hardcoded hostname
that slips past review, a `subprocess.run(shell=True)` added during a quick fix. These are caught
today by human review or not at all. An automated security gate that scans every commit catches these
before they reach production, provides clear diagnostics, and fails the build. This complements the
no-secrets meta-test (DTC-3) — this tool scans SOURCE, DTC-3 scans RUNTIME output.

## What to build
- `tools/check_security.py` — scans `src/` for security anti-patterns:
  (a) Bare `except:` or overly broad `except Exception` without `logging.exception()` or re-raise
  (b) Secrets/tokens in source files (API key patterns, token patterns)
  (c) Hardcoded IP addresses or hostnames in `src/` (catch things like `"10.0.0.1"`,
      `"example.internal"`)
  (d) `eval()` and `exec()` usage and `subprocess.run(... shell=True)` patterns
- `tests/test_check_security.py` — red-proof tests that prove the checker CAN fail:
  - Create a temp file with a bare `except:` and verify the checker flags it
  - Create a temp file with a hardcoded IP and verify the checker flags it
  - Verify clean codebase passes
  - Test each pattern (a)-(d) independently with positive and negative cases
- Exit 0 on pass, exit 1 on violation with clear file:line:pattern diagnostics.
- Register the gate in `tools/gates.json` (domain: "security").

## Acceptance
- `python3 tools/check_security.py src` exits 0 on current codebase
- Each anti-pattern (a)-(d) has a red-proof test that causes the checker to fail
- Introducing a bare `except:` in a random `src/` file causes the checker to fail with the exact
  file and line number
- Gate is registered in `tools/gates.json` with id, domain, enforcer, and invariant fields
- No src/ files touched except what the checker scans

## CONSTRAINTS
Own ONLY: `tools/check_security.py`, `tests/test_check_security.py`. Read-only on `src/` — only
scan, never edit. Must register the gate in `tools/gates.json` (add one entry). Stdlib core only;
gate GREEN (`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3
tools/check_boundary.py src ; python3 tools/check_version.py`). Conventional commits; review note →
`docs/review-log/DTC-7.md`. BACKLOG (parked).

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
