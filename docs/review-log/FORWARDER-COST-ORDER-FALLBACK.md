# FORWARDER-COST-ORDER-FALLBACK — review note

## The defect
`src/charon/forwarder.py:530-533` stated "Empty meter -> the order is
unchanged (preserves the static configured order built at startup)." The
per-provider meter was NEVER populated on the live gateway (`spend.json`
held a GLOBAL aggregate only, no per-provider breakdown), so the R2
reorder NEVER fired and the static hand-authored order governed every
request. For `deepseek-v4-flash` that order placed openrouter (rank 50)
BEFORE a funded, ~6x cheaper deepseek-direct leg (rank 8); when the
openrouter key cap 403'd, every leg failed and the whole fleet stalled
while deepseek-direct sat untried (2026-08-01 incident).

## The fix
When per-provider metered spend is absent or empty, fall back to
`cost_rank` ASC (free-first) via `routing_policy.derived_cost_rank` —
NOT to the static configured order. Precedence enforced:

  1. free legs first (`not bool(spec.get("free"))`)
  2. real per-provider metered spend, when present (unchanged R2 path)
  3. `cost_rank` ASC (derived from configured `cost_input`/`cost_output`)
  4. static configured order (last-resort tiebreak only, via stable sort)

The empty-meter sort key is `(not free, cost_class_priority,
derived_cost_rank)` — the SAME composition `pools.load_pools` and
`build_routes_and_pools` use. `cost_class` therefore ranks a
`free-daily` leg ahead of a paid leg with a lower per-token price, and an
unclassified leg (priority 4 = premium) sorts after any classified paid
leg (verified by `test_cost_class_priority_overrides_lower_token_cost`).

Reuses `routing_policy.derived_cost_rank` and `cost_class_priority` (the
same derivation `pools.load_pools` / `build_routes_and_pools` use) so a
leg with NO pricing derives to a neutral 1000 and never sorts ahead of a
known-cheap leg. The sort is stable, so a chain already in correct cost
order is returned unchanged (anti-over-block).

## Adversarial review (money-path, reviewer != builder)

The fallback CANNOT route to a costlier leg than the previous behaviour
in ANY case:
- **free-first**: a free leg was already preferred by the static
  `pools.load_pools` sort; surfacing it first matches the operator's
  stated policy. A free leg sorts before any paid leg regardless of
  cost_rank.
- **cost_rank ASC**: lower cost_rank = cheaper. The sort key
  `(not free, cost_class_priority, derived_cost_rank)` is the SAME key
  `pools.load_pools` and `build_routes_and_pools` use, so the fallback
  reproduces the catalog's intended order rather than imposing a new one.
- **unknown-cost legs never cheap**: `derived_cost_rank` returns 1000
  for a spec with no `cost_input`/`cost_output`, so an unpriced leg sorts
  LAST among priced legs (verified by
  `test_unpriced_leg_never_sorts_ahead_of_priced_cheaper`).
- **disabled/parked legs**: excluded by the DRAIN-AND-PARK pre-flight
  block (lines 424-487), which runs BEFORE this fallback. A parked leg
  is dropped before the reorder sees it (verified by
  `test_parked_leg_is_skipped`). `enabled: false` legs are excluded at
  config-load in `gateway.load_config` and never enter the chain.
- **no regression of live-meter path**: when the per-provider meter IS
  present, `order_pool_by_live_cost` is still called (verified by
  `test_live_metered_spend_wins_over_cost_rank`).

The only behavioural change vs the old code is: an empty per-provider
meter no longer leaves the static order in place; it now reorders by
cost_rank ASC. Since the static order was hand-authored and the
cost_rank is derived from the same pricing data `pools.load_pools` uses,
the new order is the order the catalog already intended — the forwarder
was simply ignoring it.

## RED then GREEN
5 tests FAIL on the named revert (empty meter → order unchanged):
  - `test_empty_meter_uses_cost_rank_not_static_order` (the incident)
  - `test_free_legs_precede_paid_legs`
  - `test_unpriced_leg_never_sorts_ahead_of_priced_cheaper`
  - `test_cost_class_priority_overrides_lower_token_cost`
  - `test_real_deepseek_v4_flash_leg_set_order`
All 8 GREEN with the fix. The 3 that pass on revert use the live-meter
path or the drain block, which are unaffected.

## Resulting order for the real deepseek-v4-flash leg set
Before (static, empty meter): nv, ng, hf(parked→skip), or, ds, cline
After (cost_rank ASC fallback):  nv, ds, or, ng, cline  (hf parked→skip)
deepseek-direct (rank 8) is now tried BEFORE openrouter (rank 50) — the
funded cheaper leg is reached before the capped one.
