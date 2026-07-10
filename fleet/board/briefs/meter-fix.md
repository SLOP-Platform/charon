# BRIEF — APPLY ADJUDICATED FIXES: METER-MODEL-PROVIDER (money-path, Wave 1)

ROLE: Apply a small, DOC-ONLY set of fixes to the money-path metering diff, adjudicated from two independent adversarial reviews. Do NOT change runtime logic. Work on branch `feat/meter-model-provider` in THIS working dir.

## CONTEXT
Two reviews returned MERGE-WITH-FIXES. The metering CODE is correct (real-cost fold, no credential leak, no drift, 8/18 tests fail-on-revert). The blockers are OVER-CLAIMS and deferred-wiring documentation, NOT logic bugs. Caller wiring (`provider=route.label` in `forwarder.py`) is intentionally deferred to Wave 2, so `_model_provider_cost` / `_model_spend` are EMPTY under real traffic today.

## REQUIRED FIXES (doc-only — no behavior change)
1. **Soften the authoritative present-tense docstrings** in `src/charon/proxy.py` (~lines 519-521, the `model_provider_cost`/`all_model_provider_costs` area) and `src/charon/balance.py` (~line 253, the `model_spend` area). Change claims like "cost-rank routing and drain-then-park read from here instead of fabricating an est_cost floor" to future/deferred phrasing, e.g. "WILL be read by Wave-2 cost-rank routing and drain-then-park; caller wiring (provider=route.label) is deferred, so this ledger is EMPTY under real traffic until Wave 2 wires it."
2. **Document the keying precondition** on `model_provider_cost()` and `all_model_provider_costs()`: the `model` argument MUST be the EXACT `requested_model` string passed to `observe()` (NOT a normalized/prefix-stripped/aliased form); entries exist ONLY for observations that passed a non-None `provider` — `provider=None` observations advance the global counter but are NOT metered per-route.
3. **Add a header note** to `tests/test_meter_model_provider.py` stating that `forwarder.py` caller-wiring is deferred to Wave 2, so the meter is EMPTY in real traffic today and these tests exercise the mechanism directly.
4. **Add a short KNOWN-WAVE2-GAPS comment** (in proxy.py near the meter, or a docstring) noting two deliberately-deferred consistency items: (a) negative/refund costs are passed through un-guarded to match the global `_usage` counter — guarding only the per-route meter would BREAK the sum(meter)==cumulative_usage delta-zero invariant, so it is intentionally NOT guarded here; (b) `unpriced` responses contribute 0 to the meter while the spend-limiter records an est_cost floor — the two ledgers diverge on unpriced routes by design; Wave-2 cost-rank routing must not ingest the meter blindly.

## DO NOT
- Do NOT change any runtime/metering logic, lock discipline, or the est_cost floor.
- Do NOT add the negative-cost `max(...,0.0)` guard (it would break the delta-zero invariant — see fix #4a).
- Do NOT touch `forwarder.py` wiring (that IS Wave 2).
- Do NOT delete or edit `REVIEW-PACKET.md` (the manager strips it at merge).

## VERIFY BEFORE COMMIT
Run: `cd <this wt> && PYTHONPATH=src python3 -m pytest tests/test_meter_model_provider.py -q`
All 18 tests must still pass (doc-only change must not alter behavior).

## LAST STEP (required)
Commit on `feat/meter-model-provider` with message `METER-MODEL-PROVIDER: soften authoritative docstrings + document deferred wiring / Wave-2 gaps (review adjudication)` and print the new commit SHA.
Do NOT push. Do NOT merge.
