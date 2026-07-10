# Provider-questions verification (read-only)

Date: 2026-07-08 · Gateway: charon-gateway-1 @ 10.0.1.60 (up 23h, healthy) · No config changes made.

## Live config ground-truth (from /data on the gateway)

- **Configured providers** (`providers.json` + `secrets.json` keys): opencode-zen, openrouter, neuralwatt, cerebras, deepseek, nanogpt, groq, mistral, together, huggingface (HF_TOKEN). **opencode-go** is a built-in provider (sole entry in `fallback.json`), sharing `OPENCODE_ZEN_KEY`.
- **NOT present anywhere**: `featherless` (0 refs, no key) and `deepinfra` (0 refs, no key). The `-hf` legs = **HuggingFace** (HF_TOKEN), NOT Featherless. So the "layered stack" Featherless/DeepInfra legs are **design proposals, not live**.
- Provider suffixes in pools: `-ng`=nanogpt, `-or`=openrouter, `-go`=opencode-go, `-ds`=deepseek, `-hf`=huggingface, `-nw`=neuralwatt.
- **Reliability (`quality.json`)**: nanogpt 1.0 (45/45), together 1.0, groq 1.0, cerebras 1.0, deepseek 1.0, opencode-zen 1.0, **openrouter 0.6 (1/10 success!)**, neuralwatt 0.6 (0/4), huggingface 0.6, opencode-go 4/6. → Prefer nanogpt over openrouter wherever both serve a model.

---

## Q1 — opencode-go: real limits + keep/drop

**Real limits (OpenCode Go plan, verified from opencode.ai/docs/go):**
- Price: **$5 first month, then $10/mo.**
- Dollar-metered caps (not token/request): **5-hour = $12 of usage · weekly = $30 · monthly = $60.**
- 13 open coding models: GLM-5.2, GLM-5.1, Kimi K2.7 Code, Kimi K2.6, MiMo-V2.5(+Pro), MiniMax M3/M2.7, Qwen3.7 Max/Plus, Qwen3.6 Plus, DeepSeek V4 Pro/Flash.
- Capacity varies by model price: e.g. DeepSeek V4 Flash ≈ 31,650 req / 5h; GLM-5.2 ≈ 880 req / 5h.

**Headroom vs operator load (~18.9M input tok / 19h, 234:1 in:out → ~80K output):**
- On a cheap model (~$0.10–0.27/M in) that ~18.9M input ≈ **$2–5 of the dollar meter per 19h burst.**
- Per 5-hour window that's ~5M in ≈ **$0.50 — vs the $12 cap**: enormous headroom. Weekly $30 / monthly $60 only get tight under *sustained 24/7* heavy use on pricier models (~720M/mo → could exceed $60). Bursty single-user use = comfortable.

**Judgment: KEEP** (drain-first cheap leg).
- It is the **only** global fallback currently configured (`fallback.json = ["opencode-go"]`) and backs the `-go` free members + `big-pickle-go`.
- Featherless does **not** subsume it: (a) Featherless isn't live; (b) even if added, opencode-go brings coding-optimized endpoints (Kimi K2.7 Code, MiMo-Pro), concurrency beyond Featherless's 4-cap, and an independent provider for failover diversity. $10/mo is cheap insurance. Revisit only after Featherless Premium is live AND proven.

---

## Q2 — DeepInfra: keep/drop + the one scenario

**Featherless Premium ($25/mo, verified):** unlimited tokens, **4 concurrent**, models any size, **but only up to 32K context.** (Agent Standard $100 = 8 concurrent / 256K ctx / ≤229B.)
**DeepInfra (verified):** pay-as-you-go, no hard concurrency cap, full context; cheapest metered big-open — Qwen3-235B-A22B **$0.18/M in · $0.54/M out** (thinking $0.30/$2.90).

**Single-user agentic coder (one agent at a time, mostly):**
- Normally does **not** hit Featherless's 4-concurrent wall. The likelier Featherless limiter is its **32K context ceiling** on Premium, not concurrency.
- DeepInfra's "metered spillover" role is **already covered** in the live stack by nanogpt (reliability 1.0) + together (1.0), which absorb metered overflow today.

**Recommendation: DROP for now** (redundant with existing nanogpt/together metered legs for a single user).
**The one scenario it's needed:** when the operator runs **parallel droid/fleet units >4 concurrent** OR needs **>32K context** that Featherless Premium can't serve — DeepInfra absorbs that spillover with no concurrency wall / no context ceiling at ~$0.18/M. Add it only when that wall is actually hit.

---

## Q3+4 — Grok 4.3 / Gemini 3.1 Pro: accessible now?

**Gemini 3.1 Pro → YES, accessible NOW.**
- Pool `gemini-3.1-pro` exists; members `gemini-3.1-pro-ng` (nanogpt, upstream `google/gemini-3.1-pro-preview`) + `gemini-3.1-pro-or` (openrouter, same upstream). (Also a `-go` variant exists.)
- **Invoke: model id `gemini-3.1-pro`.** No setup needed. Prefer the nanogpt (`-ng`) leg — reliability 1.0 vs openrouter 0.6.
- Pricing (verified): $2/M in ($4 >200K) · $12/M out · **cached $0.20–0.40/M (~90% off)** — Google implicit caching is automatic and passed through OpenRouter/nanogpt.

**Grok 4.3 → NO, ABSENT.** Only `grok-build-0.1` exists (upstream `x-ai/grok-build-0.1`) — a different/cheaper build model, not Grok 4.3.
- Pricing (verified): xAI list **$1.25/M in · $0.20/M cached (85% off) · $2.50/M out**; 1M ctx; >200K in billed 2×. OpenRouter carries `x-ai/grok-4.3` (confirmed).

**Setup — two paths:**
- **(a) OpenRouter/nanogpt NOW (config-only, no new keys) — RECOMMENDED.** Mirror the `grok-build-0.1` pattern: add pool `grok-4.3` with members `grok-4.3-ng` (nanogpt, upstream `x-ai/grok-4.3`) + `grok-4.3-or` (openrouter, upstream `x-ai/grok-4.3`). Both keys already present. xAI's automatic prompt-cache passes through both, so the 234:1 input-heavy load still gets the $0.20/M cached rate. Prefer the nanogpt leg (1.0 vs openrouter 0.6). *(Verify nanogpt lists `x-ai/grok-4.3`; OpenRouter definitely does. If nanogpt lacks it, ship the `-or` member alone.)*
- **(b) xAI-direct + Google-direct (new keys/signup).** Only worth it to guarantee cached pricing, avoid OpenRouter's ~5% markup, and dodge openrouter's 0.6 reliability. But nanogpt already gives reliability 1.0 + cache passthrough, so direct is **not** required now.

**Verdict:** Gemini 3.1 Pro = use now (`gemini-3.1-pro`, nanogpt leg). Grok 4.3 = add via config-only path (a); reserve xAI-direct only if cache-passthrough proves lossy.
