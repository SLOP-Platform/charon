# SESSION — SW-PHASE0-GRADE-READ (P0): the ranking reads NOTHING — fix the read

**Model:** a NON-ANTHROPIC model through the Charon gateway. Never Claude/Anthropic.
Graded sample, work_class `rig-meta`.
**Repo:** charon-private (PRIVATE rig) · **Ticket:** SW-PHASE0-GRADE-READ
**Branch:** `fix/sw-phase0-grade-read`
**Worktree:** `/home/stack/charon-private-wt/SW-PHASE0-GRADE-READ` — ISOLATED.
**Do NOT work in `/home/stack/charon-private`** — the manager holds it. One checkout, one agent.

## FIRST ACTS
0. **Claim your session name MECHANICALLY — do not invent one:**
   ```
   NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"
   echo "claimed: $NAME"
   ```
   Then `session-bridge_register(session_id="<the claimed NAME>", name="SW-PHASE0-GRADE-READ",
   repo="charon", ticket="SW-PHASE0-GRADE-READ", status="in-progress", model="<your model>")`.
   **Never reuse a name you see on the board.** If your lease expires, do NOT renew — **re-register**.
1. `git -C /home/stack/charon-private worktree add -b fix/sw-phase0-grade-read /home/stack/charon-private-wt/SW-PHASE0-GRADE-READ master`
2. `cd /home/stack/charon-private-wt/SW-PHASE0-GRADE-READ`
3. **Acquire the work lease FROM INSIDE THIS WORKTREE** (the lease binds to the worktree that
   acquires it — running this from charon-private leases it to the WRONG path and your commit will
   be refused; that already cost one session today):
   ```
   cd /home/stack/charon-private-wt/SW-PHASE0-GRADE-READ
   bash /home/stack/charon-private/fleet/work-lease.sh acquire SW-PHASE0-GRADE-READ
   ```
   **NEVER use `WORK_LEASE_BYPASS=1`.** If a gate refuses, STOP and report.
4. Read the ticket (BINDING): `fleet/board/SW-PHASE0-GRADE-READ.md`

## THE DEFECT — the ledger WRITES but the ranking READS NOTHING
`fleet/capability/grades.py:544-559` requires **>= 3 `strong-control` rows** per ref before a model's
rows count. `grep -c strong-control fleet/model-scorecard.tsv` = **0**. So `_rows_for` drops EVERY
live row, `GradesProvider().grade()` returns `None` for all models, and
`python3 fleet/capability/assign.py <ticket>` answers `REFUSED — no eligible candidate` for every
ticket — even with explicit `--work-class` and `--candidates`.

The ledger itself is healthy: 64 rows, all `source=live`/`stage=active`. The data is there. **Nothing
can read it.** Every graded run recorded until this is fixed feeds a ledger no decision consults —
model ranking is currently theater. This also blocks promote/demote (`model-detention.sh`,
`assign.py`) and makes the external-benchmark cold-start prior (`grades_import.py`) pointless,
because nothing can ever supersede the prior with real signal.

## THE FIX ALREADY EXISTS — PORT IT, DO NOT REDESIGN
The no-control->admit fallback landed **product-side** at
`/home/stack/code/charon/src/charon/capability/grades.py:149` (`_is_fallback_admit`, commit
`0947401`, "no-control→admit fallback so EVAL-PROMOTION-GATE grades live refs"). The RIG copy has
**zero** occurrences of it. This is a straight port of a reviewed, landed fix into the rig's copy of
the same logic — NOT a new admission policy.

If the port appears to need a DIFFERENT rule than the product's, **STOP and report**: a divergence
between the two copies is itself the finding, and is more valuable than a guessed fix.

## DELIBERATELY OUT OF SCOPE — do not touch
`fleet/done.sh:175` hardcodes `MERGE/pass/score=100` (63 MERGE vs 1 BLOCK — no discriminating
signal). That is a real second defect, but `fleet/done.sh` is owned by FOUR other live tickets with a
documented single-writer chain. It is dispositioned separately as DONE-SH-INTEGRITY-FIX defect (c).
Fixing the READ here is still correct and independently valuable: it is THE blocker.

## REQUIRED PROOF (green is not proof)
- `python3 fleet/capability/assign.py <a real live ticket id>` returns an actual candidate instead of
  `REFUSED`. **Paste the before and after output.**
- `GradesProvider().grade()` returns non-None for at least one model with live rows. Name the model
  and the row count it drew on.
- **RED-PROOF BY EXECUTION:** revert the admission predicate -> the new test goes RED naming the
  zero-control case. **Report BOTH exit codes.** A green you did not first make fail is not evidence.
- NON-VACUOUS: the test must FAIL if the scorecard has zero rows — never a silent pass on an empty
  ledger.
- **No change to the scorecard DATA.** A diff touching `fleet/model-scorecard.tsv` is out of contract
  — that file is owned by the `bench-grader` unix user for anti-gaming reasons.
- `bash fleet/validate_board.sh` must still be GREEN. **Run it from the MAIN checkout**
  (`/home/stack/charon-private`), not your worktree — a worktree run reports pre-existing REDs that
  are not yours and will mislead you.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- State what you proved by RUNNING vs by READING, and which git ref you measured on.

## OWNS — do not touch anything else
`fleet/capability/grades.py`, `fleet/capability/tests/test_grades_no_control_admit.py`.
If the fix appears to need another file, STOP and report.

## REPORT BACK (short — no diffs)
assign.py before/after output · the model+row-count that graded non-None · both exit codes from the
red-proof · validate_board result · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "SW-PHASE0-GRADE-READ: port no-control->admit so live rows reach the ranker"
```

Do NOT push.

## Dependencies & sequence
- **Depends on: NOTHING. Startable immediately.** `fleet/capability/grades.py` is owned by no other
  live ticket (the other fleet/capability owners are assign.py, availability.py, tier_classify.py,
  effort.py).
- **Blocks:** the recorded grade of every run in this wave, and all promote/demote behaviour.
  Grading is written at `done.sh` time, AFTER merge — so this must land before `done.sh` runs on the
  wave's tickets, not before they start.
- **Wave:** phase 0, parallel lane, P0.

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
