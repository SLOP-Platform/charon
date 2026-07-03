# Smart Routing — Grounding Document

**MISSION:** Route work to providers by cost, performance, and availability to the
right tier of agent without quality loss or work interruption regardless of session
balance, token caps, funds, or provider outages.

---

## 1. What it is

Smart Routing replaces Charon's simple cost-ranked failover with a multi-signal
pipeline. Every request flows through:

```
request → guardrail scan → spend check → cache lookup → quality filter →
          provider chain → failover loop → normalize → cache store →
          quality/scoring record
```

The actively-wired modules in ``_handle()`` are: **spend, guardrail, cache, quality,
normalizer.** ``SpeculativeExecutor`` and ``ConsensusRouter`` are **constructed but
not yet wired into ``_handle()``** — they are stored on the server instance
(``proxy_server.py`` constructor) but never invoked on the hot path. See SR-8 for
the wire-or-remove follow-up.

All modules are always active with safe defaults. Nothing to configure to get
better routing. Tune with `~/.charon/` config files.

> **Note:** `SpeculativeExecutor` and `ConsensusRouter` are constructed but
> **not yet wired** into `_handle()` — they are NOT in the active request path
> above. SR-8 (wire-or-remove decision) will resolve them.

---

## 2. Modules — what each does

| Module | File | Always on? | What it does |
|---|---|---|---|
| **SemanticCache** | `cache.py` | Yes | SHA-256 prompt cache, LRU eviction, TTL expiry. Hit → skip upstream. |
| **Guardrails** | `guardrails.py` | Yes | PII scan (email, SSN, CC-Luhn, phone, API keys) + keyword deny-list. BLOCK → 400. |
| **SpendLimiter** | `spend_limits.py` | Yes | Cumulative cost tracker with monthly reset. 402 when cap exceeded. 0 = unlimited. |
| **ResponseNormalizer** | `response_normalizer.py` | Yes | 4 modes: STRIP_BOILERPLATE, FIX_JSON, STANDARDIZE_MD, NONE (passthrough). |
| **RequestInspector** | `request_inspector.py` | Yes | Single-pass: detects images, tools, estimates tokens (char/4 heuristic). |
| **QualityScorer** | `quality_scorer.py` | Yes | Per-provider latency EWMA + reliability score (0.5 bootstrap). Feeds quality filter. |
| **Observability** | `observability.py` | Yes | 4 export targets: JSONL, Prometheus (/metrics), webhook (HMAC), Langfuse. |
| **SessionAffinity** | `session_affinity.py` | Yes | X-Session-ID pinning, TTL expiry, cleanup. Keeps prompt caches warm. |
| **VirtualKeyManager** | `virtual_keys.py` | Yes | Scoped API keys with permissions (model allowlist, spend cap, RPM/TPM). |
| **PolicyRouter** | `policy_router.py` | Yes | Composable routing policies: FALLBACK, LOAD_BALANCE, LATENCY. `policy/<name>` model IDs. |
| **SpeculativeExecutor** | `speculative_execution.py` | Opt-in | Race N providers, first 200 wins. MUST opt-in via config (cost-multiplying). |
| **ConsensusRouter** | `consensus.py` | Opt-in | Cross-provider Jaccard similarity check. MUST opt-in via config. |
| **ProviderDiscovery** | `discover.py` | On-demand | `charon discover` queries all configured providers' /v1/models, builds cost map. |
| **Discover (external)** | `discover.py` | On-demand | `charon discover openrouter` imports 400+ models with pricing. 3-stage fuzzy matching. |

---

## 3. Key files — what owns what

```
src/charon/
  gateway.py        — GatewayConfig (holds all module refs), load_config(),
                      build_server(), run(), _module_inst()
  proxy_server.py   — GatewayProxyServer, _handle() with all hook points,
                      chain_for() with policy/ prefix, quality filter
  config.py         — Model registry, provider config, cost map loaders
  providers.py      — Provider presets, _parse_models(), pricing capture
  types.py          — Shared dataclasses: CachedResponse, RequestHints,
                      SpendDecision, GuardrailViolation, ObsEvent, etc.
  cache.py          — SemanticCache (LRU, TTL, thread-safe)
  guardrails.py     — PII detection, keyword deny-list, Luhn validation
  spend_limits.py   — Cumulative cost tracker, monthly reset, atomic persist
  response_normalizer.py — 4 normalization modes
  request_inspector.py   — Chat message inspection (images, tools, tokens)
  quality_scorer.py      — EWMA latency, reliability scoring (α=0.34)
  observability.py        — JSONL, Prometheus, webhook, Langfuse export
  session_affinity.py     — Session pinning with TTL
  speculative_execution.py — Race-N-providers executor (opt-in)
  consensus.py            — Jaccard similarity consensus router
  virtual_keys.py         — Scoped API key manager
  policy_router.py        — Composable routing policies
  discover.py             — Provider model discovery + external import
  cli.py                  — charon discover, config commands
```

---

## 4. Config files (all in ~/.charon/)

Modules are always active with safe defaults — no config file needed.
Config files enrich behavior; delete them to return to defaults.

| File | Module | Does when absent | Example |
|---|---|---|---|
| spend.json | SpendLimiter | Unlimited ($0 cap). Startup warns if no cap set. | `{"monthly_limit_usd": 100}` |
| guardrails.json | Guardrails | PII detection active, no keywords | `{"keywords": ["internal-code-name"]}` |
| quality.json | QualityScorer | Tracks quality, bootstraps at 0.5 | auto-populated by gateway |
| policies.json | PolicyRouter | No policies defined | `{"cheap-fast": {"type": "load_balance", "members": ["free", "cheap"]}}` |
| virtual_keys.json | VirtualKeyManager | No keys defined | `{"keys": {"ck-xyz": {"label": "dev", "permissions": {...}}}}` |
| model_aliases.json | Discover | No aliases | `{"ext/model-id": "my-model-name"}` |
| speculative.json | SpeculativeExecutor | Disabled (opt-in only) | `{"enabled": true, "max_providers": 3}` |
| consensus.json | ConsensusRouter | Disabled (opt-in only) | `{"enabled": true, "similarity": 0.8}` |

### Gateway startup prints Smart Routing status

```
$ charon gateway --token gk --port 8080
Smart Routing: spend limit: $0.00 remaining, cache, guardrails, quality, inspector
  hint: set a spend cap with 'charon limits set --monthly N'
charon gateway (token-gated) on http://127.0.0.1:8080/v1 — 12 model(s), 3 pool(s)
```

---

## 5. Hook points — where modules fire

All hooks are in `proxy_server.py:_handle()`. Modules gate with `if srv.module is not None:`.

```
  ┌─ HOOK A: pre-flight (before chain_for)
  │  ├ guardrail request scan  → BLOCK → 400
  │  ├ spend cap check         → denied → 402
  │  └ cache lookup            → HIT → serve cached
  │
  ├─ chain_for(model)
  │  ├ policy/ prefix          → PolicyRouter.resolve()
  │  ├ pool lookup             → cost-ranked chain
  │  └ single route fallback
  │
  ├─ order_by_cooldown          → fresh first, cooled last
  │
  ├─ quality filter            → reliability ≥ 0.5 (med floor)
  │
  ├─ FAILOVER LOOP (for each route)
  │  ├ exhaustion detection    → 429/402/503 → cooldown → next
  │  ├ billing detection       → 401+billing patterns → next
  │  └ silent downgrade check  → next
  │
  │   (SpeculativeExecutor + ConsensusRouter are constructed but
  │    not invoked here — see SR-8 for wire-or-remove decision)
  │
  ├─ HOOK C: post-response (200 non-streaming)
  │  ├ normalizer              → transform body
  │  ├ cache store             → save for next time
  │  ├ quality scorer          → record success
  │  ├ spend limiter           → record cost
  │  └ guardrail response scan → BLOCK → 400
  │
  └─ return to client
```

---

## 6. Testing

**Unit tests:** `PYTHONPATH=src python3 -m pytest tests/` — 1016 tests

**Module-specific:**
- `tests/test_cache.py` (11 tests)
- `tests/test_guardrails.py` (23 tests)
- `tests/test_spend_limits.py` (12 tests)
- `tests/test_response_normalizer.py` (14 tests)
- `tests/test_request_inspector.py` (10 tests)
- `tests/test_quality_scorer.py` (11 tests)
- `tests/test_observability.py` (11 tests)
- `tests/test_discover.py` (34 tests)
- `tests/test_session_affinity.py` (11 tests)
- `tests/test_speculative_execution.py` (7 tests)
- `tests/test_consensus.py` (9 tests)
- `tests/test_virtual_keys.py` (8 tests)
- `tests/test_policy_router.py` (6 tests)

**Live smoke test:**
```
# 1. Configure at least one provider with a key
charon providers add openai --key sk-...

# 2. Import models
charon models import openai

# 3. Start gateway (all Smart Routing active by default)
CHARON_GATEWAY_TOKEN=gk charon gateway --token gk --port 8080

# 4. Test
curl localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer gk" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}]}'
```

---

## 7. Commits (feat/prod-install)

```
c092c19  Smart Routing always-on — modules with defaults, status at startup
799291c  Phase D — external model import
9fd5053  fix: gate hygiene
47c96b3  B3 wiring
8912f68  B3 modules
fdc1974  Phase C — quality-aware routing
2a0d089  B2 wiring
bca6233  B1 — 9 gateway modules
dd93d8d  yoda: T0 failover
39782e3  luke: ATC fixes
```

---

## 8. Architecture rules

- **Stdlib only** — no external deps in gateway modules
- **Always-on defaults** — every module auto-loads at gateway start via `_module_inst()`. Config files customize behavior; absent files use safe defaults. Only speculative and consensus need explicit `"enabled": true` in their config file. **Note:** `SpeculativeExecutor` and `ConsensusRouter` are constructed by `_module_inst()` but are **not wired** into `_handle()` — they exist as objects but never fire on the request path. SR-8 will decide whether to wire or remove them.
- **`_module_inst()`** — single factory function in `gateway.py` that creates all 13 modules from `~/.charon/<name>.json`. Returns `Any` for mypy compatibility.
- **Provider-agnostic** — no vendor hardcoding. Provider names in `providers.py` register only.
- **Circular import guard** — policy_router uses `Any` types to avoid importing UpstreamRoute from proxy_server
- **Thread safety** — all modules use `threading.RLock`

---

## 9. Quick reference — CLI commands

> **Note:** several commands below are **planned but not yet implemented**
> (marked with `[NYI]`). As of writing, only `gateway`, `discover`,
> and `discover openrouter` exist.

```
charon gateway                   Start gateway with Smart Routing
charon discover                  Discover from configured providers
charon discover openrouter       Import from OpenRouter catalogue
charon limits show               [NYI] Show spend limits
charon limits set --monthly N    [NYI] Set monthly spend cap
charon cache stats               [NYI] Cache hit/miss counters
charon quality show              [NYI] Per-provider reliability scores
charon guardrails show           [NYI] Active guardrail rules
charon policy create             [NYI] Create a routing policy
```
