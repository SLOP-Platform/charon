tier: opus
difficulty: 4  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: greenfield-feature
branch: feat/tier-phase-b-multitier
depends_on: HARD1
real-dep: HARD1 regression-guard test (tests/test_run_task_routing.py) must land FIRST so the routing invariant is guarded before the Phase-B multitier change reworks it — a true build/correctness prereq, not merge-order. Owns are disjoint by design (guard test vs router/api/acp/failover); the dep is JUSTIFIED, not assumed.
owns: src/charon/router.py, src/charon/adapters/acp.py, src/charon/api.py, src/charon/failover.py, tests/test_failover.py, tests/test_tier_lifecycle.py
prompt: /home/stack/charon-private/prompts/tier-phase-b.md
