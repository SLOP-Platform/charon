repo: charon-private
tier: strong
difficulty: 4
work_class: design-review
priority: 2
branch: feat/price-tracked-inventory-autoswap
depends_on:
owns: fleet/state/PRICE-TRACKED-INVENTORY-AUTOSWAP-DESIGN.md
work_class_note: |
  Operator directive (2026-07-23): maintain a provider inventory WITH live pricing so that SYSTEMATICALLY,
  when a provider raises prices (or degrades), it drops in the routing order and a cheaper equivalent takes
  over — no manual intervention. This is mostly COMPOSE, not build-new: the cost-rank router already sorts
  by metered cost; the missing pieces are keeping pricing FRESH + alerting on drift + guaranteeing a
  per-model alternative exists so a demoted provider has a replacement. [[always-fix-catalog-mismatches]]
  [[no-rig-as-product-adopt-dont-handroll]] [[charon-strategy-outcome-graded-gateway]]
accept: |
  DESIGN-FIRST deliverable = fleet/state/PRICE-TRACKED-INVENTORY-AUTOSWAP-DESIGN.md for operator review,
  composing the EXISTING pieces (reuse, do not rebuild):
    1. **Fresh pricing** — enable/schedule `PROVIDER-CATALOG-REFRESH` (`src/charon/routing_policy/catalog_refresh.py`,
       BUILT + wired into gateway `_MODULE_SPECS` but NOT scheduled — no catalog_refresh.json on 4-LOM).
       Recommend cadence (investigation said ~6h) + the sourced-price feed (PRICE-REFRESHER / LiteLLM adopt,
       designed-not-built) so per-(provider,model) $/Mtok stays current.
    2. **Drift alert** — land R17 pricing-limits drift checker (ticketed-not-landed) as the weekly gate that
       FIRES when a provider's price crosses a threshold (the NeuralWatt $5→$10/kWh 2× hike is the canonical
       trigger). RED/alert on drift.
    3. **Auto-swap guarantee** — the cost-rank router (R5, live) already demotes a now-expensive provider;
       the design must ensure EVERY routed model has ≥1 cheaper live alternative in its pool so the demotion
       actually swaps rather than strands. Surface "single-legged model" (no fallback) as a RED — that's the
       gap that turns a price hike into an outage instead of a swap.
    4. **Inventory as data** — the provider inventory (identity, funding_class, live price, plan options,
       per-model coverage) becomes a registry-driven table (KS29 primitive) so adding/dropping a provider
       is a data row, not code. Seed it from the operator's 2026-07-23 inventory (synthetic/trae/HF/nous/
       grok/mistral/zai/cerebras/deepinfra/deepseek/together/groq/morph + plan tiers + funding class).
  Deliverable maps each need to the existing component + the gap to close, and a decomposed build backlog.
  This is the durable form of the operator's "regular pricing cycle for CG" ask. Do NOT hand-roll a new
  price source or a new router — compose catalog_refresh + R17 + cost-rank.
scope: |
  Design a price-tracked provider inventory + auto-swap-on-price-increase system by composing the existing
  cost-rank router + PROVIDER-CATALOG-REFRESH (enable cadence) + R17 drift-alert (land) + a per-model
  alternative guarantee (single-leg = RED). Registry-driven inventory (data rows). Design for operator review.
ds: |
  ## Dependencies & sequence
  - depends_on: (none to design). Reuses: PROVIDER-CATALOG-REFRESH (built), R17 (ticketed), R5 cost-rank (live).
  - overlaps ADD-PROVIDER-MECHANIZE-COMPLETE (that ticket populates real costs on add via the same refresh
    cycle) — coordinate: the refresh mechanism is the shared spine. Sequence the refresh-enable once, consume
    in both.
  - informed-by fleet/state/PROVIDER-BEST-INVESTIGATION.md (this session's provider scorecard + refresh finding).
