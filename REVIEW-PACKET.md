# REVIEW PACKET — METER-MODEL-PROVIDER (Wave 1)

## Summary

Real per-(model, provider) cost metering to replace est_cost fabrication.
Adds a per-(model, provider) cost ledger to `GatewayProxy` and model-level
spend tracking to `BalanceTracker`, so cost-rank routing and drain-then-park
can read actual metered spend instead of fabricating an est_cost floor.

## Files + Line Ranges Changed

### `src/charon/proxy.py`
- **L279-290** — `__init__`: added `_model_provider_cost: dict[tuple[str, str], float]`
- **L304-341** — `observe()`: added `provider: str | None = None` parameter, forwarded to `record()`
- **L442-468** — `record()`: added `provider` kwarg; when truthy and `count_usage`, folds cost into `_model_provider_cost` keyed by `(obs.requested_model, provider)`
- **L515-530** — new methods `model_provider_cost()` and `all_model_provider_costs()`

### `src/charon/balance.py`
- **L14-15** — docstring: noted new `record_spend` signature and `model_spend` API
- **L166-173** — `__init__`: added `_model_spend: dict[tuple[str, str], float]`
- **L219-246** — `record_spend()`: added `model: str | None = None` parameter; tracks per-model spend on unconfigured, poll, and fixed providers alike
- **L248-255** — new method `model_spend(model, provider) -> float`

### `tests/test_meter_model_provider.py` **(NEW)**
- 18 tests: per-(model,provider) accumulation, FAIL-ON-REVERT guards, metering-invariant canary, BalanceTracker model spend

## Root Cause / Approach

The old `_spend_to_record()` in forwarder.py substituted a fabricated `est_cost`
floor (`request_bytes/4 * $1.5e-6`) for every response, inflating the spend
ledger to ~$223 fiction. The BILLING-EST-COST-FIX (#88) fixed the money path
to record real $0, but cost-rank routing still had no access to ACTUAL per-route
spend — it relied on the same fabricated estimate.

**Wave 1** builds the authoritative metering ledger IN the observation core
(`GatewayProxy`) keyed by `(requested_model, provider_label)`. Every served
response with a `provider` folds its real `cost_usd` into this ledger.
`BalanceTracker` gains model-level spend tracking for the same purpose.

Caller changes (forwarder.py wiring) are deferred to a later wave — the
`provider` parameter defaults to None for backward compatibility.

## FAIL-ON-REVERT Test

**Name:** `test_real_provider_cost_metered_not_est_floor`
**File:** `tests/test_meter_model_provider.py:102`
**Run command:**
```
python3 -m pytest tests/test_meter_model_provider.py::test_real_provider_cost_metered_not_est_floor -xvs
```
**Behavior:** A provider-reported cost of $0.42 (cost_source="provider") is
recorded verbatim in the per-(model,provider) meter. If the metering code is
reverted to substitute an est_cost floor (or if the per-(model,provider)
tracking is removed entirely), this assertion FAILS — RED.

Additional FAIL-ON-REVERT tests:
- `test_computed_cost_metered_not_est_floor` — computed cost from per-token pricing
- `test_free_response_meters_zero_not_est_floor` — free/flat responses record $0.00

## Metering-Invariant Canary

**Name:** `test_metering_invariant_cost_total_delta_zero`
**Run command:**
```
python3 -m pytest tests/test_meter_model_provider.py::test_metering_invariant_cost_total_delta_zero -xvs
```
**Behavior:** Replays a recorded 5-request stream through the new meter and
asserts `sum(all_model_provider_costs) == global_cumulative_cost` to within
floating-point tolerance.

**Name:** `test_metering_invariant_credential_shape`
**Run command:**
```
python3 -m pytest tests/test_meter_model_provider.py::test_metering_invariant_credential_shape -xvs
```
**Behavior:** A prefixed pool id (`deepseek/deepseek-v4-pro`) and a bare model
id (`deepseek-v4-pro`) on the same provider accumulate independently without
cross-talk, and the sum of both entries equals the global counter.

## Self-Run FULL GATE Result

```
CHARON GATE — running all validation checks...
  [ruff] OK
  [mypy] OK
  [SLOP-boundary] OK
  [version] OK
  [gate-registry] OK
  [public-clean] OK
CHARON-GATE: all checks passed
```

All 74 existing tests pass (test_proxy, test_balance, test_forwarder_billing).
All 18 new tests pass.

## Residual Risk + Blast Radius

- **Risk level:** LOW. Changes are purely additive — new dict fields and
  optional parameters with safe defaults (None). No behavior is altered on
  existing call paths.
- **Blast radius:** `GatewayProxy.record()` and `GatewayProxy.observe()` gain
  an optional `provider` kwarg (defaults to None → no-op on the meter).
  `BalanceTracker.record_spend()` gains an optional `model` kwarg. All
  existing call sites continue to work unchanged.
- **Memory:** Two new dicts (`_model_provider_cost` in proxy, `_model_spend` in
  balance), each unbounded but keyed by stable (model, provider) pairs — grows
  only as many distinct combinations as the pool defines.
- **Thread safety:** Both new dicts are guarded by the existing `_lock` — no
  new race surface.

- **Commit SHA:** `28f82e3`
