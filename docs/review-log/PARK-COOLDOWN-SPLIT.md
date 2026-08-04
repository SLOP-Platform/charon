# PARK-COOLDOWN-SPLIT — split park from cooldown in the sole-leg guard (D-018)

## What changed

`park_cooldown.py` previously merged Charon PARK state and litellm Router
COOLDOWN into ONE exclusion set, then `sole_leg_guard(live, chain)` restored
the FULL original chain — PARKED LEGS INCLUDED — whenever `live` was empty.
That is the exact money leak D-012 outlawed in `forwarder.py`, reimplemented
in the litellm plane. Zero `src/` callers today, so this is pre-emptive.

D-018 splits the two kinds of exclusion. They are different questions:

| | park | cooldown |
|---|---|---|
| cause | operator/config decision | transient upstream failure |
| cost of retrying anyway | real money | free |
| correct never-strand answer | fail with the D-012 503 | retry the cooled leg |

Decided rule (stated in `park_cooldown_filter_chain`'s docstring so it cannot
silently drift back):

1. Cooldown-only chain, no leg parked → never-strand guard KEPT: original
   chain restored, so a transient upstream blip never strands a request.
2. Any parked leg → park is the STRONGER signal. If no leg survives and at
   least one is parked, result is EMPTY; caller answers with the D-012 503
   (`no_provider_reason == "all_legs_parked"`, same shape as `forwarder.py`).
3. Mixed park + cooldown, none live → park rule wins: NOT restored (empty).
4. `count_viable_legs` now delegates to `park_cooldown_filter_chain`, so a
   caller can never disagree with the dispatcher about whether a pool is
   servable (req. 4).

## Files

- `src/charon/litellm_plane/park_cooldown.py` — added `_parked_and_cooled`
  (separate sets), `excluded_provider_ids` now a union of the two, rewrote
  `park_cooldown_filter_chain` + `count_viable_legs`, updated docstrings.
- `tests/test_gw_bridge4_park_cooldown.py` — INVERTED the two tests that
  cemented the money leak (`test_sole_leg_guard_keeps_last_leg`,
  `test_sole_leg_guard_multi_model`) into `test_parked_sole_leg_is_not_restored`
  and `test_parked_sole_legs_not_restored_per_chain`; added cooldown-only
  restore, mixed park+cooldown, and count/filter agreement tests.

## Red-proof (observed)

Stashed the source change and ran the updated test file against the OLD
source: exactly the 5 tests that pin the new behaviour FAILED
(`test_parked_sole_leg_is_not_restored`,
`test_parked_sole_legs_not_restored_per_chain`,
`test_mixed_parked_and_cooled_none_live_is_not_restored`,
`test_count_viable_agrees_with_filter_cooled_only`,
`test_count_viable_agrees_with_filter_mixed`); restored the change and all
27 pass. Each new assertion is backed by that observed revert, not an
asserted claim.
