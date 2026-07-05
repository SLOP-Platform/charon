tier: strong
branch: feat/obs-capture
depends_on:
owns: src/charon/adapters/acp.py, src/charon/ports/backend.py, src/charon/adapters/mock.py, src/charon/coordinator.py, src/charon/decompose.py, tests/test_acp_capture.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_acp_capture.py
prompt: /home/stack/charon-private/prompts/obs-capture.md
# BACKLOG (parked) — WORK-OBSERVABILITY follow-on: persist per-unit agent transcript.
# Thread a state_dir seam into AcpBackend.dispatch() (protocol + call sites) — write agent.log under the durable ledger dir (<state_dir>/<id>/agent.log). Does NOT touch scheduler.py; no WCI collision.
