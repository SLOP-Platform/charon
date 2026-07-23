repo: charon
tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: greenfield-feature
branch: feat/client-connect-gui
depends_on:
owns: src/charon/connect.py, tests/test_connect_gui.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_connect_gui.py
prompt: /home/stack/charon-private/prompts/client-connect-gui.md
# BACKLOG (parked) — CLIENT-CONNECT follow-on: add cline + continue to the connect registry.
