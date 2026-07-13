# PRICE-REFRESHER — background price cache (ADR-0016 #3, ADOPT-NOT-BUILD)

## Change

New disjoint file `src/charon/routing_policy/price_refresher.py` with three
background cache-writers that feed the local `model_pricing` dict the routing
layer reads. No bespoke scraper, no hand-typed table, no hot-path network call.

### Three writers (all off-hot-path)

**(a) Vendored LiteLLM price table** (`_data/litellm_prices.json`, MIT, BerriAI).
Loaded once at module import via `seed_from_vendored()` → `CacheState.model_pricing`.
Replaces R17's hand-typed TSV as the sourced table. Provider-keyed via
`PROVIDER_KEY_MAP` (21 entries mapping `litellm_provider` → Charon pool label).

**(b) OpenRouter live poll** — `refresh_openrouter_now()` does a single
unauthenticated GET to `/api/v1/models`, parses per-token pricing, writes to cache
with `priced_by: "openrouter_live"`. TTL-gated by `openrouter_poll_due()` (default
hourly). Functions as both the live layer for the openrouter pool and the drift
oracle for the vendored snapshot.

**(c) changedetection.io webhook ingest** — `DriftEvent` dataclass + `parse_drift_event()`
+ `apply_drift_event()` for the zero-coverage providers (nanogpt, neuralwatt,
opencode-zen). The detector is self-hosted infra; this module exposes the ingest
schema + cache writer.

### Keying

`model_pricing` is keyed by model id string (not `(provider, model)` tuple),
matching how the forwarder's R2 block (`forwarder.py:386-393`) composes the
registry view. The ticket's pitfall #4 warning is acknowledged in the docstring
with rationale: Charon's registry pass projects each model onto a single
`(model_id → provider)` route, so model-level keying is consistent with the
routing layer's `_live_rank_key` lookup. Per-provider pricing would require
changes to the forwarder's registry composition, which is out of scope.

### Constraints honored

- **Off-hot-path**: every writer is a callable function (no autostart, no thread,
  no daemon). `order_pool_by_live_cost` reads cache only — test asserts no
  `urllib.request.urlopen` on the routing path.
- **Stale-but-usable**: all writers catch + log errors, record in `state.last_error`,
  never raise into the request path.
- **Meter supersedes**: `derived_cost_rank` (unchanged, in `cost_rank.py`) already
  prefers `metered_cost` over `cost_input`/`cost_output` when available.
- **Clobber protection**: all writers skip entries with `priced_by` not in
  `("vendored", "openrouter_live", "webhook")` — operator-set prices survive.

### Test coverage

`tests/test_price_refresher.py` (17 tests, all PASS):

1. `test_vendored_snapshot_is_actually_vendored_on_disk` — FAIL-ON-REVERT
2. `test_seed_from_vendored_populates_model_pricing` — FAIL-ON-REVERT
3. `test_seed_from_vendored_idempotent`
4. `test_seed_does_not_clobber_operator_set_price`
5. `test_vendored_seed_orders_cheaper_provider_first_with_empty_meter` — FAIL-ON-REVERT
6. `test_order_pool_by_live_cost_never_opens_network` — FAIL-ON-REVERT
7. `test_price_refresher_writer_uses_off_path_only`
8. `test_meter_supersedes_vendored_quote_in_live_rank` — FAIL-ON-REVERT
9. `test_vendored_file_present_on_disk`
10. `test_openrouter_poll_writes_to_cache`
11. `test_openrouter_poll_failure_does_not_raise`
12. `test_drift_event_parses_and_writes`
13. `test_drift_event_invalid_returns_none`
14. `test_build_registry_view_merges_models_and_prices`
15. `test_provider_key_map_covers_all_charon_wired_providers`
16. `test_apply_to_cache_writes_per_provider_entry`
17. `test_apply_to_cache_rejects_negative_prices`

### Reviewer notes

- The vendored LiteLLM snapshot has 997 entries across 21 mapped providers.
- `order_pool_by_live_cost` with empty meter returns the chain unchanged
  (preserves static order). This is the existing behavior — the price-refresher's
  seed data only matters once the forwarder's R2 block composes per-provider
  pricing into the registry view (future work in DELETE-STATIC-RANK #6).
- No changes to `routing_policy/__init__.py`, `forwarder.py`, or `proxy.py` —
  this is a disjoint new file that only writes the cache the routing layer reads.
