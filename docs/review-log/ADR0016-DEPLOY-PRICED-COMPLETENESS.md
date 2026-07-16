# ADR0016-DEPLOY-PRICED-COMPLETENESS — review-log fragment

Ticket: **ADR0016-DEPLOY-PRICED-COMPLETENESS**
Branch: `feat/adr0016-priced-completeness-guard`

## Problem (adversarial finding)

DELETE-STATIC-RANK (ADR-0016 step #6) removed the operator's hand-typed
`cost_rank` escape hatch from the routing config. With it gone, a model that
lacks `cost_input` / `cost_output` silently collapses to the fixed `1000`
fallback (`cost_rank.py:88-89`). The `1000` is a *neutral middle* rank, not a
sort-last sentinel — so an unpriced model sorts after cheap priced models but
**before expensive ones**, and if a priced model also derives to ~1000, the
stable sort tie-breaks on config-insertion order, which can route to the
unpriced (and potentially PRICIER at the upstream) provider. The operator
override that previously could correct a bad derived order was removed
(`routing_policy/__init__.py`), and nothing guaranteed priced-completeness.

## What landed

A PRICED-COMPLETENESS preflight guard in `cost_rank.py`:

| Symbol | Purpose |
|---|---|
| `PricedCompletenessError` | Loud exception naming every offender |
| `_is_unpriced(spec)` | True iff enabled, not free, missing both cost_input + cost_output |
| `find_unpriced_models(registry)` | Returns offender ids in registry iteration order |
| `assert_priced_completeness(registry)` | Raises `PricedCompletenessError` if any offender; no-op if clean |

The guard is a **standalone preflight** — it must be run on the live registry
before purging `cost_rank` from `/data/models.json`. Disabled and free models
are exempt. The error message names each offender and the three deploy-safe
remediations (price it, mark it free, disable it).

## Design: preflight guard, not inline call site

The acceptance criteria asked: *"Either restore a safe operator-override path
OR prove the derived order is correct for every priced model."* This ticket
chooses the second path: the guard ensures every enabled, non-free model IS
priced, so the derived order IS correct for every model in the routing table.
Operators remediate by pricing unpriced models, marking them `free: true`, or
disabling them — no override needed.

**Why not wire the guard into `build_routes_and_pools` / `load_pools` inline?**
Those files (`routing_policy/__init__.py`, `pools.py`) are outside this ticket's
`owns:`. The guard is a standalone preflight function that the deploy pipeline
calls before the `cost_rank` purge. This keeps the change cohesive and within
the ticket's owned files.

## Acceptance criteria verification

| Requirement | Test(s) |
|---|---|
| A model missing pricing → guard FAILS | `test_assert_priced_completeness_raises_on_unpriced`, `test_assert_priced_completeness_names_multiple_offenders`, `test_guard_blocks_before_any_selection_can_happen` |
| Fully-priced catalog → passes | `test_assert_priced_completeness_passes_when_all_priced`, `test_fully_priced_catalog_selection_works` |
| Prove a missing-price model does NOT get selected over a cheaper priced one | `test_selection_safety_via_build_routes_and_pools` (gateway path), `test_selection_safety_via_load_pools_and_choose_from_pool` (ACP path), `test_cheap_priced_rank_is_below_1000` (unit: rank invariant) |
| Disabled model exempt | `test_find_unpriced_models_exempts_disabled_model`, `test_assert_priced_completeness_passes_disabled`, `test_disabled_model_does_not_trip_guard_but_unpriced_does` |
| Free model exempt | `test_find_unpriced_models_exempts_free_model`, `test_assert_priced_completeness_passes_free`, `test_free_model_does_not_trip_guard_but_unpriced_does` |

### Selection-safety proof (core criterion)

The selection path (both gateway and ACP) takes `pool[0]` — the first entry
after sorting by `(not free, cost_class_priority, derived_cost_rank)`. An
unpriced model gets rank `1000`; a cheap priced model gets rank `< 1000`
(proven in `test_cheap_priced_rank_is_below_1000`). So the cheaper priced model
always sorts first → becomes `pool[0]` → gets selected. The unpriced model is
NOT selected over it. This is proven end-to-end through both:

- `build_routes_and_pools` (gateway compiler) — `test_selection_safety_via_build_routes_and_pools`
- `load_pools` + `choose_from_pool` (ACP/data path) — `test_selection_safety_via_load_pools_and_choose_from_pool`

Both tests list the unpriced model FIRST in the pool map (insertion-order bias)
and assert the cheaper priced model still sorts to `pool[0]`.

The guard adds a belt-and-suspenders layer: even if the unpriced model's
upstream is PRICIER, the deploy is held before the catalog goes live
(`test_guard_blocks_before_any_selection_can_happen`).

## Files changed (all in `owns:`)

| File | Change |
|---|---|
| `src/charon/routing_policy/cost_rank.py` | Added `PricedCompletenessError`, `_is_unpriced()`, `find_unpriced_models()`, `assert_priced_completeness()` |
| `tests/test_priced_completeness.py` | NEW: 32 tests covering unit, integration, selection-safety, exemption, and edge cases |

No files outside `owns:` were modified. The guard is a standalone preflight —
wiring it into `build_routes_and_pools` / `load_pools` would require editing
`routing_policy/__init__.py` and `pools.py`, which belong to other tickets.
