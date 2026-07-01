# TEST-PORT-FLAKE — Ephemeral ports for gateway tests

**Date:** 2026-06-27  
**Branch:** feat/test-ephemeral-ports  
**Owns:** tests/test_gateway.py, tests/test_gateway_tiers.py

## Problem fixed

CI was flaking on the <self-hosted-runner> self-hosted runner with `OSError: [Errno 98] Address already in use`
because the three offending tests bound the gateway server to the fixed port 8080 (the `GatewayConfig`
default `_DEFAULT_PORT`). This directly blocked PR #65 (RELEASE-SMOKE-FIX) and PR #66
(DOCS-TWO-MODE) CI runs; `docker compose down` on <self-hosted-runner> was a manual band-aid. This ticket removes
that band-aid permanently.

## Root cause

`GatewayConfig` is a frozen dataclass with `port: int = _DEFAULT_PORT` (= 8080). Tests that built
`GatewayConfig(...)` without an explicit `port` argument therefore bound `http.server.HTTPServer`
to the fixed port `(host, 8080)`. The OS refuses if anything else already holds 8080.

`GatewayProxyServer.__init__` already defaults to `port=0` — only the `GatewayConfig` path was
broken.

## Fix (minimal diff)

Three offenders, two files:

1. `test_gateway.py::test_models_endpoint_and_token_gate` — added `port=0` to the `GatewayConfig()`
   constructor.
2. `test_gateway.py::test_gateway_forwards_chat_completions_end_to_end` — same.
3. `test_gateway_tiers.py::test_setup_tiers_branch_persists_and_reloads` — `cfg` comes from
   `gateway.load_config()` so the constructor can't be patched directly; used
   `dataclasses.replace(cfg, port=0)` before `build_server()`. Added `import dataclasses`.

No `conftest.py` helper added — the three edits are distinct enough that a shared fixture would
add indirection without removing real duplication.

## Sweep results

**tests/test_gateway.py** and **tests/test_gateway_tiers.py**: only the three named offenders used
a fixed-port `GatewayConfig`. `test_gateway_shares_core_and_excludes_privileged_loop` calls
`GatewayProxyServer()` directly (no port arg) which already defaults to 0 — not an offender.

**Rest of tests/**: all other `gateway.build_server()` calls already pass `port=0` explicitly:
- `tests/test_setup_tiers.py` (lines 53-54, 71-72): `GatewayConfig(host="127.0.0.1", port=0, ...)`
- `tests/test_models_import.py` (line 154-155): same
- `tests/test_setup_web.py`: all five `build_server()` calls use `port=0`

No additional offenders found beyond the three in the ticket.

## Gate

560 tests pass; ruff/mypy clean; check_boundary OK; check_version OK.
