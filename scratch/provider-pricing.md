# Charon Provider Pricing — Flat-Rate vs Metered (with ToS-proxy stance)

**Compiled:** 2026-07-08. **Scope:** current, primary-source-first prices for the operator's provider list, with a hard focus on flat-rate / subscription options and the ToS stance on **proxying/reselling behind a gateway**.

> **Verification discipline:** prices below are from providers' own pricing/docs pages where possible (fetched live 2026-07-08). Where a page rendered client-side or only a secondary source was available, it is flagged in the Confidence section. Model rosters and free limits drift weekly — re-confirm before hardcoding.

> **ToS legend (gateway-proxy legitimacy):**
> - **GREEN** = resale/proxy explicitly allowed (or a plan tier that permits it exists).
> - **YELLOW** = fine for a single-user PERSONAL gateway; personal/individual-use clause makes proxying third-party traffic a violation.
> - **RED** = proxy/resale/account-sharing explicitly banned, OR no usable OpenAI-compatible API at all, OR trains on your data.

---

## 1. Normalized comparison table

| Provider | Pricing model | Headline price | Models covered | Rate / concurrency | ToS-proxy | Source (2026-07-08) |
|---|---|---|---|---|---|---|
| **Featherless** | **Flat / subscription (unlimited tokens)** | $10 Basic (≤15B) · **$25 Premium (any model)** · $100 Agent-Standard (≤229B, 256K ctx) · $200 Agent-Max (any). Business "Scale" from $75–$200/unit; Feather per-request from $25 credits (100 units) | 30,000+ open-weight HF models: DeepSeek, GLM, Kimi, Qwen, Llama, Mistral | Throttled by **concurrent units** (2 / 4 / 8), not RPM/TPM. Unlimited monthly requests | **Individual = YELLOW** (personal/prototyping only, resale → terminated no refund). **Scale = GREEN** (ToS explicitly permits "inference resale") | featherless.ai/docs/plans, featherless.ai/terms |
| **CommandCode** | Metered API behind a **paid plan gate** | **Provider plan $15/mo** (+card fee), $15 usage credit then **PAYG at underlying rates, no markup**. Coding/"Go" plans do NOT unlock the API | OpenAI + open-source models via `/chat/completions`; Claude models via `/messages` (wrong endpoint → 400) | Not published | YELLOW (documented option; no explicit proxy clause found) | commandcode.ai/docs/provider, commandcode.ai/pricing |
| **MiniMax** | **Flat "Token Plan"** + PAYG | **Token Plan $20/mo ≈ up to 12.5B tokens/mo** ("$20 = 10× Claude Pro"). Coding plans $10/$20/$50. PAYG M2: $0.255/$1.02 per 1M in/out | MiniMax-M2 / M2.x (204K ctx), MSA 1M-context, multimodal (first-party MiniMax models only) | PAYG M2.x: **500 RPM / 20M TPM**; Token Plan "individual interactive use," throttles at peak | **YELLOW/RED** — account is personal, "not provide any other person access" → single-user OK, proxying third-party banned | minimax.io/price, platform.minimax.io/subscribe/token-plan, minimax.io/terms-of-service-v2 |
| **SiliconFlow** | **Metered PAYG (postpaid)** | $1 free credit. DeepSeek-V4-Flash **$0.13/$0.28**; V3.2 $0.27/$0.42; V4-Pro $1.6/$3.135; Qwen3.5-9B $0.1/$0.15; Qwen3.5-122B-A10B $0.26/$2.08; GLM-5 $0.95/$2.55; Kimi-K2.5 $0.45/$2.25 | DeepSeek, Qwen, GLM (Z.ai), Kimi (Moonshot). **No Llama on pricing page** | Monthly spend caps set in dashboard; RPM not published on pricing page | YELLOW (no explicit resale clause reviewed; China-based — verify data/ToS) | siliconflow.com/pricing |
| **Trae.ai** | Subscription (IDE/agent), token-credit metered | Lite $3 · Pro $10 · Pro+ $30 · Ultra $100/mo | Bundled coding models via IDE/SOLO app | Metered "Basic + Bonus" token credits | **RED for gateway** — **no public OpenAI-compatible API**; IDE/SOLO agent-only, MCP for tools. Cannot be proxied | trae.ai, docs.trae.ai/ide/new-plans-and-billing |
| **DeepInfra** | **Metered PAYG** | DeepSeek-V3 **$0.32/$0.89**; V3.2 $0.26/$0.38; R1-0528 $0.50/$2.15; Qwen3-235B **$0.09/$0.10**; Llama-3.3-70B-Turbo $0.10/$0.32; Llama-3.1-8B $0.02/$0.05; Mistral-Nemo $0.02/$0.04 | DeepSeek, Qwen, Llama, Mistral, GLM, Kimi (broad open catalog) | Standard 1× / Priority 1.5×; no hard RPM published | YELLOW (metered, standard commercial terms — verify resale clause) | deepinfra.com/pricing |
| **Synthetic** | **Flat / subscription (no per-token)** | **$30/mo ($1/day)** pack. Extra concurrency = buy more packs | MiniMax-M3, Kimi-K2.7-Code, Nemotron-3-120B, gpt-oss-120b, Qwen3.6-27B, GLM-4.7-Flash, GLM-5.2 (all 128–512K ctx) + free embeddings | **500 req / 5h**, **1 concurrent per model** | **RED** (prior ToS review: §2.2 account-sharing ban + §4(vi) substitute-service ban; no-train/no-retention on data) | synthetic.new/pricing |
| **DeepSeek (direct)** | Metered PAYG (first-party) | deepseek-chat/reasoner (= **deepseek-v4-flash**): **$0.14 in (miss) / $0.0028 in (cache hit) / $0.28 out** per 1M. V4-Pro $0.435/$0.87. **5M free tokens on signup**. Legacy names deprecate 2026-07-24 | deepseek-chat (non-thinking), deepseek-reasoner (thinking) — first-party only | Standard API tiers | RED-ish — **data hosted in China**; ToS silent on resale; no off-peak discount on current V4-Flash page | api-docs.deepseek.com/quick_start/pricing |
| **Together** | Metered PAYG | DeepSeek-V3.1 $0.60/$1.70; V4-Pro $2.10/$4.40; R1 $3.00/$7.00; Qwen3-235B $0.20/$0.60; Qwen3.6-Plus $0.50/$3.00; Llama-3.3-70B ~$0.88 flat | DeepSeek, Qwen, Llama, and broad open catalog ($0.05–$9/1M) | Tiered by account; not on pricing page | YELLOW (commercial PAYG; verify resale clause) | together.ai/pricing (secondary: aipricing.guru) |
| **Mistral** | Metered PAYG + optional sub | Mistral Large **$2/$6** per 1M; batch −50%. Le Chat/Vibe Pro **$14.99/mo** (app, not API); student $5.99. Free tier w/ limited msgs | Mistral Large/Medium/Small, Codestral, Ministral, Magistral, Pixtral (first-party) | La Plateforme tiers; free "Experiment" 1 RPM-ish | YELLOW (API commercial OK; **free tier trains on data** — opt-in required) | mistral.ai/pricing |
| **Ollama (cloud)** | **Subscription (GPU-time metered under cap)** | Free $0 (1 concurrent, light) · **Pro $20/mo ($200/yr), 3 concurrent, 50× free** · Max $100/mo, 10 concurrent · Team TBD | 40,000+ community/open models; cloud-enabled incl. deepseek-v4-pro (level 4) | Session limits reset 5h, weekly limits reset 7d; measured in **GPU time** not tokens | YELLOW (no explicit resale ban found; credential-responsibility clause; personal-use posture) | ollama.com/pricing, ollama.com/terms |
| **OpenRouter** | **Metered marketplace** (pass-through) | Pass-through per-token + **5.5% credit-purchase fee (min $0.80)**; **5% BYOK** fee after 1M free req/mo. Free `:free` models (1,000 RPD after ≥$10 lifetime) | 400+ models, 60+ providers (all the big open models) | 20 RPM on free; per-model | YELLOW — aggregator/proxy is its purpose, **but reselling / competing service banned + anti-circumvention** (multi-account stacking = violation) | openrouter.ai/pricing |
| **NanoGPT** | **Prepaid credits, metered (low markup)** | Pay-per-prompt from prepaid balance; effectively low per-token. Example models $3/$6 per 1M; cheap open models from ~$0.02–0.14/1M | DeepSeek, Qwen, and broad open + closed catalog | Balance-bound; no subscription | YELLOW (prepaid; privacy-forward posture; verify resale clause) | nano-gpt.com/pricing |
| **HuggingFace** | Metered PAYG (pass-through, **no markup**) | Same rates as underlying provider, **no HF fee**. Free credits: **$0.10/mo free, $2/mo PRO ($9/mo PRO sub), $2/seat Team/Enterprise** | 200+ models across integrated providers (DeepSeek, Qwen, Llama, etc.) | Provider-dependent | YELLOW (router = provider ToS applies; HF adds no resale grant) | huggingface.co/docs/inference-providers/pricing |

---

## 2. Flat-rate options ranked by "unlimited-ness" AND legitimacy

1. **Featherless — Scale plan (GREEN, from ~$75–$200/unit/mo).** The ONLY flat-rate provider whose ToS **explicitly permits inference resale**. Unlimited tokens, throttled only by concurrent units, 30K+ open models incl. DeepSeek/GLM/Kimi/Qwen. This is the standout for a gateway that may serve more than one user. NOTE the individual $10/$25 plans are personal-only (resale = termination) — you must be on a Scale plan to be clean.
2. **Featherless — Premium $25/mo (YELLOW, personal).** Best raw value for a *single-user* gateway: any-model, unlimited tokens, 4 concurrent, no logging. Clean as long as it's just the operator behind it.
3. **MiniMax Token Plan $20/mo (YELLOW).** ~12.5B tokens/mo of first-party M2.x for $20 — enormous throughput, real API (500 RPM). But MiniMax-models-only and personal-account clause → single-user only, no third-party proxying.
4. **Ollama Cloud Pro $20/mo (YELLOW).** 50× free usage, 3 concurrent, big open models incl. deepseek-v4-pro; GPU-time-capped (not truly unlimited) but generous. No explicit resale ban found (weakest ToS evidence — verify).

Runner-up / avoid for flat-rate: **Synthetic $30/mo** is genuinely flat and no-train, but its ToS **bans account-sharing and substitute-service** → RED for a shared gateway; only viable single-user. **Trae** is RED (no API at all).

---

## 3. Cheapest metered per-token for the big open models ($/1M in/out)

| Model | Cheapest found | Provider |
|---|---|---|
| **DeepSeek V3 / V3.2** | **$0.26/$0.38** (V3.2) | DeepInfra |
| **DeepSeek V4-Flash / chat** | **$0.13/$0.28** (SiliconFlow) ≈ $0.14/$0.28 first-party | SiliconFlow / DeepSeek direct |
| **DeepSeek R1** | **$0.50/$2.15** (R1-0528) | DeepInfra |
| **Qwen3-235B** | **$0.09/$0.10** | DeepInfra |
| **Llama-3.3-70B** | **$0.10/$0.32** (Turbo) | DeepInfra |
| **Llama-3.1-8B** | **$0.02/$0.05** | DeepInfra |
| **Mistral-Nemo** | **$0.02/$0.04** | DeepInfra |
| **GLM-5** | $0.95/$2.55 | SiliconFlow |
| **Kimi-K2.5** | $0.45/$2.25 | SiliconFlow |

**DeepInfra is the metered price leader across open models.** SiliconFlow is close and adds GLM/Kimi. DeepSeek-direct is cheapest for its own models if China-hosting is acceptable.

---

## 4. Biggest ToS red flags (proxy/resale axis)

- **Featherless individual plans**: "for interactive use or prototyping by the purchaser; other purposes → subscription terminated, no refund." Resale requires the **Scale** tier. (The single most important nuance — the cheap $25 plan cannot legally back a multi-user gateway.)
- **Synthetic**: account-sharing ban + substitute-service ban → RED for gateway proxying.
- **Trae**: no OpenAI-compatible API exists → structurally unusable as a gateway upstream.
- **DeepSeek direct**: data hosted in China, ToS silent on resale — data-sensitivity red flag.
- **Mistral free tier**: trains on your data (opt-in). Paid API does not.
- **OpenRouter**: reselling/competing-service ban + anti-circumvention → multi-account free-tier stacking is a violation, not just a throttle.
- **MiniMax / Ollama**: personal-account / credential clauses → single-user only; proxying third-party traffic is out of bounds (Ollama's ban is implied, not explicit).

---

## 5. Confidence — what could NOT be fully verified from a primary source

- **Featherless plan table**: fetched from featherless.ai/docs/plans (primary). Consumer $10 Basic / $25 Premium confirmed by primary + secondary; the Agent $100/$200 and Scale numbers are primary-page but the resale clause wording came via a search snippet of featherless.ai/terms (not a full-page fetch) — **re-read the full ToS before relying on the "Scale permits resale" claim.** HIGH-VALUE, MEDIUM confidence.
- **Together per-token**: pricing came via secondary aggregators (aipricing.guru) because together.ai/pricing was not fetched clean. MEDIUM confidence — verify V3.1/Qwen numbers on the live page.
- **NanoGPT**: only a general per-token description + example ($3/$6) obtained; no clean per-model table fetched. LOW-MEDIUM confidence on specific model prices.
- **MiniMax Token Plan token cap**: "12.5B tokens/mo" and "$20 = 10× Claude Pro" are from the primary price page but the exact cap and whether the Token Plan (vs PAYG) is fully API-usable for all models needs a docs re-check. MEDIUM.
- **MiniMax / Ollama / SiliconFlow / DeepInfra / Together resale clauses**: not individually read verbatim — ToS classifications are inferred from account/personal-use language. MEDIUM.
- **DeepSeek off-peak discount**: prior baseline mentioned off-peak; the current V4-Flash pricing page shows **no off-peak discount** — likely removed with the V4 renaming. Treat "off-peak" as deprecated. MEDIUM-HIGH.
- **CommandCode**: $15/mo Provider plan + no-markup PAYG + open-model `/chat/completions` access CONFIRMED via docs; the prior "403 on /chat/completions" was the Go/coding plan, not the Provider plan. HIGH confidence.
- Everything from **featherless docs, synthetic.new/pricing, ollama.com/pricing, deepinfra.com/pricing, siliconflow.com/pricing, deepseek docs, HF docs, openrouter/pricing** = primary-source, HIGH confidence.
