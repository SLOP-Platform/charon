# Premium (closed/proprietary) models — cheapest provider per tier, cache-aware

**Purpose:** when a premium *closed* model is genuinely needed, route to the cheapest source **first** — ranked by *effective* cost on a coding-agent load, not sticker price. Cache economics dominate this workload.

**Workload model:** coding agent, huge repeated context, **input:output ≈ 234:1**. Input cost dominates, so the ranking key is **effective input $/1M**.
**Cache-hit assumption:** **75% of input tokens served from cache** (plausible for a long-lived repo-context agent; stated so you can re-scale). Formula: `eff_input = 0.75 × cached + 0.25 × fresh`. Anthropic additionally pays a one-time cache-**write** premium on newly-cached tokens (modelled separately in notes).
**All prices retrieved 2026-07-08** unless noted. `$/1M` = US dollars per 1,000,000 tokens.
**ToS-proxy flag:** R/Y/G = risk of reselling/proxying a personal-tier key. Closed first-party API keys billed per-token are **G** (legitimate paid API use); aggregators reselling are **G** (that's their business); free personal tiers are **R** (out of scope here — this doc is paid closed models only).

Legend for color-coding the "effective" column (cheapest = greenest): `<$0.50` 🟢 · `$0.50–1.00` 🟩 · `$1.00–2.00` 🟨 · `>$2.00` 🟥.

---

## FRONTIER tier

| Model | Source | Input $/1M (fresh) | Cached-in $/1M | Output $/1M | Cache mechanism + realistic hit | **Eff. input $/1M @75%** | ToS | Source + date |
|---|---|---|---|---|---|---|---|---|
| **gpt-5.4** | **OpenAI direct** | 2.50 | **0.25** | 15 | Automatic prompt cache, ~90% off cached read, no extra write charge; hit realistic for repeated prefix | **0.81** 🟩 | G | developers.openai.com/api/docs/pricing (2026-07-08) |
| **gpt-5.4** | **NanoGPT** | 2.50 | 0.25* | 15 | "No % on top"; passes OpenAI cache read/write (*passthrough asserted, not line-item-verified). +5% if you PIN a provider | **0.81** 🟩 | G | nano-gpt.com/pricing (2026-07-08) |
| **gpt-5.4** | **OpenRouter** | 2.50 | 0.25* | 15 | Passthrough caching (60–80% eff. savings claim); depends on which upstream provider the request lands on | **0.81** 🟩 | G | openrouter.ai/openai/gpt-5.4 (2026-07-08) |
| gpt-5.5 (next step up) | OpenAI direct | 5.00 | 0.50 | 30 | Automatic cache, ~90% off | 1.63 🟨 | G | developers.openai.com/api/docs/pricing |
| gpt-5.5 | OpenRouter / NanoGPT | 5.00 | 0.50* | 30 | Passthrough | 1.63 🟨 | G | openrouter.ai/openai/gpt-5.5; nano-gpt.com |
| Claude Opus 4.8 | Anthropic direct | 5.00 | 0.50 | 25 | Prompt cache: read 0.1×; **write 1.25× (5m)=6.25 / 2× (1h)=10**. High hit needed to beat sticker | 1.63 🟨 (+write premium, see note) | G | claude-api skill model table, cached 2026-06-24 (docs page 404 on 2026-07-08 — NOT freshly primary-verified) |
| Claude Fable 5 | Anthropic direct | 10.00 | 1.00 | 50 | Same cache mechanics as Opus | 3.25 🟥 | G | claude-api skill table (2026-06-24) |
| Gemini 3.1 Pro | Google AI direct (Gemini API) | 2.00 (≤200K) / 4.00 (>200K) | 0.20 / 0.40 | 12 / 18 | **Explicit** context cache + **storage $4.50/1M/hr** — storage erodes benefit for fast-changing agent context | 0.65 🟩 (before storage) | G | ai.google.dev/gemini-api/docs/pricing (2026-07-08) |
| Grok 4.3 | xAI direct | 1.25 | ~0.125* | 2.50 | ~90% cached discount (verified on Grok 4.20; 4.3 cached rate inferred) | ~0.41 🟢* | G | aipricing.guru/xai (2026-06); docs.x.ai |
| Grok 4 (flagship) | xAI direct | 3.00 | ~0.30* | 15 | ~90% cached discount (inferred) | ~0.98 🟩* | G | aipricing.guru/xai (2026-06) |

**Anthropic write-premium note:** at 75% steady read-hit, if you model the 25% "miss" as fresh input, Opus 4.8 eff ≈ **$1.63**. If the miss tokens are being *written* to cache (5-min TTL, 1.25×=$6.25), eff climbs to ~**$1.94**. Anthropic caching only pays off at genuinely high, sustained hit rates; below ~50% hit it can be *more* expensive than sticker because of the write surcharge. Model per route.

## STRONG / MID tier (cheaper capable closed models)

| Model | Source | Input $/1M | Cached-in $/1M | Output $/1M | Cache mechanism + hit | **Eff. input $/1M @75%** | ToS | Source + date |
|---|---|---|---|---|---|---|---|---|
| **gpt-5.4-mini** | OpenAI direct / OR / NanoGPT | 0.75 | 0.075 | 4.50 | Automatic cache ~90% off | **0.24** 🟢 | G | developers.openai.com/api/docs/pricing |
| Claude Sonnet 5 | Anthropic direct | **2.00 intro** (→3.00 after 2026-08-31) | 0.20 intro (0.30 std) | 10 intro (15 std) | Read 0.1×; write 1.25×/2× | **0.65** 🟩 intro / 0.98 std | G | claude-api skill (2026-06-24) |
| Gemini 3.5 Flash | Google direct | 1.50 | 0.15 | 9 | Explicit cache + storage $1.00/1M/hr | 0.49 🟢 | G | ai.google.dev pricing (2026-07-08) |
| Gemini 3 Flash | Google direct | 0.50 | 0.05 | 3 | Explicit cache + storage $1.00/1M/hr | 0.16 🟢 | G | ai.google.dev pricing (2026-07-08) |
| gpt-5.4-nano | OpenAI direct / OR / NanoGPT | 0.20 | 0.02 | 1.25 | Automatic cache ~90% off | 0.06 🟢 | G | developers.openai.com; openrouter.ai/openai/gpt-5.4-nano |
| Grok 4.3 | xAI direct | 1.25 | ~0.125* | 2.50 | ~90% cached (inferred) | ~0.41 🟢* | G | aipricing.guru/xai |

---

## Cheapest-first routing order (per premium model)

**gpt-5.4 (the operator's in-window incumbent-under-test — not a finalized workhorse; per-tier selection pending real-code testing + real-outcomes benchmark #26) — all three top sources tie on sticker AND cache:**
1. **OpenAI direct** — $2.50 / $0.25 cached / $15. Safest for *guaranteed* automatic cache passthrough. Eff ≈ $0.81/1M input.
2. **NanoGPT (unpinned)** — same $2.50/$0.25/$15, "no % on top", passes cache. Ties #1. Avoid pinning a provider (+5%). Operator is already here — near-optimal.
3. **OpenRouter** — same $2.50/$0.25/$15, passthrough — *but* effective caching depends on which upstream provider the request routes to; a non-caching upstream silently drops you to $2.50/1M (3× worse). Prefer routing rules that keep it on a cache-capable upstream, or fall back to #1.
→ Net: keep gpt-5.4 on **first-party OpenAI direct OR NanoGPT-unpinned**; treat OpenRouter as equal-price-but-cache-uncertain.

**Frontier substitution when you want cheaper-than-gpt-5.4-but-still-closed-frontier:**
- **Grok 4.3 (xAI direct)** ~$0.41 eff input, $2.50 output — cheapest closed frontier-ish, if quality suffices.
- **Gemini 3.1 Pro (Google direct)** ~$0.65 eff input (ignoring cache storage) — cheap *only* if you actually use explicit context caching and the context is stable enough to amortize $4.50/1M/hr storage.

**Claude Opus 4.8 (when you specifically need Claude):** Anthropic direct is the only first-party path; eff ~$1.63–1.94 depending on write-premium exposure. There is no cheaper legitimate reseller for Claude that also passes caching. Push hit-rate high or it loses to gpt-5.4.

**Strong/mid, cheapest-first:** gpt-5.4-nano ($0.06) < Gemini 3 Flash ($0.16) < gpt-5.4-mini ($0.24) < Grok 4.3 ($0.41) < Gemini 3.5 Flash ($0.49) < Sonnet 5 intro ($0.65).

---

## KEY FINDING — cache passthrough: direct-with-cache beats cheaper-sticker-without-cache

On a **234:1 input-heavy** load, *whether the source passes through prompt caching matters more than the sticker price.*

- gpt-5.4 fresh input is $2.50/1M. **With** automatic caching at 75% hit it's **$0.81/1M** — a **3× swing** driven entirely by cache passthrough.
- **Automatic caching (OpenAI, and passthrough on OpenRouter/NanoGPT)** needs no code changes and no storage fee — best fit for a coding agent.
- **Anthropic** caching is powerful (read 0.1×) but carries a **write surcharge** (1.25× 5-min / 2× 1-hr) — only wins at sustained high hit rates; below ~50% it can *lose* to its own sticker.
- **Google Gemini** caching is **explicit** and adds **storage $/1M/hr** ($4.50 Pro, $1.00 Flash) — for rapidly-changing agent context the storage fee can eat the read discount; only cache stable prefixes.
- **The gotcha:** an aggregator that shows the *same or lower* sticker but does **not** pass caching (or routes to a non-caching upstream) will *lose* to a first-party-direct-with-cache source on this workload — you'd pay $2.50 vs $0.81 for identical gpt-5.4 tokens. OpenRouter's multi-upstream routing is the concrete risk: sticker matches but cache behavior varies by which provider serves the call.

---

## Confidence / what could NOT be primary-verified

- **HIGH (primary-verified today):** OpenAI gpt-5.4 = $2.50/$0.25/$15 and the -mini/-nano tiers (developers.openai.com); OpenRouter gpt-5.4 sticker $2.50/$15 + caching-passthrough claim; NanoGPT "no markup + cache passthrough + 5% pin surcharge"; Gemini 3.1 Pro / 3.5 Flash / 3 Flash full sticker + cache + storage (ai.google.dev).
- **MEDIUM:** gpt-5.4 cached-read rate **via OpenRouter and NanoGPT** ($0.25) is *asserted* by their passthrough language, not shown as a per-source line item — the number is OpenAI's, and passthrough is claimed, but I could not read the aggregator's own cached line for gpt-5.4. NanoGPT gpt-5.4 not individually listed (only gpt-5.5 shown) — pricing inferred from its no-markup policy.
- **MEDIUM-LOW:** **Grok 4.3 cached-input rate** (~$0.125) is *inferred* from the ~90% discount confirmed on Grok 4.20; xAI's page did not give a 4.3 cached line. Grok 4 cached (~$0.30) likewise inferred.
- **LOW / NOT freshly verified:** **Anthropic** Opus 4.8 / Sonnet 5 / Fable 5 numbers come from the bundled claude-api skill model table (cached **2026-06-24**); the live pricing docs page **404'd on 2026-07-08**, so I could not re-confirm against a fresh primary fetch. Sonnet 5 intro pricing ($2/$10) is stated to expire **2026-08-31** — re-check after that. Cache multipliers (read 0.1×, write 1.25×/2×) are from the skill, consistent with Anthropic's published model but not re-fetched today.
- **Assumption-dependent:** every "effective $/1M" scales with the **75% hit-rate** assumption — re-run the formula for your measured hit rate before hard-coding a routing order.
