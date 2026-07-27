repo: charon
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: tests
branch: feat/dtc-shared-http
depends_on:
owns: tests/conftest.py, tests/test_shared_http.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_shared_http.py
prompt: /home/stack/charon-private/prompts/dtc-2.md
# BACKLOG (parked) — shared HTTP test fixtures: create reusable pytest fixtures in conftest.py for the mock HTTP upstream pattern duplicated across 7 test files. Migrate test_routing_proxy.py as proof.
