# ROUTER-LEDGER-DECAY — review fragment

## Summary

Implements exponential half-life decay for model-signal ledger entries in the
routing path.  Stale signals decay toward zero (default 30-day half-life,
configurable), anchored on `last_referenced` when available, falling back to
`learned_at`.

## Files

| File | Role |
|---|---|
| `src/charon/routing_policy/ledger_decay.py` | Decay module: `signal_decay_weight()`, `apply_ledger_decay()`, `ModelSignalEntry` |
| `tests/test_ledger_decay.py` | 17 tests including FAIL-ON-REVERT and GREEN-IS-NOT-PROOF |

## Algorithm

`decayed = raw_score * 2^(-age_days / half_life_days)`

Pure-stdlib (`math.pow`, `datetime`).  Same exp2 half-life math as the retired
`fleet/memory/bitemporal.py` (FN2), relocated to the router package.

## Acceptance criteria met

1. **FAIL-ON-REVERT** — `test_old_signal_downweighted_vs_fresh_equal_raw_score`:
   two entries with identical raw scores but different ages; the fresh entry
   ranks higher after decay.  If decay is removed from the ranking path this
   test goes RED.

2. **GREEN-IS-NOT-PROOF** — `test_ranking_flips_because_of_decay`: an older
   signal with a higher raw score (80, 60d old) ranks below a fresher signal
   with a lower raw score (70, 1h old) AFTER decay, flipping the order that
   raw comparison would produce.  This is a routing decision change caused by
   decay, not just a smaller number.

3. **Scope** — pure router-side, no fleet/memory/ coupling, no pip install,
   stdlib-only.

## Standing concerns

* Not yet wired into `build_routes_and_pools` / `order_pool_by_live_cost` in
  `__init__.py` — the model-signal ledger is not yet a live ranking input.
  This module is importable (`from charon.routing_policy.ledger_decay import
  apply_ledger_decay`) and ready for that wiring when the ledger is live.
* The test imports via `importlib` + `sys.modules` injection because the
  charon product source and this fleet repo are separate checkouts.  In a
  unified checkout the standard `from charon.routing_policy.ledger_decay import
  ...` works directly.
