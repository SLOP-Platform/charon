repo: charon
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: tests
branch: feat/dtc-test-patterns
depends_on:
owns: tools/check_test_patterns.py, tests/test_check_test_patterns.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_check_test_patterns.py
prompt: /home/stack/charon-private/prompts/dtc-8-test-patterns.md
# BACKLOG (parked) — test-pattern enforcement gate: scans test files for duplicate names, missing docstrings, insufficient parametrization, and bloated test functions. Registers in gates.json.
