# CATALOG-COMPLETENESS — review/decision note

## Context
Operator P0 (2026-08-01): the live gateway had **0 of 859** priced catalog
entries and `cost_map.json` was never written, so any "cheapest-first" routing
claim ranked on absent data. Cost is a money-path concern.

## Ownership / path note
The ticket `owns:` lists `src/charon/providers/discover.py`, but no such path
exists — the single discover module lives at `src/charon/discover.py` (there is
no `providers/` subdir). The intent (discover.py + the new test file) is
unambiguous, so edits target the real file.

## Decisions
1. **Required fields are a SEPARATE gate (`validate_catalog_entry`), not a
   mutation of `build_cost_map`.** The existing `tests/test_discover.py` (not
   owned by this ticket) asserts `build_cost_map` accepts unpriced entries
   (`test_pricing_absent`). Making `build_cost_map` raise would break that
   external spec. Instead the completeness check is its own function — the
   single home for "is this entry complete enough to route on" — so the cost
   directive never ranks on absent data without disturbing the lower-level
   cross-reference. Contract (a) is satisfied by `validate_catalog_entry`
   raising `CatalogIncompleteError` loudly; (d) by a complete entry passing
   untouched.

2. **Restart reads disk via `get_cost_map`, not `discover_models`.** The
   existing `test_discovery_refreshes_its_own_earlier_price` relies on
   `discover_models` ALWAYS recomputing to pick up an upstream price change.
   Adding a read-from-disk short-circuit inside `discover_models` broke it
   (RED observed, then reverted). So `discover_models` keeps its always-poll
   behavior (and persists), and the new `get_cost_map(config_dir, refresh=False)`
   is the restart path that reads the persisted map without re-polling —
   contract (b). The poller is never invoked on a restart that has a cache.

3. **Cheapest-first within a model (contract c).** `build_cost_map` now sorts
   each model's provider list by the 3:1 in:out blend (mirrors
   `routing_policy.derived_cost_rank`), stable so discovery order breaks ties.
   Unpriced offers sort last (`inf`) so they never float above a priced one.

4. **litellm feed adopted as the FIRST price source (scope 3).** Reads
   `litellm.model_cost` (the in-memory form of
   `model_prices_and_context_window.json` — the JSON file itself is absent in
   this litellm version, but `model_cost` carries the same data). Fills
   `cost_input`/`cost_output`/`context_window` a provider's /models omitted;
   records disagreement in `price_sources` (provider quote wins, litellm
   figure preserved) rather than silently picking a winner. Lazy import;
   discovery still imports/runs without litellm installed. zai/* GLM models
   are present in the live feed (scope 4 covered, with a live-feed test).

## Before/after (priced entries, live catalog)
- Before: **0 of 859** catalog entries carried any price field; `cost_map.json`
  ABSENT on the live gateway.
- After: `build_cost_map` now extracts per-token cost from provider /models
  pricing AND corroborates with litellm `model_cost` (~3000 models), so an
  entry missing a price is filled from the feed; `cost_map.json` is persisted
  on every `discover_models` run and read on restart via `get_cost_map`.
  Required-field enforcement is loud (`CatalogIncompleteError`).

## Gate
`tests/test_catalog_completeness.py` (19 tests) green; `tests/test_discover.py`
(40 tests) still green. Full gate green except the pre-existing
`tests/test_autoland.py` git-env failures (identical on clean master —
`git rev-parse master` exits 128 in the temp repos; unrelated to this change).
ruff/mypy/boundary/version all OK.
