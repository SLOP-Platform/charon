repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: audit/stranded-work
depends_on:
parked: true
note: PARKED — operator directive: run only AFTER the current in-flight EVAL + memory sessions land. Manager un-parks.
owns: fleet/state/STRANDED-WORK-AUDIT.md
accept: |
  FULL ADVERSARIAL audit (operator directive) to RECOVER near-done work stranded uncommitted/unmerged — motivated by FN3
  (green CI, PR closed unmerged) and the stale board (FN1-5 mislabeled PR-OPEN). Scan ALL branches + open AND closed PRs +
  git worktrees across BOTH repos (SLOP-Platform/charon + charon-private) for code that is mostly/entirely done and needs only
  commit / merge / minor polish.
  DO:
  - Enumerate every feature/fix branch + its real PR state (draft/open/closed/merged/mergeable) + CI gate result. Cross-check
    board state vs REAL GitHub state (board is stale). Include uncommitted worktree diffs.
  - For each: assess % COMPLETE adversarially (verify against the ticket accept + diff, do NOT trust the branch name or a
    self-report) and IMPACT to the project.
  - RANK: 100%-done-AND-green first (land immediately), then descending by (impact x completeness). Flag real blockers.
  - Output a ranked recovery table -> fleet/state/STRANDED-WORK-AUDIT.md; every 100%-ready row carries its exact land.sh command.
  This is READ-ONLY discovery (writes only the audit file); the manager lands the recovered work.
