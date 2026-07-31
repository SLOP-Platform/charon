# BENCH-REGROUND-LIVE — Re-ground the grades brain on live actuals (pivot A2)

RIG-ONLY (fleet repo). This never ships in the Charon product.

## Context
The real-outcomes pivot is CONFIRMED (2026-07-08): the synthetic S0–S6 benchmark is
"theater, not measure" for ranking (graders world-readable + self-driven + self-reported;
5/7 sections saturate). Demote it to a smoke-test and re-ground the ranking / capability-grades
brain in REAL OUTCOMES = `source=live` actuals rows in `model-scorecard.tsv`, which are
out-of-band-valid by construction (a human/gate produced the verdict).

**Authoritative design of record:** `/home/stack/charon-private/scratch/pivot-implementation-plan.md`
§0 (ground truth), §1 (A2 = immediate-value, least-build), §7 (grades-table source swap),
§8 Q7. Read those sections before writing code. Driving verdict:
`fleet/BENCHMARK-VALIDITY-REVIEW.md`.

## Scope (A2)
- Make `ScorecardGradesProvider` PREFER `source=live` actuals rows and DEMOTE the synthetic
  S0–S6 composite to a smoke-only signal that no longer feeds the grade or the tier position.
- This is mostly a weighting / source-filter change in `capability/grades.py` +
  `benchmark/lib/tier_chart.py` (the module docstring already names this as the documented
  swap point; `ScorecardGradesProvider` already blends live + bench rows — the change is:
  prefer live, drop the synthetic composite's weight, keep S0 only as a sanity/smoke gate).
- Deliver the pivot thesis on existing data. Independently reversible.

## owns
`capability/grades.py`, `benchmark/lib/tier_chart.py`

## Gate / accept
`cd /home/stack/charon-private/fleet && python3 capability/selftest.py && bash model-scorecard.sh render`
Human sign-off: tier/grade now prefers `source=live`; the synthetic S0–S6 composite is
demoted to smoke and no longer feeds the grade or tier position.

## Dependencies & sequence
- depends_on: EMPTY — ship first (dep-root of the pivot spine). Head of the
  `grades.py` + `tier_chart.py` single-owner chain:
  A2 → #20 (BENCH-PROVISIONAL-SCORING) → #16 (BENCH-AGGREGATE-N) → #17 (BENCH-DIFFICULTY-CAL).
- Concurrency safety: every downstream ticket REBASES onto this file, never co-writes it.
  No other LIVE ticket owns `capability/grades.py` or `benchmark/lib/tier_chart.py`.

## LAST STEP (required)
Commit your work on branch `feat/bench-reground-live` with a clear message and report the SHA.

Do NOT push or merge.

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
