# DESTIFF-CLI-CHAT — cli.py probe routed through failover_loop

## Change
Refactored `_probe_key` in cli.py into three functions:
- `_check_probe_url(preset)` — URL safety validation (extracted from the old function)
- `_do_probe(base_url, api_key)` — single POST to /chat/completions (the actual HTTP call)
- `_probe_key(preset, key)` — backward-compatible wrapper → delegates to `_probe_keys`
- `_probe_keys(candidates)` — NEW: uses `invoke_with_failover` to try multiple providers in order

The POST at cli.py:395 is now inside `_do_probe`, which is called by `_probe_keys` through the shared
failover primitive. Existing per-key probe in `_cmd_setup` (via `_probe_key`) continues to work.

## Scope note
`tests/test_cli.py` line changed: `_probe_key(Preset(),...)` → `_do_probe(Preset.base_url, ...)`.
This was necessary because the User-Agent header test actually asserts on the HTTP transport layer,
which now lives in `_do_probe`. The test still validates the same invariant (P5 browser-like UA).

## Gates
- `PYTHONPATH=src python3 -m pytest -q tests/test_cli_chat_failover.py` — 5 pass
- `PYTHONPATH=src python3 -m pytest -q tests/test_cli.py tests/test_setup_key.py` — 21 pass
- `ruff check src/charon/cli.py` — OK
- `mypy src/charon/cli.py` — OK
- `PYTHONPATH=src python3 -m charon.cli gate` — ALL checks pass
