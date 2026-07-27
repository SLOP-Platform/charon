# DISCOVERY-SOURCE-ADAPTERS review note

Shipped `fleet/discovery/source_adapters.py` — D1 of the free-provider DISCOVERY
leg (FREE-PROVIDER-DISCOVERY-DESIGN Part 5, operator-approved P1, 2026-07-23).
Three PULL adapters that turn community source feeds into uniform `list[RawOffer]`.

## Registry shape

`_SOURCE_ADAPTERS: dict[str, Callable[[], list[RawOffer]]]` mirrors `balance.py`'s
`_POLL_ADAPTERS` pattern — one dict row per source. A `pull_all()` helper iterates
the registry and returns `dict[str, list[RawOffer]]`.

## Adapter details

1. **models.dev** `api.json` — single GET, provider-keyed JSON. Maps
   `cost.{input,output}`, `limit.{context,output}`, `open_weights`. Free flagged
   by `cost:{input:0, output:0}`. ADOPT as-is, no scraping. 5778 offers (495 free).

2. **OpenRouter** `/api/v1/models` — one unauthenticated GET. Reuses the same
   endpoint Charon already polls for live pricing (PRICING-TOOLS-EVAL). `:free` =
   `pricing.prompt == "0"` and `pricing.completion == "0"`. 343 offers (18 free).

3. **cheahjs/free-llm-api-resources** `src/data.py` — parsed via `ast.literal_eval`
   to extract `MODEL_TO_NAME_MAPPING`. SIGNAL only (no LICENSE, no vendoring).
   263 signal offers from the mapping.

## Design decisions

1. **RawOffer as dataclass** — simple container, easy to construct from each
   adapter. Source/provider/model_id are the identity triple; the normalize step
   (D2) collapses these into inventory rows.

2. **No special `netutil` import** — fleet-level script outside `src/charon/`,
   uses stdlib `urllib.request` directly with browser UA.

3. **cheahjs parsed at runtime** — the `data.py` file is fetched fresh each time
   the adapter runs. No file is vendored into the repo (no LICENSE conflict).

4. **Fail-safe** — each adapter is wrapped in try/except in `pull_all()` so a
   single source failure doesn't block the others.

5. **FAIL-ON-REVERT** — fixture-driven: feed a source payload, assert the
   adapter emits the expected `RawOffer` rows (free detection, cost/limit
   mapping, provider identity). Breaking a field mapping flips the assertion
   RED. Verified via inline harness for all three adapters + `pull_all`
   fail-safe.

6. **Off-scope cleanup** — restored a stray `f.txt` deletion from an earlier
   attempt; final diff vs master contains only the two owned paths.

7. **Lint hygiene** — removed an unused `provider_name` local flagged by ruff
   (`provider_id` already carries the `name` fallback).
