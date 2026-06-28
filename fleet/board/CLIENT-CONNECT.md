tier: opus
branch: feat/client-connect
depends_on:
owns: src/charon/cli.py, src/charon/connect.py, tests/test_connect.py
prompt: /home/stack/charon-private/prompts/client-connect.md
# PARKED until WORK-LAND-PR merges — shares cli.py with LAND-PR + OBSERVABILITY (cannot run concurrent).
# Unpark: mv CLIENT-CONNECT.md.parked CLIENT-CONNECT.md  (after the cli.py holder merges)
