# Adversarial Review — METER-MODEL-PROVIDER Wave 1 (Reviewer B)

**Branch:** `feat/meter-model-provider`  
**Commit:** `e2a9e12`  
**Diff:** `git diff master..HEAD`  
**Verdict:** **MERGE-WITH-FIXES**  
**Confidence:** 0.85

---

## Metering-Invariant: does cost-total delta stay 0 on pass-through?

**NO (with a caveat) for the invariant welted in the test, but YES mechanically on the code as written.**

Empirical demonstration in `record()` (proxy.py:461-488): the new meter fold
(proxy.py:473-476) sits inside the same `if obs.usage is not None and count_usage:`
guard that updates `self._usage` (proxy.py:465-472), and both add the *same*
`u.cost_usd`. On a no-op stream with no `count_usage=False`, the
`sum(all_model_provider_costs()) == cumulative_usage().cost_usd` holds — the
meter is a pure projection of the global counter.

**Concretely preserved:** the invariant test `test_metering_invariant_cost_total_delta_zero`
(test_meter_model_provider.py:181-205) fails RED when the meter fold is removed
(verified empirically: 8/18 tests fail on meter removal, including this one with
`AssertionError: per-(model,provider) total 0 != global total 1.51`).

**Drift vector (where delta would NOT be zero):**
- **1. `count_usage=False` path.** When a discarded attempt is recorded
  (`forwarder.py:278`, `:350-351`, `:399-401`, `:421-425`), `record()`
  executes the `if obs.failover:` branch (registers exhausted) but skips the
  `if count_usage:` branch — `u.cost_usd` is folded into NEITHER counter. So
  no metric drift. ✓ Safe.
- **2. In-flight failover mid-stream (proxy.py:412 + :447-450).** A stream
  head that contains a downgrade → `count_usage=True` but discard, then a
  SECOND `classify()` + `record(count_usage=True)` on the served attempt
  (forwarder.py:420-425 then :447-450). Two costs folded into the global
  counter AND the per-(model,provider) meter — both paths sum the SAME two
  values. Delta stays 0; both counters double-count equally. ⚠️ The
  double-count itself is intentional under the `failover_on_downgrade=True`
  toggle (called out in fwd comments: "visible, not silent"), but it means
  the meter conflates discarded-downgrade spend with served spend on the
  same `(request_model, provider)` key. Not a drift bug — but a consumer
  treating it as "burn rate on successful calls" will overestimate.

**Conclusion:** No double-count or drift *between* the two paths under the
current code, but both paths intentionally double-count on the visible-discard
failover branch, with no way to distinguish served vs discarded spend per
model. This is the dominant residual risk.

---

## No-fabrication: cost derived from REAL usage?

**YES for the new per-(model,provider) meter itself; NO for the surrounding call path.**

- The new meter folds `u.cost_usd` from a real `ProxyObservation.usage`
  (proxy.py:466, :476) — derived from provider-reported or computed cost,
  never from `request_bytes/4 * $1.5e-6`. The FAIL-ON-REVERT tests
  `test_real_provider_cost_metered_not_est_floor`,
  `test_computed_cost_metered_not_est_floor`, and
  `test_free_response_meters_zero_not_est_floor` exercise this and fail RED
  on revert (empirically verified: free-response test fails with
  `1.5e-06 == 0.0` when floor substitution is reintroduced).
- **BUT — `forwarder.py` still passes `est_cost` to the spend limiter**
  (`:376`, `:461`) via `_spend_to_record(obs, est_cost)` (forwarder.py:45).
  The unpriced-path (`obs.cost_source == "unpriced"` / `obs.usage is None`)
  still substitutes the fabricated floor (`request_bytes/4 * $1.5e-6`,
  `_pre_flight_estimate`). This is by-design ("geninely unknown → keep the
  floor so an uncosted call still advances the cap", SR-7) and out of this
  diff's scope. NOTE: the new meter does NOT retroactively sanitise this —
  unpriced responses contribute `0` to `_model_provider_cost` while the
  spend limiter records the est_cost floor. The two ledgers can diverge by
  design. NOT a bug in this diff, but worth explicitly documenting since
  cost-rank routing reading from the new meter would SKIP uncosted routes
  (zero meter) while the limiter bills them — a consistency gap for wave 2.

---

## Credential shape: provider keys / secrets leaked into meter record?

**NO.** `_model_provider_cost` keys `(requested_model, provider_label)`
(proxy.py:474); `_model_spend` keys `(model, provider)` (balance.py:236,
:244). No header, body blob, Authorization header, or URL passes into either
ledger. `provider` is a bare label like `"deepseek"` or `"openrouter"`. The
test `test_metering_invariant_credential_shape` (line 207-237) confirms
pool-id variants (`deepseek/deepseek-v4-pro` vs `deepseek-v4-pro`) keep the
model-side keying consistent — no credential leak. ✓

---

## Per-(model,provider) accuracy / namespaced-id double-bill

**NO double-bill from the prior namespaced-id bug.** The diff keys the
meter by `obs.requested_model` (as seen by the router) × provider label
(proxy.py:474). A namespaced id `deepseek/deepseek-v4-pro` and a bare id
`deepseek-v4-pro` are distinct keys with no cross-talk — confirmed by
`test_metering_invariant_credential_shape` and the concurrent test
`test_metering_invariant_concurrent_no_lost_entries` (line 240-264). Off-by-
one on provider attribution is NOT possible in this meter because the
provider label comes from a single authoritative kwarg. Floor of TIMES
weight: **LOW** for the meter itself.

**BUT (off-by-one-on-provider concern — future blast):** Wave 1 explicitly
flags caller wiring as deferred ("`provider` parameter defaults to None for
backward compatibility", REVIEW-PACKET.md summary). Until a caller wires
each attempt's true provider label, accuracy is THEORETICAL. The closest
`provider`-like token in `forwarder.py` is `route.label` (e.g.
forwarder.py:330, :352, :374), but it is never passed to record()/observe().
Risk increases sharply once wiring lands. *See M1 below.*

---

## Tests fail-on-revert

**YES (verified empirically).**

Removed the meter fold (`if provider is not None: ... +u.cost_usd`) from
`record()` and re-ran `pytest tests/test_meter_model_provider.py`. Results:
```
8 failed, 10 passed
```
Failing tests include all three FAIL-ON-REVERT guards AND both invariant
canaries AND the concurrent and per-key-accumulation tests. Severity of the
fail is high (assertion fails with documented diagnostic messages).

The three FAIL-ON-REVERT tests correctly exercise the diff:
- **`test_real_provider_cost_metered_not_est_floor`** (line 130-155):
  asserts `metered == 0.42`. Passed on new code, FAILS RED on revert
  (`metered 0.0`, not `0.42`).
- **`test_computed_cost_metered_not_est_floor`** (line 158-177): asserts
  `math.isclose(metered, 0.0035)`. FAILS RED on revert.
- **`test_free_response_meters_zero_not_est_floor`** (line 180-194):
  asserts `metered == 0.0`. FAILS RED with the historical
  `cost if cost > 0 else est_cost` substitution (`metered 1.5e-06, expected
  0.0`) — verified by simulating that exact historical revert.

**Caveat:** the `test_real_provider_cost_metered_not_est_floor` test
asserts cost_source == "provider" with a NON-ZERO value (0.42). Under the
specific historical revert (substitute `est_cost` when `cost > 0 else
floor`), it would NOT fail because 0.42 > 0 → kept verbatim. The test
documentation claims RED under "substituting `est_cost` for the actual
`cost_usd`" — this is accurate only for a *complete* substitution, not for
the ">0 else floor" historical bug. The free-response test is the real
protector against the historical bug. Minor documentation over-claim.
**Severity: LOW** (test still fails under the complete-revert scenario,
which is the dominant case).

---

## Concurrency / partial-failure

- **Concurrency.** `_model_provider_cost` shares the existing
  `self._lock` (proxy.py:461 holds it across both `self._usage` and
  per-key meter fold — no torn read). `_model_spend` (balance.py:235,
  :240, :243) shares the balance lock. Test
  `test_metering_invariant_concurrent_no_lost_entries` (line 240-264)
  fails RED on revert with `KeyError: ('m1', 'p1')`. ✓
- **Failover mid-stream.** Per (1) in metering-invariant: on downgrade
  failover the discarded attempt is folded with `count_usage=True` (visible,
  not silent), then the served attempt is also `count_usage=True`. Both
  observe the SAME provider label via `route.label. Served_leg + discarded_leg
  are added to the meter. No lost entries, no torn state. ✓
- **Partial failure (stream broke before model header).** forwarder.py:399-401
  records the attempt with `count_usage=False` → no meter entry, no global
  entry. Delta 0. ✓
- **Provider=None (default for now):** `count_usage=True` and `provider=None`
  sentence: meter entry NOT created, global counter advances. The meter
  IDS pureset is a strict subset of global counter entries once wired.
  Not a bug — just a no-op now.

---

## Findings

### M1 — Caller wiring naked (BLOCKER for "authoritative" claim)

**File:** `forwarder.py:278, 350, 399, 421, 450` (all `record()`/`observe()` sites)  
**Severity:** HIGH (correctness-claim-blocker, not bug)  
**Scenario:** As the diff ships, `_model_provider_cost` is permanently empty
under real traffic — every `record()` and `observe()` call forwards through
`forwarder.py` and **never sets `provider=`**. `model_provider_cost()` /
`all_model_provider_costs()` return `{}` until a future wave wires
`provider=route.label` into: `forwarder.py:356`, :350, :399, :421, :450 (and
the `observe()` call at `forwarder.py:181` is `count_usage=False` so skip).
REVIEW-PACKET.md is transparent about this ("Caller changes ... deferred"),
but the proxy.py docstrings over-claim:
- `proxy.py:519-521` — "...cost-rank routing and drain-then-park read from
  here instead of fabricating an est_cost floor."
- `balance.py:253` — "Read by cost-rank routing and drain-then-park..."

These asserts are unimplemented consumers — review-A should not merge
under the impression that routing already uses the meter. Either flag
`@requires_caller_wiring` in docstrings or amend to "will be read". Hard
grounding for "authoritative per-route spend". This finding is the main
driver for MERGE-WITH-FIXES rather than SAFE-TO-MERGE.

### M2 — Visible-discard double-fold persists into the meter (no isolation)

**File:** `forwarder.py:350-351, :421-422` + `proxy.py:465-476`  
**Severity:** LOW (intended behavior, but the meter inherits the aliasing)  
**Scenario:** Under `failover_on_downgrade=True`, a streaming downgrade head
is recorded with `count_usage=True` (visible) and then the served attempt is
also `count_usage=True`. Both cost_usd values fold into the meter under the
same `(request_model, provider)` key. A consumer reading
`model_provider_cost(model, provider)` as "burn rate on this route" gets a
value inflated by all discarded downgrade costs. Not a drift between paths,
but a meaning ambiguity. Wave 2 should tag meter entries with `served: bool`
if burn-rate-only accounting matters.

### M3 — Documentation over-claim on FAIL-ON-REVERT real-cost test

**File:** `tests/test_meter_model_provider.py:130-155` (docstring at :140-145)  
**Severity:** LOW  
**Scenario:** Test claims RED if "reverting to est_cost fabrication
(substituting est_cost for the actual cost_usd in the per-(model,provider)
meter)" — true under a complete-substitution revert, but the *historical*
bug substituted only on the zero path (`cost if cost > 0 else est_cost`),
under which this test's positive cost (0.42) passes silently. The
`test_free_response_meters_zero_not_est_floor` is the test that catches the
historical pattern. The docstring over-angles the case. No code impact;
tighten the claim or rename the guard to specify "complete substitution".

### L1 — Unpriced-path divergence from spend limiter

**File:** `proxy.py:473-476` vs `forwarder.py:376, :461` via `_spend_to_record`  
**Severity:** LOW (scope-excluded, but undocumented)  
**Scenario:** An `unpriced` response (no cost block, no stored pricing) has
`obs.usage.cost_usd == 0.0` and `obs.cost_source == "unpriced"`. The new
meter records 0 (no path forward); the spend limiter records `est_cost`
(forwarder.py:63-65). The two ledgers intentionally diverge on unpriced
routes. Any wave-2 cost-rank router that reads `model_provider_cost` will
*tunder*-rank uncosted routes relative to what the limiter bills. Not a
merge blocker (wave 1 explicitly excludes caller wiring), but document the
consistency gap so wave 2 doesn't ingest the meter blindly.

### L2 — `BalanceTracker.record_spend` `model` kwarg never called from production code

**File:** `balance.py:219` vs every `record_spend` call (all on `balance.py`
docstrings + tests, none in forwarder/proxy_server)  
**Severity:** LOW (parallels M1 for the BalanceTracker)  
**Scenario:** Identical to M1: `_model_spend` stays empty in the real
gateway. The `model_spend()` API returns 0.0 for all pairs. The unit tests
succeed because they call `record_spend(..., model=...)` directly. Real
traffic never reaches this path until forwarder wiring lands.

---

## Verdict

**MERGE-WITH-FIXES**. The new metering code itself is mechanically correct:
real-cost fold, no credential leakage, no drift from the global counter, no
double-bill on namespaced ids, tests fail RED on revert (empirically
verified across 8 tests including all three FAIL-ON-REVERT guards and both
invariant canaries). Merging as "authoritative" is blocked only by the
caller-wiring gap (M1) and the over-claiming docstrings (passim).

**Required before merge:**
1. Soften the proxy.py / balance.py docstrings to "will be read (wave 2)" or
   annotation `@requires_caller_wiring`; drop the present-tense
   authoritative-correctness claim.
2. Add a note to `tests/test_meter_model_provider.py` header that
   `forwarder.py` wiring is deferred and the meter is empty in real traffic.

**Recommended (wave 2):**
- Tag meter entries with `served: bool` (M2).
- Document the unpriced-path divergence (L1).
- Add an integration test that feeds through `forwarder.py` once `provider=`
  is wired, asserting the meter registers real spend (currently no test
  exercises the production call path).

---

## Reviewer's empirical evidence (reproduce)

```bash
# Verified all 18 tests pass on branch
python3 -m pytest tests/test_meter_model_provider.py -x --tb=short
# 18 passed in 10.16s

# Verified fail-on-revert: removed the if/provider meter fold in record()
# 8 failed, 10 passed (all FAIL-ON-REVERT + invariants fail)

# Verified historical-bug-fallback: re-introduced cost if cost>0 else est_cost
# test_free_response_meters_zero_not_est_floor fails with `1.5e-06 == 0.0`
# All other tests still pass (positive/cost>0 path is unaffected by that bug)
```

---

**File:** `/home/stack/charon-private/fleet/reviews/METER-REVIEW-B.md`