# LongCat availability — is it CALLABLE via an API today?

Date: 2026-07-07
Method: read-only web research (WebSearch/WebFetch). No writes to Charon/gateway made.

## 1. What LongCat models actually exist

"LongCat-2.0" is real and freshly released — **not** a mix-up with LongCat-Flash.
Meituan's LongCat family, in order:

- `meituan-longcat/LongCat-Flash-Chat` (+ `-FP8`) — 560B total / ~27B active MoE,
  released mid-2026, weights-only on HuggingFace (see §2).
- `meituan-longcat/LongCat-Flash-Thinking` (+ `-FP8`) — reasoning variant, also
  weights-only on HF.
- `meituan-longcat/LongCat-Flash-Lite` — smaller variant, HF weights + own API
  (per Meituan's own X/Twitter account, has "unlimited quota" API access via
  the LongCat API page as of its announcement).
- **`meituan-longcat/LongCat-2.0`** — the new flagship: **1.6T total params,
  ~48B active (MoE), native 1M token context, LongCat Sparse Attention (LSA),
  MIT license.** Released/unveiled 2026-06-30. Trained + served entirely on
  domestic (Chinese) ASIC compute. Benchmarks itself against GPT-5.5 /
  Gemini 3.1 Pro on SWE-bench Pro (agentic coding focus).
  - Notable wrinkle: LongCat-2.0 had been running **anonymously for ~2 months**
    on OpenRouter under the stealth codename **"Owl Alpha"** before Meituan's
    reveal on 2026-06-30. Journalism (MarkTechPost, VentureBeat, Decrypt,
    SCMP, Yahoo Tech, KuCoin, etc.) all corroborate this same story.

So the operator's "LongCat-2.0" is exactly right — it's a real, officially
released, actively-served model, not vaporware and not confusable with
LongCat-Flash (an older, still weights-only sibling).

## 2. HuggingFace inference router (router.huggingface.co)

**Weights-only. NOT served by any HF Inference Provider.**

Fetched `https://huggingface.co/meituan-longcat/LongCat-2.0` directly — the
page states verbatim:

> "This model isn't deployed by any Inference Provider. 🙋 15 Ask for provider
> support"

Same status for `LongCat-Flash-Chat` / `-FP8` (open community "please add"
discussion threads exist — `huggingface/InferenceSupport` #4502 and #4972 —
asking Novita/Hyperbolic/Together to pick it up; unresolved).

**Conclusion: HF router is a dead end today.** Repo exists, no inference
endpoint. Charon cannot route to LongCat via `router.huggingface.co` right now.

## 3. Other OpenAI-compatible providers

### Meituan's own LongCat API Platform — CONFIRMED CALLABLE, OpenAI-compatible

- Base URL (OpenAI-compatible): `https://api.longcat.chat/openai`
- Also offers an Anthropic-compatible base: `https://api.longcat.chat/anthropic/`
- Endpoint: `POST https://api.longcat.chat/openai/v1/chat/completions`
- **Exact model id: `LongCat-2.0`** (case as shown in their own curl example)
- Auth: standard `Authorization: Bearer $LONGCAT_API_KEY`
- Example (from official docs):
  ```
  curl --location --request POST 'https://api.longcat.chat/openai/v1/chat/completions' \
    --header "Authorization: Bearer $LONGCAT_API_KEY" \
    --header "Content-Type: application/json" \
    --data-raw '{ "model": "LongCat-2.0", "messages": [...], "max_tokens": 1024,
                   "temperature": 0.7, "thinking": { "type": "enabled" } }'
  ```
- Max output: 131072 tokens (128K).
- Pricing: standard $0.75/M input, $2.95/M output; launch promo $0.30/M
  input, $1.20/M output; cached-context reads free.
- Signup: email-based (no phone-number requirement surfaced in research);
  international users explicitly supported for invoicing via
  `longcat-team@meituan.com`. Not obviously China-only, but it IS a Chinese
  platform (Meituan) — no independent confirmation yet that a non-Chinese
  card/email sails through with zero friction; worth a live signup test
  before committing.
- LongCat-Flash-Lite is also separately API-served per Meituan's own
  announcement (currently "unlimited quota," free tier planned).

### OpenRouter — MURKY, do not treat as a clean "LongCat" route

- The literal ids a naive integration would try — `meituan/longcat-2.0`,
  `meituan-longcat/longcat-2.0`, `meituan-longcat/longcat-2.0-preview` — all
  **404 with "not available"** on OpenRouter today. This matches the prior
  session's ground-truth check (`longcat-add-report.md`, 2026-07-07): a
  direct catalog pull from the 4-LOM host found 0 matches for
  `longcat`/`meituan`/`cat` among the live models.
- However, OpenRouter does have a live, real page at slug
  **`openrouter/owl-alpha`** — this is the (previously anonymous) stealth
  model journalists say is LongCat-2.0 underneath. Its own OpenRouter page
  does **not** mention "Meituan" or "LongCat" anywhere — no rebrand/redirect
  has happened on OpenRouter's side as of this check. So routing to it would
  mean trusting third-party journalism (not OpenRouter's own metadata) that
  the model behind that slug is LongCat-2.0, and stealth/cloaked slots can be
  swapped or retired without notice. **Not recommended as "the LongCat
  route" for Charon** — too fragile/unverifiable at the API-metadata level,
  even though it is technically callable today.
- No confirmed listing found for LongCat on Together, DeepInfra, Novita,
  Fireworks, or SiliconFlow in this research pass (searches turned up
  nothing; HF InferenceSupport threads are still open asking those
  providers to add it).

## 4. Bottom line for Charon

**CALLABLE-VIA-MEITUAN-LONGCAT-PLATFORM/LongCat-2.0**

There IS a real, official, OpenAI-compatible route today:
- Provider: Meituan's own LongCat API Platform
- Base URL: `https://api.longcat.chat/openai`
- Model id: `LongCat-2.0`
- Needs a new provider integration in Charon (this is not one of Charon's
  existing providers) — email signup + API key, standard bearer-token OpenAI
  wire format, so it should slot into Charon's existing OpenAI-compatible
  provider pattern with no protocol surprises.

It is **NOT** reachable via HuggingFace's inference router (weights-only,
zero inference providers attached) and **NOT** cleanly reachable via
OpenRouter under a labeled LongCat id today (only via the unverified,
unlabeled `openrouter/owl-alpha` stealth slot, which is not recommended).

Recommended action: treat as a genuine "add a new provider" ticket (Meituan
LongCat API Platform), not a same-provider catalog tweak on OpenRouter. Do a
live signup test first to confirm no China-only friction before building
the integration.
