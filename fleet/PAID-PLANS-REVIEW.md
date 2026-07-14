# Charon Paid-Account Decision Matrix

> **Model/provider roster + live status SUPERSEDED by `fleet/state/CG-MODEL-CANDIDATES.md` +
> `fleet/state/CG-PROVIDERS.md`.** **Kept in full** — the flat-vs-PAYG break-even math (§2, token/mo
> crossover points per plan) and the ranked recommendation reasoning (§3) are unique analysis not
> reproduced in the roster. NanoGPT-as-anchor is confirmed still live/dominant in the CG- docs;
> CommandCode remains plan-gated and Synthetic.new remains un-activated per the roster's current
> status — this doc's ranking logic still holds, just re-check current $ figures before acting.

**Compiled:** July 2026. **For:** operator's PERSONAL single-user Charon gateway (not reselling).
**Purpose:** pick which recurring/paid plan (if any) to buy, weighted to the operator's goals:
(1) stop opencode-zen metered balance-burn, (2) offload agent + coding work off Claude to cheap capable models, (3) **tool/function-calling is REQUIRED**, (4) value **flat, predictable** cost. Free tiers already staged (Groq, Cerebras, NeuralWatt-$1-credit, OpenRouter `:free`) cover low-stakes volume — so a paid account is for **OVERFLOW + higher-quality/coding models** when free tiers throttle or lack tools.

> Prices verified against official sources this pass (see FREE-TIER-ROUTING.md for the free-tier citations). Blended $/1M below assumes a **3:1 input:output** ratio (typical agent/tool-loop: heavy context, moderate generation): blended = (3·in + out)/4.

---

## 1. Decision matrix (one row per API-routable paid option)

| Option | Cost model | Models (tool-calling) | Context | Effective $/1M (blended) | Throttles / caps | ToS |
|---|---|---|---|---|---|---|
| **NanoGPT** *(already preset + keyed on 4-LOM)* | **$12/mo flat** — works **through the API, same quota as web** | **DeepSeek V4 Pro**, GLM 5.1, Kimi K2.6, MiniMax M2.7, Xiaomi MiMo V2.5/Pro (**tools ✅**); +605-model PAYG catalog | V4-Pro 1M | flat → **→$0/1M**; full V4-Pro quota ≈ **$50+/mo of direct value for $12** | **60M INPUT tok/week** (~8.5M/day; output not counted). **V4-Pro/GLM-5.1/MiMo-Pro burn quota at 2×** → ~30M effective input/wk on V4-Pro. Fair-use = **in-flight concurrency cap + burst limit, no hard RPD** | personal |
| **NeuralWatt** *(already owned key)* | **PAYG** (token OR $5/kWh energy) + optional flat subs (~$3/kWh, $ unpublished); $1 signup credit | GLM-5.2, **Kimi-K2.7-Code**, Qwen3.5-397B, Kimi-K2.6 +16 (all **tools ✅**) | 262K; GLM-5.2 **1.05M** | GLM-5.2 **$2.21**; Kimi-K2.7-Code **$1.71**; K2.6 $1.32; "Flex" spot ~½ off | RPM/concurrency **unpublished**; no-train; 24h cache retention | personal |
| **Synthetic.new** | **$30/mo flat** (key currently **402s — not activated**) | GLM-5.2, Kimi-K2.7-Code, gpt-oss-120b, Nemotron-3-Super-120B (**tools advertised, verify**) | GLM-5.2 512K | flat → **→$0/1M at volume** | **500 req/5h**, **$24/wk credit ceiling**, **1 concurrent/model** | personal-only |
| **opencode Go** | **$10/mo** → ~**$60/mo** usage cap | ~14 incl **DeepSeek-V4-Flash/Pro**, Qwen, GLM (OpenAI-compat → tools ✅ expected) | V4 = 1M | V4-Flash **$0.18** (same as direct); maxed cap ≈ **$0.03** | ~$12/5h, $30/wk, **$60/mo** dollar caps, then spill | personal |
| **CommandCode Provider** | **$15/mo + PAYG, zero-markup**, $15 credit **rolls over** | DeepSeek-V4-Pro + **Claude** + OpenAI/Google (OpenAI schema; tools implied) | model-dep | at underlying rates (no markup); Claude-at-cost | Go/Pro app-tiers 403 the API; **Provider only** | personal-only |
| **Featherless $25** | **$25/mo flat** unlimited tokens | any-size open-weight (40k HF: DeepSeek/GLM/Kimi/Qwen), **tools ✅** | model-dep | flat → **→$0/1M** | **4 concurrent** slots (no RPM/TPM) | personal-only |
| **Featherless $10** | **$10/mo flat** unlimited | **≤15B params only**, tools ✅ | model-dep | flat → →$0/1M | **2 concurrent** | personal-only |
| **DeepSeek direct** | **PAYG** | V4-Flash / V4-Pro (**tools ✅**) | **1M** | V4-Flash **$0.18**; V4-Pro $0.54 | none meaningful; **data in China** | personal |
| **OpenRouter** | **$10 one-time** (not monthly) + PAYG | Hy3-preview, Nemotron-1M, DeepSeek, gpt-oss (**tools per-model**) | Hy3 262K; Nemotron **1M** | Hy3 **$0.11**; +unlocks **1,000 `:free` RPD** | 20 RPM; `:free` 1,000/day | personal-only |
| **Gemini paid** *(manual-only)* | **PAYG** prepay | 2.5 Flash/Flash-Lite/Pro (**tools ✅**) | 1M | Flash **$0.85**; Flash-Lite $0.18; Pro $3.44 | paid tier **does NOT train** | personal |
| **⚠️ Mistral "Le Chat Pro" $14.99/mo** | subscription | **NONE via API** | — | **N/A — TRAP** | **Consumer chat app ONLY — NO API access** (same trap as CommandCode-Go). Charon **cannot** use it. **DO NOT BUY for the gateway.** | n/a |
| **Mistral La Plateforme** *(API — has `mistral` preset, NO key on 4-LOM yet)* | **FREE "Experiment" tier** + PAYG | Mistral Large, **Codestral** (coding), Small (**tools ✅**) | 128K+ | free tier $0; PAYG Codestral **$0.30/$0.90**, Large $2/$6, Small ~$0.20 | Free: **2 RPM / 500K TPM / ~1B tok/mo** (eval only; opt-in to data training) | personal |

Sources: NanoGPT https://nano-gpt.com/subscription + https://nano-gpt.com/blog/subscription-update-february-2026 (base `https://nano-gpt.com/api/v1`) · DeepSeek https://api-docs.deepseek.com/quick_start/pricing · Gemini https://ai.google.dev/gemini-api/docs/pricing (Flash $0.30/$2.50, Flash-Lite $0.10/$0.40, Pro $1.25–2.50/$10–15, paid = no-train) · NeuralWatt models.dev/providers/neuralwatt + portal.neuralwatt.com/pricing (GLM-5.2 $1.45/$4.50, Kimi-K2.7-Code $0.95/$4.00; no-train) · Synthetic https://synthetic.new/pricing + /rate-limits · Featherless https://featherless.ai/docs/plans · OpenRouter https://openrouter.ai/docs/api/reference/limits · opencode https://opencode.ai/docs/go/ · CommandCode https://commandcode.ai/provider.

---

## 2. Break-even analysis (flat-rate vs PAYG)

A flat plan at **$P/mo** beats PAYG once your monthly usage would cost **> $P** at PAYG rates. Crossovers (blended 3:1), so the operator can self-locate by volume:

| Flat plan | Beats PAYG above… | Comparator | Reading |
|---|---|---|---|
| **NanoGPT $12** | **~22M tok/mo** | vs DeepSeek-V4-**Pro** direct ($0.54 blended) | above ~22M tok/mo of V4-Pro, the $12 flat wins — and its quota ceiling (~120M input/mo, ~30M/mo effective on V4-Pro at 2×) is **~5–10× the break-even**, i.e. up to ~$50+/mo of direct V4-Pro value for $12 |
| **Synthetic $30** | **~14M tok/mo** | vs NeuralWatt GLM-5.2 PAYG ($2.21) | if you'd run >~14M tokens/mo of **frontier-open coding models**, flat wins |
| **Synthetic $30** | **~167M tok/mo** | vs DeepSeek-Flash PAYG ($0.18) | if DeepSeek-Flash quality suffices, you'd **never** reach this under the concurrency cap → DeepSeek cheaper |
| **Featherless $25** | **~12.5M tok/mo** | vs GLM-class PAYG (~$2) | similar to Synthetic; edge = 40k-model breadth, 4 concurrent |
| **Featherless $10** | **~100M tok/mo** | vs cheap ≤15B PAYG (~$0.1) | small models are already cheap PAYG → **rarely worth it** |
| **opencode Go $10** | **~55M tok/mo** | vs DeepSeek-Flash direct ($0.18) | below 55M tok/mo, **DeepSeek-direct is cheaper** (pay only for use); 55M–333M tok/mo, **Go's $10 flat wins** (6× leverage on V4-Flash); above ~333M it throttles → spill to DeepSeek |
| **CommandCode $15** | trivial ($15 rolls over) | zero-markup PAYG | never "wasted"; only edge is **Claude/DeepSeek-V4-Pro at cost** |

**Reality check on personal single-user volume:** one human driving one gateway, offloading agent/coding from Claude, realistically burns **~10–50M tokens/mo**. At DeepSeek-Flash ($0.18) or Hy3 ($0.11) that's **~$1–9/mo of PAYG** — *below every flat plan's break-even.* Flat-rate only pays off if you sustain **>~14M tok/mo specifically on frontier-open coding models** (GLM-5.2/Kimi-tier), or you simply want a **hard predictable ceiling** over absolute-lowest cost.

---

## 3. Ranked recommendation

### #1 single paid ANCHOR: **NanoGPT — $12/mo**
The strongest fit for all four goals, and it wins on a decisive practical edge: **it's already a Charon preset (`nanogpt`, base `https://nano-gpt.com/api/v1`) and already keyed on 4-LOM — zero integration work, and the subscription is immediately API-routable at the same quota as the web app** (unlike CommandCode-Go and un-activated Synthetic, which 402 the API).
- **Directly kills the zen balance-burn** (goal 1): a **fixed $12/mo** replaces open-ended metered Zen credits.
- **Serves the #1 model you want** (goals 2–3): **DeepSeek V4 Pro** included with **tool-calling ✅** — a stronger workhorse than opencode-Go's V4-Flash tier, at ~$0/1M marginal.
- **Huge headroom:** 60M input tok/week (~30M/wk effective on V4-Pro at the 2× rate) — a personal single user won't exhaust it; up to **~$50+/mo of direct V4-Pro value for $12**, and its fair-use is **concurrency + burst, no hard RPD wall** (friendlier than Synthetic's 500-req/5h + 1-concurrent).
- **Flat + predictable** (goal 4), and it keeps a 605-model PAYG catalog on the same key for anything outside the included set.

### Best "anchor + PAYG floor" combo (recommended structure)
1. **Anchor — NanoGPT $12/mo** → DeepSeek-V4-**Pro** workhorse (+ GLM-5.1/Kimi/MiniMax) for agent/coding, flat, already wired in.
2. **Floor — OpenRouter $10 one-time** → unlocks 1,000 `:free` RPD **and** ultra-cheap **Hy3-preview ($0.11)** + **Nemotron 1M-context** for overflow, variety, and long-research.
3. **Premium coding (owned) — NeuralWatt PAYG** → GLM-5.2 / Kimi-K2.7-Code when you want a different/stronger coder; no commitment, pay per use.
4. **Always-on floor — DeepSeek direct PAYG** → catches spillover when NanoGPT's weekly quota and free tiers are exhausted ($0.18 Flash / $0.54 Pro, 1M ctx, tools).

Total recurring: **$12/mo** (+ one-time $10). NanoGPT alone likely covers the operator's entire personal agent/coding load.

### Runner-up anchors (why NanoGPT beats each head-to-head for a V4-Pro workhorse)
- **vs opencode Go $10/mo:** similar price, but NanoGPT includes **V4-Pro** (Go's $60 cap is mostly V4-**Flash**; V4-Pro on opencode/Zen is markup-diluted), gives more effective Pro tokens, and needs **no new preset**. Go's edge is a dollar-denominated cap you can spill from — marginal here.
- **vs CommandCode Provider $15/mo:** CommandCode is zero-markup **PAYG** (you pay real V4-Pro rates → $15 ≈ 28M blended tokens), whereas NanoGPT's $12 flat delivers **4–5× more V4-Pro headroom**. CommandCode's only remaining edge is **Claude-at-cost via API** — buy it *only* if that specific access matters.
- **vs Synthetic $30/mo:** NanoGPT is **cheaper**, **includes DeepSeek V4 Pro** (Synthetic doesn't reliably), has a **higher effective token ceiling**, friendlier fair-use, and is **already active** (Synthetic's key currently **402s**). Synthetic wins only if you specifically want GLM-5.2/Kimi-K2.7-Code flat with no-train guarantees.
- **vs pure PAYG (DeepSeek direct):** DeepSeek-direct is cheaper only below **~22M tok/mo** of V4-Pro; above that NanoGPT's flat $12 wins, and its ceiling sits ~5–10× higher. Keep DeepSeek-direct as the spillover floor, not the anchor.

### Skip / manual-only
- **Featherless $10** (≤15B too weak for coding); **$25** only for 40k-model breadth at flat cost.
- **Synthetic $30** unless you want frontier-open coding models flat with no-train (and activate the sub first).
- **CommandCode $15** unless **Claude-at-cost** is the goal.
- **Gemini paid** — keep manual-only; occasional high-quality reach, no subscription.
- **⚠️ Mistral "Le Chat Pro" $14.99/mo — DO NOT BUY for Charon.** It's the **consumer chat app only, with NO API access** — the exact same trap as CommandCode's Go plan. It will never route through the gateway. **What Charon actually wants is the FREE Mistral La Plateforme API tier** (create a key at console.mistral.ai) — that's a **$0 addition to the FREE stack**, not a paid purchase: ~1B tok/mo, 2 RPM / 500K TPM, includes **Codestral** (→ coding pool) and **Mistral Large** (→ daily-driver/variety), function-calling ✅. Note the free "Experiment" tier requires opting into data training → personal-only. This does **not** change the paid #1 pick.

---

## 4. Sharpest trade-offs (one-liners)
- **NanoGPT $12 vs everything for a DeepSeek-V4-Pro workhorse:** wins on price + included-V4-Pro + already-integrated/keyed + API-ready + friendlier fair-use — the clear anchor. Only caveat: V4-Pro burns the input quota at **2×**, so effective V4-Pro headroom is ~30M input/wk (still far beyond personal single-user need).
- **NanoGPT vs Synthetic vs CommandCode:** NanoGPT $12 flat (V4-Pro included, ~120M input/mo) > CommandCode $15 zero-markup PAYG (~28M blended tok) > Synthetic $30 (no V4-Pro, tighter fair-use, key not activated) — for the operator's stated #1 goal.
- **opencode Go vs DeepSeek-direct:** Go wins **only if you'll use >~55M tok/mo** of DeepSeek; below that, direct PAYG is cheaper (no floor to fill). Go's ceiling is ~$60/mo of usage then it throttles.
- **Synthetic $30 vs the $10 combo:** you pay **3× more** for a higher concurrency-throttled ceiling and no-train guarantee on frontier-open models — worth it only at sustained high coding volume or if you value one fixed number over minimizing spend.
- **Synthetic's 1-concurrent/model + 500-req/5h** is fine for a single human but would choke any parallel/agent-fleet burst — pair it with Groq/Cerebras (free) for parallelism.
- **CommandCode's DeepSeek-V4-Pro-via-PAYG** offers nothing over **DeepSeek-direct** except bundled Claude access; skip unless Claude-at-cost matters.
- **NeuralWatt is your quietly-best owned asset:** top coding models (Kimi-K2.7-Code $1.71, GLM-5.2 $2.21 blended) with tool-calling and no-train, already keyed — no reason to buy a flat plan to get coding quality you already own on PAYG.

*Every price cited to an official/live source; re-verify before hardcoding — rates drift.*
