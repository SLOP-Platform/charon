tier: frontier
branch: feat/orch-route
depends_on: CWD-CONFIG
owns: src/charon/api.py, src/charon/ports/agent_launch.py, tests/test_agent_launch_routing.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_agent_launch_routing.py
prompt: /home/stack/charon-private/prompts/orch-route.md
real-dep: CWD-CONFIG renderer writes cwd opencode.json so ACP honors per-run config
# UNBLOCKED 2026-06-30 — cwd opencode.json IS honored by opencode 1.17.11 acp.
# CWD-CONFIG implements the cwd-file injection; this ticket builds orchestrator mode on top.
# opencode issue #34638 tracks the env-var gap (OPENCODE_CONFIG_CONTENT not honored);
# cwd opencode.json is a validated workaround.
