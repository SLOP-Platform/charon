tier: sonnet
branch: feat/ci-hardening
depends_on: FB6
owns: .github/workflows/ci.yml, .github/workflows/heavy.yml, .github/workflows/release.yml, .github/workflows/windows-exe.yml, pyproject.toml
prompt: /home/stack/charon-private/prompts/fb5.md
note: From the 2026-06-27 fragility audit THEME 8 (CI/supply-chain). depends_on FB6 because it
  wires FB6's tools/check_decisions.py --check into the gate (the script must exist first).
