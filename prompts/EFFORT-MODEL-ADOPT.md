# SESSION — EFFORT-MODEL-ADOPT: replace the nsurf>=3 decompose trigger with the built effort model

**Model:** a NON-ANTHROPIC model through the Charon gateway. Never Claude/Anthropic.
Graded sample, work_class `rig-meta`.
**Repo:** charon-private (PRIVATE rig) · **Branch:** `feat/effort-model-adopt`
**Worktree:** `/home/stack/charon-private-wt/EFFORT-MODEL-ADOPT` — ISOLATED.
**Do NOT work in `/home/stack/charon-private`** — the manager holds it. One checkout, one agent.

## FIRST ACTS
0. **Claim your session name MECHANICALLY — do not invent one.** Names collide when models pick
   them; use the allocator (atomic, claim-before-build):
   ```
   NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"
   echo "claimed: $NAME"
   ```
   Then `session-bridge_register(session_id="<the claimed NAME>", name="EFFORT-MODEL-ADOPT", repo="charon",
   ticket="EFFORT-MODEL-ADOPT", status="in-progress", model="<your model>")`.
   **Never reuse a name you see on the board — those sessions are LIVE.**
   Then `session-bridge_update` every ~5 min as a HEARTBEAT (600s lease, else you are purged).
1. `git -C /home/stack/charon-private worktree add -b feat/effort-model-adopt /home/stack/charon-private-wt/EFFORT-MODEL-ADOPT master`
2. `cd /home/stack/charon-private-wt/EFFORT-MODEL-ADOPT`

## THE DECISION (already made — you are implementing it, not re-deciding it)
The decomposition trigger currently uses **`nsurf >= 3`** (number of surfaces a ticket touches).
Research measured both candidates against our OWN board:

    nsurf      vs tier :  rho = +0.075   (noise — it predicts nothing)
    difficulty vs tier :  rho = +0.413

Adopt the **already-built** `src/charon/decompose_effort.py`:

    effort = 2.0*difficulty + 0.15*size + 1.0*behaviours

External alternatives were killed on our own data or needed training data we do not have. The module
EXISTS — this is an ADOPT-AND-WIRE task, not a build. Do not write a new effort model. If you believe
the formula is wrong, STOP and report; do not substitute your own.

## YOUR FIRST JOB — LOCATE, do not assume
Nothing in this brief tells you where `nsurf >= 3` is used, because that must be established from the
code, not from memory. Find EVERY decision site that consumes `nsurf` as a decomposition trigger.
- **A zero-hit grep is NOT evidence of absence.** Grep may LOCATE candidates; only reading the call
  site may CONCLUDE. Search for the concept, not one spelling: `nsurf`, surface counts, "decompose"
  thresholds, WCI contention checks, and whatever the board validator uses.
- Report the full list of sites BEFORE changing any of them. If there is more than one consumer,
  changing only the obvious one leaves the board deciding two different ways — worse than either.

## REQUIRED CHANGE
Wire `decompose_effort` in as the trigger at every site you found. Preserve the existing behaviour
contract: whatever the trigger gates (auto-ticketing, decompose candidates, contention detection)
must keep working, only with a better signal. Choose and JUSTIFY the effort threshold — do not port
`>= 3` across as if the units were the same. They are not: the new score is a weighted sum, the old
was a count. State how you picked the cutoff and what it does to the current board.

## REQUIRED PROOF (green is not proof)
- **Show the delta on the REAL board:** for the live `fleet/board/*.md` set, which tickets does the
  old trigger flag vs the new one? List the tickets that change classification, both directions.
  A change that reclassifies nothing is either a no-op or wired wrong — say which.
- **RED-PROOF BY EXECUTION:** revert the wiring -> the new test goes RED naming the effort case.
  **Report BOTH exit codes.** A green you did not first make fail is not evidence.
- NON-VACUOUS: a test over an empty ticket set must be RED, never a silent pass.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- `bash fleet/validate_board.sh` must still be **GREEN** afterwards — it is green as of `032f852`,
  and regressing it blocks every rig push (`land-push.sh` refuses on RED).
- State what you proved by RUNNING vs by READING, and which git ref you measured on.

## OWNS
Whatever files the located decision sites live in, plus their tests. **Before editing any file, check
it is not owned by another live ticket:** `grep -h '^owns:' fleet/board/*.md | grep <file>`. If it is
owned elsewhere, STOP and report the collision instead of editing. This project has been bitten by
unchecked owns claims twice today.

## REPORT BACK (short — no diffs)
Every `nsurf` decision site found (file:line) · the threshold you chose and why · the board
reclassification delta · both exit codes from the red-proof · validate_board.sh result · commit SHA.

## ⚠ BEFORE YOUR FIRST COMMIT — ACQUIRE THE WORK LEASE
The rig refuses commits from a worktree holding no lease. Run this once, before you start:
```
bash /home/stack/charon-private/fleet/work-lease.sh acquire EFFORT-MODEL-ADOPT
```
**NEVER use `WORK_LEASE_BYPASS=1`.** The refusal message advertises that bypass; it exists for
emergencies, not for getting past your own commit. Using it defeats a safety gate and will fail
review. If the lease cannot be acquired, STOP and report — do not bypass.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "EFFORT-MODEL-ADOPT: replace nsurf>=3 decompose trigger with decompose_effort score"
```

Do NOT push.

## Dependencies & sequence

- **Depends on: NOTHING** — but its `owns:` is DISCOVERED, not pre-declared, so the collision check
  above is mandatory before any edit.
- **Concurrency safety:** rig-side. Disjoint from the Switchboard product wave. If a located site is
  `fleet/validate_board.sh`, note it is co-owned by CREATION-GATE-DECOMPOSE-WIRE and
  PROJECT-MEMBERSHIP-GATE (dep-sequenced) — STOP and report rather than becoming a third writer.
- **Wave:** parallel lane, P2.

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
