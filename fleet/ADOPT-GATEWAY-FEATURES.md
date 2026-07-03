# ADOPT-GATEWAY-FEATURES — Competitive Feature Adoption Plan

**Date:** 2026-07-02
**Trigger:** Competitive evaluation of LiteLLM, OpenRouter, Together AI, Requesty.ai, Kong vs Charon
**Pre-read:** `EVAL-RelayFreeLLM.md` for template; `BRIDGE-IMPROVEMENT-PLAN.md` for session-bridge context
**State:** Together AI already in `providers.py:67` — **zero work needed**

---

## Master Ticket Class

```
ID:        ADOPT-GATEWAY-FEATURES
Type:      Build (metaticket — owns the plan, sub-tickets own the code)
Goal:      Adopt Tier 1-3 competitive features from the 5 evaluated projects
Wave 0:    11 parallel infrastructure modules (0 file conflicts)
Wave 1:    3 gateway wiring tickets (gateway.py + proxy_server.py + cli.py)
Wave 2:    4 observability/guardrail/CLI tickets
Wave 3:    5 advanced-feature tickets
```

## File Collision Map (bottleneck analysis)

The critical shared file is `proxy_server.py` — touched by nearly every feature.
**Strategy:** each feature ships as a self-contained module (own file + own tests)
first, then integrates via targeted wiring tickets. Modules are importable,
unit-testable, and gate-green independently BEFORE any proxy_server.py touch.

| File | Touched by | Risk |
|---|---|---|
| `proxy_server.py` | Rate, cache, inspect, spend, lb, norm, guard, session, speculative, consensus, quality, observe | **BOTTLENECK** — 1 ticket/wave |
| `gateway.py` | Loadbal, inspect, quality, policy, session | Medium — 1-2 tickets/wave |
| `config.py` | Spend, vkeys, policy, all module config | Medium — 1 ticket W0 + later |
| `cli.py` | Cache, spend, guard, vkeys, observe, quality | Medium — progressive addition |
| `types.py` | Almost everything (new type defs) | Once in Wave 0 only |
| `providers.py` | Together AI — **ALREADY DONE** | Zero risk |

---

## Architecture: Clean Interfaces

Every new module exports a **single class** with a narrow interface:

```
# rate_limiter.py
class RateLimiter:
    def check(self, provider_label: str, tokens_est: int) -> RateLimitDecision: ...
    def record(self, provider_label: str, tokens_used: int, status: int): ...

# cache.py
class SemanticCache:
    def get(self, prompt_hash: str) -> CachedResponse | None: ...
    def set(self, prompt_hash: str, response: bytes, headers: dict, ttl: float): ...
    def stats(self) -> CacheStats: ...

# request_inspector.py
class RequestInspector:
    @staticmethod
    def inspect(messages: list[dict]) -> RequestHints: ...

# spend_limits.py
class SpendLimiter:
    def check(self, estimated_cost: float) -> SpendDecision: ...
    def record(self, cost: float): ...
    def remaining(self) -> float: ...

# load_balancer.py
class LoadBalancer:
    def select(self, routes: list[UpstreamRoute], strategy: Strategy,
               stats: dict[str, ProviderStats]) -> list[UpstreamRoute]: ...
    # Strategies: COST_FIRST, WEIGHTED, LATENCY, LEAST_BUSY, USAGE_BASED

# response_normalizer.py
class ResponseNormalizer:
    @staticmethod
    def normalize(content: str, mode: NormalizeMode) -> str: ...

# guardrails.py
class Guardrails:
    def scan_request(self, messages: list[dict]) -> list[GuardrailViolation]: ...
    def scan_response(self, content: str) -> list[GuardrailViolation]: ...

# quality_scorer.py
class QualityScorer:
    def record(self, provider: str, latency_ms: int, success: bool, tokens: int): ...
    def score(self, provider: str) -> float: ...

# observability.py
class Observability:
    def export(self, event: ObsEvent, targets: list[ObsTarget]): ...

# virtual_keys.py
class VirtualKeyManager:
    def create(self, label: str, permissions: KeyPermissions) -> VirtualKey: ...
    def resolve(self, key: str) -> KeyPermissions | None: ...

# policy_router.py
class PolicyRouter:
    def resolve(self, policy_name: str, routes: dict, pools: dict) -> list[UpstreamRoute]: ...

# speculative_execution.py
class SpeculativeExecutor:
    def execute(self, routes: list[UpstreamRoute], body: bytes,
                count: int) -> SpecResult: ...

# consensus.py
class ConsensusRouter:
    def verify(self, routes: list[UpstreamRoute], body: bytes,
               count: int) -> ConsensusResult: ...

# session_affinity.py
class SessionAffinity:
    def pin(self, session_id: str, provider: str): ...
    def resolve(self, session_id: str) -> str | None: ...
```

---

## Wave 0 — Infrastructure Modules (11 tickets, FULLY PARALLEL)

Each ticket creates 1 new file + 1 test file. Zero proxy_server.py/gateway.py
touch. All 11 can run in parallel from a single branch.

### T0.1 — ADOPT-TYPES

- **Owns:** `src/charon/types.py`, `tests/test_types.py`
- **Adds:** `RateLimitWindow`, `RateLimitDecision`, `CachedResponse`, `CacheStats`,
  `RequestHints`, `SpendDecision`, `LoadBalanceStrategy` (enum), `GuardrailViolation`,
  `QualityScore`, `ObsEvent`, `ObsTarget` (enum), `PolicyRoute`, `VirtualKey`,
  `KeyPermissions`, `SpecResult`, `ConsensusResult`
- **Accept:** All types round-trip JSON-serializable, mypy clean, tests pass

### T0.2 — ADOPT-RATELIMIT

- **Owns:** `src/charon/rate_limiter.py`, `tests/test_rate_limiter.py`
- **What:** 7-dimension sliding-window tracker (per sec/min/hr/day, reqs + tokens)
- **Accept:** `check()` returns allowed=False when limits exhausted, `record()` updates
  correctly, window expiry works, thread-safe, 100% coverage on window logic
- **Deps:** T0.1

### T0.3 — ADOPT-CACHE

- **Owns:** `src/charon/cache.py`, `tests/test_cache.py`
- **What:** In-memory LRU response cache keyed by SHA-256(prompt+model+temperature)
- **Accept:** get/set/stats work, TTL expiry, LRU eviction, thread-safe, cache bypass
  on exact-match collisions, 100% coverage
- **Deps:** T0.1

### T0.4 — ADOPT-INSPECT

- **Owns:** `src/charon/request_inspector.py`, `tests/test_request_inspector.py`
- **What:** Walk chat messages → `RequestHints(has_images, has_tools,
  estimated_tokens, preferred_context_window)`
- **Accept:** Detects image_url content parts, tool_calls/tools fields, char/4
  token estimate, vision/tool/context flags correct on 10+ test payloads
- **Deps:** T0.1

### T0.5 — ADOPT-SPEND

- **Owns:** `src/charon/spend_limits.py`, `tests/test_spend_limits.py`
- **What:** Cumulative cost tracker. `check(estimated_cost)` → ok|denied.
  `record(cost)` updates. Persists to `~/.charon/spend.json` (atomic write).
  Supports monthly reset window.
- **Accept:** Spend cap enforced, record accumulates, monthly reset, persistence
  survives restart, atomic write verified, 100% coverage
- **Deps:** T0.1

### T0.6 — ADOPT-LOADBAL

- **Owns:** `src/charon/load_balancer.py`, `tests/test_load_balancer.py`
- **What:** Pluggable routing strategies: COST_FIRST, WEIGHTED, LATENCY, LEAST_BUSY,
  USAGE_BASED. Takes ordered route list + strategy + stats → reordered list.
- **Accept:** All 5 strategies produce correct ordering, WEIGHTED normalizes correctly,
  COST_FIRST matches current behavior, default strategy = COST_FIRST, 100% coverage
- **Deps:** T0.1, T0.2 (USAGE_BASED reads RateLimiter state)

### T0.7 — ADOPT-NORM

- **Owns:** `src/charon/response_normalizer.py`, `tests/test_response_normalizer.py`
- **What:** Post-response text cleanup. Modes: STRIP_BOILERPLATE, FIX_JSON,
  STANDARDIZE_MD, NONE (default). Operates on `choices[0].message.content`.
- **Accept:** Strips known boilerplate patterns, fixes common JSON errors (trailing
  commas, missing brackets), normalizes markdown, NONE passthrough, 100% coverage
- **Deps:** T0.1

### T0.8 — ADOPT-GUARD

- **Owns:** `src/charon/guardrails.py`, `tests/test_guardrails.py`
- **What:** Pre-flight request scanner. Checks PII patterns (email, SSN, CC-Luhn,
  phone, API key regex). Secret redaction mode. Banned keyword deny-list. Returns
  `list[GuardrailViolation]` with WARN/BLOCK severity.
- **Accept:** Detects PII correctly (false-positive rate <0.1%), Luhn validation,
  redact mode replaces secrets, keyword blocking, config-driven, 100% coverage
- **Deps:** T0.1

### T0.9 — ADOPT-QUALITY

- **Owns:** `src/charon/quality_scorer.py`, `tests/test_quality_scorer.py`
- **What:** Per-provider latency EWMA (a=0.2) + rolling success rate (last 100).
  `score()` → quality-per-dollar metric. Persists to `~/.charon/quality.json`.
- **Accept:** EWMA converges correctly, success rate rolling window works,
  quality-per-dollar computed correctly, persistence round-trips, 100% coverage
- **Deps:** T0.1

### T0.10 — ADOPT-OBSERVE

- **Owns:** `src/charon/observability.py`, `tests/test_observability.py`
- **What:** Event export pipeline. Targets: JSONL (extend failover.log), PROMETHEUS
  (/metrics endpoint, stdlib text format), WEBHOOK (HMAC-SHA256), LANGFUSE (raw HTTP).
  Event types: REQUEST_START, PROVIDER_ATTEMPT, FAILOVER, DOWNGRADE_DETECTED,
  REQUEST_COMPLETE, RATE_LIMITED, CACHE_HIT, CACHE_MISS.
- **Accept:** All 4 target types work, JSONL appends correctly, Prometheus format
  valid, webhook HMAC verifiable, Langfuse format matches their ingestion API,
  thread-safe, 100% coverage
- **Deps:** T0.1

### T0.11 — ADOPT-CONFIG-W0

- **Owns:** `src/charon/config.py`, `tests/test_config.py`
- **What:** Config loaders for all Wave 0 modules:
  `load_rate_limits()`, `load_cache_config()`, `load_spend_config()`,
  `load_loadbalancer_config()`, `load_normalizer_config()`,
  `load_guardrails_config()`, `load_observability_config()`, `load_quality_config()`
  All return safe defaults when config files absent (feature disabled).
- **Accept:** All loaders work, defaults correct, missing files handled gracefully,
  no behavior change without config, gate green
- **Deps:** T0.1

---

## Wave 1 — Gateway Wiring: Core Pipeline (3 tickets)

### T1.1 — ADOPT-WIRE-GATEWAY

- **Owns:** `src/charon/gateway.py`
- **What:** Integrate load balancer + request inspector into `GatewayConfig`:
  - Add `load_balancer: LoadBalancer | None`, `request_inspector: RequestInspector | None`
  - Add `load_balance_strategy: LoadBalanceStrategy = COST_FIRST`
  - Add `request_inspector_enabled: bool = False`
  - `load_config()` compiles instances from config
  - New method: `inspect_request(messages)` → `RequestHints | None`
  - `model_meta` filtering by hints (vision, context_window)
  - All new fields optional → no behavior change without config
- **Accept:** GatewayConfig carries new fields, load_config compiles correctly,
  inspect_request returns hints, model filtering by hints works, backward compat,
  gate green
- **Deps:** T0.4, T0.6, T0.11

### T1.2 — ADOPT-WIRE-PROXY-P1

- **Owns:** `src/charon/proxy_server.py`
- **What:** Wire rate limiter + spend limiter + load balancer + request inspector
  into the proxy request handler. Integration points (execution order):
  1. **Pre-flight rate limit:** filter chain to routes where `rate_limiter.check().allowed`
  2. **Spend cap check:** 402 if `spend_limiter.check().allowed == False`
  3. **Request inspection:** filter routes by hints (vision, context, tools)
  4. **Load-balanced ordering:** use `load_balancer.select()` instead of raw cost-rank
  5. **Post-response recording:** `rate_limiter.record()` + `spend_limiter.record()`
  - `GatewayProxyServer.__init__` gains optional params: `rate_limiter`, `spend_limiter`,
    `load_balancer`, `request_inspector` — all default None
  - All new code gated: `if self.rate_limiter:` — zero behavior change without config
- **Accept:** All 5 integration points work, preemptive rate limiting saves upstream
  calls, spend cap returns 402, hints filter routes, load-balanced ordering correct,
  post-response recording accurate, backward compat (no config = no change), gate green
- **Deps:** T1.1, T0.2, T0.5, T0.6, T0.4

### T1.3 — ADOPT-WIRE-CLI-W1

- **Owns:** `src/charon/cli.py`, `tests/test_cli.py`
- **What:** CLI subcommands:
  - `charon cache stats` / `charon cache clear`
  - `charon limits show` / `charon limits set --monthly-spend N` / `--rpm model=N`
  - `charon balance` (alias for limits show)
  - `charon loadbal show` / `charon loadbal set --strategy latency`
  - All read/write through config.py methods from T0.11
- **Accept:** All subcommands work, config persistence round-trips, help text accurate,
  gate green
- **Deps:** T0.11, T0.3, T0.5

---

## Wave 2 — Observability & Safety Pipeline (4 tickets)

### T2.1 — ADOPT-WIRE-PROXY-P2

- **Owns:** `src/charon/proxy_server.py`
- **What:** Wire response normalization + semantic cache:
  1. **Cache check:** before routing, `cache.get(prompt_hash)`. HIT → serve
     immediately (skip failover). `X-Cache-Status: HIT`
  2. **Cache store:** after success, `cache.set()`. `X-Cache-Status: MISS`
  3. **Response normalization:** `normalizer.normalize(content, mode)` on
     `choices[0].message.content` and `choices[0].delta.content` (streaming)
  - Cache TTL from config (default 300s). Bypass on `Cache-Control: no-cache` or `?cache=false`
  - Normalization opt-in per model (default NONE)
  - `GatewayProxyServer.__init__` gains `cache` and `normalizer` params (default None)
- **Accept:** Cache hit skips upstream, cache miss stores, TTL expiry, bypass works,
  normalization transforms content correctly, streaming normalization works,
  backward compat, gate green
- **Deps:** T1.2, T0.3, T0.7

### T2.2 — ADOPT-WIRE-GUARD

- **Owns:** `src/charon/proxy_server.py`
- **What:** Wire guardrails:
  1. **Request scanning:** before routing, `violations = guardrails.scan_request(messages)`.
     BLOCK → 400. WARN → logged + proceed.
  2. **Response scanning:** after upstream, `guardrails.scan_response(content)`.
     BLOCK → 400 (response discarded). WARN → logged + proceed.
  3. **hide_secrets mode:** auto-redact in request messages BEFORE forwarding upstream
  - `GatewayProxyServer.__init__` gains `guardrails` param (default None)
- **Accept:** Request scan blocks on PII/keyword, response scan blocks on violations,
  redaction mode replaces secrets before upstream call, WARN logged to observability,
  backward compat, gate green
- **Deps:** T2.1, T0.8

### T2.3 — ADOPT-WIRE-OBSERVE

- **Owns:** `src/charon/proxy_server.py`
- **What:** Wire observability exports:
  - Emit events at 7 hook points: REQUEST_START, PROVIDER_ATTEMPT, FAILOVER,
    DOWNGRADE_DETECTED, RATE_LIMITED, CACHE_HIT/MISS, REQUEST_COMPLETE
  - JSONL target: extend existing failover.jsonl with all event types
  - Prometheus target: serve /metrics endpoint (stdlib text format, no deps)
  - Webhook target: POST with X-Charon-Signature HMAC
  - `GatewayProxyServer.__init__` gains `observability` param (default None)
- **Accept:** All 7 events fire at correct hook points, JSONL format consistent,
  Prometheus metrics increment correctly, webhook signature verifiable, backward
  compat, gate green
- **Deps:** T2.2, T0.10

### T2.4 — ADOPT-WIRE-CLI-W2

- **Owns:** `src/charon/cli.py`, `tests/test_cli.py`
- **What:** CLI extensions:
  - `charon guardrails show` / `add` / `remove`
  - `charon observability targets` / `add --target webhook --url URL --secret KEY`
  - `charon quality show` / `charon quality reset <provider>`
  - `charon norm show` / `charon norm set --model X --mode strip_boilerplate`
- **Accept:** All subcommands work, config persistence round-trips, gate green
- **Deps:** T2.3, T0.8, T0.9, T0.11

---

## Wave 3 — Advanced Features (5 tickets)

### T3.1 — ADOPT-SESSION-AFFINITY

- **Owns:** `src/charon/session_affinity.py`, `tests/test_session_affinity.py`,
  `src/charon/proxy_server.py`, `src/charon/gateway.py`
- **What:** X-Session-ID pinning for prompt cache optimization:
  - Client sends `X-Session-ID: <uuid>` → gateway pins to first healthy provider
  - TTL: 5 min idle. On failover, clear pin and re-route.
  - `X-Charon-Pinned: <provider>` response header
  - In-memory dict with RLock, periodic cleanup
- **Accept:** Sessions pin correctly, TTL expiry works, failover clears pin,
  cleanup removes expired, thread-safe, backward compat, gate green
- **Deps:** T2.3

### T3.2 — ADOPT-SPECULATIVE-EXECUTION

- **Owns:** `src/charon/speculative_execution.py`, `tests/test_speculative_execution.py`,
  `src/charon/proxy_server.py`
- **What:** Race N providers, return fastest, cancel rest:
  - `ThreadPoolExecutor` (stdlib) dispatches to N providers concurrently
  - First 200 response → return to client, cancel remaining threads
  - All fail → fall back to sequential failover
  - Config: `{enabled: false, max_providers: 3, timeout_ms: 30000}`
  - `X-Charon-Speculative: true` + `X-Charon-SpecWinner: <provider>` headers
  - Caution: Nx cost for speed. Opt-in per-request via `X-Charon-Speculative: true` header
- **Accept:** Fastest provider wins, cancels threads correctly, fallback on all-fail,
  timeout enforcement, cost tracking accounts for N upstream calls, backward compat, gate green
- **Deps:** T2.3

### T3.3 — ADOPT-CONSENSUS-ROUTING

- **Owns:** `src/charon/consensus.py`, `tests/test_consensus.py`,
  `src/charon/proxy_server.py`
- **What:** Cross-provider verification:
  - Client sends `X-Charon-Consensus: N` → send to N providers
  - Token-Jaccard similarity (>0.8) → "agreed" → return majority response
  - Disagreement → return all N responses with metadata
  - `X-Charon-Consensus: agreed|disagreed` + `X-Charon-Consensus-Models` headers
  - Opt-in per request. Config: `{enabled: true, default_count: 3, similarity: 0.8}`
- **Accept:** Agreement detection works, disagreement surfaces all answers,
  similarity threshold tunable, backward compat, gate green
- **Deps:** T2.3

### T3.4 — ADOPT-VIRTUAL-KEYS

- **Owns:** `src/charon/virtual_keys.py`, `tests/test_virtual_keys.py`,
  `src/charon/config.py`, `src/charon/proxy_server.py`, `src/charon/cli.py`
- **What:** Scoped API key management:
  - `VirtualKeyManager`: create/revoke/list keys with scoped permissions
  - Each key: label, key (32-char random), model allowlist, max_spend_monthly,
    max_rpm, max_tpm, guardrails_enabled, tags
  - Auth: `Authorization: Bearer ck-<key>` → resolved permissions
  - Master key (`CHARON_GATEWAY_TOKEN`) has full access
  - Enforcement points: model routing filter, per-key SpendLimiter/RateLimiter,
    guardrails toggle
  - Persist: `~/.charon/virtual_keys.json` (0600, atomic write)
  - CLI: `charon keys create|list|revoke|show`
- **Accept:** Key CRUD works, auth resolution correct, permissions enforced at all
  points, master key bypass, atomic persistence, backward compat (disabled by default), gate green
- **Deps:** Wave 2 complete

### T3.5 — ADOPT-POLICY-COMPOSITION

- **Owns:** `src/charon/policy_router.py`, `tests/test_policy_router.py`,
  `src/charon/config.py`, `src/charon/gateway.py`, `src/charon/cli.py`
- **What:** Composable routing policies (Requesty-inspired):
  - Policies: FALLBACK (ordered chain), LOAD_BALANCE (weighted), LATENCY (fastest-first)
  - Compose: `model="policy/fast-cheap"` → nesting
  - Config: `policies.json` — `{"fast-cheap": {"type": "load_balance", "members": [...]}}`
  - Resolve at request time → ordered `list[UpstreamRoute]`
  - `chain_for()` checks `policy/` prefix
  - CLI: `charon policy create|list|show`
  - Backward compat: non-`policy/` IDs use existing pools/tiers
- **Accept:** Policies compose correctly, resolution deterministic, nesting works,
  CLI CRUD round-trips, backward compat, gate green
- **Deps:** T1.1, T3.3

---

## Dependency Graph (ASCII)

```
                          WAVE 0 — 11 parallel
                          ===================
                    T0.1 (types) ◄── ALL others import
               ┌────────┼────────┬────────┬────────┐
              T0.2    T0.3    T0.4    T0.5    T0.6  ... T0.11
           (ratelim) (cache) (insp)  (spend) (loadbal)  (config)
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
          WAVE 1       WAVE 1        WAVE 1
          T1.1 ────▶  T1.2          T1.3
        (gateway)   (proxy-P1)      (CLI-W1)
                        │               │
            ┌───────────┼───────────┐   │
            ▼           ▼           ▼   │
          WAVE 2      WAVE 2      WAVE 2│
          T2.1 ──▶   T2.2 ──▶    T2.3  T2.4
        (proxy-P2)  (guard)    (observe)(CLI-W2)
            │           │           │
            └───────────┼───────────┘
                        │
            ┌───────┬───┼───┬───────┐
            ▼       ▼   │   ▼       ▼
          T3.1    T3.2  │ T3.3    T3.4 ─── T3.5
        (session)(spec) │(consen) (vkeys) (policy)

        LEGEND:
        ───▶ = sequential (same file touched)
        │    = parallel (different files)
```

**Parallelism summary:**

| Wave | Tickets | Parallel? | Why |
|---|---|---|---|
| 0 | 11 | **All 11 in parallel** | Each ticket owns a unique file |
| 1 | 3 | T1.3 parallel to T1.1+T1.2; T1.1→T1.2 sequential | CLI reads config, not proxy/gateway internals |
| 2 | 4 | T2.4 parallel to T2.1+T2.2+T2.3; T2.1→2.2→2.3 sequential | CLI reads config; proxy tickets share file |
| 3 | 5 | T3.1, T3.2, T3.3 in parallel; T3.4 sequential; T3.5 sequential | T3.1-T3.3 each own new module; T3.4 touches proxy+config+cli; T3.5 touches config+gate+cli |

---

## Critical Path (longest chain, determines total wall-clock time)

```
T0.1 → T0.6 → T1.1 → T1.2 → T2.1 → T2.2 → T2.3 → T3.4 → T3.5
  │      │      │      │      │      │      │      │      │
  └── Wave 0 ──┘      └─ Wave 1 ─┘  └─── Wave 2 ───┘  └ Wave 3 ┘
```

22 tickets total, 9 sequential on critical path, the other 13 run in parallel
within their waves.

---

## Gate Changes (what runs at each merge)

Every ticket checks: `PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py ; python3 tools/check_test_hygiene.py`

| Wave | Expected test count growth |
|---|---|
| W0 | +~150 tests (11 modules × ~14 tests avg) |
| W1 | +~40 tests (integration tests in existing test files) |
| W2 | +~35 tests (guard/observe/norm integration + CLI) |
| W3 | +~55 tests (adv modules + integration) |
| **Total** | **~280 new tests** added to the existing ~840 |

---

## No-Go Decisions (features explicitly excluded)

| Feature | Source | Why NOT adopt |
|---|---|---|
| Built-in chat UI | RelayFreeLLM | Charon is infrastructure, not a chat client. Zero-egress console is enough. |
| Provider-level prompt caching injection | Requesty, OpenRouter | Provider-specific cache control headers are brittle and provider-dependent |
| Fine-tuning pipeline | Together AI | Not a gateway concern. Operators use dedicated fine-tuning services |
| A2A gateway / MCP gateway | LiteLLM, Kong, Requesty | Separate problem domain. Could be a follow-on ticket if demand arises |
| Enterprise SSO/SAML/RBAC | LiteLLM, Kong, Requesty | Overkill for Charon's local-first posture. Virtual keys (T3.4) is the lightweight alternative |
| Gateway-level RAG pipeline | Kong | Massive dependency (vector DB). Far outside Charon's scope |
| LLM-as-judge eval framework | LiteLLM | Separate product. Charon's quality scorer (T0.9) is the lightweight alternative |
| Konnect SaaS / managed cloud | Kong | Charon is self-hosted. Non-negotiable |
| Credit system / billing | OpenRouter | Charon uses your own keys. No markup, no billing needed |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| proxy_server.py merge conflicts | High | Medium | Only 1 ticket touches it per wave; rebase after each merge |
| Type definition churn | Medium | Low | T0.1 locks type contracts early; all other tickets import from there |
| Performance regression from new checks | Medium | Medium | All features gated behind config; disabled-by-default means zero overhead out of the box |
| Thread safety bugs in LRU cache / rate limiter | Low | High | RLock on all mutable state; red-proof negative tests for race conditions |
| Speculative execution cost surprise | Low | Medium | Opt-in per-request header; clear cost warning in docs |
| Gate time inflation (>5s) | Medium | Low | New tests use mock upstreams (no network); cache tests use synthetic data |
| Config file sprawl | Medium | Low | All new config files in ~/.charon/ (existing convention); loaders return safe defaults when absent |

---

## Schedule Estimate

| Wave | Tickets | Parallel slots | Estimated wall-clock |
|---|---|---|---|
| Wave 0 | 11 | 11 (all parallel) | ~1 session (all can be delegated to subagents simultaneously) |
| Wave 1 | 3 | 2 (CLI parallel to gateway+proxy) | ~1 session (2 sequential steps) |
| Wave 2 | 4 | 2 (CLI parallel to proxy chain) | ~1 session (3 sequential proxy steps) |
| Wave 3 | 5 | 3 (session/spec/consensus parallel) | ~2 sessions (2 sequential steps after parallel wave) |
| **Total** | **23** | — | **~5 sessions** at full parallelism |

---

## REPARTITION — 2026-07-03 (after bridge coordination)

**Decision:** Split into two independent tracks. yoda owns the failover core; mace-windu
owns the infrastructure + non-failover features. yoda lands FIRST, then mace-windu wires on top.

### TRACK A — yoda: Core Failover / Exhaustion / Billing Switching (T0 priority)

**Owns:** `src/charon/proxy_server.py` (failover loop section), `src/charon/gateway.py`
(chain_for + pool compilation + load_config), `src/charon/config.py` (pool config loaders),
`src/charon/types.py` (new exhaustion/billing types only)

**Scope:**
1. **Billing-aware switching** — 402 Payment Required → switch to cheaper/free provider.
   Detect when a provider returns billing-exhausted (not just rate-limited). Separate
   "you're out of credits" from "you hit RPM cap" — different cooldown strategies.
2. **Expanded exhaustion detection** — beyond 429/402/503, detect: empty responses,
   rate-limit headers (Retry-After, X-RateLimit-Remaining), capacity errors (507, 529),
   provider maintenance mode (503 with specific body). Classify upstream errors into:
   RETRYABLE (try next), COOLDOWN (cool this provider), TERMINAL (return to client).
3. **Pool config improvements** — per-model rate limit config (RPM/TPM), cost caps,
   pool ordering strategies. Hot-reload on config change.
4. **Global fallback chain** (unpark FALLBACK-PROVIDER ticket) — when ALL providers in a
   pool fail, try the global fallback before returning error.
5. **Exhaustion handoff** — record exhaustion events in JSONL log. Track per-provider
   exhaustion reason + timestamp + recovery window.

**Files (exclusive — not touched by Track B until yoda lands):**
- `src/charon/proxy_server.py` — failover loop (lines ~498-770)
- `src/charon/gateway.py` — chain_for, _build_routes_and_pools, load_config
- `src/charon/config.py` — pool/exhaustion config loaders

### TRACK B — mace-windu: Infrastructure Modules + Non-Failover Features

**Phase B1 (parallel with yoda):** New modules only. Zero proxy_server.py/gateway.py touch.
- B1.1 — ADOPT-TYPES (new types NOT overlapping with what yoda adds)
- B1.2 — ADOPT-CACHE (SemanticCache)
- B1.3 — ADOPT-INSPECT (RequestInspector)
- B1.4 — ADOPT-NORM (ResponseNormalizer)
- B1.5 — ADOPT-GUARD (Guardrails)
- B1.6 — ADOPT-QUALITY (QualityScorer)
- B1.7 — ADOPT-OBSERVE (Observability)
- B1.8 — ADOPT-CONFIG-B1 (config loaders for B1 modules)

**Phase B2 (after yoda lands):** Wire modules into gateway on top of yoda's failover.
- B2.1 — Wire cache + normalizer into proxy_server.py
- B2.2 — Wire guardrails into proxy_server.py
- B2.3 — Wire observability into proxy_server.py
- B2.4 — Wire inspector into gateway.py + proxy_server.py
- B2.5 — CLI surface for all B1+B2 features

**Phase B3 (after B2):** Advanced features.
- B3.1 — Session affinity
- B3.2 — Speculative execution (races providers, uses yoda's exhaustion signals)
- B3.3 — Consensus routing
- B3.4 — Virtual keys
- B3.5 — Policy composition

### Dropped from plan (don't duplicate yoda's work):
- ~~T0.2 (ADOPT-RATELIMIT)~~ — yoda owns rate limit/exhaustion detection
- ~~T0.5 (ADOPT-SPEND)~~ — yoda owns billing-aware switching
- ~~T0.6 (ADOPT-LOADBAL)~~ — yoda owns pool ordering strategies
- ~~T1.1 (gateway wiring for loadbal+inspector)~~ — split; yoda does loadbal, B2.4 does inspector
- ~~T1.2 (proxy wiring for rate+spend)~~ — yoda owns the failover loop wiring

### Collision mitigation:
yoda's files are: proxy_server.py (failover section), gateway.py (chain_for/load_config),
config.py (pool loaders). Track B Phase 1 touches NONE of these. Phase 2 (wiring) only
begins AFTER yoda's PR merges. Zero merge conflicts possible.
