# DEGRADE-ALERT review notes

## Decision: standalone module, no forwarder modification

The degrade_alert module (`src/charon/degrade_alert.py`) is a standalone,
self-contained module — it does NOT modify `forwarder.py`. The forwarder
already detects all three degradation transitions:

1. **Pre-flight exclusion** (forwarder.py:472): `bt.park(prov)` fires when a
   class-3 drain-then-park provider hits zero — the exact hook point for
   `alert_prepaid_zero`.
2. **All-routes-excluded safety fallback** (forwarder.py:485-487): fires when
   drain routing would strand the request — hook point for
   `alert_pool_too_thin(reason="all routes excluded")`.
3. **Terminal "all providers exhausted"** (forwarder.py:702-746): every
   provider in the chain failed — hook point for
   `alert_pool_too_thin(reason="all providers exhausted")`.
4. **Last-leg serve after failovers** (forwarder.py:565+ loop, when `more` is
   False and a response is served): hook point for `alert_last_resort`.

Wiring the `DegradeAlert` instance into the forwarder requires only importing
and calling the three public methods at these existing transition points — a
trivial integration that needs no logic changes to forwarder.py. This keeps
`owns:` scoped to the two degrade_alert files.

## Design choices

- **Log-only, non-blocking**: Every method writes via `logging.getLogger
  ("charon.degrade_alert").warning(...)` — never throws, never changes
  routing or billing, never mutates shared state beyond internal counters.
- **BalanceTracker integration**: `DegradeAlert` optionally accepts a
  `BalanceTracker` reference so `alert_prepaid_zero` can read the live
  `funding_class` value without re-implementing it (the ticket explicitly
  says "do NOT re-implement it").
- **Three per-category counters**: `last_resort`, `prepaid_zero`,
  `pool_too_thin` — simple ints matching the existing counter pattern in
  `BalanceTracker._counters` and `Observability._counters`.

## Test strategy

- **unittest + assertLogs**: No external deps. `assertLogs` captures
  WARNING-level messages to `charon.degrade_alert`.
- **Fail-on-revert**: `TestFailOnRevert` tests verify both that an alert
  fires on a simulated transition AND that counters are zero when no
  transition occurred. Deleting the `alert_*` calls → counters stay at 0 →
  the revert tests pass but the transition tests go RED — proving the
  alerts are NOT just always-on noise.
- **BalanceTracker integration**: `TestBalanceTrackerIntegration` wires a
  real `BalanceTracker` with a class-3 fixed provider and verifies `fc=3`
  appears in the alert log line.
- **Non-blocking guarantee**: `TestNonBlockingGuarantee` sends empty
  strings and verifies no exceptions escape.

## Pairing

This module pairs with:
- **FLOW-CANARY** (proactive): canary pings → degrade alert surfaces when
  the pool actually thins.
- **Exhaustion ledger**: `alert_prepaid_zero` fires at the same transition
  point where the ledger records exhaustion — independent reads from the
  same live `BalanceTracker` state.
