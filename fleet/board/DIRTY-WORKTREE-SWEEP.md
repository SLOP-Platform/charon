repo: charon-private
tier: economy
priority: 1
difficulty: 2
work_class: rig-meta
branch: chore/dirty-worktree-sweep
depends_on:
owns: fleet/state/DIRTY-WORKTREE-SWEEP.md, docs/review-log/DIRTY-WORKTREE-SWEEP.md
serial_justified: |
  Seventeen worktrees, each 1-5 files, all resolved by the same three-way decision. The unit of
  work is smaller than the cost of splitting it, and the decision rule is refined by the early
  rows.
substrate: N/A
substrate-novel: |
  Detector adopted as-is: fleet/checks/stranded-work.sh already emits the dirty-worktree shape
  and produced this list. Nothing is built. The novel slice is the per-worktree verdict, which
  needs the intent behind each abandoned edit.
accept: |
  LOWEST-HANGING FRUIT in the pileup: 17 worktrees carry uncommitted/untracked files with NO
  live claim — the droid that made them is gone, so nothing will ever pick them up.
  DIFF-COVER-FIX(1) PARK-REARM-FUNDED-PROVIDER(4) BANDIT-PREEXISTING-FINDINGS(1)
  BASH-INERT-COVERAGE(3) CLAIM-LADDER-HEALTH(1) CLAIM-LIVENESS-BINDING(3)
  DOGFOOD-SCORECARD-TIMESTAMP-FIX(1) FN-MEMORY-RETIRE-ADOPT(1) GRAPHIFY-AFFECTED-WIRE(5)
  INVENTORY-TABLE(1) LOOP-GUARD-INFRA-FAULT-EXEMPT(1) NS-CONTENTION(2) REAPER-APPLY-WIRING(1)
  RECONCILE-BOARD-PR-DONE(1) ROUTER-SUBSTRATE-REEVAL(1) SHELLCHECK-OPTIONAL-CHECKS-ON(2)
  TICKET-LIFECYCLE-CANARY(1)
  For EACH, exactly one of three verdicts, with evidence:
   (a) ALREADY ON MASTER — byte-compare before clearing. Two such cases today were redundant
       duplicates of landed work left in the wrong worktree.
   (b) REAL WORK — commit it to its ticket's branch and open/refresh a PR.
   (c) DEBRIS — coverage files, editor leftovers, empty scaffolds: delete, naming what it was.
  NEVER clear without the byte-compare in (a); that check is what makes (c) safe.

## Dependencies & Sequence

P1, no inbound deps, and deliberately the FIRST pileup lane to run — smallest units, clearest
decision rule, and it drains the shape most likely to be destroyed by an unrelated `git clean`.
Disjoint from CLOSED-PR-UNLANDED-TRIAGE and PUSHED-NO-PR-TRIAGE; all three may run concurrently.
