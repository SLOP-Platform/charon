repo: charon
tier: strong
difficulty: 3
work_class: money-path
priority: 0
branch: feat/catalog-completeness
depends_on:
owns: src/charon/providers/discover.py, tests/test_catalog_completeness.py
substrate: litellm — adopt — `model_prices_and_context_window.json` ships with litellm, a library we ALREADY depend on, and carries price + context for thousands of models. Use it as a price SOURCE before scraping or hand-maintaining anything. Cross-check against provider APIs; disagreement between sources is itself signal. See the PRICING-FEED scope note in the satele-shan handoff.
serial_justified: |
  One catalog, one write path. Splitting fields from persistence ships a schema nothing writes.
source: |
  Operator-approved (unstaged since 2026-07-31), promoted to P0 2026-08-01 after measuring that
  provider cost-ranking has no data to rank on.
note: |
  ## MEASURED 2026-08-01 (live 4-LOM gateway)
  - `/data/cost_map.json` — **ABSENT**. Never written.
  - `/data/models.json` — **0 of 859** entries carry ANY price field
    (`price`/`pricing`/`cost`/`input_cost`/`prompt_price`).
  - **216 of 859** carry any context field (re-measured, matches the prior count).
  - `discover.py:66 build_cost_map` is called only from `cli.py:423` and tests — so the cost map
    is computed on demand and never persisted.

  ## WHY P0
  The operator's directive is that cost carries heavy weight and the cheapest capable model AND
  the cheapest provider for that model should win. **With zero priced entries that is not
  possible** — any "cheapest-first" claim is ranking on absent data. This blocks the cost
  directive outright, and cost is a money-path concern, not a nicety.

  ## SCOPE
  1. Make price (input/output per Mtok), context window, and free-tier flag REQUIRED catalog
     fields. Missing → loud, not silent.
  2. Persist the cost map (`build_cost_map`) instead of recomputing it per-call. It must exist
     on disk on 4-LOM.
  3. Populate from litellm's `model_prices_and_context_window.json` first (already a dependency),
     then provider APIs. Prefer MULTIPLE corroborating sources over one SSOT for observed facts;
     record disagreement rather than silently picking a winner.
  4. `zai` is a funded first-party GLM provider with only 2 flash entries catalogued — cover it.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
    a. A catalog entry missing price or context is REJECTED loudly. Revert the check → RED.
    b. `cost_map.json` exists on disk after a discovery run, and a restart reads it rather than
       recomputing.
    c. Given one model served by 2+ providers at different prices, the cheapest is ranked first.
       Prove with a fixture; revert the ordering → RED.
    d. ANTI-OVER-BLOCK: an entry with complete fields passes untouched.
  Report before/after counts of priced entries against the live catalog.

D&S — Deps & Sequence:
  - Depends on: nothing. Unblocks the cost directive and the PRICING-FEED work.
  - Product-side; blocked behind AMBIENT-COUPLED-TESTS only insofar as the product gate is red.
