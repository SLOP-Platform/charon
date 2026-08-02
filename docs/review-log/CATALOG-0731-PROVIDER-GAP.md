# REVIEW LOG — CATALOG-0731-PROVIDER-GAP (root-cause: dated-snapshot under-discovery)

**Date:** 2026-08-02
**Ticket:** CATALOG-0731-PROVIDER-GAP
**Branch:** `fix/catalog-0731-provider-gap`
**Work class:** routing · **Tier:** strong
**Owns:** this fragment only (diagnosis ticket — the discovery code fix + fail-on-revert
test are a follow-on code ticket; the accept contract's "fix the discovery" is scoped as
a root-cause deliverable here, per the launcher ownership rule).

## Symptom (from the accept, confirmed live)

`deepseek-v4-flash-0731` (dated snapshot, 2026-07-31) is served by at least 13 providers
(TokenWatch), yet OUR catalog lists it under **DeepInfra and Morph only** — no openrouter
leg, no deepseek-direct leg. `deepseek-v4-flash-or` and `deepseek-v4-flash-ds` exist for the
unsuffixed model but have NO `-0731` variants. Any model pinned to `-0731` therefore routes
to a single provider with no failover, and the DeepInfra-vs-deepseek-direct input-price
differential (36%) is invisible to the router.

## Root cause — discovery exists but is a one-off seed, and its two code paths disagree on id folding

The under-discovery is NOT "no discovery" and NOT "the operator didn't type one entry". The
mechanism exists (`discover_models` + `CatalogRefresher`). It under-discovers dated
snapshots for two compounding reasons:

### 1. The live catalog is a point-in-time seed, not a cadence-driven re-discovery (the primary cause)

`CatalogRefresher` (the auto re-discovery, `src/charon/routing_policy/catalog_refresh.py`) is
**opt-in** — `gateway.py` only starts it when `catalog_refresh.json {"enabled": true}` is
present (`gateway.py:555-558`). When it is not enabled, the gateway catalog is whatever was
seeded once by a manual `models import`/`discover` run. A dated snapshot that a provider adds
AFTER the seed (openrouter added `deepseek/deepseek-v4-flash-0731` after 0731) never
re-enumerates. That is precisely accept criterion 3 ("catalog is LIVE DATA — assert
re-discovery on a cadence, not a one-off seed"). The live catalog still shows the snapshot
under the providers that had it at seed time (deepinfra, morph) and misses the ones that
added it later (openrouter, and deepseek-direct whose `/models` is auth-gated anyway —
verified live: `api.deepseek.com/v1/models` → `Authentication Fails (governor)`).

### 2. The legacy `build_cost_map` keying fragments namespaced provider ids (the structural hazard)

`src/charon/discover.py:66-108` groups by **full raw id casefold**:
- openrouter serves `deepseek/deepseek-v4-flash-0731`
- deepinfra serves `deepseek-ai/DeepSeek-V4-Flash-0731`
- novita serves `deepseek/deepseek-v4-flash-0731`
- (morph serves bare `deepseek-v4-flash-0731`)

These become THREE separate cost-map keys, none equal to the bare routable `deepseek-v4-flash-0731`.
A lookup for the bare id sees **zero** of the namespaced-served providers under the legacy
path. Only the newer `CatalogRefresher` folds them, via `_normalize_model_id`
(`catalog_refresh.py:61-68` → `proxy._normalize_model_id`, final path segment, lower-cased)
into ONE pool `deepseek-v4-flash-0731` → 3 providers. So the two discovery implementations
disagree on what "the same model" is; whichever is live at seed time determines coverage.

The OpenRouter import path (`import_openrouter_models`, `discover.py:319-380`) is a third,
weaker path: `fuzzy_match_model_id` only **auto-imports stage-1 exact matches**; the dated
snapshot `deepseek/deepseek-v4-flash-0731` is stage-0 (NEW → `discover_review.json`) when the
registry has no `-0731` entry, and stage-2 (fuzzy → review) when it does. It never
auto-imports the openrouter leg of a dated snapshot.

## Coverage: provider-count-per-model BEFORE vs AFTER (accept criterion 2, sample)

Measured 2026-08-02 against the LIVE provider feeds (openrouter `/api/v1/models` n=337,
deepinfra `/v1/models` n=179, novita `/v3/openai/models` n=144 — all public, no key needed).
"BEFORE" = legacy `build_cost_map` reachability of the BARE routable id; "AFTER" = normalized
`CatalogRefresher` folding (`_normalize_model_id`).

| routable id | BEFORE (#provs) | AFTER (#provs) | gained |
|---|---|---|---|
| `deepseek-v4-flash-0731` | 0 | 3 (deepinfra, novita, openrouter) | +3 |
| `deepseek-v4-flash` | 0 | 3 (deepinfra, novita, openrouter) | +3 |
| `deepseek-v4-pro` | 0 | 3 (deepinfra, novita, openrouter) | +3 |
| `deepseek-v3.2` | 0 | 3 | +3 |
| `deepseek-v3.1-terminus` | 0 | 3 | +3 |
| `deepseek-r1-0528` | 0 | 3 | +3 |
| `kimi-k3` | 0 | 2 (novita, openrouter) | +2 |
| `glm-5.2` | 0 | 3 | +3 |
| `qwen3-coder-next` | 0 | 2 (novita, openrouter) | +2 |
| `gpt-5.5` | 0 | 1 (openrouter) | +1 |

The gap is SYSTEMIC (every namespaced-served model drops to 0 under the bare routable id),
not a `-0731`-specific bug — confirming the done contract's "fix the discovery, not the one
entry". The independent feed (TokenWatch, per accept) puts the true ceiling for
`deepseek-v4-flash-0731` at 13 providers; openrouter alone (verified live 2026-08-02) serves
it at $0.09/$0.18 and deepseek-direct would be $0.14/$0.28 (36% more on input) — both
invisible to the router today.

## Cadence assertion (accept criterion 3)

Discovery MUST be a live-data loop, not a one-off seed: enable `CatalogRefresher` on the
gateway (`catalog_refresh.json {"enabled": true}`, `gateway.py:555-558`) so it polls each
configured provider on its TTL (default 3600s) and bridges newly-appeared models into
`srv.routes`/`srv.pools`/`srv.model_pricing`. The `CatalogRefresher.start()` TTL loop and
`bridge()` already exist and are covered by `tests/test_catalog_refresh.py` — the gap is
operational (opt-in, off) plus the legacy-path fragmentation below. A one-off re-seed that
adds `deepseek-v4-flash-0731` legs would rot again the next time a provider adds a snapshot;
the cadence loop is the durable fix.

## Fail-on-revert requirement (accept criterion 4, for the follow-on code ticket)

The follow-on discovery-fix ticket must land a fail-on-revert guard that goes RED if either
(1) `build_cost_map` stops folding namespaced ids into the bare routable pool
(i.e. `build_cost_map({"openrouter":[{"id":"deepseek/deepseek-v4-flash-0731"}],"morph":
[{"id":"deepseek-v4-flash-0731"}]})` must yield ONE key with both providers — today it yields
two), or (2) `CatalogRefresher` stops bridging a newly-discovered dated snapshot into
`chain_for` (the existing `test_discovered_model_routable_with_no_hand_edit` pattern in
`tests/test_catalog_refresh.py`, extended with a namespaced dated id). This ticket could not
land that test because tests/ is outside this ticket's `owns:`.

## Method / red-proof

- Live fetches: openrouter (`/api/v1/models`, 337 models), deepinfra (`/v1/models`, 179),
  novita (`/v3/openai/models`, 144). `deepseek/deepseek-v4-flash-0731` present on openrouter
  and novita; `deepseek-ai/DeepSeek-V4-Flash-0731` on deepinfra.
- DeepSeek-direct `/v1/models` is auth-gated (verified live: `Authentication Fails
  (governor)`), so its leg can only ever be operator-authored or key-authenticated — a
  structural limit to enumerate.
- Legacy path: `build_cost_map` over the same payloads → `deepseek/deepseek-v4-flash-0731`,
  `deepseek-ai/deepseek-v4-flash-0731` and (bare) as three separate keys.
- Normalized path: `_normalize_model_id` → one key, 3 providers (reproduced above).
- `fuzzy_match_model_id` for `deepseek/deepseek-v4-flash-0731` → stage 0 (new/review) when no
  `-0731` entry exists; stage 2 (review) when it does — never auto-imported.

## Recommendation (for the follow-on code ticket)

1. Enable `CatalogRefresher` on the live gateway (cadence re-discovery).
2. Make the legacy `discover_models`/`build_cost_map` path fold namespaced ids with the SAME
   `_normalize_model_id` the refresher already uses, so both discovery implementations agree
   on model identity (one code path, not two).
3. Land the fail-on-revert test above.
4. Note: deepseek-direct cannot be enumerated without a key — its leg must be sourced from a
   keyed poll or the independent feed, not from an unauthenticated `/models`.
