# PARK-REARM-FUNDED-PROVIDER — park blast radius + re-arm (proxy observation core)

Ticket: `PARK-REARM-FUNDED-PROVIDER` (tier strong, priority 0, money-path).
Scope: `src/charon/proxy.py` + `tests/test_park_rearm.py` only (per `owns:`).

## What changed (all in `src/charon/proxy.py`)

1. **BLAST RADIUS — per-leg exclusion key.** The proxy's exhausted set is now keyed
   by the `(requested_model, provider)` **leg**, not the model id alone. A 402 on
   one leg records only that leg:
   - sibling legs of the same provider (`gpt-5.4-mini` vs `glm-5.2` on openrouter)
     stay eligible;
   - sibling providers serving the *same* model id (`openrouter` vs `decart`'s leg
     of `gpt-5.4-mini`) stay eligible.
   The orchestrator's model-wide view (`is_exhausted`/`exhausted_models`) is
   preserved byte-compatible; the narrow view is exposed as `is_exhausted_leg`/
   `exhausted_legs`.

   The provider-level park evidence is also built here: `_model_exhausted` tracks
   which model ids of each provider are **deterministically balance-exhausted**
   (402 / 401-403+billing, `not transient`), and `has_multiple_exhausted_models
   (provider)` reports the ≥2-models signal that distinguishes a per-key cap from
   a drained account. This is the exact input the forwarder's park gate needs to
   narrow (see "Known residual gap").

2. **RE-ARM — a clean 200 re-admits the leg.** `record()` now *drops* a leg's
   exclusion entry when that leg answers a clean 200 (no silent downgrade). A
   previously-parked leg is re-admitted within one observation window instead of
   staying excluded for the process lifetime. Pseudo-success 200s (failover) never
   re-arm, and re-arm is per-leg (one provider's 200 cannot clear another
   provider's exhaustion).

3. **CLASSIFICATION — 403 key-limit is a distinct exhaustion class.** 403 is now
   `exhausted` (failover-worthy) with label `key_limit`; 402 stays `balance`; 429
   `throttle`; 503 `unavailable`. The label is carried on `ProxyObservation.
   exhaustion_type` and embedded in the observation `note`, which is the field the
   failover ledger / `providers_tried[].reason` surfaces to operators — so 402 and
   403 are observably distinct, never silently folded. A 403 whose *body* says
   balance is still labelled `balance` (not folded into key_limit).

## DONE CONTRACT — RED then GREEN

Hermetic, offline, stubbed upstream. Reverting my proxy.py to `origin/master`
turns 10 of the 14 new tests RED (verified), including every DONE-CONTRACT axis:

- **(a) blast radius** — `test_one_leg_402_narrows_to_provider_leg_not_shared_model`,
  `test_one_leg_402_does_not_park_sibling_leg_of_same_provider`,
  `test_200_on_one_provider_does_not_rearm_sibling_provider_leg`,
  `test_single_model_402_is_not_provider_level_exhaustion`,
  `test_two_models_402_is_provider_level_exhaustion`,
  `test_transient_and_throttle_do_not_count_toward_provider_park`,
  `test_provider_signal_withdraws_on_rearm`.
- **(b) re-arm** — `test_exhausted_leg_cleared_on_200`, `test_rearm_is_per_leg`,
  `test_reexhausted_after_rearm_cycle_is_bounded`, `test_pseudo_success_200_does_not_rearm`.
- **(c) anti-over-block** — `test_both_legs_exhausted_when_all_402`
  (proxy-level), `test_all_legs_deterministic_402_parks_provider` (integration).
- **(d) classification** — `test_403_key_limit_distinct_from_402_balance`,
  `test_403_billing_body_is_balance`, `test_exhaustion_type_visible_in_ledger_note`.

Gate GREEN on the final tree: 2402 passed / 3 skipped / 1 xfailed / 1 xpassed;
`ruff check` clean; `mypy src tests` clean; `check_boundary` OK; `check_version` OK.

## ALSO ANSWER — is the missing `/data/balance.json` the cause?

**No — `/data/balance.json` is not read anywhere.** Evidence:

- Balance *config* comes from `providers.json` fields (`funding_class`, `mode`,
  `starting_balance`, `balance_base_url`, `balance_ttl`); gateway.py builds the
  tracker as `BalanceTracker(config=providers_cfg, state_dir=...)`
  (`_build_balance_tracker`, gateway.py:284-304). `R46 balance-wire`'s
  `_build_balance_tracker` construct-from-config claim is accurate.
- The tracker persists only its **parked set** to `<state_dir>/balance_park.json`
  (balance.py:54 `_PARK_STATE_FILE`); there is no `balance.json` file in the
  codebase (`grep -rn "balance.json"` under src/docs → nothing except
  `balance_park.json`).
- The funding-class **re-arm table** is `_maybe_auto_unpark` (balance.py:520),
  invoked ONLY from `remaining()`'s poll branch (balance.py:326-327) and
  `force_poll()` (balance.py:580-581). It is **wired but starved**: for a provider
  with no balance config, `remaining()` returns `None` at balance.py:278-280
  *before* the poll branch, so the auto-unpark never fires.

**Consequence:** a provider parked at runtime by the request-path auto-park
(forwarder.py:689 `bt.record_exhaustion`, which requires no balance config at all)
is, absent operator `unpark`/`top_up`, parked **unrecoverably by construction**
when it has no poll/fixed balance config — which is the observed incident
(openrouter parked, `balance_park.json` lists only huggingface, probes return 200
via its upstreams). The missing file is a symptom, not the cause: the cause is
"no balance config → re-arm table starved".

## Known residual gap (OUT of `owns:` — needs forwarder.py, sequenced with FORWARDER-COST-ORDER-FALLBACK)

The gateway-level provider-park call site is forwarder.py:686-689:

    if bt is not None and status == 402 and not obs.transient:
        prov = route.provider or route.label
        if _has_live_sibling(prov, srv.pools, bt):
            bt.record_exhaustion(prov)

Two problems (both out of `owns:`):

1. **The guard reads the WRONG evidence.** `_has_live_sibling` checks whether
   another *provider* is live — not whether THIS provider is actually drained.
   For openrouter (no `funding_class`/`mode` balance config, so `is_drained` is
   always False) every sibling counts as "live", so a SINGLE leg's 402 parks the
   whole provider — the incident. The proxy now ships the correct evidence
   (`has_multiple_exhausted_models(prov)` — ≥2 distinct models deterministically
   balance-exhausted); the forwarder gate should consume it instead of
   `_has_live_sibling`. `forwarder.py` is owned by FORWARDER-COST-ORDER-FALLBACK
   (D&S note) — sequence the wiring there.
2. **The re-arm wiring is starved at build time.** `gateway.py:_build_balance_tracker`
   (gateway.py:294-304) returns `None` unless SOME provider carries explicit
   `funding_class`/`mode` config. A poll-mode provider (openrouter/deepseek/
   nanogpt) with no explicit balance config therefore gets NO tracker, so its
   poll-recovery re-arm (`remaining()` → `_maybe_auto_unpark`) is unreachable —
   parked providers stay parked. `gateway.py` is outside `owns:`.

**Adversarial note (money-path):** the narrowing here is at the *proxy observation
core* and cannot let a genuinely drained provider keep taking traffic: the proxy
still excludes each exhausted leg, `has_multiple_exhausted_models` gives the
forwarder an account-level park gate, and `test_both_legs_exhausted_when_all_402`
+ `test_all_legs_deterministic_402_parks_provider` pin that all-legs-402 still
parks. The residual exposure is the two out-of-owns items above.
