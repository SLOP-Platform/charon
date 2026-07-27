# SESSION — LANDING SWEEP 4/4: triage unlanded branches (READ-ONLY)

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `rig-meta`.
**You TRIAGE ONLY. Do NOT land, merge, push, delete, or modify ANY branch or file under triage.**
Your single output is a report file. Nothing else changes.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="LANDING-SWEEP-4", repo="charon",
   ticket="LANDING-SWEEP", status="in-progress", model="<your model>")`.
   If the lease expires, do NOT renew — **re-register**.
1. Work from `/home/stack/charon-private` READ-ONLY (`git -C <path> ...` only). Create NO worktree.

## WHY THIS EXISTS
`fleet/fleet-idle.sh` found **50 branches carrying unlanded commits** across worktrees. Some are
finished work nobody landed; some are genuine abandonment. There is no way to tell without looking.
This is not hypothetical: `ADD-PROVIDER-MECHANIZE-COMPLETE` sat 3 days looking like abandoned WIP and
was actually a **completed security fix** (an API-key echo leak) — it landed only because someone
triaged it. Assume this pile contains both kinds.

## YOUR SLICE (12 branches — do ALL of them, no sampling)
```
  TICKET-LIFECYCLE-CANARY  [feat/ticket-lifecycle-canary]  4 commit(s)  @ /home/stack/charon-private-wt/TICKET-LIFECYCLE-CANARY
  ISSUE-BOARD-SURFACE  [feat/issue-board-surface]  2 commit(s)  @ /home/stack/charon-private-wt/ISSUE-BOARD-SURFACE
  STRANDED-WORK-DETECT  [feat/stranded-work-detect]  2 commit(s)  @ /home/stack/charon-private-wt/STRANDED-WORK-DETECT
  order-a  [feat/ordering-cost-primary]  1 commit(s)  @ /home/stack/charon-wt/order-a
  BOUNCE-1  [feat/bounce-1-egress-canary-realsut]  1 commit(s)  @ /home/stack/charon-private-wt/BOUNCE-1
  DISCOVERY-SOURCE-ADAPTERS  [feat/discovery-source-adapters]  1 commit(s)  @ /home/stack/charon-private-wt/DISCOVERY-SOURCE-ADAPTERS
  INERT-WIRING-ENFORCEMENT-DURABLE  [fix/inert-wiring-enforcement-durable]  1 commit(s)  @ /home/stack/charon-private-wt/INERT-WIRING-ENFORCEMENT-DURABLE
  LANDING-GATE-REGISTER  [feat/landing-gate-register]  1 commit(s)  @ /home/stack/charon-private-wt/LANDING-GATE-REGISTER
  PRICE-TRACKED-INVENTORY-AUTOSWAP  [feat/price-tracked-inventory-autoswap]  1 commit(s)  @ /home/stack/charon-private-wt/PRICE-TRACKED-INVENTORY-AUTOSWAP
  REPO-FIELD-REQUIRED  [feat/repo-field-required]  1 commit(s)  @ /home/stack/charon-private-wt/REPO-FIELD-REQUIRED
  RIG-BRANCH-16-DEEPDIVE  [fix/rig-branch-16-deepdive]  1 commit(s)  @ /home/stack/charon-private-wt/RIG-BRANCH-16-DEEPDIVE
  SW-PHASE0-GRADE-READ  [fix/sw-phase0-grade-read]  1 commit(s)  @ /home/stack/charon-private-wt/SW-PHASE0-GRADE-READ
```

## FOR EACH BRANCH, PRODUCE ONE DISPOSITION
- **LAND-READY** — coherent, complete, tests pass. Say what it does in one line and what proves it.
- **NEEDS-REVIEW** — real work, but you cannot confirm completeness. Say precisely what is unclear.
- **ABANDON** — superseded, empty, or already-landed-by-re-derivation. **You must show the evidence**
  (content already on master, or the superseding branch/commit).
- **UNSAFE-TO-JUDGE** — say so plainly rather than guessing. This is a valid answer.

## HOW TO JUDGE (evidence, not vibes)
- `git -C <path> log --oneline <base>..<branch>` and `git -C <path> diff --stat <base>..<branch>`.
- Look for ABANDONMENT SIGNATURES: launcher auto-commit messages ("droid exited without committing"),
  a helper defined but never called, half-updated call sites, TODO/FIXME, an import for absent code.
  **A launcher auto-commit is NOT by itself evidence of abandonment** — that is exactly the mistake
  made with ADD-PROVIDER-MECHANIZE-COMPLETE. Read the diff.
- Check whether the content is ALREADY on master (landed by re-derivation): identical content with
  different SHAs is common in this repo.
- Check `fleet/board/<TICKET>.md` for a matching live ticket, and whether it is parked/archived.
- **A zero-hit grep is NOT evidence** — read the diff before concluding anything is absent.
- If a branch contains anything that looks like a SECRET or a key, report THAT first and do not
  reproduce the value.

## RULES
- **READ-ONLY. No commits, no pushes, no deletions, no worktree changes, no `git checkout`.**
- Do not touch `/home/stack/code/charon` or `/home/stack/charon-private` working trees.
- Other sessions are ACTIVE in some of these worktrees — never write into one.
- NON-VACUOUS: a report covering fewer than 12 branches is incomplete, not partial credit.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- State what you verified by RUNNING vs by READING.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/LANDING-SWEEP-4.md`:
a table of 12 rows — branch | disposition | one-line rationale | evidence.
Then emit the SESSION REPORT v1 block (see below); put the count of each disposition in `NEXT`.

## REPORT BACK — MECHANIZED FORMAT (required)
Validate before finishing: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Spec: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`
```
=== SESSION REPORT v1 ===
TICKET:       LANDING-SWEEP-4
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       none
FILES:        1 changed: fleet/handoff-notes/LANDING-SWEEP-4.md
OWNS-OK:      yes
GATE:         n/a — read-only triage
TESTS:        n/a — read-only triage
RED-PROOF:    n/a — no code change
OBSERVABLE:   MET | DEFERRED — <why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <condition>
NEXT:         LAND-READY=<n> NEEDS-REVIEW=<n> ABANDON=<n> UNSAFE=<n>
=== END REPORT ===
```

## Dependencies & sequence
- **Depends on: NOTHING.** Read-only; owns one new report file. Runs fully parallel with the other
  three sweep sessions and with all live work — it cannot collide with anything.
- **Wave:** triage lane.
