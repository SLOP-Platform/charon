repo: charon
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: bugfix
branch: feat/setup-key-ux
depends_on:
owns: src/charon/cli.py, tests/test_setup_key.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_setup_key.py
prompt: /home/stack/charon-private/prompts/setup-key-ux.md
# BACKLOG (parked) — 2026-06-28 dogfood: setup accepted a bad key blindly (no validation, no echo).
# owns cli.py; disjoint from all other parked backlog tickets.
