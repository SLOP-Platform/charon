# GRACEFUL-DEGRADE — review notes

## Summary
Implemented the shared park/degrade state machine across router.py, failover.py, and balance.py — three North Star behaviors (RATE-LIMIT AS BACKPRESSURE, ALERT ON IMPACT, AUTO-RECOVER ON REFILL) sharing one state contract.

## Files changed
- `src/charon/balance.py` — DegradationState enum, rate-limit tracking (`record_rate_limit`, `is_rate_limited`, `rate_limit_seconds_remaining`), degradation callback (`set_degradation_callback`, `notify_throttled`, `notify_exhausted`), funding-class-aware auto-recover (`_maybe_auto_unpark` skips fc=3, `top_up` re-arms fc=3 on operator top-up)
- `src/charon/failover.py` — `classify_routing_health()` (NORMAL/THROTTLED/DEGRADED classification), `backpressure_delay()` (1-60s clamped throttle delay), `emit_degradation_alert()` (routes to notify_throttled/notify_exhausted)
- `src/charon/router.py` — `parked_keys` set on StaticRouter, `route_pool()` merges parked keys with per-call exclude
- `tests/test_graceful_degrade.py` — 30 fail-on-revert tests covering all 3 behaviors + funding-class-aware re-arm paths

## Design decisions
1. **PARK trigger is reactive** (RECONCILE 2026-07-12): the upstream exhaustion response (401 CreditsError body or 402/429/503) triggers park, NOT the modeled balance. Modeled balance is advisory. Already classified→failover at proxy.py:207; this change adds the park/degrade reaction.
2. **FUNDING-CLASS-AWARE re-arm** (shared taxonomy R11 DRAIN-THEN-PARK): fc=1/fc=2/fc=4 auto-rearm on poll recovery; fc=3 (prepaid) requires explicit `top_up()` by operator.
3. **State machine is in balance.py** because it already owns park/unpark/is_parked. Degradation state (rate limits, alerts) co-locates here as the single shared source of truth.
4. **failover.py functions are simple decision helpers** — they accept counts/delays, not full pool-entry-to-provider mappings. The forwarder does the mapping (its concern); our functions are unit-provable.
5. **router.py adds parked_keys** — a mutable set wired from the balance tracker by the forwarder. Merged into per-call exclude in route_pool(). No circular dependency.

## RECONCILE notes
- tiered (neuralwatt: primary drained + overage remaining) is NOT parked until the LAST pool hits zero — this is a park TRIGGER concern handled in forwarder.py's `_has_live_sibling`, not in these files.
- The `_has_live_sibling` guard (forwarder.py) already prevents sole-leg parking; the degrade state machine reads park state from balance.py and doesn't re-implement the guard.
