# SESSION — LANDING SWEEP 3/4: triage unlanded branches (READ-ONLY)

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `rig-meta`.
**You TRIAGE ONLY. Do NOT land, merge, push, delete, or modify ANY branch or file under triage.**
Your single output is a report file. Nothing else changes.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="LANDING-SWEEP-3", repo="charon",
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
  SG-ISSUE-CONTROL-PLANE  [feat/sg-issue-control-plane]  4 commit(s)  @ /home/stack/charon-private-wt/SG-ISSUE-CONTROL-PLANE
  SW-IDENTITY-FOLD  [fix/sw-identity-fold]  2 commit(s)  @ /home/stack/charon-wt/SW-IDENTITY-FOLD
  REVIEW-DISPENSATION-CANARY  [feat/review-dispensation-canary]  2 commit(s)  @ /home/stack/charon-private-wt/REVIEW-DISPENSATION-CANARY
  SW-STATIC-LEGS-RETIRE  [feat/sw-static-legs-retire]  1 commit(s)  @ /home/stack/charon-wt/SW-STATIC-LEGS-RETIRE
  BOARD-WRITE-LOCK  [fix/board-write-lock]  1 commit(s)  @ /home/stack/charon-private-wt/BOARD-WRITE-LOCK
  D24-SESSION-CTL-SPIKE  [spike/session-ctl]  1 commit(s)  @ /home/stack/charon-private-wt/D24-SESSION-CTL-SPIKE
  FN-MEMORY-RETIRE-ADOPT  [feat/fn-memory-retire-adopt]  1 commit(s)  @ /home/stack/charon-private-wt/FN-MEMORY-RETIRE-ADOPT
  LAND-GATE-RIG-SUITE  [fix/land-gate-rig-suite]  1 commit(s)  @ /home/stack/charon-private-wt/LAND-GATE-RIG-SUITE
  PREFLIGHT-OWNS-ARBITRATE  [fix/preflight-owns-arbitrate]  1 commit(s)  @ /home/stack/charon-private-wt/PREFLIGHT-OWNS-ARBITRATE
  RECONCILE-REVIEW-GATE  [feat/reconcile-review-gate]  1 commit(s)  @ /home/stack/charon-private-wt/RECONCILE-REVIEW-GATE
  RFL-3-CAPTURE-FIX  [fix/rfl3-dogfood-capture]  1 commit(s)  @ /home/stack/charon-private-wt/RFL-3-CAPTURE-FIX
  SUBAGENT-WORKTREE-SANDBOX  [feat/subagent-worktree-sandbox]  1 commit(s)  @ /home/stack/charon-private-wt/SUBAGENT-WORKTREE-SANDBOX
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
- NON-VACUOUS: a report covering fewer than 12 branches is incomplete, not partial credit.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- State what you verified by RUNNING vs by READING.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/LANDING-SWEEP-3.md`:
a table of 12 rows — branch | disposition | one-line rationale | evidence.
Then emit the SESSION REPORT v1 block (see below); put the count of each disposition in `NEXT`.

## REPORT BACK — MECHANIZED FORMAT (required)
Validate before finishing: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Spec: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`
```
=== SESSION REPORT v1 ===
TICKET:       LANDING-SWEEP-3
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       none
FILES:        1 changed: fleet/handoff-notes/LANDING-SWEEP-3.md
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
