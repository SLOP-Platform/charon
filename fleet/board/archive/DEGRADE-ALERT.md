repo: charon
tier: strong
difficulty: 2
work_class: money-path
priority: 1
branch: feat/degrade-alert
depends_on:
owns: src/charon/degrade_alert.py, tests/test_degrade_alert.py
work_class_note: |
  Salvage from GRACEFUL-DEGRADE (#172 closed, superseded 2026-07-23). The park/drain half is now live via
  funding_class/drain-then-park — but it parks SILENTLY. The residual value worth keeping is the
  ALERT-ON-IMPACT signal: surface WHEN routing actually degrades so a silent slide isn't invisible.
  Pairs with FLOW-CANARY (proactive) + the live meter. [[monitored-preflight-failure-attribution]]
  [[latency-is-a-failure-class]] [[charon-drain-then-park-provider-class]]
accept: |
  Emit an ALERT (log/surface, non-blocking) when routing IMPACT degrades — the signal funding_class's
  silent parking currently hides:
    1. LAST-RESORT / throttle: a request served only after failing over to the last leg (or throttled) —
       the pool is thinning; surface it (pairs with the exhaustion ledger).
    2. PREPAID LEG HITS ZERO: a drain-then-park provider actually parks (funding-class re-arm table fires)
       — surface "provider X parked, spilled to Y" instead of parking silently.
    3. ALL-degraded / pool-too-thin: escalate loudly (this is the state the whole session started in —
       it must never be silent again).
  Read the LIVE funding_class/balance/park state (do NOT re-implement it — funding_class + drain-then-park
  are live; hook the alert onto their existing transitions). Additive, non-blocking (an alert must never
  change routing/billing). Fail-on-revert test: a simulated park/last-resort transition emits the alert;
  revert → no alert → RED.
scope: |
  Alert-on-impact salvaged from GRACEFUL-DEGRADE: surface last-resort/throttle, prepaid-leg-parked, and
  pool-too-thin transitions that funding_class currently parks silently. Non-blocking; hooks the live
  funding_class/drain-then-park state, doesn't re-implement it.
ds: |
  ## Dependencies & sequence
  - depends_on: none (funding_class/drain-then-park are LIVE). owns a new distinct module — no collision
    with forwarder/balance. Composes with FLOW-CANARY (proactive) + the exhaustion ledger.
