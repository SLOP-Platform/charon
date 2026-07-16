# GATEWAY-NONTOKEN-METERING

**Problem:** NeuralWatt bills by energy (kWh/request), not tokens. The proxy's
`_gateway_usage` only extracts `cost`/`total_cost` from the OpenAI-compatible
usage dict — NeuralWatt responses that carry cost in a different field (e.g.
`energy_cost`, `total_cost` at top level) were recorded as $0.

**Solution:** Added non-token cost extraction in `gateway.py`:

1. `_extract_non_token_cost(body)` — checks `_NON_TOKEN_COST_FIELDS`
   (`total_cost`, `energy_cost`, `energy_kwh`, `total_cost_usd`) at both the
   response top-level and within the usage sub-object.
2. `_NonTokenAwareProxy(GatewayProxy)` — overrides `classify` to apply
   non-token extraction when the standard path yields zero cost.
3. `build_server` now passes a `_NonTokenAwareProxy` as the observer.

Extensible to future non-token billing shapes (flat-rate, request-cap) by
adding field names to `_NON_TOKEN_COST_FIELDS`.

**Scope:** `src/charon/gateway.py` only.
