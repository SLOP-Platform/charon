# WIRING-AUDIT-MATRIX: Built-But-Inert Feature Sweep

**Ticket:** R43-WIRING-AUDIT
**Date:** 2026-07-12
**Scope:** `charon` gateway data-plane (`src/charon/`) — all `_module_inst` entries + explicit balance/cost wiring.
**Method:** Trace each built capability from construction through `_handle()` → `forward_with_failover()`. Every WIRED verdict carries a reachable call-site citation. Every INERT verdict carries a confirmed 0-caller citation.

---

## Module Wiring Matrix

| # | Feature | Defining file:line | Constructed? | INVOKED on a real request path? | Verdict | Evidence (path:line) |
|---|---|---|---|---|---|---|
| 1 | **SemanticCache** (`.get` / `.set`) | `cache.py:23` | `gateway.py:253-254` via `_module_inst("cache")` | YES — `.get()` on cache-lookup path; `.set()` on post-200 path | **WIRED** | `.get()` at `forwarder.py:361`; `.set()` at `forwarder.py:546` (non-stream) / `forwarder.py:646` (stream) |
| 2 | **Guardrails** (`.scan_request`) | `guardrails.py:44` | `gateway.py:258-260` via `_module_inst("guardrails")` | YES — invoked pre-forward for every data-plane request | **WIRED** | `.scan_request()` at `forwarder.py:348` |
| 3 | **QualityScorer** (`.score` / `.record`) | `quality_scorer.py:25` | `gateway.py:264-266` via `_module_inst("quality")` | YES — `.score()` pre-forward; `.record()` post-200 | **WIRED** | `.score()` at `forwarder.py:402`; `.record()` at `forwarder.py:552` |
| 4 | **SpendLimiter** (`.check` / `.record`) | `spend_limits.py:22` | `gateway.py:267-271` via `_module_inst("spend")` | YES — `.check()` pre-forward; `.record()` post-200 writes `spend.json` to disk | **WIRED** | `.check()` at `forwarder.py:337`; `.record()` at `forwarder.py:555` (non-stream) / `forwarder.py:649` (stream) |
| 5 | **ResponseNormalizer** (`.normalize`) | `response_normalizer.py:30` | `gateway.py:255-257` via `_module_inst("normalizer")` | YES — invoked per served 200 | **WIRED** | Via `_normalize_message_content()` helper at `forwarder.py:539` → calls `normalizer.normalize()` |
| 6 | **PolicyRouter** (`.resolve`) | `policy_router.py:28` | `gateway.py:294-296` via `_module_inst("policy")` | YES — invoked in `chain_for()` when model starts with `policy/` | **WIRED** | `.resolve()` at `proxy_server.py:625-628` (called from `forwarder.py:225`) |
| 7 | **GatewayProxy.record** — per-(model,provider) cost meter | `proxy.py:448-493` | `proxy_server.py:560` (stored as `self.observer`) | YES — `provider=route.label` passed on EVERY served 200 | **WIRED** | Forwarder call sites — all pass `provider=route.label`: `forwarder.py:431-432` (unreachable), `forwarder.py:452-453` (non-200), `forwarder.py:527-529` (downgrade failover), `forwarder.py:533-535` (served non-stream), `forwarder.py:605-607` (streaming failover), `forwarder.py:635-636` (served stream). Meter data feeds cost-rank routing at `forwarder.py:382-396`. ADR/docstring at `proxy.py:462-465` and `proxy.py:524-528` claiming "Wave-2 deferred" is **STALE**: the meter IS wired under real traffic. |
| 8 | **BalanceTracker** — drain routing API (`.funding_class` `.remaining` `.is_parked` `.is_drained` `.should_drain` `.park` `.unpark`) | `balance.py:120-280` | `gateway.py:216-229` via `_build_balance_tracker()` — returns `None` when no provider has `funding_class`/`mode` | YES — routing methods ARE invoked when `bt is not None`. `record_spend` behind same guard. | **PARTIALLY WIRED** | Drain-routing calls at `forwarder.py:279-323`. `record_spend()` at `forwarder.py:557` (non-stream 200) / `forwarder.py:651` (stream 200) — guarded by `if srv.balance_tracker is not None` which is currently `None` in production. |
| 9 | **RequestInspector** (`.inspect`) | `request_inspector.py:7` | `gateway.py:272-274` via `_module_inst("inspector")` | NO — `.inspect()` has zero call sites in `src/charon/` | **INERT** | `grep -r '\.inspect(' src/charon/` → 0 results (excluding test files). Stored at `proxy_server.py:560`, never consumed. |
| 10 | **SessionAffinity** (`.pin` `.resolve` `.clear` `.touch` `.cleanup`) | `session_affinity.py:15` | `gateway.py:275-277` via `_module_inst("session_affinity")` | NO — zero call sites for any method in `src/charon/` | **INERT** | `grep -r '\.(pin|clear|touch|cleanup)(' src/charon/` → 0 results (excluding `Path.resolve()`). Stored at `proxy_server.py:563`, never consumed. |
| 11 | **Observability** (`.export` `.get_metrics`) | `observability.py:19` | `gateway.py:261-263` via `_module_inst("observability")` | NO — zero call sites in `src/charon/` | **INERT** | `grep -r '\.export(' src/charon/` → 0 results; `grep -r '\.get_metrics(' src/charon/` → 0 results. Stored at `proxy_server.py:559`, never consumed. |
| 12 | **SpeculativeExecutor** (`.execute`) | `speculative_execution.py:35` | `gateway.py:278-283` via `_module_inst("speculative")` — returns `None` unless `{"enabled": true}` in config | NO — `.execute()` has zero call sites in `src/charon/` | **INERT** | `grep -r 'speculative_executor\.' src/charon/` → 0 results (only assignment at `proxy_server.py:564`). SR-4 confirmed: constructed, stored, never invoked. |
| 13 | **ConsensusRouter** (`.verify`) | `consensus.py:21` | `gateway.py:284-290` via `_module_inst("consensus")` — returns `None` unless `{"enabled": true}` in config | NO — `.verify()` has zero call sites in `src/charon/` | **INERT** | `grep -r 'consensus_router\.' src/charon/` → 0 results (only assignment at `proxy_server.py:565`). SR-4 confirmed: constructed, stored, never invoked. |
| 14 | **VirtualKeyManager** (`.create` `.resolve` `.revoke` `.list_keys`) | `virtual_keys.py:40` | `gateway.py:291-293` via `_module_inst("vkeys")` | NO — zero call sites in `src/charon/` | **INERT** | `grep -r 'virtual_key_manager\.' src/charon/` → 0 results (only assignment at `proxy_server.py:566`). Stored, never consumed. |

---

## Per-Request Invocation Frequency

### WIRED — invoked on every data-plane call
- SemanticCache (lookup + store)
- Guardrails (scan)
- QualityScorer (score + record)
- SpendLimiter (check + record + disk persist)
- ResponseNormalizer (normalize)
- GatewayProxy.record (per-(model,provider) meter, with `provider=route.label`)
- PolicyRouter.resolve (only when model id starts with `"policy/"`)

### WIRED conditionally — invoked when configured
- BalanceTracker drain-routing API (when providers carry `funding_class` + `mode`)

### INERT — never invoked in production
- RequestInspector
- SessionAffinity
- Observability
- SpeculativeExecutor
- ConsensusRouter
- VirtualKeyManager

---

## INERT-to-WIRED Wiring Map

Each INERT module needs ONE wiring intervention to become live on the request path:

| INERT Module | One wiring change to make it live | Downstream owner |
|---|---|---|
| **RequestInspector** | Insert `srv.request_inspector.inspect(req)` pre-forward alongside guardrails scan at `forwarder.py:346-356` | R44 (dogfood-gate) |
| **SessionAffinity** | Insert `srv.session_affinity.pin(session_id, route.label) + .resolve(session_id)` around route selection/caching in `forward_with_failover()` | R44 (dogfood-gate) |
| **Observability** | Wire `.export()` to an HTTP metrics endpoint in `console_router.py` or a periodic flush from `proxy_server.py` background thread | R44 (dogfood-gate) |
| **SpeculativeExecutor** | Insert `srv.speculative_executor.execute()` in the R2 cost-rank reorder path (`forwarder.py:375-396`) — fan-out N cheapest providers, return first 200 | R45 (inert-startup-check) |
| **ConsensusRouter** | Insert `srv.consensus_router.verify(responses)` as a quality gate after speculative fan-out completes — serve only when ≥N responses agree above similarity | R45 (inert-startup-check) |
| **VirtualKeyManager** | Wire `.resolve(api_key)` as virtual-key → real-key translation in auth path (`proxy_server.py:402`); add console routes for `.create()`, `.revoke()`, `.list_keys()` | R44 (dogfood-gate) |
| **BalanceTracker.record_spend** (fully wire) | Add `funding_class` + `mode` to one provider entry in production `providers.json`. Construction chain (`gateway.py:216-229`) and call sites (`forwarder.py:557,651`) already ready; the `None` guard resolves to a live `BalanceTracker` | R46 (balance-wire) |

---

## Key Architectural Notes

1. **Meter is LIVE despite stale docstrings.** The per-(model,provider) cost meter (`GatewayProxy.record()` at `proxy.py:448-493`) receives `provider=route.label` on every served 200 (`forwarder.py:533-535`, `635-636`). Comments at `proxy.py:462-465` and `proxy.py:524-528` saying "Wave-2 deferred" are **STALE** — the forwarder already passes `provider=route.label` at all six call sites. This meter feeds `all_model_provider_costs()` which is read by cost-rank routing (`forwarder.py:382-396`). The meter IS wired end-to-end under real traffic.

2. **SpeculativeExecutor + ConsensusRouter are SR-4-confirmed constructed-but-never-invoked.** Both require explicit `{"enabled": true}` config, but even when non-None they have zero call sites. Exhaustive trace: `_handle()` (`proxy_server.py:374-451`) → `forward_with_failover()` (`forwarder.py:197-660`) references neither.

3. **BalanceTracker is dual-entity.** Drain-routing API (funding_class, remaining, parked, drained, should_drain, park, unpark at `forwarder.py:279-323`) IS wired when providers have balance config. But `record_spend()` (per-provider budget ledger at `forwarder.py:557,651`) is behind the same `None` guard — currently inert in production. The proxy meter (`GatewayProxy.record()`) runs in parallel and already records all spend from the same forwarder call sites.

4. **6 of 13 `_module_inst` modules are INERT** (Rows 9-14). All are identically constructed, stored on `GatewayProxyServer`, and sit as dead instance fields. The `_module_inst` ladder at `gateway.py:200-211` treats them no differently from their WIRED peers — the gap is entirely in `forward_with_failover()` not reaching for them.

5. **Cost-ledger landscape (summary):**
   - `GatewayProxy._model_provider_cost` (in-memory, `proxy.py:478-481`): **WIRED**, written every 200 with `provider=route.label`
   - `BalanceTracker._model_spend` (in-memory, `balance.py:311-314`): **INERT**, written only if `bt is not None` (never in production)
   - `SpendLimiter._spent_usd` (persisted `spend.json`, `spend_limits.py:75-91`): **WIRED**, `record()` on every 200
   - `CoordinatorLedger` (per-task checkpoint, `coordinator.py:163-184`): **WIRED**, agent-plane only (not gateway)
