tier: economy
difficulty: 2
work_class: rig-meta
priority: 2
branch: feat/project-membership-gate
depends_on: DIFFICULTY-SCHEMA
owns: /home/stack/charon-private/fleet/validate_board.sh, /home/stack/charon-private/fleet/state/ROADMAP.tsv
accept: |
  validate_board.sh flags (RED) any LIVE ticket (board/*.md, not parked/retired) that is NOT present as a
  row in state/ROADMAP.tsv — i.e. not folded into a Project. Fail-on-revert: add a live ticket absent from
  ROADMAP.tsv -> validate_board non-zero; add its row -> green. Mechanizes the "fold, don't proliferate"
  rule: every new ticket must belong to one of the 5 Projects; a new Project needs a strong case + a
  re-analysis of what moves into it.
scope: Operator 2026-07-10: all new work folds into existing Projects by default; enforce it, don't rely on recall.
ds: Now (rig-only). FLEET project.
