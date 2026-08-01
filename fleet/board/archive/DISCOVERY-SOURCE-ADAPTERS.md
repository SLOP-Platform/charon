repo: charon-private
tier: strong
difficulty: 3
work_class: generalist
priority: 1
branch: feat/discovery-source-adapters
depends_on:
owns: fleet/discovery/source_adapters.py
note: |
  D1 of the free-provider DISCOVERY leg (FREE-PROVIDER-DISCOVERY-DESIGN Part 5, operator-approved P1,
  2026-07-23). Three PULL adapters that turn community source feeds into a uniform `list[RawOffer]`.
  REUSE-FIRST: models.dev is the ADOPT source (clean MIT JSON API — no scraping); OpenRouter /models is
  already Charon's live-price feed (reuse the same GET); cheahjs is parsed from its structured data.py as
  a SIGNAL only. Mirror catalog_refresh's `ListModelsFn` injection shape + the `_SCANNERS`/`_POLL_ADAPTERS`
  registry pattern (one row per source) so overlap stays low. [[no-rig-as-product-adopt-dont-handroll]]
accept: |
  A `_SOURCE_ADAPTERS` registry (KS29 shape, one row per source) with three pull adapters, each
  `() -> list[RawOffer]`, off the hot path:
    1. **models.dev** `api.json` — single GET, provider-keyed JSON (api/base_url, env, cost.{input,output},
       limit.{context,output}, open_weights; free flagged by cost:{input:0,output:0}). ADOPT the JSON as-is,
       no HTML scraping.
    2. **OpenRouter** `/api/v1/models` — one unauthenticated GET (`data[]`); `:free` = prompt/completion "0".
       REUSE the existing pull already used for live pricing (PRICING-TOOLS-EVAL); do not add a second client.
    3. **cheahjs/free-llm-api-resources** — parse the structured `src/data.py` (RPD/RPM/TPM/TPD per
       provider+model) as a SIGNAL. No LICENSE -> surface for review, DO NOT vendor/redistribute its data.
  (zukixa: out of scope here — weekly manual reference tail only.)
  Adapter registry mirrors catalog_refresh's injection shape so a new source = one new row.
  FAIL-ON-REVERT: feed a fixture source payload -> adapter emits the expected RawOffer rows; break the
  field mapping -> RED.
scope: |
  Build the 3-adapter pull registry (models.dev JSON, OpenRouter /models, cheahjs data.py) -> list[RawOffer],
  off-hot-path, mirroring catalog_refresh's ListModelsFn/registry shape. Adopt clean JSON APIs; parse
  cheahjs as a signal (no vendoring). No normalize/diff here (D2/D3).
ds: |
  ## Dependencies & sequence
  - depends_on: (none) — pure pull, does not touch the inventory table.
  - feeds: DISCOVERY-NORMALIZE (D2) consumes the RawOffer rows.
  - reuse: catalog_refresh ListModelsFn shape; existing OpenRouter /models pull; models.dev MIT JSON.
  - concurrency: disjoint new file fleet/discovery/source_adapters.py.
