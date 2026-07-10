# Model × Work Matrix — first pass (2026-07-05)

Scope: routing assignment for SLOP/mediastack + Charon work (Python backend, gateway, CLI,
agentic coding, tests, CI). FIRST PASS from published benchmarks/reputation + our cost data —
to be **validated empirically** by the `quality_scorer` (live feedback) + an eval harness (budget-gated).

Cost tiers via our stack: **flat** = covered by NanoGPT $12/mo sub (near-zero marginal); **cheap-paid** ≈ $0.1–2/1M; **free** = Groq/Cerebras/Mistral daily tiers.

| Model | Cap tier | Cost via stack | Best-at (assign here) | Avoid for | Quality note |
|---|---|---|---|---|---|
| **DeepSeek V4 Pro** | frontier-open | flat (NanoGPT) / $0.x direct | **agentic coding, complex impl, review** | trivial mechanical (overkill) | top open coder+tools; current daily-driver |
| **DeepSeek V4 Flash** | strong | flat / **$0.18** direct | **routine coding, high-volume, mechanical edits** | hardest multi-step | fast, cheap, solid; the volume workhorse |
| **Kimi K2.6** | frontier-open | flat / NeuralWatt ~$1.7 (K2.7-Code) | **agentic + long-context coding, tool-heavy** | — | top-tier open coder; strong on big repos |
| **GLM 5.2** | strong | flat / NeuralWatt $2.21 | **general coding, reasoning, review 2nd-opinion** | — | reliable all-rounder + tools |
| **Qwen 3.6 Plus** | strong | flat / OpenRouter | **coding, multilingual, general reasoning** | — | strong coder, good tools |
| **Hy3 Preview (Hunyuan 3.0)** | frontier-ish | **$0.11** OpenRouter | **agentic coding (cheap frontier), 256K ctx** | unverified reliability | SWE-bench 74.4%; cheapest frontier-agentic |
| **Nemotron 3 (Super/Ultra)** | strong→frontier | flat / OpenRouter (1M ctx) | **long-context analysis, whole-repo reasoning** | interactive low-latency | big-context specialist |
| **MiniMax M2.7 / M3** | mid-strong | flat | **general work, cost-efficient batch** | hardest coding | efficient generalist |
| **MiMo V2.5** | economy | flat | **cheap reasoning, simple classification, cron/heartbeat** | complex coding | small/fast; background tier |
| **Qwen/Groq/Cerebras gpt-oss-120b** | strong (FREE) | **free** (Groq/Cerebras) | **daily-driver primary when free RPM allows** | sustained high-RPM agentic (throttles) | free + tool-calling; use first, fail over |
| **Step 3.7 Flash** | economy | flat | **fast simple tasks, high-volume mechanical** | complex/agentic | speed tier |

## Tier → default primary (cheap-first, quality-corrected)
- **agentic coding (hard):** DeepSeek V4 Pro / Kimi K2.6 → Hy3 → (GLM 5.2 / Qwen 3.6) → premium only on repeated failure
- **routine coding / mechanical:** DeepSeek V4 Flash / free gpt-oss-120b → MiniMax → Step Flash
- **review / 2nd opinion:** a *different* strong model than the author (GLM 5.2 / Qwen 3.6 / DeepSeek V4 Pro) — diversity matters
- **long-context / whole-repo:** Nemotron 3 (1M ctx) / Kimi K2.6 (256K)
- **background / classify / cron:** MiMo V2.5 / Step Flash / free 8B
- **premium (gate, NOT default):** GPT-5.5 / Claude-Opus — review, consensus, final passes only (too costly for day-to-day)

## How this becomes real (not just a doc)
1. Seed `cost_class`/tier + these primaries into pools (ticket #6 auto-cost_rank + #19 tier pools).
2. `quality_scorer` (live, ticket below) demotes any model that underperforms on a work-type → self-correcting.
3. Eval harness (budget-gated) runs each model on a fixed SLOP/Charon task suite to validate + fill gaps.
