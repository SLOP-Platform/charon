You are a SMOKE-TEST droid validating the charon-fleet harness end-to-end. Do the MINIMUM to prove the loop works — nothing more. This is throwaway; do not do real work.

1. Make your worktree per the JOIN-PROMPT step 1, on branch chore/fleet-smoke.
2. Create a single file `FLEET-SMOKE.md` at the repo root containing one line:
   `charon-fleet smoke test OK`
3. Commit it: `git add FLEET-SMOKE.md && git commit -m "chore: fleet smoke test"`.
4. Do NOT run the gate, do NOT open a PR, do NOT push (this is a local-only smoke).
5. Run: `bash /home/stack/charon-private/fleet/submit.sh SMOKE`
6. STOP. Print one line: "SMOKE OK". The operator will delete the worktree + branch.

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
