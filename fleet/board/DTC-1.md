tier: strong
work_class: ci-infra
branch: feat/gate-registry
depends_on:
owns: tools/gates.json, tools/check_gate_registry.py
accept: python3 tools/check_gate_registry.py
prompt: /home/stack/charon-private/prompts/dtc-1.md
# BACKLOG (parked) — gate registry + validator: single source of truth for every active validation rule, enforcer resolution, domain/invariant uniqueness, and @covers annotation consistency.
