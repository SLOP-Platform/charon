# Best provider stack for Charon — "closest to unlimited" recommendation

**Synthesized:** 2026-07-08 from usage-profile.md, provider-pricing.md, six-provider-verify.md, active-providers.md.
**Question:** what provider stack gets the operator's Charon gateway closest to "UNLIMITED" for their ACTUAL demand, weighted by ToS-legitimacy and cost.

---

## 1. Demand extrapolation (sizing the target)

**Observed (19h in-memory window, single container):**
- 18,890,932 tokens IN / 80,580 tokens OUT → **~234:1 input:output**.
- $7.462376 real metered cost (100% openrouter).
- ~122 serves, ~155k in-tokens per serve, ~660 out-tokens per serve → a coding-agent (opencode/droid Build) shape: huge repo context, tiny completions.

**Steady-state monthly estimate.** Assumptions: the 19h slice is an *active Build burst*, single-tenant and bursty — not every hour of the month runs this hot. So I bracket rather than point-estimate.

| Basis | Extrapolation | Monthly figure |
|---|---|---|
| 19h metered pace held continuously (30d) | $7.46 × (720h / 19h) = ×37.9 | **~$283/mo cash**, ~716M in / ~3.05M out tokens |
| Discounted for bursty/idle (~25–35% duty) | ~×26 | **~$195–$220/mo cash**, ~500–570M in tokens |
| 8-day persisted aggregate $221.84 (includes est_cost for free serves) | ×3.75 | **~$832/mo economic-value UPPER BOUND** (NOT pure cash) |

**Working numbers for the stack:** treat the target as **~500–720M input tokens/mo** at **~$200–285/mo real cash** under today's routing, with **$832/mo as the economic-value ceiling**. The load-bearing fact for provider choice: **it is input-heavy (234:1)** — so a provider that prices *input* cheaply, or flat, wins disproportionately. There is **no per-model ledger**, so this is aggregate-only; confidence MEDIUM on the monthly number, HIGH on the shape.

---

## 2. The capability catch (surface it explicitly — this is the pivot)

The in-window incumbent is **`gpt-5.4`** — an **incumbent-under-test**, not a chosen workhorse (its observed dominance was ONE long test session; **no model is finalized for any tier**, selection pending real-code testing + the real-outcomes benchmark #26) — and the only providers that serve it are **openrouter / nanogpt** (metered marketplaces). **Every flat-rate "unlimited" provider serves OPEN models only** — Featherless / MiniMax / Ollama Cloud front DeepSeek / GLM / Qwen / Kimi, **not gpt-5.4**.

**Therefore "closest to unlimited" almost certainly requires moving the coding workhorse off gpt-5.4 onto an open model on a flat-rate host.** Whether that is acceptable is a **QUALITY question, not a cost question**: does DeepSeek-V4 / GLM-5 / Qwen3 do the Build work as well as gpt-5.4? That is exactly what the operator's **real-outcomes benchmark pivot** (actuals ledger + reds-replay, ticket #26) is being built to answer.

**This dependency is not free and must not be assumed away.** The recommendation below is structured to *de-risk* the swap (run the open model as flat-rate primary while keeping gpt-5.4 as a metered escape hatch) rather than betting the whole load on an unproven substitution.

---

## 3. Candidate stacks

Each stack = tiers: **primary** (bulk load) / **metered-cheap spillover** / **free-quota + funded backstop**.

### Stack A — FLAT-RATE-first (open-model workhorse)
- **Primary:** Featherless **Premium $25/mo** — any open model, *unlimited tokens*, 4 concurrent units. Serve DeepSeek-V4 / GLM-5 / Qwen3 as the coding workhorse.
- **Spillover:** DeepInfra metered (Qwen3-235B $0.09/$0.10, DeepSeek-V3.2 $0.26/$0.38) when >4 concurrent.
- **Backstop:** groq (14.4k req/day), mistral, together (free) + neuralwatt $22 / deepseek $9.93 (funded).
- **Est $/mo:** **~$35–55** ($25 flat + light metered spillover).
- **Unlimited-ness:** HIGH on tokens (Featherless throttles *concurrency*, not tokens — ideal for 234:1 since input is effectively free). Wall = 4 concurrent units; parallel Build bursts queue.
- **ToS:** YELLOW single-user (Premium is personal-only). Multi-user → must move to Featherless **Scale** (GREEN, ~$75–200).
- **Models:** open only. **Full capability swap required — highest quality risk.**

### Stack B — METERED-cheap (keep gpt-5.4-class closed model)
- **Primary:** keep gpt-5.4 on **openrouter/nanogpt** (only backends that serve it), balance topped up. Optionally substitute a cheap open model on DeepInfra/SiliconFlow if quality permits.
- **Spillover:** SiliconFlow (adds GLM/Kimi), DeepSeek-direct ($0.14/$0.28, China-hosted).
- **Backstop:** same free + funded tier.
- **Est $/mo:** **~$200–285** keeping gpt-5.4 (current pace); **~$60–160** if swapped to cheap open on DeepInfra (Qwen3-235B ≈ 600M×$0.09 = ~$54 in).
- **Unlimited-ness:** MEDIUM — no hard wall, but *no cost ceiling either*; a Build burst just spends more. This is essentially today's model, cost-reduced.
- **ToS:** YELLOW single-user. OpenRouter is an aggregator (proxy is its purpose) but bans competing-resale + anti-circumvention.
- **Models:** keeps gpt-5.4 → **no capability swap**, but most expensive and least "unlimited."

### Stack C — HYBRID (flat-rate bulk + metered premium escape) ★ recommended
- **Primary (bulk input-heavy load):** Featherless **Premium $25/mo** flat — open workhorse (DeepSeek-V4 or GLM-5). Absorbs the ~500–720M input tokens for a fixed $25 (the 234:1 shape makes flat-rate a landslide win).
- **Premium escape hatch:** keep **gpt-5.4 on [nanogpt, openrouter] metered**, routed to *only* when a request explicitly needs the premium model — a small fraction of traffic. This keeps the capability swap *reversible* and A/B-testable against the benchmark before any full cutover.
- **Metered-cheap concurrency spillover:** DeepInfra (Qwen3-235B $0.09/$0.10, DeepSeek-V3.2 $0.26/$0.38) when Featherless's 4 concurrent units saturate.
- **Free + funded backstop:** groq / mistral / together (free headroom) + neuralwatt $22 / deepseek $9.93 (funded) as last-resort spillover.
- **Est $/mo:** **~$45–85** ($25 flat + ~$20–60 metered for premium escape + concurrency overflow).
- **Unlimited-ness:** HIGH — bulk load has no token wall; premium is on-demand; concurrency overflow is covered by metered; free/funded tiers backstop balance events.
- **ToS:** YELLOW single-user today (all tiers personal-OK). Multi-user → swap Featherless Premium for Scale (GREEN).
- **Models:** open workhorse **+ gpt-5.4 retained** as escape hatch → **capability swap de-risked, not forced.**

### Comparison

| | Stack A flat-first | Stack B metered | **Stack C hybrid ★** |
|---|---|---|---|
| Est $/mo | ~$35–55 | ~$200–285 (gpt-5.4) / ~$60–160 (swapped) | **~$45–85** |
| vs today (~$200–285) | ~5–7× cheaper | ~same / ~2× cheaper | **~3–5× cheaper** |
| Unlimited-ness | HIGH (concurrency wall) | MEDIUM (cost, no wall) | **HIGH** |
| Capability risk | HIGH (full swap) | LOW (keeps gpt-5.4) | **LOW–MED (swap reversible)** |
| ToS single-user | YELLOW | YELLOW | YELLOW |
| ToS multi-user | needs Scale | OpenRouter-only defensible | needs Scale |

---

## 4. Recommendation: **Stack C (Hybrid)**

**Rationale.** The demand is input-heavy (234:1) and single-tenant — the perfect profile for a flat-rate host that charges by *concurrency* rather than tokens, because the expensive dimension (input volume) becomes free. Featherless Premium at $25/mo collapses the ~$200–285/mo bulk cost to a fixed $25 while removing the token wall entirely. But the incumbent-under-test is `gpt-5.4` (not a finalized workhorse pick) and the open→gpt-5.4 quality equivalence is *unproven* (the whole reason the real-outcomes benchmark is being built), so Stack A's full swap is premature. Stack C keeps gpt-5.4 alive as a **metered escape hatch** — the operator runs the open workhorse as primary, measures it against gpt-5.4 on real Build outcomes, and only widens or narrows the escape hatch once the benchmark says so. Net: ~3–5× cheaper than today, "unlimited" for the bulk load, and the capability bet is hedged instead of forced.

**Concrete config changes** (`/data/providers.json` + pools):
1. **Add `featherless`** provider: base_url `https://api.featherless.ai/v1`, `key_env: FEATHERLESS_API_KEY`, on the **Premium $25** plan. (Provider is not yet in the preset registry — add via `/data/providers.json` override.)
2. **Add `deepinfra`** provider: base_url `https://api.deepinfra.com/v1/openai`, `key_env: DEEPINFRA_API_KEY` — cheap metered spillover (favor Qwen3-235B $0.09-in given the input-heavy shape).
3. **Create the bulk coding pool** (the workhorse alias the Build client actually calls, e.g. keep pointing opencode at its current model id but re-back it) with chain **`[featherless, deepinfra, neuralwatt, deepseek]`** — flat-rate first, cheap-metered second, funded backstop last.
4. **Keep the `gpt-5.4` pool as `[nanogpt, openrouter]`** but **top up openrouter balance** and route to it only for explicit premium requests — do NOT make it the default bulk target.
5. **Set `fallback_providers`** (currently `[]`) to include `groq, mistral, together, neuralwatt, deepseek` as global backstop so a balance event never dries a pool.
6. **Fix the outbound User-Agent** on the gateway proxy path to a browser-like UA — groq/cerebras/together return spurious Cloudflare `403 error 1010` on `Python-urllib`, which would make healthy funded backends look dead (from six-provider-verify.md).
7. Because of 234:1, **order every chain input-cheap-first** — flat (Featherless) → lowest input $/1M (Qwen3-235B $0.09, DeepSeek-V3.2 $0.26) → funded.

---

## 5. ToS verdict

- **Legitimately usable TODAY (single-user gateway, operator-only behind it):** Stack C as written is **clean under a YELLOW reading** — Featherless Premium (personal/prototyping by the purchaser), plus metered providers (DeepInfra/OpenRouter/nanogpt/DeepSeek) and the funded/free backstops are all fine for one operator. No GREEN plan is *required* while it is single-tenant.
- **If the gateway ever fronts more than the operator:** the Featherless Premium primary is **no longer legitimate** (individual plans: "for use by the purchaser … resale → terminated, no refund"). It must move to **Featherless Scale (GREEN, ~$75–200/unit)** — the *only* flat-rate provider whose ToS explicitly permits inference resale. MiniMax, Synthetic and Ollama are all out for multi-user (personal-account / account-sharing / substitute-service bans). Even OpenRouter, though an aggregator, bans building a competing resale service + anti-circumvention. So the multi-user-clean spine is **Featherless Scale + OpenRouter pass-through**, at materially higher cost (~$75–200 base).
- **Caveats to re-verify before committing:** Featherless "Scale permits resale" came from a ToS search snippet, not a full-page read (MEDIUM confidence) — re-read the full terms first. DeepSeek-direct is China-hosted (data-sensitivity), keep it as backstop only. Mistral's *free* tier trains on data — use paid/opt-out.

---

## Confidence
**MEDIUM-HIGH** on cost structure, the input-heavy lever, and ToS tiering. **The single load-bearing unknown is the capability swap** (does an open model match gpt-5.4 on real Build outcomes) — that is explicitly gated on the real-outcomes benchmark, and Stack C is chosen precisely because it hedges that unknown instead of betting on it. Monthly $ is MEDIUM (aggregate-only, no per-model ledger, one 19h window + one 8-day scalar).
