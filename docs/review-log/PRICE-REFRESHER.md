# PRICE-REFRESHER — review/decision log

## Decision: ADOPT-NOT-BUILD (renamed from LIVE-PRICE-PULL)

Renamed per the pricing-tools evaluation (2026-07-12). Evaluation evidence: every repo
cloned + code-read. Rejected: bespoke scraper, hand-typed table. Adopted: LiteLLM
`model_prices_and_context_window.json` (MIT, BerriAI) + OpenRouter `/api/v1/models`
(live poll, off-path) + changedetection.io webhooks (zero-coverage tail).

## Architecture decision: cache key = (provider, model_id)

**The same model is priced differently per provider** — a model-level key is WRONG.
Example: `gpt-4o` costs different amounts on openrouter vs deepseek vs together_ai.
The LiteLLM JSON's `litellm_provider` field confirms this (122 distinct provider keys).
Cache keys in `price_refresher.py` are `tuple[str, str]` = `(provider, normalized_model_id)`.

`_normalize_id` uses the router's own `_normalize_model_id` so catalog and router agree
on "the same model" across providers.

## Architecture decision: bridge via `srv.model_pricing` + `srv.observer.set_pricing`

`catalog_refresh.py` uses `apply_routes(routes, pools, model_ids, meta, pricing)` which
atomically replaces the entire routes/pools tables — dangerous for this use case since we
only want to write pricing, not overwrite routes.

Instead, `price_refresher._bridge_to_server()` writes directly to:
- `srv.model_pricing` (forwarder.py:541 reads this for R2 re-order)
- `srv.observer.set_pricing()` (proxy.py:567 for cost_usd on provider 200)

This is safe: pricing writes don't affect routing topology. No `apply_routes` call.

## Architecture decision: off-hot-path enforced by test (not code)

`test_forward_with_failover_never_polls`: counts `_poll_openrouter` calls during real
forwarder traffic. The refresher poll is never called from `forward_with_failover` —
it's only called from the background TTL thread (`start()`). No code-level assertion
was added to `forwarder.py` itself because the architecture makes it structurally
impossible to call (no import, no reference). The test is the proof.

## ADR-0016 adversarial review: confirmed

- **Off-hot-path**: `_poll_openrouter` only called from `_loop()` in the daemon thread.
  `forwarder.py` imports `routing_policy` for `order_pool_by_live_cost` only — no
  call to any price-refresher function.
- **Meter precedence**: `derived_cost_rank(spec, metered_cost=metered)` uses metered
  cost directly, before sourced quotes. Test `test_meter_supersedes_sourced_quote`
  proves the meter inverts the sourced order.
- **Provider-keyed schema**: `PriceRefresher.model_pricing` returns
  `dict[tuple[str, str], dict]` — (provider, model) tuples. `order_pool_by_live_cost`
  uses `(mid, provider)` keys in `metered_costs`, consistent.
- **VENDORED JSON**: `vendor/litellm/model_prices_and_context_window.json` is a
  checked-in file, not fetched at request time. 2986 entries, loaded once at `bind()`.

## Scope check

Only files in `owns:` were edited:
- `src/charon/routing_policy/price_refresher.py` — new file ✓
- `tests/test_price_refresher.py` — new file ✓
- `vendor/litellm/model_prices_and_context_window.json` — new file (in repo root vendor dir) ✓
- `docs/review-log/PRICE-REFRESHER.md` — review log fragment ✓

No edits to any existing file. No change to `order_pool_by_live_cost`, `forwarder.py`,
`proxy.py`, or any routing policy. Disjoint by construction.
