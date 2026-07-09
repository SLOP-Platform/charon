> ARCHIVED 2026-07-08 — superseded by POOLS-REDESIGN-ADR-v2.md + COST-RANK-AUTO + DRAIN-ROUTING (cost-aware-routing north-star salvaged into the ADR; no unique unabsorbed mechanism remained)

# Proposal 1 — Cost-Aware Provider Routing for Charon Gateway

**Priority:** #1 | **Date:** 2026-07-03 | **Based on:** Competitive eval (LiteLLM, OpenRouter, Together, Requesty, Kong, RelayFreeLLM)

---

## Goal

Charon routes to the **cheapest provider of a specific model** without quality loss,
and sends work to the **correct capability tier** for the task class. When a provider
hits billing caps, rate limits, or exhausts credits, Charon switches silently.

---

## What Charon already has (keep these)

| Feature | Moat status |
|---|---|
| Silent downgrade detection | **Unique.** Keep, strengthen. |
| Streaming buffered failover | **Unique.** Keep. |
| Provider-keyed cooldown | **Unique.** Keep. |
| Cost-ranked failover (free→flat→cheap) | Good base. Extend. |
| Tier abstraction (low/med/high) | Good base. Extend to cost-aware. |
| `code_safe` flag | **Unique.** Keep. |
| Stdlib-only core | **Unique.** Keep. |

---

## What to build (in priority order)

### Phase A — Provider Cap Discovery (cheapest first)

**Problem:** Charon knows provider base URLs but not which providers carry which models
at what price. The operator has to manually add models.

**Solution:** A `charon discover` subcommand that queries ALL configured providers'
`/v1/models` endpoints, cross-references model IDs, and builds a **cost map**:
which providers carry `claude-sonnet-4-5`, what each charges, which are free/cheap/premium.

```
charon discover --refresh
  → Queries 28 providers
  → 847 models discovered
  → Cross-referenced: 23 dupes across providers
  → Cost map written to ~/.charon/cost_map.json
```

**Files:** `src/charon/discover.py` (new), `src/charon/cli.py` (subcommand)

**Effort:** 1 ticket. Self-contained new module.

---

### Phase B — Quality-Adjusted Cost Scoring

**Problem:** "Cheapest" doesn't mean "worst." A $0.15/MTok model with 95% success rate
is better than a free model with 40% success rate. Need quality-per-dollar.

**Solution:** `QualityScorer` (from ADOPT plan) tracks per-provider-per-model:
- Latency EWMA (α=0.2)
- Rolling success rate (last 100 calls)
- Cost per token (from cost map)
- **Quality-per-dollar = (latency_score × reliability_score) / cost_per_token**

Stored in `~/.charon/quality.json`. Updated passively on every successful/failed
upstream call. Zero network overhead.

**Files:** `src/charon/quality_scorer.py` (new), `tests/test_quality_scorer.py`

**Effort:** 1 ticket. Self-contained. Zero proxy_server.py touch.

---

### Phase C — Tier-Aware Smart Routing

**Problem:** Charon has `low/med/high` tiers but routing is cost-ranked only.
A `high`-tier task shouldn't route to a free model that can't solve it.

**Solution:** Extend `_build_routes_and_pools()` in `gateway.py`:

1. **Tier→quality floor mapping:**
   - `low` → any model, cheapest-first
   - `med` → quality_score ≥ 0.5, cost-ranked within band
   - `high` → quality_score ≥ 0.8, cost-ranked within band

2. **Task-class→tier mapping (existing):**
   - `diagnosis` → high
   - `review` → high
   - `refactor` → med
   - `codegen` → med
   - `hygiene` → low
   - `doc` → low

3. **Routing algorithm:**
   ```
   resolve_chain(model_id, task_class):
     tier = tier_for(task_class)
     candidates = providers_carrying(model_id)
     candidates = filter(candidates, quality_score ≥ tier_floor)
     return sort(candidates, key=quality_per_dollar, reverse=True)
   ```

4. **Request hints (from ADOPT-INSPECT):**
   - Vision detected → filter to vision-capable models
   - Tool definitions → filter to tool-capable models
   - Large context → filter to high-context-window models

**Files:** `src/charon/gateway.py`, `src/charon/config.py`

**Effort:** 1 ticket. Extends existing routing, no new module.

---

### Phase D — Provider Swarm Discovery (free/cheap expansion)

**Problem:** Charon has 28 providers. The ecosystem has 100+ (LiteLLM), 400+ (OpenRouter).

**Solution:** Two sources of cheap providers:

1. **OpenRouter's model list** — `GET https://openrouter.ai/api/v1/models` returns
   400+ models with pricing. Parse and cross-reference against Charon's providers.
   Free models marked with `:free` suffix or zero pricing.

2. **Provider-flatrate ticket** (already parked at `PROVIDER-FLATRATE.md.parked`) —
   featherless.ai ($25/mo unlimited, 40k+ models) + DeepInfra + Cerebras as
   ultra-cheap per-token providers.

3. **Auto-import**: `charon discover --openrouter` pulls the OR catalog, maps to
   Charon providers, bulk-imports models with pricing metadata.

**Files:** `src/charon/discover.py` (extend), `src/charon/config.py` (bulk import)

**Effort:** 1 ticket. Extends Phase A.

---

### Phase E — Spend Caps + Rate Limit Awareness

**Problem:** Charon has no spend enforcement. A session can burn through credits
unnoticed.

**Solution:** Two separate features from the ADOPT plan:

1. **SpendLimiter** (`spend_limits.py`):
   - Pre-flight cost estimate (context_window × price per token)
   - 402 Payment Required if cap exceeded
   - Monthly/per-session reset windows
   - Config: `spend_limit_usd` in `~/.charon/config.json`

2. **RateLimitAware switching** (yoda's scope in Track A):
   - Detect 402 (billing exhausted) → switch to cheaper provider
   - Detect 429 with Retry-After → cooldown provider, continue chain
   - Different exhaustion classes: BILLING (switch), RATE_LIMIT (cooldown),
     CAPACITY (retry with backoff)
   - Record exhaustion events in JSONL log

**Files:** `src/charon/spend_limits.py` (new), `src/charon/proxy_server.py` (yoda's)

**Effort:** 2 tickets. Spend limits = new module. Rate limit = yoda's failover work.

---

## What NOT to build (cost vs benefit)

| Feature | Why skip |
|---|---|
| Prompt caching across providers | Provider-specific cache headers, brittle |
| Cross-provider consensus routing | 3× cost. Opt-in only (Phase 3). |
| Fine-tuning pipeline | Not a gateway concern |
| Full model eval framework | Overkill. Quality scorer is enough |
| Built-in chat UI | Not infrastructure. Use existing clients |

---

## Implementation Plan (3 waves, minimal collision)

### Wave 1 (parallel — 3 tickets, 3 distinct files)
| Ticket | Owns | What |
|---|---|---|
| COST-DISCOVER | `discover.py`, `tests/test_discover.py` | Provider model discovery + cost map |
| COST-QUALITY | `quality_scorer.py`, `tests/test_quality_scorer.py` | Quality-per-dollar tracking |
| COST-CONFIG | `config.py`, `tests/test_config.py` | Config loaders for cost map + quality |

### Wave 2 (sequential — extends gateway routing)
| Ticket | Owns | Depends on |
|---|---|---|
| COST-ROUTE | `gateway.py`, `config.py` | W1 all. Extends routing with tier+quality filters |
| COST-SWARM | `discover.py`, `config.py`, `providers.py` | W1-COST-DISCOVER. OpenRouter import + flatrate providers |

### Wave 3 (after yoda lands failover)
| Ticket | Owns | Depends on |
|---|---|---|
| COST-SPEND | `spend_limits.py`, `config.py`, `proxy_server.py` | yoda Track A + W2. Spend caps + 402 switching |

---

## Token/Resource Cost

| Feature | Runtime overhead | Context cost | Dependencies |
|---|---|---|---|
| Discovery | One-time per `--refresh` | None at runtime | None (stdlib urllib) |
| Quality scorer | ~1KB memory, ~10μs per call | None | None (stdlib math) |
| Tier routing | Same as current routing + 2 dict lookups | None | None |
| Spend limiter | ~2KB memory, atomic write on cost change | None | None (stdlib json) |
| **Total** | **~3KB memory, <50μs per request** | **Zero context bloat** | **Zero new deps** |

Every feature uses stdlib only. No framework, no database, no network at runtime
(discovery is one-time offline). This is the Charon way.

---

## Review Findings Addressed

### F1: Quality scorer lacks a "success" oracle. What defines success for an LLM response? Binary pass/fail is impossible.

**Fix:** The scorer does not attempt to judge LLM output quality. Instead it computes a
**reliability score** from three observable proxy signals, each available on every
upstream call without an LLM-judge:

| Signal | Weight | Observable? |
|---|---|---|
| Latency within threshold (`latency_ok`) | 0.3 | Yes — wall-clock measured at proxy |
| HTTP 200 with parseable content (`http_200`) | 0.4 | Yes — response code + body parse |
| No silent-downgrade detected (`no_downgrade`) | 0.3 | Yes — Charon's existing downgrade detector |

```
reliability_score = (latency_ok × 0.3) + (http_200 × 0.4) + (no_downgrade × 0.3)
```

The formula is purely observational. Phase B spec and the metric name are updated
from "quality_score" to "reliability_score" throughout.

### F2: Where does the gateway learn `task_class`? Chat completions don't carry it.

**Fix:** Two mechanisms, layered:

1. **Authoritative: `X-Charon-Task-Class` HTTP header.** The client sets it explicitly
   (e.g., `diagnosis`, `review`, `refactor`, `codegen`, `hygiene`, `doc`). If present,
   it overrides inference.

2. **Fallback: inference from request body.** A single-pass scan of the messages array:
   - Short prompts (<500 tokens total) → `simple`
   - Long prompts with code-related patterns → `codegen`
   - Multi-turn with review/audit language → `review`
   Otherwise → `default` (routes to `med` tier).

The header is authoritative; inference is the fallback. Neither adds a new
dependency — the scan is a stdlib str operation on the already-in-memory
messages payload.

### F3: OpenRouter model IDs don't map 1:1 to Charon provider models.

**Fix:** Add a mapping layer in `discover.py` with three stages:

1. **Exact match** — same ID, same provider → auto-import.
2. **Fuzzy match** — lowercase, strip provider prefixes (`openai/`, `anthropic/`),
   resolve known aliases (`claude-sonnet-4-20250514` ↔ `claude-sonnet-4-5`).
   Auto-import if confidence ≥ 0.9; flag for operator review otherwise.
3. **Manual override** — `~/.charon/model_map.json` keyed by OpenRouter ID, maps to
   Charon model ID. Operator-curated. Takes precedence over fuzzy matching.

Only stage 1 results are imported automatically; stages 2–3 produce a review report
(`~/.charon/discover_review.json`) the operator audits before bulk import.

### F4: Request hints (vision/tools/context) add latency to every proxy call.

**Fix:** Request inspection is **disabled by default.** When enabled:

1. It runs only on the **first request** in a session chain (detected via
   `X-Charon-Session-Id` header or a per-connection cache key).
2. Result is cached for the session lifetime (in-memory dict, TTL = session duration).
3. The scan is a single-pass O(n) read of the messages array — no LLM call, no
   network, <1 ms for typical payloads.

Configuration: `request_hints.enabled = false` in `config.json`. The operator
opt-in is required.

### F5: Cost-routing vs failover precedence unclear.

**Fix:** The routing decision follows a strict three-phase order:

```
Phase 1 — TIER FILTER (quality floor)
  Candidates must have reliability_score ≥ tier_floor(tier)

Phase 2 — COST RANK (within tier)
  Surviving candidates sorted by cost_per_token ascending
  (cheapest-first) within the same tier band

Phase 3 — FAILOVER CHAIN (same order)
  Try candidates in cost order. Each failure advances to
  the next candidate. Failover NEVER drops below the
  tier floor — a candidate whose reliability_score has
  fallen below the floor is excluded from the chain.
```

If all providers in the tier exhaust:
1. Charon adds `X-Charon-Warning: tier-exhausted` to the response.
2. It falls back to the **next tier down** (high→med→low) with the same
   cost-rank-and-failover logic, and adds `X-Charon-Warning: tier-degraded`.
3. If all tiers exhaust, it returns 502 with `X-Charon-Warning: all-providers-exhausted`.

### YODA-F1: Discovery needs parallelism+timeout for 28 providers

**Fix:** Phase A discovery uses `concurrent.futures.ThreadPoolExecutor` (stdlib) with
`max_workers=5` and a per-provider timeout of 10s. Results are collected as they
complete. Timeout providers are logged as `UNREACHABLE` in the cost map. Total
discovery time: ~60s max instead of sequential 28×10s = 280s.

### YODA-F2: Quality cold-start deadlock — new model scores 0, never selected

**Fix:** Bootstrap default `reliability_score = 0.5` (median) for all new models.
The first 10 calls establish the real score. During the bootstrap window, the model
is eligible for all tiers. After bootstrap: actual score is used. This prevents
new-model starvation while still allowing the model to prove itself.

### YODA-F3: EWMA alpha=0.2 too slow for latency detection, use 0.34

**Fix:** Changed alpha from 0.2 to 0.34 (repowire's recommended value — weights
last 3 observations at ~50%). Faster convergence on latency changes. Updated in
the Phase B latency EWMA description.

### YODA-F4: Pre-flight cost estimate uses context_window not actual prompt length — 100× over-estimate

**Fix:** Use actual prompt token estimate (`char_count / 4` heuristic from
ADOPT-INSPECT) when the request body is available. Fall back to `context_window`
as a ceiling only when the request body is not yet parsed. Spend cap enforcement is
best-effort — over-estimation is safer than under-estimation for budget caps, but
the ceiling-only approach was too coarse.

### YODA-F5: cost_map.json vs cost_rank — no integration plan, competing cost sources

**Fix:** `cost_map.json` is the single source of truth for provider pricing. The
existing `cost_rank` field in the model registry becomes a derived field populated
from `cost_map.json` at load time. `charon discover --refresh` regenerates
`cost_map.json`, which triggers a re-derivation of `cost_rank` on the next gateway
restart. No dual-source conflict.
