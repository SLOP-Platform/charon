---
description: "#1 REMEDIATION: the per-provider cost METER is inert (half-measure) — BalanceTracker never constructed from config, record_spend guarded off, ledger EMPTY per the code's own comment; R4 meter-wire added calls not construction"
metadata: 
name: charon-meter-inert
node_type: memory
originSessionId: a95dc541-223e-4053-8197-6848f0322d6b
type: project
tags: [billing, charon, meter]
last_referenced: 2026-07-13
---
**2026-07-11 — the "which provider is cheaper" METER does NOT work today (the BalanceTracker Issue, again).** Confirmed by reading the code (not docs):
- `BalanceTracker` class + a per-`(model,provider)` spend ledger EXIST (`src/charon/balance.py`).
- The forwarder HAS the record call sites: `forwarder.py:467` and `:561` call `srv.balance_tracker.record_spend(route.label, cost, model=requested)` on committed 200s — but guarded `if srv.balance_tracker is not None`.
- **`cfg.balance_tracker` is NEVER constructed from config** — `gateway.py:94` defaults it to `None`; the ONLY `BalanceTracker(...)` in the whole tree is a **docstring example** (`balance.py:149`). So the guard is always false → `record_spend` never fires.
- The code's OWN comment (`balance.py:170`): *"Caller wiring is deferred to Wave 2, so this ledger is EMPTY under real traffic today."*

So tonight's ROUTER **R4 "meter-wire" was a half-measure**: it added the record *calls* but not the *construction/config wiring* — exactly the class KSF exists to catch, and exactly what the operator means by "I DO NOT WANT HALF MEASURES."

**Fix (top item next session):** construct a real `BalanceTracker` from provider config (funding class / starting balances per [[charon-drain-then-park-provider-class]]) and assign it to `cfg.balance_tracker` in the gateway server build (`gateway.py` ~329), so `record_spend` fires → the per-`(model,provider)` ledger fills → `cost_rank.derived_cost_rank(spec, metered_cost)` returns REAL observed per-provider cost. Also address the `est_cost` fabricated-floor the operator flagged (spend uses it as a floor, not real cost). Verify with the FULL gate + a real-traffic probe that the ledger is non-empty (green-is-not-proof). Request-level cost is separately observed via `note_request`/observer + the actuals-ledger, but the dedicated per-provider cost meter is the gap.

Relates to [[charon-drain-then-park-provider-class]], [[benchmark-not-a-valid-ranker]], [[green-is-not-proof]], [[charon-silent-downgrade-leak]], [[merge-gate-is-full-ci-not-pytest]].
