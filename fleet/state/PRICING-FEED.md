# PRICING-FEED — derived pricing store design

**Ticket:** `fleet/board/PRICING-FEED.md`
**Owner:** PRICING-FEED
**Date:** 2026-08-02
**Status:** DESIGN (eval-only, no code)

## Problem statement

Charon routes by cost and quality. Both require current pricing data. Currently
`src/charon/model_catalog.py` ships with hardcoded LiteLLM static JSON from June 2026.
This is stale for models launched after that date and covers a fraction of the
provider universe. PRICE-REFRESHER and SPEND-METRIC-TRUSTWORTHY both need
live pricing — they must not hard-code a single feed.

## Policy: corroboration over SSOT

> "For EXTERNAL reference data prefer multiple corroborating sources over SSOT.
> Disagreement between feeds is ITSELF A SIGNAL. SSOT applies to data we OWN and
> is a category error for facts we OBSERVE."

— operator input, SESSION-HANDOFF-satele-shan.md:104-110

Pricing feeds are facts we **observe**, not data we **own**. A single authoritative
source creates a hidden dependency: when that source goes stale or wrong, every
downstream consumer propagates the error without knowing it.

## Candidates evaluated (2026-08-02, live fetch + code check)

| Candidate | MCP | API-addressable | Auth | Refresh | License | Verdict |
|---|---|---|---|---|---|---|
| pricepertoken.com | **YES** (`/mcp/mcp` HTTP) | yes | none | stated "regularly" | not stated | ADOPT |
| benchlm.ai | no | **YES** (`/api/data/leaderboard`) | none | daily | MIT | ADOPT |
| whatllm.org | no | **YES** (shares BenchLM API) | none | daily | MIT | ADOPT (overlaps BenchLM) |
| TokenWatch (tokenwatch.wyrdwerk.com) | no | **YES** (`/api/v1/*`) | none | **2-hourly** | MIT | **ADOPT — PRIMARY** |
| cheahjs/free-llm-api-resources | no | no (markdown list) | — | — | — | SKIP |
| 12britz/awesome-free-models | no | no (markdown list) | — | — | — | SKIP |
| LiteLLM static JSON | n/a | no (git-vendored file) | — | static | MIT | ADOPT — fallback only |

Detailed per-candidate verdicts follow. (EVAL-REGISTRY rows must be added by the
registry owner — this ticket does not own `fleet/state/EVAL-REGISTRY.md`.)

### pricepertoken.com — ADOPT (MCP-first)

- **MCP:** **YES** — `https://api.pricepertoken.com/mcp/mcp` (MCP JSON-RPC over HTTP), 7 tools
- **API-addressable:** yes
- **Auth:** none
- **Refresh:** provider docs state "updated regularly" — cadence not machine-declared
- **License:** no explicit licence stated (built by 68 Ventures LLC)
- **Role:** MCP-first per operator brief. Live pricing + benchmarks for 300+ models.
  Primary value is benchmark/TTFT data; pricing is a feed, not a direct provider API —
  cross-validate against TokenWatch.

### TokenWatch (WyrdWerk/tokenwatch) — ADOPT (PRIMARY, Tier 1)

- **MCP:** no
- **API-addressable:** **YES** — `https://tokenwatch.wyrdwerk.com/api/v1/`
- **Auth:** none
- **Refresh:** **2-hourly** via GitHub Actions cron
- **License:** MIT
- **Scope:** 993 models, 81 providers, 3-tier sourcing (direct /v1/models → OpenRouter
  de-aggregated → CSV/hardcoded). fetches from provider /v1/models endpoints — first-party
  pricing for Tier 1 providers (DeepInfra, Crof, etc.). Cross-validation spot-check: gpt-4.1-mini
  OpenAI $0.40/$1.60 matches OpenAI published pricing exactly.

### BenchLM (benchlm.ai) — ADOPT (quality-index primary)

- **MCP:** no
- **API-addressable:** **YES** — `https://benchlm.ai/api/data/leaderboard`
- **Auth:** none
- **Refresh:** daily (2026-08-02 snapshot confirmed)
- **License:** MIT (confirmed via GitHub)
- **Scope:** 297 models, BenchAlign composite scores, pricing from providers.
  Primary value is BENCHMARK quality data — pricing data is secondary.

### WhatLLM (whatllm.org) — ADOPT (overlaps BenchLM)

- **MCP:** no
- **API-addressable:** **YES** (shares BenchLM API)
- **Auth:** none
- **Refresh:** daily
- **License:** MIT
- **Scope:** 149 models, 56 providers. Shares Artificial Analysis Intelligence Index as
  data source with BenchLM. NOT independently valuable — mark for deprecation if BenchLM
  covers the same data at equal freshness.

### cheahjs/free-llm-api-resources — SKIP

- **MCP:** no
- **API-addressable:** no (GitHub markdown list only)
- **Auth:** N/A
- **Refresh:** N/A (curated list)
- **License:** N/A
- **Reason:** Informational index of free LLM providers, not a pricing feed. No structured
  pricing data, no API. Superseded by TokenWatch.

### 12britz/awesome-free-models — SKIP

- **MCP:** no
- **API-addressable:** no (GitHub markdown list only)
- **Auth:** N/A
- **Refresh:** N/A (curated list)
- **License:** N/A
- **Reason:** Curated markdown list of free models, not a pricing feed. No structured
  pricing data, no API. Superseded by TokenWatch.

### LiteLLM `model_prices_and_context_window.json` — ADOPT (fallback only)

- **MCP:** N/A
- **API-addressable:** no (git-vendored static file)
- **Auth:** no
- **Refresh:** static (repo-fetch cadence)
- **License:** MIT
- **Role:** Fallback when live feeds are unavailable (cold start, network down).
  Already shipped (PR #97, commit 3314989). Gap confirmed: `deepseek-v4-flash` and
  `glm-5.2` MISSING from static file.

## Derived store design

### Source precedence (declared, not hardcoded)

```
Tier 1 (highest authority):  Live feeds — TokenWatch API
Tier 2:                      Price Per Token MCP (live, MCP-first per operator)
Tier 3:                      BenchLM API (quality-index primary, pricing secondary)
Tier 4:                      LiteLLM static JSON (git-vendored, fallback)
```

Precedence is for **authoritative value selection**. When multiple Tier-1 feeds agree,
use that value. When they disagree, surface the disagreement (see §Disagreement
signal below).

### Tier 1 source: TokenWatch API

- **Endpoint:** `https://tokenwatch.wyrdwerk.com/api/v1/`
- **Auth:** none
- **Refresh:** 2-hourly via GitHub Actions cron
- **Scope:** 993 models, 81 providers; 3-tier sourcing (direct /v1/models →
  OpenRouter de-aggregated → CSV/hardcoded)
- **Key endpoints:**
  - `GET /api/v1/models?search=<model>&limit=N` — model rows
  - `GET /api/v1/models/<canonical_id>/providers` — all providers for a model,
    sorted by cost, with `zdr`, `subscription`, `cache_read` fields
  - `GET /api/v1/stats` — corpus stats

**Cross-validation spot-check (2026-08-02):**

```
gpt-4.1-mini:
  TokenWatch (OpenAI):  $0.40 / $1.60  (cache_read $0.10)
  OpenAI published:     $0.40 / $1.60  ← EXACT MATCH
  ✓ Confirmed

glm-5.2 (Crof):
  TokenWatch:  input $0.30 / output $1.05 / cache_read $0.05
  LiteLLM JSON:  MISSING (not in static file)
  ✓ TokenWatch more current than static fallback
```

### Tier 2 source: Price Per Token MCP

- **Endpoint:** `https://api.pricepertoken.com/mcp/mcp` (MCP JSON-RPC over HTTP)
- **Auth:** none
- **Tools:** `get_all_models`, `get_model`, `compare_models`, `compare_providers`,
  `get_benchmarks`, `get_providers`, `search_models`
- **Refresh:** stated "regularly" — cadence not machine-declared
- **Role:** corroborate Tier 1 on price; primary for benchmark/TTFT data

MCP-first per operator brief: wire this first.

### Tier 3 source: BenchLM API

- **Endpoint:** `https://benchlm.ai/api/data/leaderboard`
- **Auth:** none
- **Refresh:** daily
- **Role:** quality-index primary (BenchAlign composite scores), NOT a pricing
  authority. Use TokenWatch for provider-level pricing precision.
- **Note:** WhatLLM shares the same API — deprecate WhatLLM row if BenchLM
  covers the same data.

### Tier 4 source: LiteLLM static JSON

- **Location:** `model_prices_and_context_window.json` (git-vendored, MIT)
- **Role:** cold-start and network-failure fallback ONLY. Not the primary source.
- **Gap known:** `deepseek-v4-flash` MISSING from this file; `glm-5.2` MISSING.
- Never advertise as "live" — the file is static by construction.

### Disagreement signal

Two feeds differing on a price for the same (model, provider) pair is a finding
to **surface**, not a value to **average**.

Implementation contract for PRICE-REFRESHER:

```python
@dataclass
class PriceFeedResult:
    value: float | None          # $/M tokens, or None if no feed knew
    feeds: dict[str, float]      # {feed_name: value} for all feeds that answered
    disagreement: bool           # True if >=2 feeds answered and values differ
    stale_feeds: set[str]        # feeds that returned but with outdated data

def resolve_price(model: str, provider: str, direction: str) -> PriceFeedResult:
    """Return the price, which feeds agreed, and whether they disagreed."""
    # Fetch from Tier 1 (TokenWatch), Tier 2 (PPT MCP), Tier 3 (BenchLM)
    # Tier 4 (LiteLLM static) only when all others fail
    values = {name: feed.get_price(model, provider, direction) for name, feed in FEEDS}
    values = {k: v for k, v in values.items() if v is not None}
    if not values:
        return PriceFeedResult(value=None, feeds={}, disagreement=False, stale_feeds=set())
    # Tier-1 wins for authoritative value; disagreement is always surfaced
    primary = values.get("tokenwatch", values.get(next(iter(values))))
    return PriceFeedResult(
        value=primary,
        feeds=values,
        disagreement=len(set(values.values())) > 1,
        stale_feeds=set(),
    )
```

When `disagreement == True`, log a structured finding:

```
PRICING-DISAGREEMENT: model=glm-5.2 provider=crof direction=output
  tokenwatch=$1.05/M  pricepertoken=$0.98/M  delta=6.8%
```

This goes to the SPEND-METRIC feed — not averaged, not silently resolved. A
persistent disagreement is evidence about the **feed**, not about the **model**.
It may indicate: a provider changed pricing without updating their /v1/models
endpoint, a feed is reading a cached value, or a model quant/region variant
is being conflated.

### Consumers

- **PRICE-REFRESHER** (`fleet/board/PRICE-REFRESHER.md`): fallback price path
  when the gateway has no cached price for a (model, provider) pair. Reads the
  derived store. Must NOT hard-code a single feed.
- **SPEND-METRIC-TRUSTWORTHY** (`fleet/board/SPEND-METRIC-TRUSTWORTHY.md`):
  cost per ACCEPTED task. Reads the derived store's `disagreement` signal as
  an input to confidence scoring.
- **Routing** (`src/charon/balance.py`): hot-path cost lookup. Caches derived
  store prices with a TTL. TTL must be configurable and short (≤ 2 hours for
  Tier-1 feeds, ≤ 24h for Tier-4 fallback).

### What this does NOT decide

Price data **informs routing**. It never **decides routing alone**, because
quality is a model × provider property — see `fleet/board/GRADE-MODEL-PROVIDER-PAIR.md`.
A cheap model with degraded quality on a given provider may cost more per
useful-output-token than a more expensive model that produces correct answers faster.

## Implementation notes for PRICE-REFRESHER

1. Wire Price Per Token MCP first — operator-specified MCP-first shape.
2. Add TokenWatch HTTP API as the Tier-1 fallback when MCP is unavailable.
3. Implement the `PriceFeedResult` dataclass above — disagreement must be logged.
4. Configurable feed precedence in `fleet/config.py` or env vars so the operator
   can reorder without code changes.
5. TTL per feed: TokenWatch ≤ 2h, PPT MCP ≤ 1h, BenchLM ≤ 24h, LiteLLM static
   = repo-fetch cadence.
6. Graceful degradation: if TokenWatch is down, fall back to PPT MCP; if both
   are down, fall back to LiteLLM static; if static is also unavailable, return
   None and let the router use its hardcoded defaults.

## Verification plan

After PRICE-REFRESHER ships:
1. Cross-check TokenWatch's glm-5.2 (Crof) price against an actual API call to
   Crof's `/v1/models` endpoint. This is the corroboration step — a feed that
   agrees with the provider is more trustworthy than one that doesn't.
2. Verify the `disagreement` signal fires for a known divergent case.
3. Confirm SPEND-METRIC-TRUSTWORTHY surfaces the disagreement as a confidence
   qualifier.
