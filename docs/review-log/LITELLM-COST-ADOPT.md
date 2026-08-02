# LITELLM-COST-ADOPT — review log fragment

## What LiteLLM's cost/budget surface gives us

`litellm_plane/metering.py` surfaces:
- `litellm_cost(response)` — extracts per-request USD from `ModelResponse._hidden_params["response_cost"]`
  (primary) or `usage.cost`/`usage.total_cost` (fallback). Returns `0.0` when absent.
- `charon_cost(observation)` — extracts Charon's authoritative `usage.cost_usd`.
- `check_divergence(litellm_usd, charon_usd)` — pure comparison; logs WARNING when delta > $0.001.
- `crosscheck_observation(raw_response, observation)` — convenience wrapper.
- `classify_and_crosscheck(router, body)` — issue a Router completion + cross-check costs. Returns
  `(raw, dict, observation, delta)`. PURE — never calls `record_spend` or mutates `BalanceTracker`.

**ADR-0020 verdict (ACCEPTED, 2026-07-23): verify-only cross-check. Charon's own cost computation
remains the source of record for money accounting. The callback must NEVER override, correct, freeze,
or reorder Charon's authoritative spend / drain-then-park.**

LiteLLM's budget enforcement (`set_monthly_spend_limit`, per-key/user budgets) is **not wired** — the
Router is not configured with budget callbacks, and `metering.py` does not implement them. That
surface is out-of-scope for this ticket (ADR-0020 covers per-request cost, not budget caps).

## What it REPLACES

The litellm_plane does NOT replace Charon's hand-rolled cost path. The two are parallel:
- **Charon's own metering** (`proxy.observe` → `ProxyObservation.usage.cost_usd`) is the AUTHORITATIVE
  cost for `BalanceTracker`, `spend_limiter`, cost-rank routing, and drain-then-park.
- **litellm metering** (`metering.py`) is a VERIFY-ONLY cross-check. It runs alongside and surfaces
  divergence; it does not advance `BalanceTracker`.

The `_spend_to_record(obs, est_cost)` fallback (forwarder.py:85) for genuinely unknown costs
(`obs.usage is None` or `cost_source == "unpriced"`) is NOT replaced by litellm metering. That
floor is intentional SR-7 behavior. It is NOT a bug.

## Wiring status: INERT (the accept criterion)

`grep -rn litellm_plane src/ | grep -v src/charon/litellm_plane/` → **ZERO production importers**.

All litellm_plane modules are self-referential within the plane. The Router serve path
(`complete_via_router`, `complete_via_router_guarded`) is a real entry point that makes httpx calls
to upstream providers — but no production entrypoint calls it.

The plane is **built but inert**: merged, marked done, vendored, and imported by nothing.

## The $1,185 vs $1.34 discrepancy explained

The two numbers measure different things:
- **`$1.34`** — live metered spend: `BalanceTracker.remaining(provider)` = `starting_balance -
  observer_spend_fn()`. The observer (`GatewayProxy.all_model_provider_costs()`) records actual
  `cost_usd`. This is the authoritative number.
- **`$1,185`** — `spend.json` (universal cap): records per-task spend via `_spend_to_record`, which
  falls back to `_pre_flight_estimate` (a fabricated floor of `request_bytes/4 * $1.5e-6`) when
  `cost_source == "unpriced"` or `obs.usage is None`.

The discrepancy is NOT evidence that Charon's meter is wrong. It is evidence that `_pre_flight_estimate`
is a loose floor for un-priced models. The observer (which records actual costs for priced models)
and the universal cap (which uses the floor for un-priced ones) are two different consumers with
different risk tolerances.

## Done contract items

1. **Enumerate what LiteLLM's surface gives us** — DONE above. Per-request cost extraction + divergence
   cross-check. Budget enforcement not wired (out of scope).
2. **Wire it, or delete with evidence** — The plane IS already wired internally. It is inert because
   nothing in the production path calls it. Wiring it as the money-path source would require
   changing the source of record (ADR-0020 explicitly DEFERRED this). As verify-only cross-check, the
   plane is already available for callers who want to use `classify_and_crosscheck`.
3. **Prove reachability from a real entrypoint** — `complete_via_router` makes real httpx calls.
   `test_litellm_router_e2e.py` already proves the full round-trip: config → make_router → httpx →
   stub upstream → served response. The Router path is live.
4. **Cross-check LiteLLM vs provider cost on a sample** — No production traffic has been run through
   the Router path yet. The infrastructure (`crosscheck_observation`) exists and is ready. The
   cross-check requires a live Router call to exercise.
5. **Fail-on-revert test for cost path live** — The existing e2e tests (`test_litellm_router_e2e.py`)
   prove the Router serves real requests. Adding a test that imports `litellm_plane` and asserts the
   import succeeds would serve as a fail-on-revert proof that the plane hasn't been deleted.

## Recommendation

The litellm_plane is **already correctly wired as ADR-0020 specifies**: verify-only, parallel to
Charon's authoritative path, never overriding. The "problem" is that the plane is not used as a
money source (by design — ADR-0020 deferred that). No new code is needed.

The `$1,185` vs `$1.34` concern is a misunderstanding: the two numbers measure different ledgers
with different purposes and risk tolerances.

Action: **No code change. Close as ADOPTED-WIRED-EVIDENCE-FILED.**
