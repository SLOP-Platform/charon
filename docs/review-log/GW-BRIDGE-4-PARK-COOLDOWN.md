# GW-BRIDGE-4-PARK-COOLDOWN — Adversarial review fix

## Problem

The cooldown union read `router._failed_calls` — a private attribute that
**does not exist** in the installed `litellm.Router` (≥1.93). The union was a
dead no-op in production: cooldown-based exclusion silently degraded to
park-only. The tests only asserted against a hand-rolled mock, so the failure
was invisible.

## Fix

1. **`_maybe_add_cooled`** — switched from reading the non-existent
   `router._failed_calls` to reading the **public** cooldown API:
   `router.cooldown_cache.get_active_cooldowns(model_ids, parent_otel_span=None)`.
   This is the same API `litellm`'s own `_get_cooldown_deployments` uses at
   runtime, so the bridge now sees exactly what the Router considers cooled.

2. **Provider mapping** — deployment IDs returned by `get_active_cooldowns` are
   mapped to Charon provider IDs via `model_info.provider` (a field preserved
   by litellm through its model_list processing).

3. **Tests** — replaced all hand-rolled `_MockRouter`/`_MockRouterExpired`/etc.
   with tests that exercise a **real** `litellm.Router`, call
   `cooldown_cache.add_deployment_to_cooldown()` directly, and prove a
   really-cooled provider is excluded and an expired (TTL=0) cooldown is not.

## Files changed

- `src/charon/litellm_plane/park_cooldown.py` — `_maybe_add_cooled` rewritten;
  `_monotonic` removed (no longer needed).
- `tests/test_gw_bridge4_park_cooldown.py` — mock Router tests replaced with
  real `litellm.Router` tests; `_patch_monotonic` removed.
