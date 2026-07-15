repo: charon-private
tier: economy
difficulty: 2
work_class: rig-meta
branch: fix/done-sh-repo-aware
owns: fleet/done.sh
depends_on:
note: |
  BUG (found 2026-07-15): done.sh looks up the merged PR in the PRODUCT repo only, so a RIG
  (charon-private) ticket's auto-done-mark FAILS ("no MERGED PR for branch ...") even though the
  PR merged — leaving dependents blocked (hit on RULE-SYNC-AUDIT #74). Class-level: done.sh must
  resolve the PR in the TICKET'S OWN repo, read from the board file's `repo:` field.
accept: |
  ## Task
  - In done.sh, read the ticket's `repo:` field from its board file (board/<id>.md or
    board/archive/<id>.md). Map repo -> owner/slug (charon -> SLOP-Platform/charon,
    charon-private -> Nnyan/charon-private) and use THAT for the `gh pr list --repo` merged-PR
    lookup (currently hardcoded/defaulted to product). Fall back to current behavior if no repo field.
  - The land.sh auto-done-mark path (which passes the id) must then succeed for rig tickets too.
  ## Accept (fail-on-revert)
  - A test/fixture: a rig ticket whose branch has a MERGED charon-private PR is done-marked by
    done.sh WITHOUT --override (proves repo-aware lookup); reverting the repo-map makes it REFUSE.
  - bash -n fleet/done.sh; existing done.sh path for product tickets still works.
  ## Dependencies & sequence
  depends_on: (none) — self-contained done.sh fix.
