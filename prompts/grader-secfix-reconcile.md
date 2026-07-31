# GRADER-SECFIX-RECONCILE

Reconcile the VERIFIED security-hardened grader (`feat/bench-oob-grading @ e879957`) into the canonical
grader on the active RIG branch. Both `feat/bench-oob-grading` and `feat/fragility-tickets` edited
`fleet/benchmark/grader-daemon.py` + `graders/reds_replay.py` + `selftest/test_grader_daemon.py` after
their shared base `b14f084`, so a plain cherry-pick conflicts (add/add on the test file).

## MANDATORY — the security fixes MUST survive (non-negotiable)
- **F1** path traversal → the `_confine()` / `SandboxError` sandbox (`os.path.realpath` confinement; rejects
  `../` escape and absolute paths that discard the root).
- **F2** shell injection → `subprocess.run(argv, shell=False, ...)` (argv list, never a shell string).
- **F5** false-green → pre-fix baseline must FAIL; a curated red already green pre-fix scores 0, not 100.
- The 3 fail-on-revert security tests (`test_F1_path_traversal_rejected`, `test_F2_shell_injection_neutralized`,
  `test_F5_false_green_already_green_scores_zero`) must remain and still go RED when their guard is reverted.

## TASK
1. Diff the two lineages: `git diff feat/fragility-tickets..feat/bench-oob-grading -- fleet/benchmark/`.
2. Produce ONE reconciled grader-daemon.py / reds_replay.py / test_grader_daemon.py that keeps the
   security-hardened versions for all security-relevant paths AND any fragility-branch grader improvements
   worth keeping. Security-hardened version WINS on any security-relevant conflict.
3. Land on the active RIG branch. Retire `feat/bench-oob-grading` once merged.

## VERIFY BEFORE COMMIT
`cd fleet/benchmark && PYTHONPATH=. python3 -m pytest selftest/test_grader_daemon.py -q` all green, then
run the fail-on-revert proof on F1/F2/F5 and confirm each goes RED on guard-revert.

## Dependencies & sequence
- **depends_on:** BENCH-OOB-GRADING (shared `fleet/benchmark/grader-daemon.py`, `graders/`, `selftest/` —
  reconciles the two lineages that both edited those files after base `b14f084`).
- **wave:** immediately after BENCH-OOB-GRADING (this is its last mile; it gates real benchmark scoring).
- **concurrency safety:** single-writer on `fleet/benchmark/` — must NOT run concurrently with any other
  grader/benchmark ticket touching those files. Retire `feat/bench-oob-grading` once merged.

## LAST STEP (required)
Commit with the reconcile message + print the SHA.
Do NOT push. Do NOT merge to master.

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
