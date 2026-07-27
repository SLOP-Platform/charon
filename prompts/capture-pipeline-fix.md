# BRIEF — capture-pipeline: FIX 3 review defects (the HIGH one caused live damage)

The false-success detector itself is correct — do NOT rewrite it. Fix the 3 defects below. This is
integrity-critical; a non-hermetic test already polluted a live artifact, so hermeticity is the top fix.

## Where you are
- Worktree on branch `feat/capture-pipeline` (@0264a77) of the charon-private rig. Fix in place, commit. No push/merge.
- READ the review (authoritative): `/home/stack/charon-private/fleet/state/overnight/CAPTURE-PIPELINE-REVIEW.md`.

## Fix
- **HIGH #1 — HERMETIC TESTS (caused real damage):** the capture handler writes the versioned `scorecard.vN.json` (and the `.tsv`) via HARDCODED live paths with no test override, so the suite wrote 61 fake rows into the LIVE `fleet/benchmark/scorecard.v1.json`. Make EVERY test write ONLY to a scratch path: add an explicit path override (env var e.g. `SCORECARD_DIR` / function param) threaded through the handler AND the `.vN.json` writer; tests MUST set it to a tmp dir and NEVER touch `fleet/benchmark/scorecard.*`. Prove (in the report) that a full test run leaves the real `fleet/benchmark/` untouched. ALSO: the `.vN.json` sits OUTSIDE the bench-grader tamper boundary — bring it inside (written only by the daemon-as-bench-grader path, same as the `.tsv`), so tamper-resistance covers BOTH files, not just the `.tsv`.
- **MED #2 — emit-verdict.sh:159** hardcodes `claimed=SUCCESS`, so an honest non-SUCCESS claim gets mislabeled FALSE-SUCCESS. Carry the ACTUAL claimed_result from the provisional record / harness, not a constant.
- **MED #3 — provisional→active pairing is dead:** a fresh `run_id` is minted per enqueue so FINAL never pairs with its PROVISIONAL and provisionals orphan. Use a STABLE correlation key (ref/run) so the FINAL capture matches its PROVISIONAL and promotes it.

## Do NOT
- Do NOT write the live scorecard, do NOT restart the grader daemon, do NOT push/merge.
- The 61 already-injected junk rows in the live scorecard.v1.json are cleaned by the MANAGER separately — don't touch the live file.

## LAST STEP
- Hermetic test run pipe-free: `python3 -m pytest <tests> -q; echo "EXIT=$?"` → 0, AND show `fleet/benchmark/scorecard.*` is unchanged after the run. Fail-on-revert intact for the detector.
- Commit on `feat/capture-pipeline`; report SHA. Do NOT push/merge (separate line).
- Write `/home/stack/charon-private/fleet/state/overnight/CAPTURE-PIPELINE-FIX-REPORT.md`: the 3 fixes (file:line), the hermeticity proof (real `git status`/diff of fleet/benchmark after a test run = clean), gate/pytest EXIT, SHA.
- Print `PACKET: <report path>` + ≤8-line honest summary. Real outputs only.

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
