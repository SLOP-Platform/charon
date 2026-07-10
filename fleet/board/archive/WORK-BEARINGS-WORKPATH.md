tier: opus
difficulty: 4  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: greenfield-feature
branch: feat/work-bearings-workpath
depends_on: WORK-LAND-PR
real-dep: WORK-LAND-PR owns cli.py and introduces the _ReviewingRunner this ticket must modify (overlapping owns + must build on LAND-PR's runner) — a true build prereq, not merge-order.
owns: src/charon/engine/board.py, src/charon/engine/scheduler.py, src/charon/cli.py, src/charon/types.py, tests/test_work_bearings.py
prompt: /home/stack/charon-private/prompts/work-bearings-workpath.md
# PARKED until WORK-LAND-PR merges. Unpark: mv WORK-BEARINGS-WORKPATH.md.parked WORK-BEARINGS-WORKPATH.md
