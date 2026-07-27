# HANDOFF-PIPEFAIL — Fix the handoff.sh gate-masking bug

## Context
handoff.sh lines 59-60 run gates under `2>&1 | tail -3 || true`. This is the exact `| tail`
+ `set -e` masking pattern that handoff gotcha #14 warns about. The `|| true` defeats
`pipefail` and makes gate output non-fatal — a red gate (VERSION DRIFT, failing pytest) is
silently swallowed.

## Fix (build-rig, fleet repo)
In `/home/stack/charon-private/fleet/handoff.sh`, fix lines 59-60. Options:
(a) Capture the gate's own exit code before tail:
```bash
PYTHONPATH=src python3 -m pytest -q --no-header 2>&1 | tail -3 ; pytest_rc=${PIPESTATUS[0]}
ruff check src tests 2>&1 | tail -3 ; ruff_rc=${PIPESTATUS[0]}
[ $pytest_rc -ne 0 ] && echo "WARNING: pytest failed (rc=$pytest_rc)"
[ $ruff_rc -ne 0 ] && echo "WARNING: ruff failed (rc=$ruff_rc)"
```
(b) Drop `|| true` and let pipefail fail the script. (May be too aggressive for a
    handoff-generation script that should still produce output on gate failure.)
(c) Use `set -o pipefail` on those lines without `|| true`, but wrap in a subshell to
    avoid killing the whole script.

Recommended: (a) — capture exit codes, report warnings, don't kill the script (handoff.sh
should still generate output even if gates are red, but the output must NOT hide the
failure).

## Dependencies & sequence
No depends_on. Build-rig fix, not product.

## Gate
`bash /home/stack/charon-private/fleet/handoff.sh 2>&1 | grep -q "version OK\|VERSION DRIFT\|passed"`

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
