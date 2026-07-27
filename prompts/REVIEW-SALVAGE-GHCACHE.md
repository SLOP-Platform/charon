# SESSION — REVIEW-SALVAGE-GHCACHE (P0): review unlanded branches

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `design-review`.
**READ-ONLY.** You produce a report. No edits, no commits, no landing, no deletion.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="REVIEW-SALVAGE-GHCACHE", repo="charon",
   ticket="REVIEW-SALVAGE-GHCACHE", status="in-progress", model="<your model>")`.
   If the lease expires, do NOT renew — **re-register**.
1. Read the ticket (BINDING): `fleet/board/REVIEW-SALVAGE-GHCACHE.md`
2. Work read-only from `/home/stack/charon-private` using `git -C`. Create NO worktree.

## YOUR BRANCHES — salvage/preflight-verify-merged-ghcache-wip (6 commits, 50 files, +443/-4173)
```
  salvage/preflight-verify-merged-ghcache-wip
```
## WHY THIS ONE IS ALONE AND P0
**4,173 deletions across 50 files.** That is by far the largest destructive diff in the unlanded set,
on a branch literally named `salvage/...-wip` — work-in-progress that was rescued, not finished.
Landing it blind could remove large amounts of live rig machinery.
**Establish FIRST whether those deletions are real or a diff artifact.** A branch far behind master
shows master's additions as deletions under a two-dot diff. Use the three-dot form and say plainly
which it is — that single question decides everything else.

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
Write to `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-SALVAGE-GHCACHE.md`.

## REPORT BACK — MECHANIZED FORMAT (required)
Validate: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>` ·
Spec: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`
```
=== SESSION REPORT v1 ===
TICKET:       REVIEW-SALVAGE-GHCACHE
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       none
FILES:        1 changed: fleet/handoff-notes/ADVREVIEW-SALVAGE-GHCACHE.md
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
