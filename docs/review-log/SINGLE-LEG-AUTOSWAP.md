# SINGLE-LEG-AUTOSWAP review log

## Decision: scope of single-leg-guard.sh

The INVENTORY-TABLE accessor (inventory-table.sh) was already written by INVENTORY-TABLE.
Single-leg-guard reads it via the same `_normalize_model_id` import and TSV schema.

`models.json` (not the catalog) is the right live pool source — it's what the operator
has configured for routing, not the discovered catalog. If a model is in models.json but
absent from the inventory TSV, it's skipped (not RED) since it's not in the inventory.

## Design choice: blended cost vs. raw cost

Uses 3:1 blended cost matching `derived_cost_rank` (ci*0.75 + co*0.25). This ensures
consistency with how R5 orders the chain. Raw cost could diverge and cause false REDs.

## Design choice: status=exhaust|fail excluded

Offers with status "exhaust" or "fail" in INVENTORY-TABLE are treated as not-live. This
matches the guard's purpose: "does a demotion have somewhere to go?" An exhausted offer
is not a fallback target.

## Design choice: GREEN when multiple legs at same cost

When multiple providers offer the model at identical cost, no leg is strictly "cheaper".
The guard is about a DEMOTION target — if all providers cost the same, there's no
cheaper alternative to swap TO. However, for multiple-leg case, we still GREEN because
there IS a fallback (a different provider), just not a cheaper one. This is intentional:
the guard fires on NO fallback (single-leg), not on no-cheaper-fallback.

## Fail-on-revert test path

1. Upsert a model with one provider → leg_count=1 → RED fires
2. Add a cheaper alternative → RED clears
3. Remove the cheaper alternative → RED fires again

Test covered by the guard's own `guard` output: count of RED lines.
