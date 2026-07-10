tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: ci-infra
branch: feat/dtc-charon-gate
depends_on: DTC-1
owns: src/charon/cli.py, tools/check_boundary.py, tools/check_version.py, .github/workflows/ci.yml
accept: python3 -m charon gate && python3 tools/check_boundary.py src && python3 tools/check_version.py
prompt: /home/stack/charon-private/prompts/dtc-4.md
# BACKLOG (parked) — unified `charon gate` subcommand: runs ruff + mypy + boundary + version + gate-registry checks as one tool. Update CI from 7 steps to 3-4. Individual tools remain callable standalone.
