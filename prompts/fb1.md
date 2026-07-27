Fix a FALSE-POSITIVE in the engine-stdlib-only boundary scan added by E0
(tools/check_boundary.py). It currently flags RELATIVE imports inside
src/charon/engine/ — e.g. `from .board import X`, `from ..ledger import Y` — as
"engine-stdlib-only" violations. Relative imports are intra-`charon` and MUST be allowed
(they are the repo's standard style — see coordinator.py `from .ledger import`).

FIX (tools/check_boundary.py): in the engine scan, treat any `ImportFrom` with `level >= 1`
(a relative import) as charon-internal → ALLOWED. Only flag ABSOLUTE imports whose
top-level package is neither stdlib nor `charon`. Genuine third-party absolute imports
(e.g. `import requests`) must STILL fail. The transitive `sys.modules` gateway test stays
as-is.

Add a regression test in tests/test_boundary.py: an engine-style file using
`from ..ledger import X` PASSES; one using `import requests` FAILS.

CONSTRAINTS: own ONLY tools/check_boundary.py, tests/test_boundary.py. Gate green every
commit (pytest, ruff check, mypy src tests, python3 tools/check_boundary.py src,
python3 tools/check_version.py). Stdlib-only. No secrets. Conventional commits. Open a
DRAFT PR base=master; do NOT merge. (This unblocks E1, whose code is correct.)

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
