repo: charon
tier: opus
difficulty: 4  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: greenfield-feature
branch: feat/client-connect
depends_on:
owns: src/charon/cli.py, src/charon/connect.py, tests/test_connect.py
prompt: /home/stack/charon-private/prompts/client-connect.md
# PARKED until WORK-LAND-PR merges — shares cli.py with LAND-PR + OBSERVABILITY (cannot run concurrent).
# Unpark: mv CLIENT-CONNECT.md.parked CLIENT-CONNECT.md  (after the cli.py holder merges)
