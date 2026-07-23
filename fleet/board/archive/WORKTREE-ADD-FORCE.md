repo: charon
tier: sonnet
difficulty: 2  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: feat/worktree-add-force
depends_on:
owns: src/charon/gitutil.py, tests/test_gitutil_worktree.py
prompt: /home/stack/charon-private/prompts/worktree-add-force.md
# BACKLOG (parked) — surfaced by the 2026-06-27 cert: add_worktree --detach (no -f/prune) aborts a
# re-run on a stale registration. Tackle after the priority cluster if budget remains.
