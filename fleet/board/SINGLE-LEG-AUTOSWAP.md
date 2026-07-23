repo: charon-private
tier: strong
difficulty: 3
work_class: money-path
priority: 1
branch: feat/single-leg-autoswap
depends_on: INVENTORY-TABLE
dep-kind: build
owns: fleet/single-leg-guard.sh
note: |
  The AUTO-SWAP consumer of the price-tracked inventory (PRICE-TRACKED-INVENTORY-AUTOSWAP accept #3,
  operator-approved P1, 2026-07-23). COMPOSE, do not build-new: the cost-rank router (R5, live) ALREADY
  demotes a now-expensive provider — the missing guarantee is that EVERY routed model has >=1 cheaper live
  alternative so the demotion actually SWAPS instead of stranding. Surface "single-legged model" (no
  fallback) as a RED — the gap that turns a price hike into an OUTAGE instead of a swap. Reads the shared
  INVENTORY-TABLE for per-model coverage. [[always-fix-catalog-mismatches]] [[charon-strategy-outcome-graded-gateway]]
accept: |
  A gate that guarantees the cost-rank auto-swap can't strand:
    1. For each routed model, read the shared price-tracked-inventory table (INVENTORY-TABLE) + live pool
       and assert >=1 alternative live provider-offer exists for that model (a demotion has somewhere to go).
    2. **RED on a single-legged model** — a routed model with NO fallback offer is surfaced as a tracked RED
       + operator alert (this is what makes a NeuralWatt-class price hike a swap, not an outage).
    3. Do NOT re-implement the swap — R5 cost-rank already reorders by metered cost; this ticket only
       proves an alternative EXISTS so the reorder has an effect.
  FAIL-ON-REVERT: mark a model as having only one provider offer in the inventory -> single-leg RED fires;
  add a cheaper alternative offer -> green.
scope: |
  The single-legged-model RED guard: read the shared inventory + live pools, RED any routed model lacking a
  cheaper live alternative so R5's demotion always has a swap target. Composes cost-rank + INVENTORY-TABLE;
  no new router.
ds: |
  ## Dependencies & sequence
  - depends_on: INVENTORY-TABLE (reads per-model coverage from the shared table). Real build dep.
  - composes: R5 cost-rank (live, the actual swap); does NOT edit it (no owns overlap).
  - concurrency: disjoint new file fleet/single-leg-guard.sh.
