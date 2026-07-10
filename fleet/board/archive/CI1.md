tier: sonnet
difficulty: 2  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: ci-infra
branch: feat/ci-runner-var
depends_on:
owns: .github/workflows/ci.yml, .github/workflows/heavy.yml, .github/workflows/release.yml, docs/DECISIONS.md, CONTRIBUTING.md
prompt: /home/stack/charon-private/prompts/ci-runner-var.md
