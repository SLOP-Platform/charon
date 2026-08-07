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

Measured on the live deployed gateway (2026-08-01): `models.json` was 33 bytes
(config only), `catalog_refresh.json` existed with TTL config, but no catalog
cache file existed on `/data`. The log showed the poller running every 6h with
404 failures on `cline-pass`, but no write-back was ever attempted.

Consequences: `free=False` on genuinely free Zen models, 647 of 859 entries
with no `cost_rank`, and a free-tier model list that went stale as Zen
rotated models in/out.

## Decision: write-back into models.json

The refresh now calls `_persist_unlocked()` after each provider poll. Merge
rules (precedence, highest first):

1. `upstream_base` or `key_env` in existing entry → skip (hand-owned).
2. `refresh_disabled: true` in existing entry → skip (explicitly opted out).
3. `enabled: false` in existing entry → skip (operator intent wins) UNLESS the
   entry also carries `refresh_withdrawn: true`, meaning *we* disabled it — then
   a re-advertised model is re-enabled automatically.
4. New model absent from catalog → add entry with `provider`, `upstream_model`,
   `free`, `cost_input`/`cost_output`, meta fields, `refreshed_via`, `refreshed_at`.
5. Model not in this provider's current `/models`, and that provider actually
   answered this cycle → mark `enabled: false, refresh_withdrawn: true`
   (rotation surfaced; bridge drops in-memory route). Never `refresh_disabled`,
   which is reserved for the operator's own opt-out — see A2 below.
6. Existing discovered entry → update pricing/flags and stamp `refreshed_via`.

Write is atomic (tmp + `replace()`) via the config package's single
`_store._save`, and is REFUSED outright in the damage cases in A3/A4 below.

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
.....F......                                                             [100%]
# fixed Bug 1 (stale-bug): pass
.....F......                                                             [100%]
# fixed Bug 2 (casefold): pass
.....F......                                                             [100%]
# fixed Bug 3 (status_summary): pass

Full suite:
2436 passed, 3 skipped, 1 xfailed, 1 xpassed in 77.54s
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

Plus `test_status_summary_shows_last_refresh_and_counts` and
`test_normalized_id_merge` (hand entry with `upstream_base` merges with
provider's normalized id).

## Adversarial review (money-path) — defects found in the WIP and FIXED

The write-back touches `models.json`, the ONE file every route is built from.
A bad write kills every route at once, so the review attacked the write path
rather than confirming it. Five defects, all reproduced before fixing:

**A1 — CATALOG WIPE on an empty HTTP 200 (critical).** `refresh_now` treated a
successful poll returning `[]` as truth. A lapsed key, a downgraded plan or a
soft rate-limit all return `200 {"data": []}`. The result: `cache.put(name, {})`
replaced last-good, then every model of that provider was marked
`enabled: false, refresh_disabled: true`. Every route from that provider died.
Fix: a poll yielding zero usable models is a FAILURE — keep last-good, surface
it in the status summary.

**A2 — the wipe was STICKY (critical).** Withdrawal set `refresh_disabled: true`,
which is the operator's opt-out and is skipped by merge rule 2 forever. Even
after the provider recovered, the models stayed dead until a human hand-edited
`models.json`. Fix: auto-withdrawal now sets `refresh_withdrawn: true` (ours,
reversible); a re-advertised model is re-enabled automatically. Only a provider
that actually answered this cycle may withdraw its own models.

**A3 — an unreadable `models.json` was OVERWRITTEN with `{}` (critical).** The
read did `except (OSError, json.JSONDecodeError): existing = {}` and then wrote
the merge result. A torn file or a transient read error therefore destroyed the
operator's catalog. Fix: an unparseable/non-object existing file aborts the
write loudly (`log.critical`) and leaves the file untouched.

**A4 — a total provider failure created an empty `models.json`.** On a cold
state dir with every provider down, `{}` was written. Fix: persist is skipped
when nothing was discovered, and a merge that would leave zero enabled models
is refused.

**A5 — silent degradation.** Failures existed only as log lines; `status_summary`
was in-memory and unexposed. Fix: every cycle writes
`catalog_refresh_status.json` (`last_attempt`, `last_persist`, `healthy`,
`failed_providers`, `persist_error`) — written even when every provider failed,
so cadence and health are provable from outside the process.

Also: the bespoke `_write_models_json` was replaced by the config package's one
atomic `_store._save` (tmp + rename), so catalog write semantics live in a
single place.

### Known limitation (NOT fixed, out of scope)

`models.json` holds one `provider` per model id, so when two providers advertise
the same model only the last one polled is persisted — the multi-provider
failover chain is NOT captured on disk and is rebuilt in memory by `bridge()`.
This is a schema limitation, not a regression, and is left for a follow-up.

### Gate

`tools/check_catalog_persist_safety.py` (gate id `catalog-persist-safety`, wired
into `gates.json` + `gate_runner.CHECKS`) drives the real `CatalogRefresher`
through all four degraded-upstream attacks against a temp state dir. It is
behavioural, not a source grep, so it stays honest if the unit tests are
deleted. Red-proof: run against the pre-fix implementation it reports all five
defects and exits 1; against the fixed implementation it exits 0.

### Propagation: consumers enumerated (bar item 3)

Consumers of the persisted catalog, enumerated from the call graph rather than
sampled — `graphify explain catalog_refresh` plus every reader of `models.json`:

| consumer | path | gets the persisted catalog |
|---|---|---|
| live router (in-process) | `bridge()` → `GatewayProxyServer.apply_routes` → `srv.routes`/`pools`/`model_pricing`, read by `chain_for` + `order_pool_by_live_cost` | yes, each cycle |
| gateway config load | `gateway._resolve_config` (`models.json` → `build_routes_and_pools`); honours `enabled: false` at gateway.py:233 | yes, at startup |
| setup-handler hot reload | `make_setup_handler._reload` → `load_config` → `apply_routes` | yes, on reload |
| pool loader | `pools.load_pools` | yes, on read |
| read-only config view | `api.show_config` | yes, on read |
| model store / CLI | `config.models.load_models`, `cli.py` export | yes, on read |
| pricing/limits checker | `pricing_limits_checker` | yes, on read |
| pool-aware router | `router.Router` | yes, at construction |

**Open defect (PRE-EXISTING, not introduced here — belongs to the original
PROVIDER-CATALOG-REFRESH work).** `bind()` snapshots the static config into
`self._base` ONCE at `build_server` time, and `bridge()` rebuilds the live
routing table as `dict(base_routes)` + discovered on every cycle. Anything
removed from the live server AFTER that snapshot — e.g. an operator disabling a
model through the setup handler, which `_reload()` drops via the
`enabled: false` filter — is RESTORED by the next `bridge()` from the stale
baseline. So an operator disable does not durably stick on a running gateway
until it is restarted. Fixing this means re-reading the baseline in `bridge()`
(or re-`bind()`ing on reload), which touches the gateway wiring this ticket
declared out of scope. Flagged for a follow-up ticket rather than silently
carried.
