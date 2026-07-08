tier: strong
work_class: refactor
branch: feat/bridge-harden
depends_on:
owns: ~/.config/opencode/session-bridge/server.py, ~/.config/opencode/opencode.json, AGENTS.md, /home/stack/charon-private/fleet/BRIDGE-IMPROVEMENT-PLAN.md
accept: python3 ~/.config/opencode/session-bridge/server.py --health 2>/dev/null; echo "verify: board returns advisories + expires_in_seconds"
prompt: /home/stack/charon-private/prompts/bridge-harden.md
# PARKED — requires operator review of BRIDGE-IMPROVEMENT-PLAN.md before activation.
# Cross-repo: bridge server lives at ~/.config/opencode/session-bridge/ (not under src/).
