# CATALOG-REFRESH-PERSIST — review fragment

Ticket: CATALOG-REFRESH-PERSIST
Branch: fix/catalog-refresh-persist (off origin/master)
Owns: src/charon/routing_policy/catalog_refresh.py, tests/test_catalog_refresh_persist.py

## Problem

The catalog refresher (`catalog_refresh.py`) polls every configured provider's
`GET /models` on a TTL and bridges results into the live router via
`apply_routes`. This works for in-memory routing — but the catalog was NEVER
persisted to disk. `models.json` held only operator hand-entries; the refresher
held results in RAM. Every restart discarded all discovered models.

Measured on the live gateway (2026-08-01): `models.json` was 33 bytes
(config only), `catalog_refresh.json` existed with TTL config, but no catalog
cache file existed on `/data`. The log showed the poller running every 6h with
404 failures on `cline-pass`, but no write-back was ever attempted.

Consequences: `free=False` on genuinely free Zen models, 647 of 859 entries
with no `cost_rank`, and a free-tier model list that went stale as Zen
rotated models in and out.

## Decision: write-back into models.json

The refresh now calls `_persist_unlocked()` after each provider poll. Merge
rules (precedence, highest first):

1. `upstream_base` or `key_env` in existing entry → skip (hand-owned).
2. `refresh_disabled: true` in existing entry → skip (explicitly opted out).
3. `enabled: false` in existing entry → skip (operator intent wins; does NOT set
   `refresh_disabled` so operator can re-enable).
4. New model absent from catalog → add entry with `provider`, `upstream_model`,
   `free`, `cost_input`/`cost_output`, meta fields, `refreshed_via`, `refreshed_at`.
5. Model not in this provider's current `/models` → mark `enabled: false,
   refresh_disabled: true` (rotation surfaced; bridge drops in-memory route).
6. Existing discovered entry → update pricing/flags and stamp `refreshed_via`.

Write is atomic: JSON serialized to `.tmp`, then `replace()`.

## Bugs found during development

**Bug 1 (stale-but-usable regression)**: The initial implementation called
`cache.put(provider, {}, failure=exc)` on a poll failure, overwriting the
cache with empty entries — breaking the existing `CatalogCache.put` behavior
where failure means "keep prior entries." Fix: skip `put` entirely on failure;
only set `last_failure[name] = failure` and clear `updated[name]`.

**Bug 2 (casefold merge)**: `_normalize("My-Model") = "my-model"` but the
hand-entry key was `"mymodel"`. Casefold match on normalized id fails. Fix:
match by `upstream_model` field instead of key name — `_find_by_upstream_model`
scans existing entries for matching `upstream_model` and updates that key in
place.

**Bug 3 (status_summary)**: `status_summary` checked `name in cache.updated`
to decide OK vs failed, but a failed poll doesn't call `cache.put` so `updated`
retained the stale success timestamp. Fix: also check `name in cache.last_failure`
as the primary indicator; clear `cache.updated[name]` on failure alongside
setting `last_failure`.

## What's NOT in scope

- No changes to `proxy_server.py`, `gateway.py`, `routing_policy/__init__.py`.
  The bridge (`bridge()`) already works; persistence is orthogonal.
- No changes to `discover.py`'s `_update_model_pricing_from_discovery` — that
  function handles a different flow (on-demand discovery, not TTL polling).
- No changes to the catalog that feeds `model_catalog.py` (curated tier
  recommendations — a separate system).

## Verification

```
PYTHONPATH=src python3 -m pytest -q tests/test_catalog_refresh_persist.py
tests/test_catalog_refresh.py
12 passed in 0.37s

Full suite: 2436 passed, 3 skipped, 1 xfailed, 1 xpassed in 72.06s
ruff: clean
mypy: clean
check_boundary: clean
check_version: clean
```

All 5 RED contracts from the ticket are green:
- (a) new model persists + survives restart: `test_discovered_model_persists_and_survives_restart`
- (b) rotated-out model marked unavailable: `test_disappeared_model_marked_unavailable`
- (c) `free` flag from provider: `test_free_flag_from_provider_lands_in_catalog`
- (d) operator intent survives: `test_enabled_false_survives_refresh` + `test_hand_added_entry_survives_refresh`
- (e) stale-but-usable + failure surfaced: `test_stale_but_usable_and_failure_surfaced`
