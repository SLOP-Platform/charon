# Provider best/cheapest PER MODEL — canonical routing reference

**Purpose (operator, 2026-07-10):** the CANONICAL "who is best/cheapest for each model" table so we
STOP re-analyzing providers every session. This drives `cost_rank` in the gateway pools and the
drain-then-park order. Source of truth for prices/limits = `fleet/reviews/PROVIDER-REVIEW-2026-07-10.md`
(live-verified, URLs cited) + `fleet/FREE-TIER-ROUTING.md`. Promo prices flagged; re-verify promos before relying.

## Standing strategy (funding-class first, then cheapest-capable)
- **Flat-rate anchors (marginal ~$0 → routine volume):** opencode-Go $10/mo (GLM-5.2 + DeepSeek + Kimi + MiMo, $60/mo cap), NanoGPT $12/mo.
- **Drain finite prepaid credit cheapest-first** before adding new spend: OpenRouter, DeepSeek-direct, Together.
- **Metered overflow:** Chutes (cheap DeepSeek/Qwen/GLM), then NeuralWatt (energy-metered, rates RISING $5→$10/kWh → tertiary only).
- **Scoped lane:** CommandCode $15/mo = the DeepSeek-V4-Pro (4× off) + MiMo (5× off) source ONLY (no GLM).
- **DROPPED / do-not-add:** Synthetic ($30, 1-concurrent-per-model kills gateway fan-out), haloon (video aggregator), Nous Portal (OpenRouter reseller), Trae (an IDE), Devin (agent product, no API), Ollama Cloud (GPU-time + 60 RPM DeepSeek cap).

## Per-model routing (primary = cheapest capable with real concurrency)
| Model | PRIMARY (best value + concurrency) | Flat-bundle alt | Overflow | Gateway suffixes | Notes |
|---|---|---|---|---|---|
| **GLM-5.2** | **OpenRouter** `z-ai/glm-5.2` $0.42/$1.32 promo (base $1.40/$4.40), 1M ctx, Exacto tools, failover | opencode-Go ($10) | Chutes $1.40/$4.40 → NeuralWatt | `-or -go -ng -hf -nw -cline` | **Do NOT buy Synthetic.** OpenRouter already wired. |
| **GLM-5.1 / GLM-5** | NanoGPT (incl) / OpenRouter | opencode-Go | Chutes (GLM-5 $0.95/$2.55) | `-ng -or -hf` | superseded by 5.2; keep only if pinned |
| **DeepSeek V4 Pro** | **CommandCode** (4× off, once keyed) → DeepSeek-direct $0.435/$0.87 | opencode-Go / NanoGPT | OpenRouter → Chutes (V3.2 ~$0.28/$0.42) | `-go -ng -or -ds -cline` | live pool primary today = `-go` |
| **DeepSeek V4 Flash** | DeepSeek-direct $0.14/$0.28 | opencode-Go / NanoGPT | Chutes → OpenRouter | `-go -ng -hf -or -ds -cline` | cheapest raw = direct |
| **MiMo V2.5** | **CommandCode** (~5× off, once keyed) | NanoGPT (incl, 2× rate) | — | — | CommandCode's standout deal |
| **MiniMax M3** | Together.ai $0.30/$1.20 | — | OpenRouter | `-together` | already in `auto` pool |
| **Kimi K2.x-Code** | NeuralWatt / NanoGPT | opencode-Go | Chutes (K2.5) | — | coding-strong |
| **Qwen 3.x** | **Chutes** from $0.08/$0.24 (cheapest) | NanoGPT | OpenRouter | — | Chutes is the Qwen value leader |
| **gpt-oss-120B / Gemma-4** | **Groq / Cerebras FREE** | — | OpenRouter `:free` | `free-groq free-cerebras` | free rate-limited; light work only |
| **Claude (Opus/Sonnet/Haiku)** | CommandCode (zero-markup) / OpenRouter | NanoGPT `-ng` | — | `-go -ng -or` | premium-gated; not routine |

## What each provider is BEST at (one-liner)
- **OpenRouter** — best GLM-5.2 feed + universal metered failover hub (already the $10-lifetime-unlocked aggregator).
- **opencode-Go $10** — cheapest FLAT bundle spanning GLM-5.2 + DeepSeek + Kimi + MiMo (stay < $60/mo cap).
- **NanoGPT $12** — flat anchor for DeepSeek-Pro/GLM-5.1/Kimi/MiMo/MiniMax routine volume.
- **CommandCode $15** — cheapest DeepSeek-V4-Pro + MiMo lane (permanent 4×/5× credit multipliers).
- **Chutes** — cheapest metered overflow for Qwen + DeepSeek + GLM.
- **DeepSeek-direct** — cheapest raw DeepSeek V4 Flash/Pro tokens (prepaid credit → drain).
- **Groq / Cerebras** — free gpt-oss-120B / Gemma-4 for light work.
- **NeuralWatt** — tertiary zero-markup overflow; DECLINING (energy rates rising).

## Pending (operator subscribing 2026-07-10)
- **Chutes** — signing up; wire `llm.chutes.ai/v1` + key when provided → set as Qwen/DeepSeek/GLM overflow.
- **CommandCode $15/mo Provider** — signing up; wire OAI endpoint + key → set as DeepSeek-Pro/MiMo primary.
