repo: charon-private
tier: strong
priority: 1
difficulty: 3
work_class: design-review
branch: chore/rescue-triage-rig
depends_on:
owns: fleet/state/RESCUE-TRIAGE-RIG.md, docs/review-log/RESCUE-TRIAGE-RIG.md
substrate: N/A
substrate-novel: |
  The MECHANICAL half of this is already solved by tools we hold and this ticket ADOPTS them
  rather than reimplementing: `git cherry` and `git patch-id` answer "is this commit already on
  master by another route" across a squash-merge, `gh pr list --state all --head <branch>` answers
  "was a PR ever opened for it", and fleet/checks/stranded-work.sh already enumerates the stranded
  classes. None of those is rebuilt here.
  What no external tool decides is the JUDGEMENT the done-contract turns on: whether a rescued
  branch still CONTRIBUTES, or has been superseded by work that reinvented it under another name
  with a different diff. patch-id equality proves sameness of a hunk; it cannot see that
  feat/substrate-first-gate and feat/substrate-first-gate-v2 are two shapes of one intent, or that
  a HELD branch's blocker has since shipped. That reading of intent against the current master is
  the novel slice, and its output is evidence attached to a PR body or a closure note, not a tool.
serial_justified: |
  Nine branches in ONE repo, and the decisions are coupled: two of the nine are competing shapes
  of a single change, so a lane that judged one without seeing the other would open two PRs for
  one intent. One reader, one pass, one disposition table.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. Read-only against master; the only writes are PR
  opens, PR/branch closures, and this ticket's two evidence files. NEVER `--force`, never a raw
  `git push`, never a rebase of someone else's branch.
source: |
  RESCUE-PUSH-TOOL's live sweep, 2026-08-01. 47 local-only branches were pushed to origin the same
  day. Pushing made them SAFE FROM DISK LOSS. It did not make them reviewed, and it did not make
  them visible: nine rig branches now sit on the remote with no PR of any kind against them.
note: |
  ## THE STATE THE RESCUE LEFT BEHIND
  A push is a backup, not a review. The sweep converted "invisible and one disk away from gone"
  into "safe and still invisible", which is strictly better and still not done. Nine rig branches
  carry commits that no PR references, so no gate has ever run on them, no reviewer has ever seen
  them, and nothing on the board tracks them. They are indistinguishable from abandoned work until
  somebody reads them.

  ## THE NINE BRANCHES (rig, no PR of any kind)
  1. chore/retire-wire-graphify
  2. feat/bench-oob-grading
  3. feat/coverage-meta-gate
  4. feat/pr-queue-rest-etag
  5. feat/substrate-first-gate
  6. feat/substrate-first-gate-v2
  7. fix/broker-bare-tier-legs
  8. fix/budget-source-reconcile
  9. salvage/session-notes-20260719

  ## DONE CONTRACT — ONE DISPOSITION PER BRANCH, EVIDENCE ON EVERY ONE
  For EACH of the nine, answer both questions before choosing:
    a. Is its change ALREADY on master by another route — squash-merged under a different branch
       name, superseded by a later ticket, or reinvented from scratch? Prove it with commit shas,
       a `git cherry` / `git patch-id` result, or the file content on master. "Looks similar" is
       not evidence.
    b. Does it still CONTRIBUTE anything master lacks today?
  Then exactly one of:
    OPEN a PR whose body states what the branch delivers, what is already on master, and what is
    left — so a reviewer can judge it without re-deriving this triage; or
    CLOSE / delete the branch with the evidence that it is dead, recorded in this ticket's
    evidence file.
  CLOSING DEAD WORK WITH EVIDENCE IS AN EQUALLY VALID OUTCOME. Do not resurrect corpses. Nine PRs
  is a FAILING result if some of those branches are already on master — it converts a rescue into
  nine review-queue slots that consume reviewer capacity and land nothing.

  ## TWO BRANCHES THAT NEED A DECISION, NOT A DEFAULT
  * `feat/substrate-first-gate` and `feat/substrate-first-gate-v2` are TWO SHAPES OF ONE THING.
    Pick one. Opening both is the failure mode. Say in the evidence file why the loser lost, and
    check first whether the gate that is live on master today already supersedes BOTH.
  * `fix/broker-bare-tier-legs` was deliberately HELD pending GRADE-MODEL-PROVIDER-PAIR. That hold
    was a reason, not a filing decision. CHECK WHETHER IT STILL HOLDS before treating the branch
    as either live or dead — if the blocker has since landed, the hold is spent; if it has not,
    say so and leave the branch alone with the reason recorded.

  ## DELIVERABLE
  `fleet/state/RESCUE-TRIAGE-RIG.md` — one row per branch: branch, commit count, verdict
  (PR-OPENED #N / CLOSED-DEAD / HELD-WITH-REASON), and the evidence that verdict rests on. Plus a
  short `docs/review-log/RESCUE-TRIAGE-RIG.md` fragment. A verdict with no evidence cell is not a
  verdict — it is a guess, and this ticket exists because guesses are what left the branches
  unread in the first place.

## Dependencies & Sequence

- **depends_on: none.** This is a read-then-dispose pass over existing remote branches. It builds
  nothing, imports no fleet module and changes no gate, so nothing has to land first.
- **Sequence: NOW, while the rescue is fresh.** Every day these sit unreferenced is a day someone
  can reinvent one of them, which is how two shapes of the substrate gate came to exist at all.
- **Concurrency safety — owns-collision: none.** Both owned paths are NEW files named after this
  ticket. No other live ticket owns `fleet/state/RESCUE-TRIAGE-RIG.md` or
  `docs/review-log/RESCUE-TRIAGE-RIG.md`. Verified against the live board before minting.
- **Runs in PARALLEL with `RESCUE-TRIAGE-PRODUCT` and `PR-QUEUE-DRIVE`, by construction.** This
  ticket touches ONLY rig branches with no PR; RESCUE-TRIAGE-PRODUCT touches only PRODUCT-repo
  branches in a different checkout; PR-QUEUE-DRIVE touches only branches that ALREADY have an open
  PR. The three sets are disjoint, so no two lanes can contend for the same branch.
- **Hand-off, not a dependency:** any PR this ticket OPENS becomes PR-QUEUE-DRIVE's input on its
  next pass. That is merge-order, not a build prereq — neither ticket blocks the other.
- **Related, do NOT fold in:** `RESCUE-PUSH-TOOL` is the sweep that created this backlog. It is
  the ACTING half; this is the TRIAGE half. Do not modify `fleet/rescue-push.sh` from this lane.
