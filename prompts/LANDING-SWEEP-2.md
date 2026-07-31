# SESSION — LANDING SWEEP 2/4: triage unlanded branches (READ-ONLY)

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `rig-meta`.
**You TRIAGE ONLY. Do NOT land, merge, push, delete, or modify ANY branch or file under triage.**
Your single output is a report file. Nothing else changes.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="LANDING-SWEEP-2", repo="charon",
   ticket="LANDING-SWEEP", status="in-progress", model="<your model>")`.
   If the lease expires, do NOT renew — **re-register**.
1. Work from `/home/stack/charon-private` READ-ONLY (`git -C <path> ...` only). Create NO worktree.

## WHY THIS EXISTS
`fleet/fleet-idle.sh` found **50 branches carrying unlanded commits** across worktrees. Some are
finished work nobody landed; some are genuine abandonment. There is no way to tell without looking.
This is not hypothetical: `ADD-PROVIDER-MECHANIZE-COMPLETE` sat 3 days looking like abandoned WIP and
was actually a **completed security fix** (an API-key echo leak) — it landed only because someone
triaged it. Assume this pile contains both kinds.

## YOUR SLICE (13 branches — do ALL of them, no sampling)
```
  TIER-BALANCE  [feat/tier-classifier]  5 commit(s)  @ /home/stack/charon-private-wt/TIER-BALANCE
  SUBSTRATE-GATE-V2  [feat/substrate-first-gate-v2]  3 commit(s)  @ /home/stack/charon-private-wt/SUBSTRATE-GATE-V2
  REGISTRY-META-CATALOG  [feat/registry-meta-catalog]  2 commit(s)  @ /home/stack/charon-private-wt/REGISTRY-META-CATALOG
  SECRET-HOTROTATE  [fix/secret-hot-rotation]  1 commit(s)  @ /home/stack/charon-wt/SECRET-HOTROTATE
  BLAST-TIER-ENFORCEMENT-DESIGN  [design/blast-tier-enforcement]  1 commit(s)  @ /home/stack/charon-private-wt/BLAST-TIER-ENFORCEMENT-DESIGN
  CONFIG-SSOT-CANARY-REGISTER  [feat/config-ssot-canary-register]  1 commit(s)  @ /home/stack/charon-private-wt/CONFIG-SSOT-CANARY-REGISTER
  FLOW-CANARY-FIX-FREEFIRST  [fix/flow-canary-freefirst]  1 commit(s)  @ /home/stack/charon-private-wt/FLOW-CANARY-FIX-FREEFIRST
  KS29-DISCOVERY-LEG  [feat/ks29-discovery-leg]  1 commit(s)  @ /home/stack/charon-private-wt/KS29-DISCOVERY-LEG
  MERGE-QUEUE-EVAL  [eval/merge-queue]  1 commit(s)  @ /home/stack/charon-private-wt/MERGE-QUEUE-EVAL
  RECONCILE-BOARD-PR-DONE  [feat/reconcile-board-pr-done]  1 commit(s)  @ /home/stack/charon-private-wt/RECONCILE-BOARD-PR-DONE
  REVIEW-WORKLOOP-ATTEMPT3  [review/workloop-attempt3]  1 commit(s)  @ /home/stack/charon-private-wt/REVIEW-WORKLOOP-ATTEMPT3
  STUCK-TICKET-LOUD-VISIBILITY  [feat/stuck-ticket-loud-visibility]  1 commit(s)  @ /home/stack/charon-private-wt/STUCK-TICKET-LOUD-VISIBILITY
  WORK-LEASE-RESOLVE  [fix/work-lease-worktree-resolve]  1 commit(s)  @ /home/stack/charon-private-wt/WORK-LEASE-RESOLVE
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

- **USE THE RIGHT DIFF — the two-dot form LIES.** `git diff origin/master..<branch>` renders
  master's additions since the branch forked as if the BRANCH deleted them. It has already produced
  false "this branch deletes board tickets" readings.
  * What the branch actually changes: `git diff --stat origin/master...<branch>` (THREE dots)
  * Is that content already on master (squash-merge safe):
    `P=$(git diff --name-only origin/master...<branch>); git diff --stat origin/master <branch> -- $P`
    An EMPTY result means master already has it. Commit-count NEVER proves this — a squash-merged
    branch reports unlanded commits forever.

## RULES
- **READ-ONLY. No commits, no pushes, no deletions, no worktree changes, no `git checkout`.**
- Do not touch `/home/stack/code/charon` or `/home/stack/charon-private` working trees.
- Other sessions are ACTIVE in some of these worktrees — never write into one.
- NON-VACUOUS: a report covering fewer than 13 branches is incomplete, not partial credit.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- State what you verified by RUNNING vs by READING.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/LANDING-SWEEP-2.md`:
a table of 13 rows — branch | disposition | one-line rationale | evidence.
Then emit the SESSION REPORT v1 block (see below); put the count of each disposition in `NEXT`.

## REPORT BACK — MECHANIZED FORMAT (required)
Validate before finishing: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Spec: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`
```
=== SESSION REPORT v1 ===
TICKET:       LANDING-SWEEP-2
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       none
FILES:        1 changed: fleet/handoff-notes/LANDING-SWEEP-2.md
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
