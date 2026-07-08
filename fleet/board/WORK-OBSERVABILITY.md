tier: opus
work_class: greenfield-feature
branch: feat/work-observability
depends_on: CLIENT-CONNECT
real-dep: CLIENT-CONNECT owns cli.py which this ticket also owns — overlapping owns, must land after it (sequencing, not merge-order-only).
owns: src/charon/engine/scheduler.py, src/charon/cli.py, tests/test_work_observability.py
prompt: /home/stack/charon-private/prompts/work-observability.md
# PARKED until CLIENT-CONNECT merges. Unpark: mv WORK-OBSERVABILITY.md.parked WORK-OBSERVABILITY.md
