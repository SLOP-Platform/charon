tier: frontier
difficulty: 4
work_class: money-path
branch: feat/graceful-degrade
depends_on: ROUTER-CORE
owns: src/charon/router.py, src/charon/failover.py, src/charon/balance.py
accept: |
  The router's North Star (fleet/state/ROUTER-DESIGN.md §North Star) — three behaviors, each fail-on-revert:
  1. RATE-LIMIT AS BACKPRESSURE: when the only remaining viable provider is rate-limited, the session is
     THROTTLED (queued/slowed) to that provider's limit instead of erroring. Test: with all-but-one
     provider exhausted and that one at its RPM, a burst is throttled+served, NOT failed.
  2. ALERT ON IMPACT: when routing degrades (throttled last-resort, OR a prepaid leg hits zero), the
     operator is NOTIFIED — "performance impacted; refill <provider>". Test: drive a leg to zero -> a
     degradation notice with the provider-to-refill is emitted.
  3. AUTO-RECOVER ON REFILL: after a refill, a health CHECK/probe re-arms the parked provider and routing
     returns to it automatically. Test: park on exhaustion, restore credit, probe passes -> next request
     routes back to it with no manual reconfig.
scope: |
  Operator North Star (2026-07-10): "I don't want to worry about pools/exhaustion IF I have a viable
  option; if the last option is rate-limited, throttle the session; tell me when performance is impacted
  and to refill; on refill, auto-route back to a better provider after a check." Composes with R2
  router-core (invisible failover + throttle), R10 free-tier-quota-spill, R11 drain-then-park (re-arm).
  [[charon-drain-then-park-provider-class]] [[charon-work-engine-vision]]
ds: money-path; sequence AFTER R2 router-core. PROJECT ROUTER.
