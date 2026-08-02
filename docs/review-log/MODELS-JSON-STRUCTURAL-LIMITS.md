# MODELS-JSON-STRUCTURAL-LIMITS — the persisted catalog cannot hold the routing structure

Documentation-only ticket. No code moves. Records two structural limits of the
on-disk catalog (`models.json`) that the gateway's in-memory routing already
solves but the file format cannot express, plus the concurrency hazard that will
turn into a lost-update bug the moment PRICE-REFRESHER (ADR-0016 step #3) makes
`models.json` the cost-ordering source. Both were **documented but NOT fixed** by
the CATALOG-REFRESH-PERSIST wave; this fragment is the standing record so the
fix is not re-discovered the hard way in the price-refresher ticket.

## Finding 1 — one provider per model id: the failover chain cannot be persisted

`models.json` maps a model id to a **single** entry, and that entry carries at
most **one** `provider` (or a direct `upstream_base`):

- `config/models.py:add_model` builds one `entry` with a single `provider` key
  (`src/charon/config/models.py:76-89`).
- `config/models.py:add_models_bulk` stamps one `"provider": provider` per model
  id (`src/charon/config/models.py:120-131`).
- `config/_store.py` persists whatever dict it is handed; it has no notion of a
  provider list.

But the routing structure the gateway **actually uses** is a *chain*: one routable
(virtual) model id → an **ordered list** of provider-specific routes. That chain
lives in three in-memory places, none of which `models.json` can represent:

- `pools.json` → `pool_map` (virtual id → ordered `[model id]`), compiled into
  failover chains by `build_routes_and_pools`
  (`src/charon/routing_policy/__init__.py:144-208`) and served by
  `chain_for` (`src/charon/proxy_server.py:620-633`).
- the catalog-refresh cache, where each member id is `"<provider>/<raw>"` and the
  same normalized model id pools *several* provider members together
  (`src/charon/routing_policy/catalog_refresh.py:107-128`,
  `CatalogCache.registry_and_pool_map`).
- `GatewayConfig.pool_map`, merged in `load_config`
  (`src/charon/gateway.py:163-164,177,187`).

So the *multi-provider* failover chain — one logical model served by several
providers in cost order — is expressible in the running gateway but **not** on
disk in `models.json`. The persisted catalog can only ever hold one provider per
model id; the chain must be re-derived in memory from `pools.json` + the
provider-prefixed member ids. Any tool that treats `models.json` as "the routing
structure" (as PRICE-REFRESHER is slated to do) will silently see a
single-provider world.

## Finding 2 — read-modify-write is not mutually excluded: last writer wins

Every writer to `models.json` follows the same read-modify-write shape:
`load_models()` → mutate the dict → `_save(...)`:

- `config/models.py:add_model` (`75-90`), `add_models_bulk` (`108-133`),
  `set_model_enabled` (`140-144`)
- `config/_store.py:remove` (`63-70`)
- `discover.py:_update_model_pricing_from_discovery`
  (`src/charon/discover.py:210-248` — `config.load_models()` then a full
  `config._save("models.json", ...)`)
- `discover.py:import_openrouter_models` (`330-362` — calls `config.add_model`
  per match, i.e. a fresh read-modify-write per imported model)

There is **no file lock anywhere** in `src/charon` (no `fcntl`, `flock`,
`filelock`, `msvcrt`). `_save` is atomic per write (tmp + `replace`,
`src/charon/config/_store.py:42-49`), but that only prevents a torn file — it
does **not** serialize the load→mutate→save cycle. Two writers that load the same
snapshot concurrently both write back their full dict, and the **last writer
wins**, silently dropping the other's edit.

The catalog refresher's `self._lock`
(`src/charon/routing_policy/catalog_refresh.py:156`) guards only its *in-memory*
cache and the `bridge()` compile — it does not touch the `models.json` writers.
The known writers today are CLI-initiated (`add_model`, `import`,
`set_model_enabled`) and discovery-initiated (`_update_model_pricing_from_discovery`),
which run in separate paths and can interleave.

## Why both bite PRICE-REFRESHER

ADR-0016 step #3 (`docs/adr/0016-demand-driven-capability-match.md:186`) lands a
`price_refresher.py` that writes `model_pricing`; DELETE-STATIC-RANK (step #6,
landed) already makes ordering **derive from `cost_input`/`cost_output` in
`models.json`** plus the live meter
(`src/charon/routing_policy/cost_rank.py:64-92`). So `models.json` is (or
becomes) the cost-ordering source. When the price refresher starts writing cost
data into that file:

1. **Finding 1** means it can attach prices only to single-provider entries; a
   per-(model,provider) price for the second/third leg of a chain has no slot on
   disk — the cost-ordered chain the gateway actually routes with cannot be
   reconstructed from the file alone.
2. **Finding 2** means its writes race the existing writers
   (`discover.py`, `config/models.py`) with no exclusion — a refresh landing
   mid-`add_model` (or vice versa) silently loses one side's update, and the
   "cost-ordering source" starts serving a half-applied catalog.

## Fix direction (deferred — out of scope here)

A single follow-on can address both: give the on-disk entry an optional
`providers: [...]` / `upstream` list (keeping the legacy scalar `provider` for
back-compat), and serialize all `models.json` writers under one advisory file
lock (or route every mutation through a single store that owns the
load→mutate→save under one mutex). Neither is safe to bolt on casually because
every current writer assumes whole-file ownership; the change belongs to the
PRICE-REFRESHER ticket or its immediate prereq, not to a docs-only ticket.

## Verification

Both findings are READ-verified against `origin/master`:

- Single-provider persistence: `config/models.py:76-89` and `120-131` prove the
  entry schema can hold at most one `provider`.
- Chain-only-in-memory: `catalog_refresh.py:107-128`, `routing_policy/__init__.py:144-208`,
  `proxy_server.py:620-633`, `gateway.py:163-187` — every multi-provider
  structure is a runtime/pool artifact, never a `models.json` field.
- No lock: `grep -rn "fcntl\|flock\|filelock\|msvcrt" src/charon` → no matches.
- Writers enumerated from `grep -rn "_save(\"models.json\"\|load_models(" src/charon/`.

No code changed, so the standard gate (`pytest`, `ruff`, `mypy`, boundary,
version) is unaffected by construction.
