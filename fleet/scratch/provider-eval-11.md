# Provider Evaluation — Ticket #11 (freebuff.com, huggingface, together.ai, atlascloud.ai)

**Compiled:** 2026-07-07. Read-only research + assessment. No product changes.
**Scope:** evaluate 4 candidate providers for the Charon gateway against the existing catalog
(nanogpt, groq, cerebras, mistral, together, openrouter, neuralwatt, deepseek, opencode-zen +
fireworks/sambanova/replicate/xai/cohere/openai/perplexity/local presets).

---

## 0. Grounding (confirmed live, 2026-07-07)

**Code** — `/home/stack/code/charon/src/charon/providers.py` `PRESETS`:
- `together`: preset exists — `https://api.together.xyz/v1`, key_env `TOGETHER_API_KEY`.
- `huggingface`: preset exists — `https://router.huggingface.co/v1`, key_env `HF_TOKEN`, noted as
  an OpenAI-compatible chat-only router across many inference providers (`org/model[:provider|:fastest|:cheapest]` ids).
- `freebuff.com`, `atlascloud.ai`: **no preset** — not in code at all.

**Live 4-LOM production** (`ssh -i ~/.ssh/4lom stack@10.0.1.60`, container `charon-gateway-1`, `CHARON_HOME=/data`):
- `/data/secrets.json` keys present: `OPENCODE_ZEN_KEY, OPENROUTER_API_KEY, NEURALWATT_API_KEY,
  DEEPSEEK_API_KEY, NANOGPT_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY, MISTRAL_API_KEY,
  TOGETHER_API_KEY`. **No `HF_TOKEN`.**
- `/data/models.json` has an active `minimax-m3-together` entry (`provider: together`,
  `upstream_model: MiniMaxAI/MiniMax-M3`, `cost_rank: 120`) — confirms `together` is live and
  routing real traffic, not just a dormant preset.
- `/data/providers.json` (override file) only lists `opencode-zen, openrouter, neuralwatt, cerebras`
  — the others (incl. `together`) run on unmodified `PRESETS` defaults, which is why it doesn't
  appear there despite being active.

**Verdict on the "already integrated?" question:**
| Provider | Integrated? | Evidence |
|---|---|---|
| together.ai | **YES — fully live** | preset + keyed in `secrets.json` + active model routing real traffic |
| huggingface | **Code-ready, NOT activated** | preset exists, no `HF_TOKEN` anywhere on 4-LOM, no model references it |
| freebuff.com | **NO** | no preset, no code reference |
| atlascloud.ai | **NO** | no preset, no code reference |

---

## 1. Comparison table

| Provider | Integrated? | API | Pricing/Free tier | ToS-ok for gateway? | Unique models | Verdict |
|---|---|---|---|---|---|---|
| **freebuff.com** | No | **No official API** — free coding-agent product (CLI/web/chat), ad-supported. Only "API access" found is a community reverse-engineered proxy (`Freebuff2API`) that scrapes web tokens / CLI config and uses "stealth fingerprints" to impersonate the client | "5 free hours DeepSeek V4 Flash/day," ad-supported, no published rate-limit docs | **No — there is no legitimate API to have ToS for.** Only access path is circumvention (token scraping, fingerprint spoofing); the proxy repo explicitly disclaims official affiliation and "not production-ready" | None — DeepSeek V4/Kimi K2.6/MiniMax M2.7-M3 all already reachable via nanogpt/together/deepseek/openrouter | **SKIP (hard)** — no real API to integrate; would mean routing a public gateway product through a scraped/unofficial channel that can break or get blocked at any time, for zero net-new model access |
| **huggingface** | **Code-ready, unkeyed** | Yes — OpenAI-compatible `router.huggingface.co/v1`, Bearer `HF_TOKEN`, chat-only | Pass-through, **no HF markup** (same rate as underlying provider). Free credits are token, not tier: $0.10/mo (free acct), $2/mo (PRO $9/mo) — not a meaningful free tier | Ambiguous but likely fine — no explicit reselling clause found in official ToS (only informal community norms: "no reselling, one account per provider"); billing is pass-through to real provider accounts, structurally similar to OpenRouter's already-accepted aggregator model | Router spans 45,000+ models / 18+ inference partners on ONE key — could reach providers Charon hasn't individually keyed (Novita, Nebius, etc.) without new integration work per-provider | **CONDITIONAL / low-priority ADD** — zero code work (preset already ships), just needs an `HF_TOKEN`; value is breadth-of-last-resort, not price or exclusivity, and mostly overlaps what openrouter/nanogpt/together already reach |
| **together.ai** | **YES (already live)** | OpenAI-compatible `api.together.xyz/v1`, Bearer `TOGETHER_API_KEY` — already verified in prod | Standard PAYG (e.g. MiniMax M3 $0.30/$1.20 per 1M). No free tier | ToS §4.3(d) bans "transfer, distribute, resell, lease, license, or assign the Services... on a standalone basis," §4.3(c) bans competing-product use; default (non-ZDR) allows training use unless Zero-Data-Retention opted in. Same posture as Groq/OpenRouter already accepted for the operator's **personal single-user** gateway — fine as-is, not for third-party product traffic | 200+ open models (Llama/DeepSeek/Mixtral/MiniMax); mostly overlaps other integrated providers, but is already the specific route for MiniMax M3 | **N/A — already done.** Nothing to add; confirms the ticket's hint |
| **atlascloud.ai** | No | Yes — OpenAI-compatible `api.atlascloud.ai/v1`, Bearer auth, streaming confirmed (tool-calling not confirmed in docs pulled) | PAYG, no subscription, LLM range **$0.08–$1.70/1M**; no confirmed free tier | **Explicit red flag**: Acceptable Use Policy states *"Creating a thin wrapper for raw API resale is strictly prohibited"* and *"Atlas Cloud APIs cannot be exposed directly to end users without added value."* This targets Charon's exact architecture (an OpenAI-compatible proxy/wrapper) more directly than peers' generic no-resell clauses. Company looks legit (SOC I/II, HIPAA claims, positive Trustpilot) | DeepSeek/Qwen/GLM/MiniMax/Kimi/Claude/GPT/Gemini — all already reachable elsewhere; Doubao (ByteDance) is the one plausibly-new name but unconfirmed as otherwise-unavailable | **SKIP** — redundant catalog, no pricing edge, and the AUP's "thin wrapper" language is the sharpest ToS objection of the four candidates against building exactly what Charon is |

---

## 2. Ranked recommendation

1. **together.ai** — no action needed; already fully integrated and live (backs `minimax-m3-together`). Ticket item is closed by confirmation.
2. **huggingface** — cheapest possible "add": code is already merged (preset ships in `providers.py`), so this is purely an operator key-acquisition + pool-placement task, not a build ticket. Worth doing opportunistically for aggregator breadth, but low urgency — it mostly duplicates openrouter/nanogpt reach and its "free tier" is trivial ($0.10-$2/mo credit, not a capacity tier).
3. **atlascloud.ai** — SKIP. Would need a brand-new preset (~1-2hr effort) for a fully redundant model catalog, no free tier, and an AUP clause ("no thin wrapper for resale") that reads as a more pointed objection to Charon's proxy architecture than any already-accepted provider's ToS.
4. **freebuff.com** — SKIP (hard no). Not a real API — only access path found is reverse-engineered token scraping / client fingerprint spoofing via a third-party community proxy with no official affiliation or stability guarantee. Wrong risk profile for a gateway product, and offers no models unavailable elsewhere anyway.

**Net new work generated:** none required. `together` confirmed done; `huggingface` is a same-day operator task (get `HF_TOKEN`, drop in secrets.json, pick a pool) whenever breadth is wanted — no code ticket needed since the preset already exists.
