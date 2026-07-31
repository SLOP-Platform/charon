# ADR-0021 — LiteLLM Capability Adoption: disposition every `Router.__init__` parameter

- **Status:** ACCEPTED (operator ratification pending)
- **Deciders:** Nnyan (solo operator)
- **Repo:** `github.com/SLOP-Platform/charon`
- **Relates to:** ADR-0017 (outcome-graded gateway; adopt `litellm.Router`), ADR-0020 (litellm
  metering bridge — verify-only), `ADOPT-MAP.md` §"Slice boundary" (first slice = default-OFF
  parity), `docs/DECISIONS.md` D025 (no double-bill)
- **Installed litellm:** `1.93.0` (verified via `pip show litellm`)
- **Generated from:** `inspect.signature(litellm.Router.__init__)` — 52 parameters (excluding
  `self`), enumerated programmatically on 2026-07-31. Never hand-copied from upstream docs.

---

## Context

`litellm.Router.__init__` accepts **52 parameters**. `src/charon/litellm_plane/litellm_router.py`
`make_router()` currently passes **six**: `model_list`, `cooldown_time`, `allowed_fails`,
`num_retries`, `retry_after`, `set_verbose`. The first slice (`feat/gateway-litellm-adopt`)
deliberately scoped to default-OFF parity — the live money-path stayed byte-identical (ADR-0017
§"Slice boundary", `ADOPT-MAP.md:65`). The deferrals were "documented, NOT silently dropped" but
were never scheduled.

This ticket schedules them. Every unused Router capability is dispositioned in a single pass
against a single set of criteria, producing one coherent decision register. Splitting it produces
inconsistent verdicts (adopt `fallbacks` while declining the `routing_strategy` that fallbacks
depends on) and leaves no record of *why* each capability was taken or declined.

**This is a DESIGN/DECISION pass, not an implementation.** Implementation of any ADOPT verdict
is sequenced AFTER `GW-CUTOVER-LIVE-WIRE` lands (which itself needs `LITELLM-ORDER-PRECALL`).

### Why single-pass

The measured gap is substantial: even after GW-CUTOVER-LIVE-WIRE puts Router on the live path,
we would run a maintained router in roughly the shape of the hand-rolled one it replaces.
**Wired is not the same as used** — the unused capabilities map onto REAL observed failures
on this rig:

| Capability | Failure it addresses (all observed on this rig) |
|---|---|
| `fallbacks` / `default_fallbacks` / `max_fallbacks` | `glm-5.2` exists as SIX separate catalog entries (`-or`/`-nw`/`-ng`/`-cline`/`-hf`/`-go`) that routing cannot reach from one name |
| `provider_budget_config` | the 402 "all providers exhausted" outage — budget-aware routing around a drained provider |
| `routing_strategy` + `routing_strategy_args` | we hand-roll `cost_rank` ordering |
| `context_window_fallbacks` | `deepseek-v4-flash` silent truncation at a 48-request session cap |
| `enable_health_check_routing`, `health_check_*` | legs that pass a 1-shot probe then collapse under session load |
| `enable_weighted_failover` | the SOLE-LEG GUARD case (199 hits in one log window) |
| `enable_tag_filtering` | tier / capability routing |
| `cache_responses`, `cache_kwargs` | direct cost reduction |
| `retry_policy`, `model_group_retry_policy` | per-group retry instead of one global `num_retries` |

## Decision

**Every `litellm.Router.__init__` parameter receives exactly one verdict: ADOPT, DECLINE, or
DEFER.** The verdict table below is the authoritative register. Implementation is sequenced
individually — an ADOPT verdict does not mean "implement now"; it means "this capability
SHOULD be adopted when implementation is scheduled."

### Verdict rules

- **ADOPT** — The capability has a confirmed hand-rolled Charon equivalent that it replaces
  (named by `file:line`), OR it fills a gap with no hand-rolled equivalent (noted as "additive").
  Adopting a Router capability must DELETE Charon code, not sit alongside it.
- **DECLINE** — The capability duplicates rather than replaces, conflicts with Charon policy
  (preserved controls), is irrelevant to Charon's Router-as-library usage, or would surrender
  differentiation. A concrete reason is given.
- **DEFER** — The capability is potentially useful but cannot be adopted without a precondition
  that is not yet met. An explicit TRIGGER (what must become true) is given. "Later" is not a
  trigger.

### Guards applied

1. Per-provider free-tier windows are Charon policy that litellm does not model → those stay
   Charon policy fed into the Router pre-order.
2. Anything touching billing/spend is money-path: flagged for RED/GREEN/dogfood at
   implementation time.
3. Some Charon policy is genuinely ours (free-tier windows, funding-class ordering, grading).
   Do NOT recommend surrendering policy that encodes our differentiation.
4. Do not recommend adopting a capability not verified in the INSTALLED version.

---

## Disposition table

52 parameters enumerated from `inspect.signature(litellm.Router.__init__)`,
litellm `1.93.0`. "Already passed" = currently wired in `make_router()`
(`src/charon/litellm_plane/litellm_router.py:363-369`).

| # | Parameter | Verdict | Detail |
|---|---|---|---|
| 1 | `model_list` | **ADOPT** | Already passed. Maps Charon chains → litellm deployments; replaces hand-rolled chain iteration in `forwarder.py:565` (`for i, route in enumerate(ordered)`). |
| 2 | `assistants_config` | **DECLINE** | OpenAI Assistants API integration. Charon does not build Assistants endpoints; this is a proxy-server concern irrelevant to Router-as-library. |
| 3 | `search_tools` | **DECLINE** | Search tool infrastructure. Charon does not host search tools; proxy-server concern. |
| 4 | `guardrail_list` | **DECLINE** | Guardrails / content filtering. Charon routes requests, does not content-filter them; proxy-server concern. |
| 5 | `redis_url` | **DEFER** | **Trigger:** Charon adopts Redis for cross-process state sharing (currently in-process only). Without Redis, cross-deployment cooldown/cache state is single-process-scoped. |
| 6 | `redis_host` | **DEFER** | **Trigger:** same as `redis_url`. |
| 7 | `redis_port` | **DEFER** | **Trigger:** same as `redis_url`. |
| 8 | `redis_password` | **DEFER** | **Trigger:** same as `redis_url`. |
| 9 | `redis_db` | **DEFER** | **Trigger:** same as `redis_url`. |
| 10 | `cache_responses` | **ADOPT** | Replaces `cache.py:31-70` `SemanticCache` (SHA-256 exact-match LRU cache) + `forwarder.py:514-526` cache check + `forwarder.py:818-821` cache set (non-stream 200) + `forwarder.py:917-920` cache set (complete stream). **Money-path: flag for RED/GREEN/dogfood.** litellm's cache supports Redis/disk persistence with TTL — a strict upgrade from in-memory-only. |
| 11 | `cache_kwargs` | **ADOPT** | Paired with `cache_responses`; passes TTL, backend, cache key customisation. Replaces `cache.py:31` `SemanticCache.__init__` TTL/max_size params. |
| 12 | `caching_groups` | **DEFER** | **Trigger:** when Redis-backed cross-process caching is adopted (`redis_url` adopted). Router-as-library can use `cache_responses` without groups. |
| 13 | `client_ttl` | **DECLINE** | Proxy-client registration TTL. Charon does not run the litellm proxy server; clients connect directly to Charon's own serve path. |
| 14 | `polling_interval` | **DECLINE** | DB poll interval for litellm proxy's config sync. Router-as-library does not poll a DB. |
| 15 | `default_priority` | **DECLINE** | Single global priority number. Charon uses multi-factor ordering (funding class + cost + drain state + coarse) — a single priority cannot encode this. Surrendering the multi-axis order for one number would regress. |
| 16 | `num_retries` | **ADOPT** | Already passed. Replaces `forwarder.py:611-663` retry-once transient logic + `failover_loop.py:58-100` `invoke_with_failover` retry. |
| 17 | `max_fallbacks` | **ADOPT** | Replaces the implicit N-deployments-per-chain iteration cap in the `forwarder.py:565` loop. Currently no max — adopting provides a configurable cap (prevents unbounded failover churn). |
| 18 | `timeout` | **ADOPT** | Replaces `forwarder.py:582,633` `srv.fwd_timeout` (currently 180.0, hardcoded) + `netutil.py:313` urllib timeout. Already partially wired in `litellm_plane/litellm_router.py:215-224` `no_redirect_client`. |
| 19 | `stream_timeout` | **ADOPT** | Replaces `forwarder.py:43` `_STREAM_HEAD_CAP` (65536 byte buffer) + streaming relay timeout in `forwarder.py:890-903`. Timeout distinct from non-stream by Router default. |
| 20 | `default_litellm_params` | **DECLINE** | Global params injected into every deployment. Charon builds per-route params deliberately in `build_model_list` (`litellm_router.py:146-169`) — injecting globals would bleed configuration across deployments and weaken the per-route binding controls (base-bound key, egress screening). |
| 21 | `default_max_parallel_requests` | **DEFER** | **Trigger:** when `max_concurrency` is promoted from per-route field (R7, `forwarder.py:410-412`) to Router-level enforcement. Currently per-route only. |
| 22 | `set_verbose` | **ADOPT** | Already passed. Controls litellm debug logging; harmless, enables troubleshooting during adoption. |
| 23 | `debug_level` | **DECLINE** | litellm log level override. Charon has its own structured logging; `set_verbose=True` + Charon's own log level is sufficient. Setting `debug_level` would silently reconfigure litellm's internal logging separately. |
| 24 | `default_fallbacks` | **ADOPT** | Replaces `proxy_server.py:257-263` `chain_for` fallback-to-pool logic. Enables the missing glm-5.2 routing: one model name → pooled providers fallback without six separate catalog entries. |
| 25 | `fallbacks` | **ADOPT** | Replaces per-pool fallback chains in `routing_policy/__init__.py:144-208` `build_routes_and_pools` + the `is_sole_leg` guard in `forwarder.py:457-469`. litellm's fallback chain allows explicit A→B→C without Charon synthesizing chains from pool membership. |
| 26 | `context_window_fallbacks` | **ADOPT** | Replaces `forwarder.py:400-422` R7 `max_context` eligibility check. litellm natively skips deployments whose `max_input_tokens` can't fit the request — Charon's hand-rolled `est_tokens > mc` check (`forwarder.py:408`) is made redundant. |
| 27 | `content_policy_fallbacks` | **DEFER** | **Trigger:** when Charon adds a content-policy field to `UpstreamRoute` or model spec (e.g., "no-csam", "no-adult"). No current data to drive this. |
| 28 | `model_group_alias` | **DECLINE** | Aliases one model name to another. Charon's own `model_id` → chain mapping in `proxy_server.py:636-649` already supports aliasing via pool/routes config; adding a second alias layer adds indirection without benefit. |
| 29 | `enable_pre_call_checks` | **DEFER** | **Trigger:** after `LITELLM-ORDER-PRECALL` ticket (`fix/litellm-order-precall`) lands. That ticket already wires pre-call checks; adopting here before it lands risks conflict. |
| 30 | `enable_tag_filtering` | **ADOPT** | Replaces `forwarder.py:384-398` capability-based route exclusion (R3) + `routing_policy/matrix.py:44-115` `CapabilityMatrix`. litellm's native tag filtering: set `tags: ["reasoning"]` on capable deployments, `tags` in request `metadata` → Router filters automatically. The `CapabilityMatrix` static deny table for known-incapable providers (`openrouter` denies `reasoning`, `novita` denies `reasoning`) maps to deployment tags. |
| 31 | `tag_filtering_match_any` | **ADOPT** | Paired with `enable_tag_filtering`. Controls OR vs AND semantics for multiple tags. |
| 32 | `retry_after` | **ADOPT** | Already passed. Replaces `proxy_server.py:686-699` `retry_after_hint` and `proxy_server.py:716-727` `set_cooldown` Retry-After clamping. |
| 33 | `retry_policy` | **ADOPT** | Replaces `forwarder.py:611-663` retry-once transient logic at the per-request level. Current `num_retries` is global; `retry_policy` allows per-HTTP-status retry control (e.g., no retry on 401, retry up to 3 on 429). Also replaces `proxy.py:42-56` `_TRANSIENT_BILLING_BODY_PATTERNS` — litellm retry policy maps status codes natively. |
| 34 | `model_group_retry_policy` | **ADOPT** | Replaces the single global `num_retries` with per-model-group retry config. Enables tuning: high-value models retry more, experimental models retry less. No Charon equivalent exists — additive, but the global `num_retries` becomes a fallback default. |
| 35 | `allowed_fails` | **ADOPT** | Already passed. Replaces `proxy_server.py:651-677` `order_by_cooldown` threshold — failures before a deployment is cooled. |
| 36 | `allowed_fails_policy` | **DEFER** | **Trigger:** when a custom fail-counting policy is needed (e.g., count only `429` as a cooldown-triggering failure, not `503`). Default `allowed_fails` behaviour is sufficient for the current cooldown model. |
| 37 | `cooldown_time` | **ADOPT** | Already passed. Replaces `proxy_server.py:716-727` `set_cooldown` default duration + `proxy_server.py:593-594` `_cooldown` dict. |
| 38 | `disable_cooldowns` | **DECLINE** | Cooldown is a core availability guarantee: a failing upstream leg must be quarantined, not retried endlessly. Disabling cooldowns would regress to the pre-cooldown "hammer a failing provider" behaviour that the cooldown machinery was built to stop. |
| 39 | `routing_strategy` | **ADOPT** | Replaces `forwarder.py:530-551` R2 live-cost reorder (`order_pool_by_live_cost`) + `routing_policy/cost_rank.py:64-93` `derived_cost_rank` mechanical sort + `routing_policy/__init__.py:297-318` `order_pool_by_live_cost`. Maps to `routing_strategy="cost-based-routing"` (replaces cost-rank sort) or `"latency-based-routing"` (replaces `proxy_server.py:669-676` latency tiebreak + `latency.py:11-61` `RollingLatency` EWMA). **Charon's funding-class pre-ordering is NOT surrendered** — it runs BEFORE the Router's strategy as a pre-filter (`routing_policy/__init__.py:220-296` `order_chain_by_funding_class` stays). |
| 40 | `optional_pre_call_checks` | **DEFER** | **Trigger:** when litellm adds pre-call check hooks that go beyond `enable_pre_call_checks` (currently, `enable_pre_call_checks` covers the ordering/policy need). |
| 41 | `routing_strategy_args` | **ADOPT** | Paired with `routing_strategy`. Passes `{"ttl": 600}` for cost-cache freshness (replaces `routing_policy/cost_rank.py` implicit TTL) or `{"lowest_latency": True}` for latency strategy config. |
| 42 | `routing_groups` | **DEFER** | **Trigger:** when Charon needs model-group-level routing config separate from `model_list` ordering. Currently chain ordering + `routing_strategy` covers all use cases. |
| 43 | `provider_budget_config` | **ADOPT** | Replaces `balance.py:148-628` `BalanceTracker` budget tracking + `spend_limits.py:15-91` `SpendLimiter`. litellm's `provider_budget_config` provides per-provider dollar/time budgets with auto-cooldown at exhaustion. **Money-path: flag for RED/GREEN/dogfood.** Directly addresses the 402 "all providers exhausted" failure. **CAVEAT: does NOT replace `BalanceTracker.park`/`unpark` lifecycle (disk persistence, manual re-arm) or `funding_class` pre-ordering — those stay Charon policy.** The budget config replaces the *tracking* and *threshold* logic, not the *lifecycle* and *ordering* policy. |
| 44 | `alerting_config` | **ADOPT** | Replaces `degrade_alert.py:35-133` `DegradeAlert` WARNING logs (last-resort, prepaid-zero, pool-too-thin). litellm's native alerting provides Slack, webhook, and email on budget exhaustion, failure spikes, and spend anomalies. **Does NOT replace `observability.py:20-150` — JSONL/Prometheus/webhook/Langfuse export is additive (Charon's own telemetry).** |
| 45 | `router_general_settings` | **DECLINE** | `async_only_mode` and `pass_through_all_models` are proxy-server behaviours. Charon uses Router synchronously with an explicit `model_list` — `pass_through_all_models` would bypass the deliberate model-list construction (including the egress screening, base-bound key, and never-Anthropic controls). |
| 46 | `deployment_affinity_ttl_seconds` | **DEFER** | **Trigger:** when Charon adopts sticky sessions or deployment affinity for stateful backends (e.g., conversation state pinned to one deployment). No current use case. |
| 47 | `model_group_affinity_config` | **DEFER** | **Trigger:** same as `deployment_affinity_ttl_seconds`. |
| 48 | `ignore_invalid_deployments` | **DECLINE** | Fail-closed posture: an invalid deployment in the `model_list` is a config error that must be surfaced (raises, blocks startup), not silently ignored. Silently dropping deployments risks a pool going empty without detection. |
| 49 | `enable_health_check_routing` | **ADOPT** | **Additive — no hand-rolled equivalent to delete.** Charon's current approach is purely reactive: try a leg → fail → `set_cooldown` (`proxy_server.py:716-727`). litellm's health check routing runs async background probes and preemptively excludes unhealthy deployments BEFORE a live request fails. This addresses "legs that pass a 1-shot probe then collapse under session load" (ticket note). The reactive cooldown path (`forwarder.py:586-600`, `proxy_server.py:716-727`) stays as fallback for failures that slip past health checks — the two mechanisms are complementary, not duplicative. |
| 50 | `health_check_staleness_threshold` | **ADOPT** | Paired with `enable_health_check_routing`. Controls how stale a probe result can be before the deployment is re-probed. |
| 51 | `health_check_ignore_transient_errors` | **ADOPT** | Paired with `enable_health_check_routing`. Prevents a single transient probe failure from blacklisting a deployment — similar to the `_TRANSIENT_BILLING_BODY_PATTERNS` distinction in `proxy.py:42-56`. |
| 52 | `enable_weighted_failover` | **ADOPT** | Replaces the linear failover iteration in `forwarder.py:565` (`for i, route in enumerate(ordered)`) with weighted distribution across candidates. When paired with health check routing, this means traffic is distributed rather than sent 100% to the first healthy leg — directly addresses the SOLE-LEG GUARD case (199 sole-leg hits in one log window) by keeping traffic spread across multiple healthy legs. **Does NOT replace `forwarder.py:457-469` `is_sole_leg` guard — that guard prevents orphaning when a pool's last leg is drained; it is a pre-flight safety check, not a traffic distribution mechanism.** |

---

## Summary

| Verdict | Count | Notes |
|---|---|---|
| **ADOPT** | 28 | Includes 6 already passed in `make_router()` |
| **DECLINE** | 14 | Irrelevant to Router-as-library (7), conflicts with Charon policy (5), or duplicates existing behaviour (2) |
| **DEFER** | 10 | Blocked on Redis adoption (5), pending tickets (2), or gated on new Charon features (3) |

### ADOPT params with money-path implications

These six ADOPT verdicts touch billing/spend and must be flagged for RED/GREEN/dogfood at
implementation time (following D025 no-double-bill):

1. `cache_responses` + `cache_kwargs` — cached responses never reach the cost callback; verify
   that the cost of a cached response is correctly accounted (or intentionally $0).
2. `provider_budget_config` — replaces BalanceTracker tracking/threshold; must not regress
   `funding_class` ordering, `park`/`unpark` lifecycle, or `is_drained` accuracy.
3. `routing_strategy` — cost-based routing must match Charon's own cost computation (ADR-0020
   verify-only cross-check applies).
4. `routing_strategy_args` — TTL must not cause stale-cost routing (failed-deploy risk).
5. `alerting_config` — budget-exhaustion alert must fire BEFORE a spend cap breach, not after.

### Charon policy preserved (NOT surrendered)

These are genuine Charon differentiators that litellm does not model. They are preserved as
pre-/post-processing around the Router, never replaced:

- **Free-tier per-provider windows** (funding class `free-daily` / `expiring`) — litellm has no
  concept of provider-specific free-tier quotas that replenish daily. Preserved via
  `order_chain_by_funding_class` pre-ordering in `forwarder.py:424-487`.
- **Funding-class ordering** (free-daily → expiring → prepaid → metered → premium) — litellm's
  `routing_strategy="cost-based-routing"` does not model funding class tiers. Preserved as
  pre-ordering in `forwarder.py:430-441`.
- **Capability-based route exclusion** (R3 `CapabilityMatrix`) — litellm tag filtering is
  category-based, not per-provider deny rules for known-incapable providers. The `CapabilityMatrix`
  at `routing_policy/matrix.py:44-53` (provider deny table) is preserved as a pre-filter that
  synthesizes deployment tags.
- **Drain-then-park + sole-leg guard** — litellm budget config stops routing to a drained
  provider but does not model the park/unpark lifecycle (disk persistence, manual re-arm) or the
  sole-leg guard (never orphan a pool when every leg is drained). Preserved in
  `forwarder.py:424-487` + `balance.py:407-444`.
- **Silent downgrade detection** (SR-1/SR-2, `forwarder.py:788-806,837-884`) — litellm does not
  detect when the Router serves a different model than requested. Preserved as
  `complete_via_router_guarded` in `litellm_plane/litellm_router.py:301-341`.

## Consequences

**If accepted:** the ADOPT-MAP grows from first-slice parity to a full capability set. The
decision register makes the implementation backlog explicit: 22 ADOPT verdicts are un-scheduled
(after removing the 6 already passed) and can be claimed individually or in coherent groups.
No implementation is safe until `GW-CUTOVER-LIVE-WIRE` lands (Router on live path), but the
design is ready.

**Gates:** `tests/test_litellm_capability_map.py` asserts this ADR's param list matches the
INSTALLED `Router.__init__` signature. When litellm is upgraded and gains/loses params, the
test goes RED — forcing a re-disposition. This prevents silent drift.

**Implementation sequencing:** ADOPT verdicts are grouped by dependency:

1. **Group A (no dependencies):** `routing_strategy` + `routing_strategy_args`, `timeout`,
   `stream_timeout`, `max_fallbacks`, `fallbacks`, `default_fallbacks`,
   `context_window_fallbacks`, `retry_policy`, `model_group_retry_policy`,
   `enable_weighted_failover`, `enable_tag_filtering` + `tag_filtering_match_any`.
2. **Group B (money-path, needs RED/GREEN/dogfood):** `cache_responses` + `cache_kwargs`,
   `provider_budget_config`.
3. **Group C (additive, no Charon deletion):** `enable_health_check_routing`,
   `health_check_staleness_threshold`, `health_check_ignore_transient_errors`,
   `alerting_config`.
4. **Group D (DEFER triggers met):** `enable_pre_call_checks` (after LITELLM-ORDER-PRECALL),
   Redis params (after Redis adoption), deferred params (after feature triggers).

All groups are sequenced AFTER `GW-CUTOVER-LIVE-WIRE`. No ADOPT verdict is implemented before
the Router is on the live path.
