# FALLBACK-PROVIDER — global fallback provider chain for the gateway

## Dependencies & sequence
**depends_on: NONE — Wave 2.** Owns `gateway.py` + `config.py` + `proxy_server.py`.
Can run independently of any other ticket. A fresh Charon can claim it immediately.

## Why (operator, 2026-06-30)
Today the gateway has per-model failover pools (create a pool `model_id → [a, b, c]`).
This requires configuring every model individually. When a provider exhausts credits
(e.g. opencode-zen today), the operator must manually add failover to every model.

A DEFAULT fallback provider solves this once: "for any model whose primary provider
fails, try this chain." One setting, all models covered.

## What to build
A global fallback provider chain — persisted config + gateway route extension:

1. **Config storage:** Add `fallback_providers` (list of provider names) to the
   gateway's config model. Persist to a new `fallback.json` in `config_dir()`,
   or to the existing `providers.json`. The UI writes it; the gateway reads it.
2. **Gateway integration:** In `_build_routes_and_pools` or `load_config`, after
   building each model's route chain, APPEND the fallback provider routes to
   the end of every model's pool chain. The fallback providers are tried ONLY
   after the model's own providers fail.
3. **Web setup UI:** Add a "Global fallback" section to `_SETUP_HTML` that lets
   the user select providers from the configured list and order them.
4. **Hot-reload:** When the fallback config changes, recompile all model chains
   via the existing `apply_routes` / `_reload` path.

## Security
- Fallback providers must already have configured keys (no key entry in this UI).
- The fallback list is stored in `fallback.json` (no secrets).

## Acceptance
- A model with only opencode-zen as provider + fallback set to opencode-go:
  when opencode-zen returns 429, the gateway fails over to opencode-go.
- The fallback config persists across gateway restarts.
- Web UI shows the current fallback chain and allows reordering.
- No secrets in responses or logs.

## CONSTRAINTS
Own ONLY: `src/charon/gateway.py`, `src/charon/config.py`, `src/charon/proxy_server.py`,
`tests/test_fallback_provider.py`. Stdlib core only; gate GREEN. Conventional commits.
