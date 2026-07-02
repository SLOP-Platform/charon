tier: frontier
branch: feat/console-provider-mgmt
depends_on:
owns: src/charon/proxy_server.py, src/charon/config.py, src/charon/gateway.py, tests/test_console_provider_mgmt.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_console_provider_mgmt.py
prompt: /home/stack/charon-private/prompts/console-provider-mgmt.md
# BACKLOG (parked) — operator 2026-06-28: manage providers/models from the web console (not CLI-only).
# SERIALIZE with OBS-UI (both own proxy_server.py) — cannot run concurrently. Key handling is security-sensitive.
