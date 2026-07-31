# SESSION — REVIEW-BACKLOG-B (P0): review unlanded branches

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `design-review`.
**READ-ONLY.** You produce a report. No edits, no commits, no landing, no deletion.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="REVIEW-BACKLOG-B", repo="charon",
   ticket="REVIEW-BACKLOG-B", status="in-progress", model="<your model>")`.
   If the lease expires, do NOT renew — **re-register**.
1. Read the ticket (BINDING): `fleet/board/REVIEW-BACKLOG-B.md`
2. Work read-only from `/home/stack/charon-private` using `git -C`. Create NO worktree.

## YOUR BRANCHES — four small branches (35-262 insertions each)
```
  feat/inventory-table
  review/reconcile-gate-design
  feat/price-tracked-inventory-autoswap
  fix/inert-wiring-enforcement-durable
```
## NOTES
* `review/reconcile-gate-design` and `feat/price-tracked-inventory-autoswap` were flagged
  DESIGN-REVIEW-ONLY — likely docs with no executable surface. If so, say so and judge on whether the
  design is sound and current, not on tests that do not exist.
* `fix/inert-wiring-enforcement-durable` (35 lines) — smallest in the set. Related to the inert-code
  detector blind spot found today (registry-registration treated as reachability); check for overlap
  with INERT-INSTANCE-DETECT before recommending LAND.

## HOW TO REVIEW (binding — the diff commands matter)
**Two-dot diff LIES.** `git diff master..<branch>` renders master's later additions as if the BRANCH
deleted them. On 2026-07-26 that produced two WRONG destructive verdicts. Use:
* what the branch changes: `git diff --stat master...<branch>` (THREE dots)
* already on master?: `P=$(git diff --name-only master...<b>); git diff --stat master <b> -- $P`
  (empty => landed; commit-count NEVER proves this — squash-merged branches look unlanded forever)

For EACH branch, produce: **LAND / REWORK / ABANDON / UNSAFE-TO-JUDGE** with evidence.
* **LAND** — say what proves it: which tests you RAN and their exit codes. "Looks fine" is not evidence.
* **REWORK** — name the specific defect and what would fix it.
* **ABANDON** — show the content is already on master, or that it is superseded. Never infer.
* **UNSAFE-TO-JUDGE** — a valid answer. Say what you would need.

## THE FAILURE CLASS TO WATCH FOR (cost us two rejected gates today)
Work that satisfies the LETTER of its contract with machinery that CANNOT FAIL. Both P0 gates built
today passed their own red-proofs because the red-proof tested SELF-CONSISTENCY (mutating the
check's own input). If a branch adds a gate/check/test, **break it EXTERNALLY yourself** — revert a
real fix elsewhere, add a genuinely new case — and confirm it goes RED. A check that only fails when
you edit its own list is decorative.

## RULES
- **READ-ONLY.** No edits, no commits, no landing, no branch deletion. You produce a report.
- Run tests where they exist; report exit codes you OBSERVED, not ones claimed in commit messages.
- A zero-hit grep is NOT evidence — read the code.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail`.
- Say what you proved by RUNNING vs by READING.
- NON-VACUOUS: a report covering fewer branches than assigned is incomplete, not partial credit.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-BACKLOG-B.md`.

## REPORT BACK — MECHANIZED FORMAT (required)
Validate: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>` ·
Spec: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`
```
=== SESSION REPORT v1 ===
TICKET:       REVIEW-BACKLOG-B
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       none
FILES:        1 changed: fleet/handoff-notes/ADVREVIEW-BACKLOG-B.md
OWNS-OK:      yes
GATE:         n/a — read-only review
TESTS:        <what you ran, per branch>
RED-PROOF:    <external breaks you attempted> | n/a — <why>
OBSERVABLE:   MET | DEFERRED — <why>
RAN:          <proved by EXECUTING>
READ:         <concluded by READING only>
BRIEF-ERRORS: none | <what this brief got wrong>
BLOCKED-BY:   none | <condition>
BUDGET:       ok | TRUNCATED — <what you could not finish>
NEXT:         LAND=<n> REWORK=<n> ABANDON=<n> UNSAFE=<n>
=== END REPORT ===
```

## Dependencies & sequence
- **Depends on: NOTHING.** Read-only, owns one report file, cannot collide.
- **Wave:** review lane, P0.
