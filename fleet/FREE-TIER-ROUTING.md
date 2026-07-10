# Charon Free-Tier Stacked Routing — Provider Comparison & Pool Design

**Compiled:** July 2026 (v0.3.1 era). **Status:** research/design only — no product source changed.
**Scope:** verified free/cheap LLM API providers + a proposed tiered pool arrangement mapped onto Charon's pool model.

> **Verification discipline:** every numeric limit below is backed by an official source URL. Free-tier limits drift constantly — several numbers the operator recalled were **stale** and are corrected here. Where an official page renders its table client-side (Google) or 404s / ships a JS shell (some ToS pages), that is flagged and a corroborating source is named. Re-confirm live before hardcoding anything.

---

## 0. TL;DR headline corrections

| Operator's recalled figure | Verdict | Correct current number |
|---|---|---|
| Gemini Flash ~1,500 req/day | **STALE / WRONG** | Gemini **2.5 Flash = 250 RPD**; only **Flash‑Lite = 1,000 RPD**. (1,500 was Gemini **1.5** Flash.) |
| Groq ~14,400 req/day on 8B | **CONFIRMED** | Llama 3.1 8B Instant = **14,400 RPD** (but **6,000 TPM** is the real bottleneck) |
| OpenRouter ~1,000 req/day w/ $10 deposit | **CONFIRMED** | 1,000 `:free` RPD after **≥$10 lifetime** credit (else 50/day); 20 RPM always |
| Cerebras ~1M tokens/day | **CONFIRMED** | **1M TPD per model** — but free models are now `gpt-oss-120b`/`zai-glm-4.7`/`gemma-4-31b` (NOT Llama/Qwen), and RPM is only **5** |
| "~18,000+ req/day, $0/mo + one‑time $10" | **HOLDS (with nuance)** | see §7 — real sum ≈ **18k+ RPD**, but ~14.4k of it is Groq's small 8B model; tool‑capable large‑model capacity is only a few thousand/day |

---

## 1. Provider comparison table (free tiers unless noted)

| Provider | OpenAI base_url | Tools | Stream | Free limits (headline) | Trains/retains free data? | Resale/proxy allowed? |
|---|---|---|---|---|---|---|
| **Google Gemini** | `https://generativelanguage.googleapis.com/v1beta/openai/` | ✅ | ✅ | 2.5 Flash 10 RPM/**250 RPD**/250K TPM; Flash‑Lite 15/**1000**/250K; Pro 5/**100**/250K (per‑**project**) | **YES (free tier trains + human review)** | **No** (competing‑model + extraction ban) |
| **Groq** | `https://api.groq.com/openai/v1` | ✅ | ✅ | 8B 30 RPM/**14,400 RPD**/6K TPM/500K TPD; 70B 30/1000/12K/100K; L4 Scout 30/1000/30K/500K (per‑**org**) | **No** (contractual; optional zero‑retention) | **No** (no resell/sublicense) |
| **Cerebras** | `https://api.cerebras.ai/v1` | ✅ | ✅ | gpt‑oss‑120b / glm‑4.7 / gemma‑4‑31b each **5 RPM / 30K TPM / 1M TPD** | No (per privacy policy; not verbatim free clause) | Restricted (implied; AUP unverified verbatim) |
| **OpenRouter** | `https://openrouter.ai/api/v1` | ⚠️ per‑model | ✅ | 20 RPM; **1,000 `:free` RPD** w/ ≥$10 lifetime credit (else 50) | Upstream‑dependent (`:free` often logged/trained) | Aggregator OK; **reselling/competing service banned; anti‑circumvention** |
| **Mistral La Plateforme** | `https://api.mistral.ai/v1` | ✅ | ✅ | **Free "Experiment" tier:** 2 RPM / 500K TPM / **~1B tok/mo**; incl **Codestral** + Mistral Large | **YES on free tier** (must opt into training) | personal‑only (free = training opt‑in) |
| **Featherless** | `https://api.featherless.ai/v1` | ✅ | ✅ | **No free tier.** $10 Basic (≤15B, 2 concurrent) / $25 Premium (any model, 4 concurrent), flat unlimited tokens | **No — does not log prompts/completions** | Resale unverified verbatim (flat‑rate seat → check AUP) |
| **Synthetic.new** | `https://api.synthetic.new/openai/v1` | ⚠️ advertised, under‑documented | ✅ | $30/mo pack: **500 req/5h**, **$24/wk** credit ceiling, **1 concurrent/model** | **No — no train, no retention** | **No** (§2.2 account‑sharing + §4(vi) substitute‑service) |
| **DeepSeek (direct)** | `https://api.deepseek.com` (`/v1` optional) | ✅ | ✅ | **No free tier.** V4‑Flash $0.14/$0.28 per 1M; V4‑Pro $0.435/$0.87 | ToS silent (unverifiable); **data in China** | No explicit resale ban found |
| **opencode Zen / Go** | Zen `https://opencode.ai/zen/v1/chat/completions`; Go `.../zen/go/v1/...` | ⚠️ implied | ✅ | Go = $10/mo, ~$60/mo usage cap; Zen = PAYG credits | n/a (paid) | No explicit clause |
| **CommandCode Provider** | `https://api.commandcode.ai/provider/v1/` | ⚠️ implied | ? | **Provider plan only** ($15/mo+$1.01, $15 credit then PAYG no‑markup); **Go plan 403s the API** | n/a (paid) | n/a — documented option only |
| **Tencent Hy3 preview** | via OpenRouter `https://openrouter.ai/api/v1` | ✅ | ✅ | `tencent/hy3-preview` paid ~$0.07/$0.24; `:free` variant $0 | `:free` upstream may log | via OpenRouter ToS |

✅ = supported · ⚠️ = conditional/unconfirmed · legend: RPM=req/min, RPD=req/day, TPM=tokens/min, TPD=tokens/day.

---

## 2. Per-provider notes

### 2.1 Google AI Studio / Gemini — **personal-only, trains on free data**
- **Free limits (per project, reset midnight Pacific):** 2.5 Pro 5 RPM / 250K TPM / **100 RPD**; 2.5 Flash 10 / 250K / **250 RPD**; 2.5 Flash‑Lite 15 / 250K / **1,000 RPD**. 2.0 Flash/Flash‑Lite also free. Gemini 3 Flash preview free‑priced.
  - Source: https://ai.google.dev/gemini-api/docs/rate-limits (numbers render client‑side from AI Studio; corroborated by multiple 2026 trackers and Google's dev forum). Live dashboard: https://aistudio.google.com/rate-limit
  - Pricing / "free‑of‑charge" model list: https://ai.google.dev/gemini-api/docs/pricing
  - **"1,500 RPD" is stale** — that was Gemini **1.5** Flash. Free daily quotas were *cut* in late 2025 (2.5 Flash briefly ~20–50 RPD, settled to 250).
  - **Limits are per‑PROJECT, not per‑key** — adding keys does NOT add quota.
- **OpenAI‑wire:** base_url `https://generativelanguage.googleapis.com/v1beta/openai/`; **tool calling ✅ + streaming ✅**. Source: https://ai.google.dev/gemini-api/docs/openai
- **ToS landmine (critical):** free tier **uses your prompts+outputs to improve products** and *"human reviewers may read, annotate, and process your API input and output."* Paid tier does not. Also bans building competing models + reverse‑engineering. Source: https://ai.google.dev/gemini-api/terms + pricing page "Content used to improve our products = Yes" column.
  - **Verdict:** fine for the operator's PERSONAL single‑user gateway; **blocker for routing third‑party/product traffic** (data exposure + no clean proxy permission).

### 2.2 Groq — **best free host for a proxy on data grounds; small model is the RPD king**
- **Free limits (per org):** Llama 3.1 8B Instant 30 RPM / **14,400 RPD** / 6K TPM / 500K TPD; Llama 3.3 70B 30 / 1,000 / 12K / 100K; Llama 4 Scout 30 / 1,000 / 30K / 500K. Source: https://console.groq.com/docs/rate-limits
  - **14,400 RPD confirmed**, but **6,000 TPM on 8B is the practical throttle** (≈200 tokens/req sustained).
  - Model roster rotates — confirm Llama 4 Maverick / current models live.
- **OpenAI‑wire:** `https://api.groq.com/openai/v1`; tools ✅ + streaming ✅. Unsupported params: `logprobs`, `logit_bias`, `top_logprobs`, `N>1`, `temperature=0`→coerced. Source: https://console.groq.com/docs/openai
- **ToS:** *"Groq is not permitted to use Inputs or Outputs for training or fine‑tuning… unless instructed by Customer"*; optional zero‑retention setting. **BUT** *"Customer will not… sell, resell, sublicense, transfer, or distribute any of the Cloud Services"* + *"may not resell or lease access to its Account."* Source: https://console.groq.com/docs/legal/services-agreement
  - **Verdict:** best data posture of the free hosts; personal gateway ✅; **reselling banned** so product‑routing third‑party traffic on one key is a ToS violation.

### 2.3 Cerebras — **huge token/day, blazing fast, but 5 RPM & narrow model list**
- **Free limits (per model):** `gpt-oss-120b`, `zai-glm-4.7`, `gemma-4-31b` (vision) each **5 RPM / 30K TPM / 1M TPH / 1M TPD**. Source: https://inference-docs.cerebras.ai/support/rate-limits
  - **1M TPD confirmed** (per model, resets daily — not one‑time credit). **Corrections:** free list is now gpt‑oss/GLM/gemma (NOT Llama/Qwen); RPM only **5**, TPM only **30K** (older "30 RPM/60K" is stale). No published RPD → daily cap is token‑bound.
  - Context ~131K per model pages (some historical 8,192 free‑tier context caps reported — treat as volatile, verify at signup).
- **OpenAI‑wire:** `https://api.cerebras.ai/v1`; tools ✅ (https://inference-docs.cerebras.ai/capabilities/tool-use) + streaming ✅.
- **ToS:** no‑training per privacy policy (https://www.cerebras.ai/privacy-policy); proxy/resale clause **not verifiable verbatim** (cloud terms rendered as JS shell). Check AUP PDF directly before product use.
  - **Verdict:** superb for **batch/heavy** (token budget) and fast agent bursts; the 5 RPM cap limits rapid interactive loops.

### 2.4 OpenRouter — **the aggregator; $10 lifetime unlock is the key move**
- **Free‑model limits:** 20 RPM always; **50 `:free` RPD** if lifetime credit purchase < $10; **1,000 `:free` RPD** once you've bought ≥$10 (lifetime unlock — persists even if balance later drops). Source: https://openrouter.ai/docs/api/reference/limits
- **Free models (churns weekly):** gpt‑oss‑120b/20b, Gemma 4 31B, NVIDIA Nemotron 3 (up to 1M ctx), Poolside Laguna, Cohere North Mini Code, Qwen3 Coder, DeepSeek variants, Hy3‑preview. Live filter: https://openrouter.ai/models (price → free).
- **OpenAI‑wire:** `https://openrouter.ai/api/v1`; **tools per‑model** (not every free model supports them — filter), streaming ✅.
- **ToS:** it *is* an aggregator/proxy (using it as upstream is consistent), **but §7 forbids "reselling API access to Models or otherwise developing a competing service"** and **bans "bypassing or circumventing use limits"** — so multi‑account free‑tier stacking is a ToS violation, not just a throttle. Free models "may store or train on your Inputs" (upstream‑set). Source: https://openrouter.ai/terms
  - **Verdict:** essential fallback/variety hub; the $10 lifetime deposit is the single highest‑leverage spend. Product resale banned.

### 2.5 Featherless — **no free tier; $10/$25 flat unlimited, best data posture**
- **No free tier.** $10 Basic (≤15B params, 2 concurrent) / $25 Premium (any model, 4 concurrent) / Agent $100–$200. Flat‑rate **unlimited tokens**, throttled by **concurrent slots** not RPM/TPM. Source: https://featherless.ai/docs/plans
- **Models:** 40,000+ open‑weight HF models (DeepSeek/GLM/Kimi/Qwen/Llama). $10 tier capped at ≤15B; big models need $25+.
- **OpenAI‑wire:** `https://api.featherless.ai/v1`; tools ✅ + streaming ✅.
- **ToS:** *"Featherless does not log chats, prompts, or completions sent through our API… processed in real time and not stored."* Source: https://featherless.ai/docs/privacy-and-logging. Proxy/resale clause not verified verbatim (check https://featherless.ai/terms).
  - **Verdict:** strongest privacy story; good cheap‑paid floor for open‑weight variety at flat cost.

### 2.6 Synthetic.new — **$30/mo flat, best data posture, but personal-only ToS**
- **Plan reality:** $30/mo "Subscription Pack" — flat fee, **no per‑token billing**, but **"unlimited" is throttled**: **500 requests / 5 hours** per pack (regenerates ~5%/15 min), a **~$24/week underlying‑credit ceiling** (the real economic cap), and **1 concurrent request per model** (different models run in parallel; same‑model calls queue). Request weighting is model‑dependent — a `GLM-4.7-Flash` call ≈ 0.1 request, so the 500/5h budget stretches far on small models. **Stacking = buy more packs on your account, not more keys.** Embeddings are free/unmetered. Sources: https://synthetic.new/pricing , https://synthetic.new/rate-limits
  - **Effective $/1M:** flat $30 → marginal token cost → ~$0/1M at volume, but hard‑bounded by the 1‑concurrent‑per‑model cap (throughput‑starved for a busy multi‑user gateway) and the $24/wk credit regen. Great for a single interactive user.
- **Models (always‑on, live `/models`):** GLM‑5.2 (**512K ctx**, largest), GLM‑4.7‑Flash (small/fast), Kimi‑K2.7‑Code (256K, vision/code), Qwen3.6‑27B, MiniMax‑M3, NVIDIA Nemotron‑3 Super **120B**, gpt‑oss‑**120b**. `syn:large:text` / `syn:small:text` aliases auto‑route. DeepSeek/Llama appear in docs examples but were absent from the live list (roster rotates). Source: https://dev.synthetic.new/docs/api/models
- **OpenAI‑wire:** base `https://api.synthetic.new/openai/v1` (also `/anthropic/v1`); **streaming ✅**; **tool calling advertised** (drop‑in for Cline/Roo/OpenCode/Copilot) **but not explicitly documented** — validate a live `tools` request before depending on it. Source: https://dev.synthetic.new/docs/api/overview , https://docs.litellm.ai/docs/providers/synthetic
- **ToS (critical):** **favorable data** — *"we do not use prompts or completions… to train, fine‑tune… any models"* and *"We do not store model prompts or completions from the API without your explicit consent… deleted from our systems."* **BUT personal‑only:** §2.2 bans sharing/making your account available to third parties; §4(vi) bans developing a "similar, substitute, or competing" service; §4(iv) bans programmatic data extraction; §4.5 bans emulated Service environments. No verbatim "no reselling" line — the block is the *combined effect*. Sources: https://synthetic.new/policies/terms-of-service , https://synthetic.new/policies/privacy
  - **Verdict:** excellent flat‑rate **personal** floor with clean no‑train/no‑retain data; **NOT licensed to front external users' traffic** on one account → get enterprise terms for product. Get written confirmation before any product use.

### 2.6b Mistral La Plateforme — **free "Experiment" tier adds Codestral (coding) to the free stack**
- **⚠️ Trap to avoid:** **Le Chat Pro ($14.99/mo) is the consumer chat app — NO API access.** Charon cannot use it. What Charon wants is the **La Plateforme API**, which has a genuinely FREE tier.
- **Free "Experiment" tier:** **2 RPM / 500K TPM / ~1B tokens/month**, $0, for evaluation (not production SLA). Includes **all API models** — notably **Codestral** (code specialist, FIM support) and **Mistral Large** + Small. Source: https://docs.mistral.ai/deployment/ai-studio/tier + https://mistral.ai/pricing/
- **PAYG (if you outgrow free):** Codestral **$0.30 / $0.90** per 1M, Mistral Large $2 / $6, Small ~$0.20. Source: https://mistral.ai/pricing/
- **OpenAI‑wire:** base `https://api.mistral.ai/v1`; **function/tool calling ✅ + streaming ✅**.
- **ToS landmine:** the **free tier requires opting into having your data used for training** (phone verification also required). → **personal‑only**; paid tier does not train. Data in EU.
- **Charon status:** `mistral` preset already exists (`MISTRAL_API_KEY`), but **NO key on 4‑LOM yet** — operator must create one at https://console.mistral.ai. **Placement:** Codestral → coding/daily‑driver; Mistral Large → daily‑driver / fallback‑variety.

### 2.7 DeepSeek (direct) — **cheapest metered floor; V4 generation now**
- **Pricing (per 1M tokens):** `deepseek-v4-flash` $0.0028 cache‑hit / **$0.14** miss in / **$0.28** out; `deepseek-v4-pro` $0.435 in / $0.87 out. Source: https://api-docs.deepseek.com/quick_start/pricing
  - `deepseek-chat` (V3) / `deepseek-reasoner` (R1) names **deprecated 2026‑07‑24**, alias to V4‑Flash non‑thinking/thinking modes. No off‑peak discount on V4 currently (V3/R1 off‑peak scheme gone). 1M context.
- **OpenAI‑wire:** `https://api.deepseek.com` (`/v1` optional); tools ✅ + streaming ✅. Source: https://api-docs.deepseek.com/
- **ToS:** does not explicitly state train/retain (gap); no explicit resale ban; **data historically stored in China** (compliance flag for a product). No official free tier. Source: https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html

### 2.8 opencode Zen / Go — **$10/mo bundle → DeepSeek V4 + ~14 models**
- **Go:** $5 first month then **$10/mo**; ~14 models incl DeepSeek V4 Pro/Flash, Qwen, GLM, MiniMax. Dollar‑denominated caps ≈ $12/5h, $30/wk, **$60/mo** (medium confidence). base_url `https://opencode.ai/zen/go/v1/chat/completions`; model id `opencode-go/<model>`. Source: https://opencode.ai/docs/go/
- **Zen (PAYG credits):** DeepSeek V4 Pro $1.74/$3.48, Flash $0.14/$0.28 (+ limited‑time Flash Free). base_url `https://opencode.ai/zen/v1/chat/completions`. Note Zen marks up V4‑Pro vs DeepSeek‑direct (~4×). Source: https://opencode.ai/docs/zen/
- Tool calling implied by OpenAI‑compat, not explicitly documented.

### 2.9 CommandCode Provider — **documented option only, NOT a free primary**
- **Go plan 403s `/chat/completions`** (`upgrade_required`) — confirmed. **Provider plan** $15/mo + $1.01 fee → $15 credit then PAYG at underlying rates **no markup**. base_url `https://api.commandcode.ai/provider/v1/`, OpenAI schema. Source: https://commandcode.ai/provider , https://commandcode.ai/docs/provider
- Tool calling implied; **Cloudflare/User‑Agent 403 risk UNVERIFIED** (generic WAF behavior — see §9 note; Charon sets an explicit UA so the blank‑UA block is unlikely). A separate internal `alpha/generate` surface is *not* OpenAI‑compatible (LiteLLM issue #27582) — don't confuse the two.

### 2.10 Tencent Hy3 preview (Hunyuan 3.0) — **added per operator request**
- **What it is:** Tencent Hunyuan 3.0, open‑weights **preview** (HF `tencent/Hy3-preview`, released ~Apr 2026). **295B total / 21B active MoE**, configurable fast/slow reasoning, **256K context**. Strong **coding/agentic** tier: SWE‑bench Verified **74.4%**, briefly #1 on OpenRouter usage. Frontier‑adjacent (below Opus 4.6, ~GLM‑5/Kimi‑K2.5 class).
- **Served via OpenRouter** (already a Charon preset): `tencent/hy3-preview` paid ~**$0.07 in / $0.24 out** per 1M; `tencent/hy3-preview:free` at $0 (upstream may log). base_url `https://openrouter.ai/api/v1`; **tools ✅ + streaming ✅**, 262K ctx. Also first‑party Tencent Cloud (base URL unconfirmed). The launch free‑token window has expired; the persistent `:free` route remains listed.
  - Sources: https://openrouter.ai/tencent/hy3-preview , https://huggingface.co/tencent/Hy3-preview , https://artificialanalysis.ai/models/hy3
- **Placement:** its cheap paid rate + tool‑calling + strong coding = a **daily‑driver** candidate (cheaper than DeepSeek‑Pro), with `:free` in **fallback/variety**. Its 256K context also makes it a **batch/heavy** option. See §6.

---

## 3. Proposed Charon pool stack

Design honors: **OpenAI‑compat required everywhere**, **tool‑calling required for agent pools**, and Charon **already fails over across candidates on exhaustion/error**, so each pool is an ordered list. `PERSONAL` tags a candidate that is fine for the operator's own gateway but a ToS risk if Charon routes third‑party product traffic (see §8).

### Pool A — `daily-driver` (interactive/agent work, tool-calling MANDATORY)
| # | Provider · model | base_url | Why | Tag |
|---|---|---|---|---|
| 1 | **Groq · Llama 3.3 70B** (or Llama 4) | `api.groq.com/openai/v1` | 30 RPM (best interactive cadence), tools, fast, no‑train | ok‑both |
| 2 | **Cerebras · gpt-oss-120b** | `api.cerebras.ai/v1` | fastest tokens, strong agentic 120B, tools; 5 RPM caps bursts | ok‑both |
| 3 | **OpenRouter · `tencent/hy3-preview`** (paid) | `openrouter.ai/api/v1` | cheap ($0.07/$0.24), 74% SWE‑bench, 256K ctx, tools | ok‑both (cheap paid) |
| 4 | **Mistral · Codestral** (coding) | `api.mistral.ai/v1` | free 1B tok/mo, tools, code‑specialist (FIM) | **PERSONAL** (free trains) |
| 5 | **Gemini · 2.5 Flash** | `…/v1beta/openai/` | 250K TPM, tools+stream, but 250 RPD | **PERSONAL** (trains) |
| 6 | **DeepSeek · v4-flash** (floor) | `api.deepseek.com` | metered $0.14/$0.28, always‑on tools | cheap‑paid floor |

### Pool B — `background` (heartbeats, cron polls, cheap classification — high RPD, cheap, small OK)
| # | Provider · model | base_url | Why |
|---|---|---|---|
| 1 | **Groq · Llama 3.1 8B Instant** | `api.groq.com/openai/v1` | **14,400 RPD** — the RPD king; tools; watch 6K TPM |
| 2 | **Gemini · 2.5 Flash-Lite** | `…/v1beta/openai/` | 1,000 RPD, 15 RPM (**PERSONAL** — trains) |
| 3 | **OpenRouter · small `:free`** (gpt-oss-20b, Nemotron Nano) | `openrouter.ai/api/v1` | 1,000/day w/ $10 unlock |

### Pool C — `batch/heavy` (large-context / long research — high TPD)
| # | Provider · model | base_url | Why |
|---|---|---|---|
| 1 | **Cerebras · gpt-oss-120b / glm-4.7** | `api.cerebras.ai/v1` | **1M TPD per model**, 131K ctx |
| 2 | **OpenRouter · Nemotron 3** (`:free`) | `openrouter.ai/api/v1` | up to **1M context**, free |
| 3 | **OpenRouter · `tencent/hy3-preview`** | `openrouter.ai/api/v1` | 256K ctx, cheap, tools |
| 4 | **Gemini · 2.5 Pro/Flash** | `…/v1beta/openai/` | 250K TPM, 1M ctx (**PERSONAL**) |
| 5 | **DeepSeek · v4** (floor) | `api.deepseek.com` | 1M context, metered |

### Pool D — `fallback/variety` (breadth, non-critical)
| # | Provider · model | base_url | Why |
|---|---|---|---|
| 1 | **OpenRouter · any `:free`** (Qwen3 Coder, Gemma 4, Hy3‑preview:free) | `openrouter.ai/api/v1` | dozens of free models, one key |
| 2 | **Mistral · Large** (free tier) | `api.mistral.ai/v1` | free 1B tok/mo, tools (**PERSONAL** — free trains) |
| 3 | **Featherless** (if subscribed) | `api.featherless.ai/v1` | 40k open‑weight models, flat cost, no‑log |
| 4 | **NanoGPT / Chutes / Together** (existing presets) | provider default | extra breadth |

### Pool E — `cheap-paid floor` (all free exhausted — ordered by $/1M)
| # | Option | Effective cost | Notes |
|---|---|---|---|
| 1 | **DeepSeek v4-flash direct** | $0.14 / $0.28 per 1M | cheapest metered; China‑data flag |
| 2 | **OpenRouter `tencent/hy3-preview`** | ~$0.07 / $0.24 per 1M | even cheaper input; via existing preset |
| 3 | **opencode Go** | $10/mo, ~$60/mo cap | flat‑ish bundle incl DeepSeek V4 |
| 4 | **Synthetic.new** | $30/mo flat (500 req/5h, $24/wk cap, 1 concurrent/model) | no‑train/no‑retain; **personal‑only ToS**; 512K‑ctx GLM‑5.2 |
| 5 | **Featherless $25 Premium** | $25/mo flat | unlimited tokens, concurrency‑capped, no‑log |
| 6 | **CommandCode Provider** | $15/mo + PAYG | documented option; Go plan can't hit the API |

---

## 4. Key-acquisition checklist (operator does this — Charon can't self-provision)

| Provider | Where to get the key | One-time action |
|---|---|---|
| Google AI Studio | https://aistudio.google.com/apikey | create project |
| Groq | https://console.groq.com/keys | — |
| Cerebras | https://cloud.cerebras.ai/ → API Keys | — |
| OpenRouter | https://openrouter.ai/keys | **deposit ≥$10 (lifetime unlock → 1,000 free RPD)** |
| Mistral (La Plateforme API) | https://console.mistral.ai | free "Experiment" tier; **NOT** Le Chat Pro (app‑only); phone verify + training opt‑in |
| DeepSeek | https://platform.deepseek.com/api_keys | add credit (no free tier) |
| Featherless | https://featherless.ai/ | subscribe $10 or $25 first |
| Synthetic.new | https://synthetic.new | subscribe ~$30 *(pending)* |
| opencode Go/Zen | opencode.ai → auth via opencode CLI | $10/mo (Go) |
| CommandCode | https://commandcode.ai/provider | **Provider plan** ($15/mo) for API access |

---

## 5. Product-integration note

**Already a Charon preset — just configure key + pool placement (no code):**
`groq`, `openrouter`, `deepseek`, `opencode-zen`, `opencode-go`, plus `nanogpt`, `zai`, `chutes`, `together`, `mistral`, `fireworks`, `sambanova`, `replicate`, `xai`, `cohere`, `openai`, `huggingface`, `neuralwatt`, `perplexity`, `local`.
→ **Hy3 preview needs NO new preset** — it's a model *on* OpenRouter (`tencent/hy3-preview`).

**Needs a NEW preset in `src/charon/providers.py` (product ticket — normal gate/merge chain, NO fleet/SLOP/personal strings):**
- **Google / Gemini** — base `https://generativelanguage.googleapis.com/v1beta/openai/`
- **Cerebras** — base `https://api.cerebras.ai/v1`
- **Featherless** — base `https://api.featherless.ai/v1`
- **Synthetic.new** — base *(pending §2.6)*
- **CommandCode** — base `https://api.commandcode.ai/provider/v1/`

**User-Agent / Cloudflare (verification TODO — resolved):** Charon's outbound path sets an **explicit** User‑Agent (`charon-proxy/0.1` in `providers.py`/`discover.py`/`recommend.py`; a `_DEFAULT_UA` constant + client‑UA normalization in `proxy_server.py:499-510`), **not** the bare `python-urllib` default. So the specific blank/library‑UA Cloudflare 403 that reportedly hit CommandCode is **unlikely**. Residual risk: a strict WAF could still challenge a non‑browser UA string — if CommandCode 403s, the mitigation is to set a browser‑like UA for that provider preset. (Confirm `_DEFAULT_UA`'s value before relying on this.)

---

## 6. Where Hy3 landed (for operator confirmation)

**Concluded:** "Hy3 preview" = **Tencent Hunyuan 3.0 open‑weights preview** (295B/21B MoE, 256K ctx, strong coding/agentic). **Placed as a `daily-driver` candidate (#3)** via OpenRouter paid `tencent/hy3-preview` — it has tool‑calling, is frontier‑adjacent on SWE‑bench, and is *cheaper than DeepSeek*. Its `:free` variant sits in `fallback/variety`, and its 256K context also lists it in `batch/heavy`. **If the operator meant a different "Hy3"** (e.g. a preview on another provider), flag it — this is the dominant, confirmed match.

---

## 7. Does the "~18,000 req/day, $0/mo + one-time $10" thesis hold?

**Yes, with an important nuance.** Summing verified free RPD (one account each):

| Source | Free RPD |
|---|---|
| Groq Llama 3.1 8B | 14,400 |
| Groq Llama 3.3 70B | 1,000 |
| Groq Llama 4 Scout | 1,000 |
| Gemini 2.5 Flash + Flash‑Lite + Pro | 250 + 1,000 + 100 = 1,350 (PERSONAL) |
| OpenRouter `:free` (w/ $10) | 1,000 |
| Cerebras (token‑bound, ~few hundred practical @ 5 RPM) | ~few hundred |
| **Total** | **≈ 18,750+ RPD** |

- **Headline is real** (~18k+ RPD, **$0 recurring + one‑time $10 OpenRouter deposit**). But **~14,400 of it is Groq's small 8B model** (great for background/classification, weak for agent work). **Tool‑capable, larger‑model daily‑driver capacity is only ~4,000/day** (Groq 70B+Scout 2,000 + OpenRouter 1,000 + Cerebras + Gemini 1,350‑if‑personal).
- **Drop Gemini for a PRODUCT** (trains on data): subtract 1,350 → ~17,400 RPD, and daily‑driver tool capacity ~3,000/day.
- TPM/concurrency, not RPD, is often the real ceiling (Groq 8B 6K TPM; Cerebras 5 RPM).

---

## 8. Personal-vs-product boundary (the load-bearing distinction)

The entire free stack is **viable for the operator's PERSONAL single‑user gateway**. It is **NOT safe as a shipped product that routes other users' traffic through the operator's free keys**, because:
- **Reselling banned:** Groq (no resell/sublicense), OpenRouter §7 (no reselling API access / competing service), Cerebras (implied), Gemini (competing‑model ban).
- **Anti‑circumvention:** OpenRouter §7 explicitly bans "bypassing use limits" → multi‑account free stacking is a ToS violation.
- **Training exposure:** Gemini free + many OpenRouter `:free` upstreams train on / log prompts → routing third‑party data there is a privacy problem.
- **Product path:** ship Charon so each end‑user **brings their own keys**, or route product traffic only to **properly‑licensed/paid** providers (DeepSeek/Featherless/opencode/Synthetic within their ToS). Best data posture among cheap options: **Featherless (no‑log)** and **Groq (contractual no‑train + zero‑retention)** — but both still ban reselling, so BYO‑key remains the clean product model.

---

## 9. Top risks / outside-the-box flags

1. **Per‑key stacking needs multiple accounts → ToS violation.** Gemini limits are per‑**project**, not per‑key (extra keys add nothing). OpenRouter explicitly bans circumventing limits. Stacking is fine as *distinct providers under one account each*; multiplying accounts per provider is the landmine.
2. **ToS / training exposure.** Gemini free + OpenRouter `:free` = trained/logged. Fine personal, blocker for product third‑party traffic.
3. **Tool‑calling gaps.** Many OpenRouter `:free` models and small models lack reliable tools → cannot be agent‑pool primaries. Verified tool support: Gemini, Groq, Cerebras, DeepSeek, Hy3, Featherless. Keep agent pools to these.
4. **Free‑tier instability.** Gemini cut RPD ~6× in late 2025; Cerebras dropped Llama/Qwen for gpt‑oss/GLM; numbers render client‑side / churn weekly. **Presets must carry runtime‑configurable limits, never hardcoded numbers.**
5. **Personal‑vs‑product boundary** (see §8) — the single biggest constraint on turning this stack into shippable product routing.
6. **Concurrency/TPM ceilings hide behind RPD.** Groq 8B's 6K TPM and Cerebras' 5 RPM mean the "14,400/day" and "1M/day" headlines are only reachable with small requests / paced calls — size Charon's scheduler to TPM+RPM, not just RPD.

---

*Every factual limit above is cited to an official source URL. Re-verify before hardcoding — free tiers drift.*
