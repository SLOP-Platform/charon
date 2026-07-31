# ADOPT-MAP — `litellm.Router` (as a library) for the gateway commodity plane

**Branch:** `design/litellm-capability-adoption` · **ADR:** 0017 (§Build-vs-Adopt) + 0021
(§Capability Disposition) · **Governing rule:** MANAGER-OPERATING-RULES §0 ADOPT-FIRST ·
**Installed litellm:** `1.93.0` (verified via `pip show litellm`)

## What is being adopted, and how

`litellm.Router` is imported **as a library** — NOT its proxy-server / FastAPI / Prisma /
Redis deployment. Its `__init__` exposes 52 parameters (excluding `self`), of which 6 are
currently wired in `make_router()`. This document maps Charon hand-rolled behaviour onto
Router capabilities and records the disposition of every parameter.

## Current wiring (first slice — default-OFF parity)

`src/charon/litellm_plane/litellm_router.py:363-369` (`make_router`):

| Router param | Charon source | Replaces |
|---|---|---|
| `model_list` | `build_model_list(chains)` | `forwarder.py:565` chain iteration |
| `cooldown_time` | `server.default_cooldown` (60.0) | `proxy_server.py:716-727` `set_cooldown` |
| `allowed_fails` | `DEFAULT_ALLOWED_FAILS = 3` | `proxy_server.py:651-677` cooldown threshold |
| `num_retries` | `DEFAULT_NUM_RETRIES = 1` | `forwarder.py:611-663` retry-once |
| `retry_after` | `int(cooldown)` | `proxy_server.py:686-699` `retry_after_hint` |
| `set_verbose` | `False` | (harmless, enables litellm debug logging) |

## Full capability disposition (ADR-0021)

52 parameters, 3 verdicts. See `docs/adr/0021-litellm-capability-adoption.md` for the
complete register with rationale. Summary:

| Verdict | Count | Notes |
|---|---|---|
| **ADOPT** | 28 | Includes 6 already passed. 22 un-scheduled, claimable individually. |
| **DECLINE** | 14 | Proxy-server concerns (7), Charon policy conflicts (5), or duplicates (2) |
| **DEFER** | 10 | Redis (5), pending tickets (2), new Charon features (3) |

### ADOPT: Charon code to delete (by file:line)

| Router param | Charon code deleted | LOC impact |
|---|---|---|
| `model_list` | `forwarder.py:565` chain iteration (`for i, route in enumerate(ordered)`) | ~370 |
| `num_retries` | `forwarder.py:611-663` retry-once transient | ~53 |
| `max_fallbacks` | `forwarder.py:565` implicit iteration cap (no max → configurable) | — |
| `timeout` | `forwarder.py:582,633` `srv.fwd_timeout` + `netutil.py:313` | — |
| `stream_timeout` | `forwarder.py:43` `_STREAM_HEAD_CAP` + `forwarder.py:890-903` streaming relay | ~14 |
| `default_fallbacks` | `proxy_server.py:257-263` `chain_for` fallback logic | — |
| `fallbacks` | `routing_policy/__init__.py:144-208` `build_routes_and_pools` pool compilation | ~65 |
| `context_window_fallbacks` | `forwarder.py:400-422` R7 max_context eligibility | ~23 |
| `enable_tag_filtering` + `tag_filtering_match_any` | `forwarder.py:384-398` R3 capability exclusion + `routing_policy/matrix.py:44-115` `CapabilityMatrix` | ~95 |
| `retry_after` | `proxy_server.py:686-699` `retry_after_hint` | ~14 |
| `retry_policy` + `model_group_retry_policy` | `forwarder.py:611-663` retry-once + `proxy.py:42-56` `_TRANSIENT_BILLING_BODY_PATTERNS` + `failover_loop.py:58-100` | ~125 |
| `allowed_fails` | `proxy_server.py:651-677` `order_by_cooldown` threshold | ~27 |
| `cooldown_time` | `proxy_server.py:716-727` `set_cooldown` + `proxy_server.py:593-594` `_cooldown` dict/lock | ~28 |
| `routing_strategy` + `routing_strategy_args` | `forwarder.py:530-551` R2 live-cost reorder + `routing_policy/cost_rank.py:64-93` `derived_cost_rank` + `routing_policy/__init__.py:297-318` `order_pool_by_live_cost` + `proxy_server.py:669-676` latency tiebreak + `latency.py:11-61` `RollingLatency` | ~165 |
| `provider_budget_config` | `balance.py:148-628` `BalanceTracker.remaining`/`should_drain`/`is_drained` tracking + `spend_limits.py:15-91` `SpendLimiter` | ~557 |
| `alerting_config` | `degrade_alert.py:35-133` `DegradeAlert` | ~99 |
| `cache_responses` + `cache_kwargs` | `cache.py:31-70` `SemanticCache` + `forwarder.py:514-526,818-821,917-920` cache check/set | ~99 |
| `enable_weighted_failover` | `forwarder.py:565` linear failover iteration (replaced with weighted distribution) | — |
| `enable_health_check_routing` + `health_check_*` | Additive — no Charon code deleted. Complements reactive cooldown with proactive probing. | — |

**Total LOC on path to delete after full adoption:** ~1,650 LOC (exceeds ADR-0017's initial
~650–750 estimate because the full adoption goes beyond the first-slice commodity plane into
budget tracking, caching, alerting, and retry policy).

### ADOPT: capabilities preserved via pre-/post-processing

These are NOT replaced by Router — they are Charon policy that runs as pre-filters or
post-processing around the Router:

1. **Free-tier per-provider windows** — `forwarder.py:424-487` drain-then-park + funding-class ordering. litellm has no concept of per-provider free-tier quotas that replenish daily.
2. **Funding-class ordering** — `routing_policy/__init__.py:220-296` `order_chain_by_funding_class`. litellm's `routing_strategy="cost-based-routing"` does not model funding tiers.
3. **CapabilityMatrix deny rules** — `routing_policy/matrix.py:44-53`. Per-provider known-incapable rules that litellm tag filtering can't express (provider X is known-incapable for capability Y).
4. **Drain-then-park lifecycle** — `balance.py:407-444` `park`/`unpark` with disk persistence + manual re-arm. litellm budget auto-cooldown lacks park/unpark lifecycle.
5. **Sole-leg guard** — `forwarder.py:457-469`. Never orphan a pool when every leg is drained. litellm's `provider_budget_config` does not model pool-level sole-leg safety.
6. **Silent downgrade detection** — `forwarder.py:788-806,837-884` SR-1/SR-2. litellm does not detect model substitution. Preserved as `complete_via_router_guarded` (`litellm_router.py:301-341`).

## HARD-PRESERVE controls, and where they live under litellm

The money-path is **not clean commodity** — it is fused with security + Charon policy. These
controls are preserved at `model_list` build time and re-proved (fail-on-revert tests in
`tests/test_litellm_router_adopt.py` + `tests/test_litellm_router_e2e.py`):

1. **base-bound provider key (#181, `secrets.get_provider_key`).** litellm sends `api_key`
   to `api_base` 1:1. The adapter resolves each route's key via
   `get_provider_key(provider, base_url=route.upstream_base)` (base-bound) and attaches it
   ONLY to that route's own `api_base`; a moved base resolves **no key**.
2. **SSRF / non-routable refusal (`netutil.validate_base_url`).** Link-local / cloud-metadata
   / non-http bases raise before entering the `model_list`.
3. **Preset-derived egress allowlist (`egress.assert_base_allowed`) — the egress.py
   reconciliation.** The `litellm_plane` outbound path is a NEW way to reach providers, so it
   enforces the SAME fail-CLOSED allowlist the live path enforces at
   `routing_policy.route_from_spec`: the EFFECTIVE base (the exact value written into the
   nested `litellm_params['api_base']` litellm actually dials — the LiteLLM CVE-2024-6587
   lesson) must be a git-tracked preset external host or a local host, else the route is
   REFUSED (`EgressPolicyError`).
4. **No-redirect.** `httpx` (litellm's transport) does not follow redirects by default;
   `no_redirect_client()` pins `follow_redirects=False`.
5. **SG-never-Anthropic (`providers.is_anthropic_route`).** Every candidate is screened; an
   Anthropic model/provider/base is dropped from the `model_list` (never selectable).
6. **drain-then-park + funding-class ordering.** Preserved as a PRE-ordering
   (`routing_policy.order_chain_by_funding_class` + parked-provider exclusion).

## Slice boundary — what this branch delivers vs defers

**THIS BRANCH (design/litellm-capability-adoption) — DESIGN PASS ONLY, no code changes to `src/`:**

- `docs/adr/0021-litellm-capability-adoption.md` — full 52-param disposition table with every
  verdict grounded.
- `ADOPT-MAP.md` — updated with complete file:line deletion map and LOC impact.
- `tests/test_litellm_capability_map.py` — asserts the ADR's param list matches the INSTALLED
  `Router.__init__` signature, preventing silent drift on litellm upgrade.

**FIRST SLICE (feat/gateway-litellm-adopt — already landed):**

- `litellm` in `pyproject.toml` as the optional extra `router`.
- `src/charon/litellm_plane/` — the config→Router mapping with controls 1–6 enforced.
- fail-on-revert preservation tests + e2e + dogfood.

**DEFERRED to the next slice (documented, NOT silently dropped):**

- **The wire-in**: replacing `forwarder.forward_with_failover` / stdlib `http.server` so Router
  serves live traffic. Owned by `GW-CUTOVER-LIVE-WIRE`.
- **Free-tier quota (parked FT-WIRE-QUOTA):** unchanged — preserved via the funding-class
  pre-ordering; litellm does not model per-provider free-tier windows.
- **All 22 un-scheduled ADOPT verdicts** — claimed individually or in coherent groups
  (see ADR-0021 §"Implementation sequencing").

## Files / LOC this adopt is on a path to DELETE

- `forwarder.py` (934 LOC) — failover loop, retry-once, live-cost reorder, capability
  exclusion, drain-then-park, max_context eligibility. **KEEP (novel/policy):** silent-downgrade
  detection (SR-1/SR-2, `:788`/`:878`), drain-then-park + funding-class + sole-leg (`:424`–`:487`),
  streaming-head downgrade detection (`:837`).
- `proxy_server.py` cooldown machinery — `order_by_cooldown:651`, `set_cooldown:716`,
  `retry_after_hint:686`, `_cooldown`/`_cooldown_lock`.
- `routing_policy/cost_rank.py:64-93` `derived_cost_rank` mechanical sort — **KEEP**
  `cost_class_priority` (`:51-62`) for funding-class pre-ordering.
- `routing_policy/__init__.py:297-318` `order_pool_by_live_cost` — **KEEP**
  `order_chain_by_funding_class` (`:220-296`).
- `routing_policy/matrix.py:44-115` `CapabilityMatrix` — maps to deployment tags; static deny
  rules kept as tag synthesis.
- `cache.py:31-70` `SemanticCache` — replaced by `cache_responses`.
- `latency.py:11-61` `RollingLatency` — replaced by `routing_strategy="latency-based-routing"`.
- `balance.py:148-628` tracking logic — `remaining`, `should_drain`, `is_drained` replaced by
  `provider_budget_config`. **KEEP** `park`/`unpark` lifecycle (`:407-444`) + `funding_class`
  (`:394-403`) + `top_up` (`:584-600`).
- `spend_limits.py:15-91` `SpendLimiter` — replaced by `provider_budget_config`.
- `degrade_alert.py:35-133` `DegradeAlert` — replaced by `alerting_config`.
- `failover_loop.py:58-100` `invoke_with_failover` — replaced by `retry_policy`.
- `netutil.py` — most of the file deleted (httpx does not follow redirects by default).
