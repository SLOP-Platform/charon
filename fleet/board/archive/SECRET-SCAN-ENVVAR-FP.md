tier: sonnet
difficulty: 2  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: feat/secret-scan-envvar-fp
depends_on:
owns: .gitleaks.toml, tests/test_land_secret_allowlist.py
prompt: /home/stack/charon-private/prompts/secret-scan-envvar-fp.md
# BACKLOG (parked) — surfaced by the 2026-06-27 cert: land gate false-positives on env-var bearer
# headers. Tackle after the priority cluster if budget remains. Unpark: mv *.md.parked *.md
