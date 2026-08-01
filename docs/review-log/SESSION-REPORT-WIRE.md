# SESSION-REPORT-WIRE — review/decision fragment

## What this ticket ships

The SESSION REPORT v1 format (defined in `fleet/SESSION-REPORT-FORMAT.md`, validated by
`fleet/check-session-report.sh`) was BUILT BUT INERT for droids — the validator existed but
the format spec was never asked of droids. The fix is a WIRE, not a build:

* `fleet/fleet-droid.sh` now defines an `emit_session_report` function that DERIVES ~11 of the
  16 v1 fields MECHANICALLY from facts the launcher already holds (ticket id, droid+model, the
  gate's real exit code, git diff, the model's `CHARON_RUN_RESULT`).
* The function writes the block to `fleet/state/reports/<droid>-<ticket>.md` AND echoes it on
  stdout so the caller can append it to the PR body.
* `fleet/JOIN-PROMPT.md` now asks the model for ONLY the 5 judgment fields
  (OBSERVABLE / RAN / READ / BRIEF-ERRORS / NEXT) via a partial-block file at
  `state/judgment/<droid>-<id>.md`. A missing file is filled with `NOT-REPORTED` — explicit
  sentinel, never a silent blank line.
* The launcher runs the gate itself, just before submitting, to obtain the REAL exit code.
  The report's `GATE:` field is grounded in the launcher's observation, not the model's claim.
* ANTI-OVER-BLOCK: a droid that emits a FULL valid v1 block keeps its judgment fields verbatim.
  Both blocks live in the report file; a STATUS or GATE disagreement is flagged as
  `MODEL-LIE-FLAG:` (the highest-value signal the wire produces — feed it to
  auto-log-model-lies).
* Failure path: a session that exited non-zero (charon-run.sh returned !=0) also writes a
  BLOCKED report — "the most valuable report of all" per the format spec.

## RED-PROOF evidence

`fleet/tests/session-report-wire.test.sh` runs 44 assertions across 7 scenarios; the FAIL-ON-REVERT
class catches a hardcoded `GATE: PASS` (b.revert1/2) and a missing function definition. The
test extracts the inline function from `fleet-droid.sh` via awk, then exercises it against a
hermetic temp git repo + worktree. All 44 pass; reverting any derivation REDs the matching
assertion.

Two pre-existing pytest failures
(`fleet/capability/tests/test_tier_classify.py::test_live_board_drift_is_exactly_the_pending_retiers`,
`fleet/tests/test_capture_pipeline.py::test_flaw1_provisional_then_final_same_run_id_distinct_filenames`)
are unrelated to this work — verified by stashing the changes and re-running against
`origin/master`: identical failures. Not caused by this wire.

## Decisions worth recording

1. **Launcher runs the gate itself, in addition to the model's run.** Two runs of the gate per
   session is a non-trivial cost (the gate is the whole CI suite). The alternative was to
   trust a marker file the model writes, but the ticket's whole point is that "the gate's real
   exit code" must be the launcher's own observation, not a model attestation. A model that
   knows its gate went red and writes `gate_exit=0` to a marker file would silently invert
   the wire's premise. Cost vs integrity: integrity wins. A `state/skip-launcher-gate/<id>`
   marker remains as the operator escape hatch.

2. **NOT-REPORTED as a sentinel, not a blank line.** The format spec says "Never leave a field
   out" but also "Silence must never render as a blank line." `NOT-REPORTED` is greppable and
   greps distinctly from a model that WROTE nothing. A real "not-reported" is a model that had
   nothing to say; the sentinel signals "this is the launcher's fallback, not a model
   assertion."

3. **Both blocks kept verbatim on conflict.** The ticket is explicit ("keep BOTH and flag the
   conflict. Do not silently prefer one"). A `STATUS: DONE` over a derived `GATE: FAIL` is the
   canonical self-report lie — the manager needs to see BOTH the model's claim AND the
   derived truth side-by-side, not have the launcher choose for them.

4. **Failure-path report writes STATUS=BLOCKED, GATE=NOT-RUN** (exit code 125). The model's
   transcript may be empty/garbled when charon-run.sh exits non-zero; recording the report with
   `GATE=NOT-RUN` distinguishes "the gate failed" (the launcher ran it) from "no gate was
   run" (charon-run.sh failed first). The sentinel makes the two cases tellable apart.

5. **Five judgment fields, not three, not eight.** The ticket's note splits 16 fields into 11
   mechanical and 5 judgment. The 5 are: OBSERVABLE (did you observe your claim?), RAN (what
   you EXECUTED), READ (what you INFERRED from READING), BRIEF-ERRORS (a free-text audit of the
   ticket itself — the highest-value field per the format spec), NEXT (the dispatch decision).
   These are the ones that benefit from a model's judgment; the rest are derivable facts.

## Out of scope (recorded, not re-litigated)

* Changing the v1 format's 16 fields. The ticket reuses them as-is.
* Rewriting `check-session-report.sh`. The validator is reused unchanged.
* Adding a new field. A separate ticket.
* Block-or-warn: rejected in the ticket note and rejected here. The wire IS the response,
  not a softer version of it.