tier: strong
branch: feat/dtc-meta-tests
depends_on: DTC-2
owns: tests/test_no_secrets.py, tests/test_auth_meta.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_no_secrets.py tests/test_auth_meta.py
prompt: /home/stack/charon-private/prompts/dtc-3.md
# BACKLOG (parked) — meta-tests: two property-based tests replacing 22+ individual tests. (1) zero-secrets: no output surface leaks a known secret pattern. (2) auth-gate: all write endpoints reject unauthenticated requests.
