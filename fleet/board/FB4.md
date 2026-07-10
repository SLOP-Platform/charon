tier: opus
difficulty: 4  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: feat/fix-engine-concurrency
depends_on:
owns: engine/claim.py, engine/scheduler.py, tests/test_claim.py, tests/test_scheduler.py
prompt: /home/stack/charon-private/prompts/fb4.md
note: BLOCKS E8 (auto-land) — E8 must not launch until FB4 lands; it builds directly on
  the fenced reclaim primitive this ticket fixes. From the 2026-06-27 fragility audit
  (Theme 7); see charon-private/fleet/AUDIT-2026-06-27.md.
