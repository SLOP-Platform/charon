tier: strong
branch: feat/model-discovery
depends_on: DS-PLAN-REVIEW
owns: src/charon/config.py, src/charon/providers.py, src/charon/gateway.py, src/charon/proxy_server.py, src/charon/api.py, src/charon/cli.py, tests/test_gateway.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_gateway.py -k "models_endpoint or model_meta" && PYTHONPATH=src python3 -m pytest -q
prompt: /home/stack/charon-private/prompts/model-discovery.md
# BACKLOG — dogfood-driven: enrich /v1/models response with model metadata + exclude pool IDs from discovery.
# NOTE: collisions with OBS-UI (owns proxy_server.py) and ORCH-ROUTE (owns api.py). Sequence me AFTER Wave 1 or carefully.
