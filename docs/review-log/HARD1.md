# HARD1 — run_task tier-routing end-to-end test

**Ticket:** HARD1  
**Branch:** feat/run-task-routing-test  
**Date:** 2026-06-27

## What was built

`tests/test_run_task_routing.py` — two tests that exercise the routing glue
the tier-routing reviewers identified as unverified:

```
config.resolve_tier(role)
  → gateway.load_config(state_dir).pools[tier_vid]
  → per-run GatewayProxyServer
  → AcpBackend(OpencodeRenderer)
  → mock upstream at the wire
```

## Design decisions

### `accept=["false"]` instead of `["true"]`

`Ledger.is_complete()` is evaluated before the dispatch loop. With `accept=["true"]`,
the acceptance check passes immediately (before any dispatch), so the coordinator
returns `"complete"` with `checkpoints=0` — the ACP backend is never invoked.
Using `"false"` (always fails) forces the coordinator to dispatch the stub backend
once before returning `"blocked"` (L0 propose-only).

### Stub ACP agent (written to `tmp_path/stub_agent.py`)

A minimal Python script that:
1. Speaks ACP JSON-RPC over stdin/stdout (`initialize` / `session/new` / `session/prompt`)
2. On `session/prompt`: reads `OPENCODE_CONFIG_CONTENT` (set by `OpencodeRenderer`),
   extracts `baseURL` and the short model key (the tier vid), and POSTs to the
   per-run gateway proxy.
3. The POST happens BEFORE responding to `session/prompt` so it is guaranteed
   complete before `AcpBackend._rpc` returns (no race with `b.kill()`).

### `CHARON_HOME` vs `state_dir`

`config.load_tiers()` reads `tiers.json` from `config_dir()` = `CHARON_HOME`.
`gateway.load_config(state_dir=…)` reads `models.json` from `state_dir`.
The test sets `CHARON_HOME` via `monkeypatch.setenv` to a `tmp_path` subdir,
keeping both registries hermetic and independent.

### Mismatch test

`tiers.json` names `"ghost-model"` which is absent from `models.json`.
`_build_routes_and_pools` filters out unresolvable members → empty chain for
the `"high"` vid. The dry-pool early-return in `api.run_task` fires and returns
`{status:"exhausted"}` BEFORE any dispatch — the upstream is never hit.

## Assertions

**Happy path:**
- `result.get("status") != "exhausted"` — pool was non-empty, proxy served
- `upstream.received == ["wire-model"]` — the upstream_model rewrite reached the wire

**Mismatch regression:**
- `result["status"] == "exhausted"` — dry-pool early-return fired
- `upstream.received == []` — no routing occurred
