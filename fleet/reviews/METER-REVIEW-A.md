# ADVERSARIAL REVIEW A — METER-MODEL-PROVIDER Wave 1

**Branch:** `feat/meter-model-provider`  
**Commit:** `e2a9e12`  
**Reviewer:** Adversarial (read-only)  
**Date:** 2026-07-10

---

## VERDICT: MERGE-WITH-FIXES — confidence: MODERATE

The core logic is sound: the same `u.cost_usd` value is atomically added to both `_usage` and `_model_provider_cost` under a single lock acquisition. No double-count, no drift when `provider` is consistently set. Fail-on-revert tests are genuine. No credential leakage.

**Blocking the merge on one medium-severity finding.** Two additional low-severity design risks to consider but not block on.

---

## FINDING 1 (MEDIUM) — Silent invariant break when `provider` is omitted

**File:** `src/charon/proxy.py:473`  
**Scenario:** A mixed stream where some `observe()` calls pass `provider` and some omit it (defaults to `None`).  

```python
# observe() call A — WITH provider
p.observe("m", 200, body={"usage": {"cost": 1.0}}, provider="p")
# observe() call B — WITHOUT provider (backward compat)
p.observe("m", 200, body={"usage": {"cost": 2.0}})
```

**Result:** Global `_usage.cost_usd` = 3.0. `_model_provider_cost` total = 1.0.  
**Delta:** 2.0 — the per-(model,provider) ledger silently under-reports by the cost of every `provider=None` observation.  

The canary test `test_metering_invariant_cost_total_delta_zero` explicitly guards against this case by saying "no failovers, no count_usage=False" — but it should also say "all observations pass provider" or the test should use `provider` consistently. Worse, there is **no assertion or warning** in production code that catches this. Every caller must independently remember to pass `provider`, and Wave 2's forwarder wiring may forget some call site.

**Impact:** Cost-rank routing reads under-reported spend for a (model, provider) pair, potentially mis-ranking providers (over-selecting one whose cost was partially unmetered).

**Fix:** Either:
- (a) Add an assertion or log warning in `record()` when `provider is None` and the observation is a non-failover non-zero-cost 200, or
- (b) Make the metering-invariant test exercise a mixed-stream and explicitly document the delta.

---

## FINDING 2 (LOW) — Credential-shape mismatch risk at the call site

**File:** `src/charon/proxy.py:474` (and `all_model_provider_costs` consumers)  
**Scenario:** The meter keys by the raw `requested_model` as seen by the router. If the router in Wave 2 normalizes the model ID (strips prefix, lowercases, strips quantization) *before* looking up cost in the ledger — but the observation recorded it under the raw prefixed ID — the read returns $0.

The `test_metering_invariant_credential_shape` test demonstrates that `deepseek/deepseek-v4-pro` and `deepseek-v4-pro` are tracked as separate keys. The test calls this "credential-shape invariance" — and it IS invariant in the ledger. But a consumer that normalizes before lookup will miss entries.

**Impact:** Silent zero-cost read for models with prefixed pool IDs. Only manifests when Wave 2 wiring is deployed. Not a bug in this code, but the ledger provides no normalization guarantees to callers.

**Fix:** Document the keying convention explicitly on `model_provider_cost()` — "the `model` parameter MUST match the exact `requested_model` string passed to `observe()`, NOT a normalized/aliased form."

---

## FINDING 3 (LOW) — Negative cost passthrough in `proxy.py`'s `record()`

**File:** `src/charon/proxy.py:473-476` vs `src/charon/balance.py:230-231`  
**Scenario:** A provider response body with `"cost": -1.00` (refund/credit adjustment).  

`record_spend()` in `balance.py` guards against this at line 230-231:
```python
if usd <= 0.0:
    return  # negative/zero spend is ignored
```

`record()` in `proxy.py` has no such guard. A negative cost is added directly to both `_usage` and `_model_provider_cost`, making both counters non-monotonic. Pre-existing for `_usage` (unchanged by this diff), but now the same issue applies to `_model_provider_cost`.

**Impact:** Low — negative costs from providers are rare, and the ledger truthfully records whatever the provider reported. But the inconsistency between `BalanceTracker` (which discards ≤0) and `GatewayProxy` (which accepts negative) means callers reading from one vs. the other see different totals.

**Fix:** Add a `max(u.cost_usd, 0.0)` guard in the `proxy.py` `record()` meter update, matching `balance.py`'s convention, OR document that the proxy ledger allows negatives while BalanceTracker does not.

---

## ATTACK CHECKLIST

### 1. Metering invariant — cost-total DELTA stays exactly 0 on pure path?
**Yes** — when ALL `observe()` calls pass `provider`. The same `u.cost_usd` is atomically added to both `_usage.cost_usd` and `_model_provider_cost[key]` under a single lock acquisition (`proxy.py:461-476`). The sum of `all_model_provider_costs()` equals `cumulative_usage().cost_usd`.

**No** — if ANY observation omits `provider`. See Finding 1 above. The test `test_metering_invariant_cost_total_delta_zero` only exercises the all-provider path; there is no guard for mixed streams in production.

### 2. No fabrication — cost derived from real usage?
**Yes.** The cost value `u.cost_usd` flowing into the per-(model,provider) meter originates from:
- `classify()` → `_gateway_usage(body)` → `float(u.get("cost", 0.0))` (the real provider-reported cost), OR
- Computed from stored per-token pricing when provider reports 0 cost (`proxy.py:367-386`).

There is NO reference to `est_cost` or any fabricated floor in the metering path. The old `est_cost` fabrication lives in `forwarder.py`'s `_spend_to_record()`, which is completely separate — it is NOT fed into `_model_provider_cost`.

### 3. Credential shape — no keys/secrets leaked into meter records?
**Yes — clean.** The `_model_provider_cost` key is `(str, str)`: `(requested_model, provider_label)`. Both are routing metadata — not API keys, tokens, or secrets. The value is a float cost. No credential material anywhere in the meter.

### 4. Per-(model, provider) accuracy — namespaced/aliased id attribution?
**Treats prefixed and bare IDs as distinct keys, by design.** `deepseek/deepseek-v4-pro` and `deepseek-v4-pro` accumulate independently. This is the correct behavior — the ledger faithfully records what the router asked for. The risk is only at the *reading* side (Finding 2).

### 5. Tests fail-on-revert?
**Three tests DO fail on revert:**
- `test_real_provider_cost_metered_not_est_floor` — if `_model_provider_cost` update is removed or `provider` kwarg is gone, assert `metered == 0.42` fails. **Yes, turns RED.**
- `test_computed_cost_metered_not_est_floor` — same pattern. **Yes, turns RED.**
- `test_free_response_meters_zero_not_est_floor` — same pattern. **Yes, turns RED.**

**One test would NOT catch a partial revert that replaces `u.cost_usd` with a coincidentally equal value** — but this is the standard limitation of assertion-based testing and not practically exploitable.

**BalanceTracker model-spend tests** also fail on revert of `_model_spend` tracking. **Yes, turn RED.**

### 6. Concurrency / partial-failure?
**Lock discipline is correct.** `_model_provider_cost` is updated under the same `self._lock` as `_usage` in `proxy.py:461`. Consistent ordering, no deadlock, no torn reads.

**Mid-stream response failure:** The proxy model is synchronous — one `observe()` per complete response. A failed stream (non-200) returns no usage, so nothing is metered. Correct.

**TOCTOU in `BalanceTracker.record_spend()`:** `cfg = self._config.get(provider)` on line 232 is read outside the lock. A concurrent `configure()` call could change the provider's mode between the read and the lock acquisition. This is a pre-existing bug (present on `master`) that affects `_fixed_balances` decrement, NOT the new `_model_spend` ledger (which is updated the same way in both branches). Not a regression, but still listed as it lives in the diff.

---

## SUMMARY

| # | Severity | File:Line | Issue |
|---|---|---|---|
| 1 | **MEDIUM** | `proxy.py:473` | No guardrail when `provider` is omitted — meter silently under-reports |
| 2 | LOW | `proxy.py:474` | Key convention (raw requested_model) undocumented for callers |
| 3 | LOW | `proxy.py:473-476` | Negative cost passthrough (pre-existing pattern, now on new meter) |

**Recommendation:** Fix Finding 1 (add assertion or log warning for omitted `provider` on non-zero-cost 200s) before merging. Findings 2-3 are documentation/consistency items — non-blocking.
