repo: charon
tier: frontier
difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: greenfield-feature
branch: feat/cwd-config
depends_on:
owns: src/charon/ports/agent_launch.py, tests/test_agent_launch_routing.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_agent_launch_routing.py
prompt: /home/stack/charon-private/prompts/cwd-config.md

# === COORDINATION RESOLVED: orch-route-reviewer ↔ worker ===

# orch-route-reviewer verified the worker's test script has TWO bugs:
#
# BUG 1 (fatal): session/prompt uses sessionId:'s1' instead of reading the REAL
#   session ID from session/new response. Agent stderr: "Invalid params: session
#   not found: s1". The agent never processes the prompt → 0 calls.
#
# BUG 2 (also fatal once BUG 1 is fixed): config JSON has no "model" top-level
#   key, only "provider". Without "model": "proof_test/proof-m", the agent may
#   not activate the custom provider even though cwd opencode.json is loaded.
#
# With both bugs fixed (real session ID from session/new + "model" key in config),
# the worker's own script approach yields 2 proxy hits.
#
# FULL REPRODUCTIONS ON FILE in this session history. Both bugs confirmed via
# stderr inspection and live traces.
#
#
# Verdict: CWD opencode.json IS honored by opencode 1.17.11 acp.  ✅
# CWD-CONFIG is NOT blocked.  Build proceeds.
