# Provider Review — 2026-07-10

Live-verified provider research for the Charon gateway (single-user, OpenAI-compatible, needs
concurrency + tool-calling). All prices/limits below were pulled live from official sources on
2026-07-10; URLs cited inline. Where a page showed a promo price, the promo is flagged.

Scope note: the current GLM flagship is **GLM-5.2** (1M context). GLM-4.6 references in older
notes are superseded.

---

## TASK 1 — Best source for GLM-5.2

### Comparison table

| Provider | Model of interest | Marginal $/1M (in / out) | Flat plan | Context | Concurrency | OAI-compat? | Data / ToS notes |
|---|---|---|---|---|---|---|---|
| **z.ai / Zhipu DIRECT** (maker) | GLM-5.2 | **$1.40 / $4.40** PAYG API | GLM Coding Plan: Lite $18 (~$12.60 promo), Pro $72, Max $160 — Lite ≈80 prompts/5h, ≈400/wk; Max ≈1600/5h, ≈8000/wk | ~200K (1M on some SKUs) | Not published (users report throttling after days) | PAYG API is OAI-compat; **Coding Plan is an Anthropic/Claude-Code–style endpoint** (coding tools, not a general OAI gateway) | First-party. Coding Plan is a per-seat coding subscription, awkward to fan out through a gateway |
| **synthetic.new** | GLM-5.2 (512K) | — | **$30/mo** ($1/day), 500 req/5h; $60/mo tier for more | 512K | **1 concurrent request per model** (buy packs to raise) — hard limit for a gateway | Yes | Open-weights only (GLM/Kimi/MiniMax/Qwen; no DeepSeek). Personal-use subscription |
| **opencode Go** | GLM-5.2 + DeepSeek + Kimi + MiMo + Qwen | — | **$10/mo** ($5 first mo). 3-layer cap: $12/5h, $30/wk, **$60/mo** | 1M (GLM-5.2) | Shared cap, single-stream oriented | Yes | Curated coding pool. Cheapest flat bundle that includes GLM-5.2 **and** DeepSeek |
| **opencode Zen** | GLM/DeepSeek/Kimi | pay-per-request, **zero markup** | $20 PAYG balance, $5 auto-topup | — | metered | Yes | Same catalog, metered instead of capped |
| **OpenRouter** | GLM-5.2 | **$0.42 / $1.32** (current 70%-off promo; base ≈$1.40/$4.40) | none (metered) | **1M** | High (multi-provider routing) | Yes; **Exacto** tool-calling mode | No train-on-data (BYO privacy), resale allowed. Built-in multi-provider failover |
| **Chutes.ai** | GLM-5.2 (also GLM-5 $0.95/$2.55, DeepSeek V3.2 ~$0.28/$0.42, Qwen from $0.08/$0.24) | **$1.40 / $4.40** | none (metered) | large | High (serverless) | Yes (`llm.chutes.ai/v1`) | Decentralized serverless; cheap DeepSeek/Qwen |
| **Ollama Cloud** | GLM-5.2 / DeepSeek V4 Pro / Kimi | GPU-time metered | Pro **$20/mo**, Max $100/mo | model-dep | 5h-session + weekly caps; DeepSeek 60 RPM bottleneck | Yes | Subscription = GPU-time, not tokens. Rate caps hurt concurrent agents |
| **NeuralWatt** | GLM-5.2 | energy-metered **$5/kWh** flat (~$3/kWh on subscription) — **rates rising toward $10/kWh** | optional subscription | 256K | metered | Yes (`api.neuralwatt.com/v1`) | Zero markup across models; energy billing is hard to predict per-token |
| **devin.ai** | — | n/a | ACU billing $2.25/ACU | — | — | **NO** | **Not a model API** — autonomous agent product only. **DROP.** |

Sources: [z.ai subscribe](https://z.ai/subscribe) · [z.ai API pricing](https://docs.z.ai/guides/overview/pricing) · [aipricing.guru GLM plan](https://www.aipricing.guru/z-ai-subscription-pricing/) · [synthetic pricing](https://synthetic.new/pricing) · [opencode Go](https://opencode.ai/go) · [opencode Zen](https://opencode.ai/zen) · [OpenRouter GLM-5.2](https://openrouter.ai/z-ai/glm-5.2) · [Chutes pricing](https://chutes.ai/pricing) · [Ollama pricing](https://ollama.com/pricing) · [NeuralWatt pricing](https://portal.neuralwatt.com/pricing) · [NeuralWatt GLM-5.2](https://portal.neuralwatt.com/models/glm-5.2) · [Devin pricing](https://devin.ai/pricing/)

### Ranking for a single-user OpenAI-compatible gateway (concurrency + tool-calling)

1. **OpenRouter** — best all-around GLM-5.2 endpoint *right now*. True metered, real concurrency,
   OAI-compatible, Exacto tool-calling, built-in multi-provider failover. Currently the cheapest
   effective token price too, at $0.42/$1.32 during the 70%-off promo (undercuts everyone; even at
   base $1.40/$4.40 it ties Chutes/z.ai but adds failover).
2. **opencode Go ($10/mo)** — best *flat-rate bulk* value: GLM-5.2 **plus** DeepSeek/Kimi/MiMo in one
   $10 sub, if you stay under the $60/mo cap and don't need heavy parallelism.
3. **Chutes.ai** — best metered *overflow*: GLM-5.2 at $1.40/$4.40, plus very cheap DeepSeek/Qwen.
4. **z.ai direct** — first-party GLM, but PAYG is priced identically to Chutes and the cheap Coding
   Plan is an Anthropic-endpoint coding subscription (not a clean OAI gateway feed) with unpublished
   concurrency.
5. **NeuralWatt** — works, zero-markup, but energy billing is unpredictable and rates are climbing
   ($5→$10/kWh); keep as a tertiary overflow.
6. **synthetic.new** — good open-weights flat sub, but **1-concurrent-per-model** cripples gateway
   fan-out; only worth it if you buy multiple packs.
7. **Ollama Cloud** — GPU-time caps + 60 RPM DeepSeek bottleneck make it weak for concurrent agents.
8. **devin.ai** — not an API. Dropped.

### VERDICT
- **Single BEST GLM-5.2 source:** **OpenRouter** (`z-ai/glm-5.2`) as the primary metered feed —
  OAI-compatible, concurrent, tool-calling, multi-provider failover, currently cheapest at
  $0.42/$1.32 (base ≈$1.40/$4.40). If you prefer a flat cap over metered, **opencode Go $10/mo** is
  the cheapest bundle that includes GLM-5.2.
- **Best OVERFLOW source:** **Chutes.ai** (metered GLM-5.2 $1.40/$4.40 + dirt-cheap DeepSeek/Qwen),
  with **NeuralWatt** as a tertiary fallback.

---

## TASK 2 — Unreviewed providers

- **haloon.ai — SKIP.** All-in-one consumer aggregator skewed to *video* models (Sora 2, Veo 3.1,
  Seedance, MiniMax). API is credit-metered behind Expert/Max plans (only ~€4 API credit) with no
  standalone OpenAI-compatible coding-model endpoint and no GLM/DeepSeek focus. Not a gateway feed.
  [haloon.ai](https://haloon.ai/)
- **nousresearch (Nous Portal) — SKIP.** OpenAI-compatible catalog (300+ models incl.
  DeepSeek/Qwen/Hermes, Plus $20/mo + $22 rollover credits) but it is **powered by OpenRouter** — a
  thin reseller with markup. No advantage over hitting OpenRouter directly; Hermes models are niche.
  [Nous Portal](https://portal.nousresearch.com/api-docs) · [model ref](https://www.llmreference.com/provider/nous-portal/models)
- **Chutes (chutes.ai) — ADD.** Real OpenAI-compatible serverless API (`llm.chutes.ai/v1`). Broad
  open-weights catalog: GLM-5/5.1/5.2, DeepSeek V3.2 (~$0.28/$0.42), Kimi K2.5, Qwen from
  $0.08/$0.24. Metered per token. Strong cheap-overflow slot (esp. DeepSeek/Qwen).
  [Chutes pricing](https://chutes.ai/pricing) · [models](https://chutes.ai/models)
- **Trae (trae.ai) — SKIP.** ByteDance AI **IDE**, not a model API. Subscription IDE ($3 Lite /
  $10 Pro / $20 SOLO) with token-credit metering *inside the IDE*; supports BYO custom models via API
  keys but does not sell an OpenAI-compatible model API to route through a gateway.
  [Trae pricing](https://www.trae.ai/pricing) · [docs models](https://docs.trae.ai/ide/models)

---

## TASK 3 — CommandCode $15/mo "Provider" API plan — re-assessment

**Facts (verified):** Provider plan is **$15/mo + processing fee**, "pay-as-you-go, zero markup,"
with **OpenAI- and Anthropic-compatible endpoints**. Standout deals: **DeepSeek V4 Pro permanently
~75% off (credits stretch 4×)** and **MiMo V2.5 ~5×**; also Qwen 3.7 Max, MiniMax M3, Claude Opus 4.8.
Pro tier ≈25K requests/mo. Credits roll over / never expire. From 2026-09-01 standard token pricing
is $3 in / $15 out / $0.30 cache-read.
[CommandCode pricing](https://commandcode.ai/pricing) · [pricing limits](https://commandcode.ai/docs/resources/pricing-limits)

**Key gap:** CommandCode's catalog has **no GLM-5.2** — it does not compete for the operator's GLM
question at all. Its edge is purely DeepSeek/MiMo economics.

**VERDICT: STILL-A-GO (scoped).** Worth adding *specifically as the cheapest DeepSeek V4 Pro + MiMo
V2.5 source* — the permanent 4×/5× credit multipliers make it cheaper for DeepSeek-class work than
Chutes' already-low DeepSeek metered rate, and it's zero-markup OAI-compatible. It is **not** a GLM
source and should not be positioned as one. **Drop it only if** you decide not to route any
DeepSeek/MiMo-class work; otherwise keep the $15 Provider plan as the DeepSeek/MiMo lane, with
Chutes as the GLM/Qwen overflow and OpenRouter as the primary GLM-5.2 feed.
