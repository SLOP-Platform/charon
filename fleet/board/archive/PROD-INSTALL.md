repo: charon
tier: frontier
difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: greenfield-feature
branch: feat/prod-install-bootstrap
depends_on:
owns: install.sh, src/charon/cli.py, src/charon/doctor.py, README.md, docs/
accept: PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py
prompt: /home/stack/charon-private/prompts/prod-install.md
