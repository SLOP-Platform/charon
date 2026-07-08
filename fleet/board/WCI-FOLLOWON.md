tier: frontier
work_class: greenfield-feature
branch: feat/wci-semantic-slice
depends_on: WCI
real-dep: DSGN-WCI-PROOF §5.1 proof APPROVED 2026-07-02 — §5.1 contract at fleet/DSGN-WCI-5-1-PROOF.md
owns: src/charon/engine/board.py, src/charon/engine/semantic_proof.py, src/charon/intake.py, tests/test_semantic_proof.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_semantic_proof.py ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py
prompt: /home/stack/charon-private/prompts/wci-followon.md
