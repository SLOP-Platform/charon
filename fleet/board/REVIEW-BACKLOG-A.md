repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 0
branch: review/review-backlog-a
depends_on:
owns: fleet/handoff-notes/ADVREVIEW-BACKLOG-A.md
prompt: /home/stack/charon-private/prompts/REVIEW-BACKLOG-A.md
serial_justified: |
  ONE review batch producing ONE verdict file. Owns no code — the deliverable is a per-branch
  disposition so the operator can land or discard with evidence rather than guesswork.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample. READ-ONLY.
source: |
  Landing sweeps 1-4, 2026-07-26: 50 branches triaged, 34 LAND-READY landed on executed-test
  evidence. These were flagged NEEDS-REVIEW precisely because triage could NOT establish that
  evidence. Batching them with the rest is how an unreviewed money-path commit reached master today.
note: |
  ## SCOPE — four mid-size branches (250-400 insertions each)
  feat/ticket-lifecycle-canary
  feat/reconcile-board-pr-done
  feat/router-ledger-decay
  feat/fn-memory-retire-adopt
## NOTES
* `feat/ticket-lifecycle-canary` (3 commits) — sweep flagged an UNMERGED DEP. Identify it and say
  whether it still blocks.
* `feat/router-ledger-decay` — its board ticket's `repo:` was corrected to `charon` today (product
  paths). Confirm the branch content matches a PRODUCT ticket.
* `feat/reconcile-board-pr-done` and `feat/fn-memory-retire-adopt` — no prior flag; judge on merit.
accept: |
  DONE-CONTRACT:
  - A per-branch verdict (LAND / REWORK / ABANDON / UNSAFE-TO-JUDGE) with the evidence behind it.
  - For any LAND verdict: the tests you RAN and their exit codes. Claims from commit messages are
    not evidence.
  - For any branch adding a gate/check: an EXTERNAL break attempted, with the result.
  - Content-vs-ancestry stated correctly — a squash-merged branch reports unlanded commits forever.
  - NON-VACUOUS: fewer verdicts than branches assigned is incomplete.
  - READ-ONLY: no edits, commits, landings or deletions.
## Dependencies & sequence
- **Depends on: NOTHING.** Read-only; owns one report file. Runs fully parallel with the other
  review batches and with all other work.
- **Wave:** review lane, P0.
