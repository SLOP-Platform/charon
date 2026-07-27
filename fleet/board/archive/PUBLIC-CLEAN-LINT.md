repo: charon
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: ci-infra
branch: feat/public-clean-lint
depends_on:
owns: tools/check_public_clean.py, tools/check_boundary.py, tests/test_public_clean.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_public_clean.py
prompt: /home/stack/charon-private/prompts/public-clean-lint.md
# BACKLOG (parked) — 2026-06-28 audit: public repo leaks recur. Mechanize a hard-gate lint
# (+scrub current charon leaks) and research the cross-repo approach (SLOP ticket mirrors it).
