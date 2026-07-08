tier: strong
work_class: ci-infra
branch: feat/dtc-arch-boundary
depends_on:
owns: tools/check_arch.py, tests/test_check_arch.py
accept: python3 tools/check_arch.py src
prompt: /home/stack/charon-private/prompts/dtc-5.md
# BACKLOG (parked) — architecture layer audit tool: validates Charon's architectural invariants (engine↔gateway isolation, no circular imports, stdlib-only core, no vendor hardcoding in engine/gateway).
