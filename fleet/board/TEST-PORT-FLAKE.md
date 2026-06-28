tier: sonnet
branch: feat/test-ephemeral-ports
depends_on:
owns: tests/test_gateway.py, tests/test_gateway_tiers.py
prompt: /home/stack/charon-private/prompts/test-ephemeral-ports.md
scope: CI robustness (test-only). The gateway tests bind a FIXED port (8080) — `GatewayConfig.port`
  defaults to `_DEFAULT_PORT = 8080` and the offenders never override it — so on the shared 4-lom
  self-hosted runner they fail `OSError: [Errno 98] Address already in use` whenever anything else
  holds 8080 (leftover `charon gateway`, a Docker container, or a concurrent CI job). Fix: bind an
  EPHEMERAL port (port 0) and read the actually-bound port back via `server.server_address[1]`
  (the `GatewayProxyServer.url` property already does this; the mock UPSTREAM helper already binds
  port 0 — mirror it for the gateway server). 3 offenders:
  `tests/test_gateway.py::test_models_endpoint_and_token_gate`,
  `tests/test_gateway.py::test_gateway_forwards_chat_completions_end_to_end`,
  `tests/test_gateway_tiers.py::test_setup_tiers_branch_persists_and_reloads`.
  A tiny `tests/conftest.py` helper is PROVISIONAL — only if it removes real duplication; prefer
  editing the tests directly.
note: ACTIVE / claimable. Real CI bug found 2026-06-27: the FIXED-8080 bind made #65
  (RELEASE-SMOKE-FIX) and #66 (DOCS-TWO-MODE) CI flake on 4-lom with Errno 98; a manual
  `docker compose down` to free 8080 unblocked them — this ticket removes that band-aid for good.
  CONSTRAINTS: TEST-ONLY — do NOT touch src/ (`_DEFAULT_PORT` stays 8080, the correct PRODUCT
  default; only the tests must not pin it); product-clean (no SLOP/fleet/rig leak);
  agent/provider-agnostic; minimal diff; tests still pass. No depends_on — stands alone.
  OWNS-COLLISION CHECK (authoring, 2026-06-27): `tests/test_gateway.py` and
  `tests/test_gateway_tiers.py` are owned by NO other ACTIVE ticket (the whole board is DONE).
