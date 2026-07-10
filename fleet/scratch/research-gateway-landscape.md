# LLM-Gateway / Model-Router Landscape — for Charon's tier-pool + benchmark-driven-failover vision

**Date:** 2026-07-06
**Scope:** Survey of gateway/router products Charon could adopt, borrow-the-design from, or reject. Charon = self-hosted, provider-agnostic, OpenAI-compatible gateway; today hand-maintains ~50 static failover pools; TARGET = a few TIER-based pools + capability-aware failover that picks the strongest *currently-available* model in a tier *for the job type*, driven by benchmark scores.
**Companion docs (do not duplicate):** `research-litellm-bifrost.md`, `research-opencode-ecosystem.md` cover LiteLLM / Bifrost / opencode.

---

## TL;DR — the one finding that matters

**None of the mainstream self-hostable gateways route on quality/benchmark scores.** Every "smart routing" feature in Portkey, Kong, Cloudflare, Helicone, TrueFoundry, and llmgateway.io is cost-, latency-, uptime-, or static-weight-based. Capability/quality-aware routing (Charon's actual target) exists only in (a) SaaS routers with closed internals (Unify, Not Diamond, Martian, Requesty) and (b) two self-hostable open projects — **RouteLLM (LMSYS, Apache-2.0)** and **Arch-Router (Katanemo, open-weight 1.5B)**. That split is the whole story: the shape Charon wants is not available as a drop-in self-hosted gateway; Charon must **borrow the design** from the open routers and build the tier-quality logic itself.

---

## 1. llmgateway.io (the one the operator named)

**What it is:** Unified OpenAI-compatible proxy over 40+ providers / ~298 models, by "The Open Company," with usage analytics and cost tracking. [llmgateway.io](https://llmgateway.io/) · [GitHub theopenco/llmgateway](https://github.com/theopenco/llmgateway)

- **Routing/fallback model:** Metrics-based *dynamic* routing, NOT capability/benchmark-aware. Four strategies via a per-request `routing` field: `auto` (weighted blend of price/uptime/throughput/latency/cache), `price` (~90% cost), `throughput`, `latency`. Failover is health-check driven (rolling ~60-min window, avoids providers under ~95% uptime, retries up to 2x on 5xx/timeout). "Auto" scales to "more powerful models" by **context size, not quality benchmarks.** (Two docs pages give conflicting exact weights — treat precise numbers as unverified.) [Routing docs](https://docs.llmgateway.io/features/routing) · [Failover blog](https://llmgateway.io/blog/how-we-handle-llm-provider-failover)
- **Config style:** Hybrid — per-request JSON `routing` field + web dashboard; enterprise-only routing-weight overrides. No standalone config-file model.
- **Self-hostable:** Yes. Docker + compose (Postgres + Redis). [GitHub](https://github.com/theopenco/llmgateway)
- **Open-source / license:** **Open-core** — core is **AGPLv3**; `ee/` enterprise dir is separately commercially licensed.
- **Cost routing:** Yes (`price` strategy ~90% cost weight; unprefixed model IDs auto-pick cheapest provider). Capability/benchmark routing: **no.**
- **Pricing (SaaS):** Free tier = 3 rate-limited free models, 20 req/min, 30-day retention. Paid = pass-through per-token + **5% fee on credit top-ups** (1% enterprise, **0% if you bring your own keys**). [Pricing](https://llmgateway.io/pricing)

**Verdict for Charon as an upstream provider: redundant, do not add.** Its confirmed providers (Groq, Cerebras, Together AI, DeepSeek) are already *direct* in Charon at 0% fee; the rest of its catalog overlaps OpenRouter, which Charon already has. llmgateway would add a network hop + 5% top-up fee + reduced upstream visibility, with no exclusive models, no durable free tier, and no pricing edge. [providers page](https://llmgateway.io/providers) · [pricing](https://llmgateway.io/pricing) **As a routing *design*, its `auto` strategy is weaker than what Charon already targets** (no quality signal). Net: not-a-fit for either adoption or borrowing.

---

## 2. General self-hostable gateways (breadth)

| Product | Self-host / license | Provider-agnostic | Routing mechanism | Config upkeep |
|---|---|---|---|---|
| **Portkey Gateway** | Yes, **Apache-2.0** (full gateway open-sourced in "Gateway 2.0") [repo](https://github.com/portkey-ai/gateway) | 1,600+ models / 45+ providers, OpenAI-compat | Composable/nestable JSON configs: `fallback` (ordered, error-triggered), `loadbalance` (weighted), `conditional` (route on request field). **No quality/benchmark input.** [combining strategies](https://portkey.ai/docs/guides/use-cases/combining-routing-strategies) | Hand-maintained nested JSON (same pain class as Charon's pools); dashboard "Model Catalog" lists models but doesn't drive routing [catalog](https://portkey.ai/docs/product/model-catalog) |
| **Kong AI Gateway** | Core AI Proxy **Apache-2.0**; multi-provider failover (**AI Proxy Advanced**) is **Enterprise-gated** [announcement](https://konghq.com/blog/product-releases/announcing-kong-ai-gateway) | ~16 providers, format-normalizing | round-robin / weighted / consistent-hash / lowest-latency / lowest-usage / semantic(embedding); `failover_criteria` on error/timeout. **No benchmark routing.** [load balancing](https://developer.konghq.com/ai-gateway/load-balancing/) | Declarative plugin config (Admin API / YAML / Konnect); failover itself is paid |
| **Cloudflare AI Gateway** | **No** — managed-only, no self-host path [overview](https://developers.cloudflare.com/ai-gateway/) | Unified endpoint over many providers | Static ordered fallback array, sequential on error/timeout (`cf-aig-step` header). No cost or quality routing. [fallbacks](https://developers.cloudflare.com/ai-gateway/configuration/fallbacks/) | Hand-maintained ordered array per gateway |
| **Helicone AI Gateway** | Yes, **Apache-2.0**, Rust; Docker / npx / K8s [repo](https://github.com/Helicone/ai-gateway) | 100+ models / 20+ providers; catalog in upstream `providers.yaml`; OpenAI-compat | `router.yaml` `load-balance.strategy`: `latency`/`model-latency`, provider-latency (P2C + PeakEWMA), `weighted`, cost (cheapest adequate); separate fallback/rate-limit blocks. **Cost/latency only — no quality score.** [intro blog](https://www.helicone.ai/blog/introducing-ai-gateway) | Hand-maintained `router.yaml`, BUT the model/provider catalog is **maintained upstream** (`providers.yaml`), not by the operator — partial relief of Charon's upkeep pain |
| **TrueFoundry AI Gateway** | **Not open-source**; self-host is Enterprise-tier (~$499/mo Pro + infra) [modes](https://docs.truefoundry.com/docs/ai-gateway/modes-of-deployment) | Hosted + self-hosted OSS (vLLM/SGLang/Triton) behind OpenAI-compat | LoadBalancer: `weight`-based or `latency`-based (lowest time-per-output-token, rolling 20-min window); standalone Fallback config **deprecated** in favor of retry-in-LB. No benchmark routing. [loadbalancers](https://docs.truefoundry.com/docs/loadbalancers) | GitOps YAML via CLI into K8s, or dashboard |

**Also noted:** *Unify* markets a benchmark/live-performance-driven router (closest concept to Charon) but is **SaaS-only** — see §3. *Eden AI* is a broad multi-modal aggregator, not quality-routing. *OpenRouter* is hosted-only (baseline comparison; already a Charon upstream).

**Cross-cutting finding:** the Helicone pattern of an **upstream-maintained model/provider catalog** (`providers.yaml`) is the single most directly reusable idea in this section — it attacks Charon's ~50-pool hand-maintenance pain without requiring quality routing.

---

## 3. CAPABILITY / QUALITY-AWARE routers (MOST RELEVANT — Charon's target design)

### RouteLLM (LMSYS) — the reference implementation
1. **How it decides best-for-task:** Genuinely a **trained router** framework. Four interchangeable router types, each outputs a "win-rate" score for the strong model given a query: **matrix factorization** (recommended default), **BERT classifier**, **causal-LLM classifier**, **similarity-weighted (SW) ranking** (weighted Elo). All trained on **Chatbot Arena human preference data**, optionally augmented with GPT-4-as-judge labels. Reported: MF router hits ~95% of GPT-4 quality while routing only ~26% of queries to GPT-4 (~48% cheaper than random). [README](https://github.com/lm-sys/RouteLLM/blob/main/README.md) · [LMSYS blog](https://www.lmsys.org/blog/2024-07-01-routellm/)
2. **Tier concept:** **Strictly binary** — "route between 2 models: a stronger/expensive and a cheaper/weaker." No native N-tier; Charon would cascade multiple binary routers to get multi-tier.
3. **Self-hostable:** **Yes — Apache-2.0**, ships as a local OpenAI-compatible proxy (`python -m routellm.openai_server`); trained weights/datasets on Hugging Face.
4. **Borrow for Charon:** Strongest candidate to embed/reimplement. Apache-2.0 code + published methodology (Arena preference data + matrix factorization) + a local OpenAI-compatible server that mirrors Charon's own proxy shape. Use its training approach to build the "pick strongest available model in a tier" decision as a lightweight local classifier — **no hosted dependency.**

### Arch-Router (Katanemo) — the policy-based open-weight option
1. **How it decides:** Open-weight **1.5B model** (`katanemo/Arch-Router-1.5B`) that routes by matching a query to **user-defined domain/action policies** (natural-language descriptions), NOT fixed benchmarks. 93.17% routing accuracy in-paper; add routes/models without retraining. [arXiv:2506.16655](https://arxiv.org/html/2506.16655v1)
2. **Tier concept:** No benchmark tiers, but its policy abstraction ("coding," "reasoning," "summarization" → mapped to models) is a clean fit for Charon's *work-class-aware* dimension.
3. **Self-hostable:** **Yes** — open-weight, 1.5B, runs locally.
4. **Borrow for Charon:** Decouples routing logic from any single benchmark — you *define* work classes as policies and map them to tiers, adding new models without retraining. Complements RouteLLM: RouteLLM gives the quality gradient, Arch-Router gives the job-type classification.

### Unify.ai
1. **How:** Neural-net router trained on Unify's continuous benchmarking (Open Hermes, GSM8K, HellaSwag, MMLU, MT-Bench) → per-LLM quality score, combined with **live runtime telemetry** (per-endpoint speed/cost) to route per prompt. [TechCrunch](https://techcrunch.com/2024/05/22/unify-helps-developers-find-the-best-llm-for-the-job/) Hybrid static-benchmark × live-health — conceptually the closest to Charon's vision.
2. **Tiers:** No discrete tiers — continuous scored ranking.
3. **Self-hostable:** **SaaS**; mentions on-prem enterprise toolkit but no OSS repo/weights. *Caveat: unify.ai homepage now reads "AI teammates" — likely pivoted away from the router; treat as historical.* [YC launch](https://www.ycombinator.com/launches/L4t-unify-the-best-llm-on-every-prompt)
4. **Borrow:** The **two-signal design** — static per-category benchmark quality score decides tier placement; live endpoint health decides which tier member wins right now. This is almost exactly Charon's target formalized.

### Not Diamond
1. **How:** Trained "meta-model" predicting per-input which LLM gives best quality/cost. Offers a **pre-trained router** (+ coding-specific variant) and a **custom router** you train via `train_custom_router` on your own (prompt, per-model response) pairs in minutes–hour. Internals undisclosed; related OSS project **RoRF** uses jina embeddings + random-forest routers. [docs](https://docs.notdiamond.ai/docs/what-is-not-diamond) · [training quickstart](https://docs.notdiamond.ai/docs/router-training-quickstart) · [RoRF](https://github.com/Not-Diamond/RoRF)
2. **Tiers:** No tiers — continuous prediction + `tradeoff` param (quality/cost/latency).
3. **Self-hostable:** **SaaS/API-only** (router closed). Their [awesome-ai-model-routing](https://github.com/Not-Diamond/awesome-ai-model-routing) is a bibliography, not code.
4. **Borrow:** The **custom-router training recipe** (real prompts + per-model responses + judge labels → small classifier) is a documented methodology Charon can replicate in-house.

### Martian (withmartian)
1. **How:** Proprietary "Model Mapping" — an interpretability technique estimating how a model would perform *without running it*, to pick the cheapest model matching top-tier quality. No public methodology paper. Team also published **RouterBench** (open benchmark/dataset for evaluating routers). [TechCrunch](https://techcrunch.com/2023/11/15/martians-tool-automatically-switches-between-llms-to-reduce-costs/) · [routerbench](https://github.com/withmartian/routerbench)
2. **Tiers:** Continuous ("best LLM per prompt").
3. **Self-hostable:** **SaaS/API-only** for the router; RouterBench is open + self-runnable. Product status uncertain (code-router preview reportedly ended) — least stable option.
4. **Borrow:** **RouterBench** — a public dataset + harness Charon can use to *validate its own tier-assignment logic* against a known benchmark, no hosted dependency.

### Requesty
1. **How:** "Smart Routing" — intent/task classification (factual/creative/code/math/translation) → policy mapping labels to primary/fallback models with cost & latency ceilings → fallback on low confidence. (An AI-summary claim of a "65M-param transformer / 50k examples" was **NOT corroborated** by Requesty's own blog — treat as unverified.) [Smart Routing blog](https://www.requesty.ai/blog/smart-routing-demystified-choosing-the-fastest-cheapest-model-per-request-1751654257)
2. **Tiers:** Task-label → {primary, fallback[]} policy is effectively tier-like, but vendor-authored, not benchmark-derived.
3. **Self-hostable:** **No** — SaaS/API-only.
4. **Borrow:** The **`label → {primary, fallback[], max_cost, max_latency}` policy-as-YAML** structure is a clean config format Charon could copy directly, independent of Requesty's classifier.

### OpenRouter `auto` router (Charon already talks to OpenRouter)
1. **How:** **Confirmed powered by Not Diamond** (OpenRouter docs + launch tweet + Not Diamond founder). Prompt analyzed for complexity/task-type/model-capability → optimal model from a curated ~19-model pool. [OpenRouter auto-router docs](https://openrouter.ai/docs/guides/routing/routers/auto-router) · [OpenRouter on X](https://x.com/OpenRouterAI/status/1876465116293808179)
2. **Tiers:** Task-type-aware in principle but exposes no tier taxonomy — black-box continuous choice, tunable only via `cost_quality_tradeoff` 0–10 (default 7) + `allowed_models` glob.
3. **Self-hostable:** **No** — hosted meta-model. Billing: standard rate for the chosen model, **no extra fee**, but zero pre-call visibility into which model was picked.
4a. **Leverage directly?** Charon could add `openrouter/auto` as a model-id in its existing OpenRouter integration at near-zero cost, punting "best model in category" to the black box. **Risks:** opacity (no pre-call visibility), lock-in to OpenRouter's curated pool (excludes NeuralWatt/NanoGPT/direct providers), no control over taxonomy — undermines Charon's provider-agnostic goal.
4b. **Borrow:** the *pattern* — a single tunable cost/quality dial instead of hand-built ordering; "task type" as a first-class signal; curated-pool-plus-meta-selector architecture Charon implements itself with benchmark scores.

---

## Ranked shortlist — most relevant to Charon's tier-pool + benchmark-driven-failover vision

**1. RouteLLM (LMSYS) — BORROW-THE-DESIGN (and consider embedding).**
The only self-hostable project that does true quality-aware routing with a published, replicable methodology (Chatbot Arena preference data → matrix-factorization win-rate score) and a local OpenAI-compatible server matching Charon's own shape. Its binary strong/weak split maps naturally onto Charon's tier boundaries (cascade N binary routers for N tiers). **License: Apache-2.0, fully self-hostable, weights on HF.** *Key reason: closest working reference for "is the top-tier model actually needed, or does a lower tier suffice for this query" — the core of benchmark-driven tier selection, with zero hosted dependency.*

**2. Unify.ai two-signal design — BORROW-THE-DESIGN (pattern only).**
Not adoptable (SaaS, likely discontinued), but its architecture *is* Charon's target stated precisely: **static per-category benchmark quality score → tier placement; live endpoint health/latency → which tier member wins now.** Charon should formalize its tier logic on exactly this two-signal split. *Key reason: it is the cleanest articulation of "strongest *remaining* model in a tier for the job type." License/self-host: SaaS, no OSS — borrow the concept, not the code.*

**3. Arch-Router (Katanemo) — BORROW-THE-DESIGN (or adopt as a component).**
Open-weight 1.5B local router that classifies queries into **user-defined work-class policies** (coding/reasoning/summarization) without retraining when models change. Supplies the *job-type* axis that RouteLLM's quality axis lacks. **Open-weight, self-hostable, runs locally.** *Key reason: gives Charon benchmark-independent work-class classification that stays stable as the ~50 pools churn — pair with RouteLLM's quality gradient.*

**4. Helicone AI Gateway catalog pattern + Requesty policy schema — BORROW-THE-DESIGN (upkeep relief).**
Two small, concrete borrows that attack Charon's *hand-maintenance* pain directly: Helicone's **upstream-maintained `providers.yaml` catalog** (decouple model metadata from operator-authored pools) [repo](https://github.com/Helicone/ai-gateway), and Requesty's **`label → {primary, fallback[], max_cost, max_latency}` policy-as-YAML** as the tier-config file format. *Key reason: shrinks the ~50-pool upkeep burden without needing quality routing. Helicone: Apache-2.0 self-hostable; Requesty: SaaS, borrow schema only.*

**5. Martian RouterBench — BORROW (validation harness).**
Not a router to run, but an open dataset + evaluation harness to **validate Charon's own tier-assignment logic** against a known benchmark before shipping. [repo](https://github.com/withmartian/routerbench) *Key reason: lets Charon prove its benchmark-driven tiers actually beat static ordering. Open-source, self-runnable.*

**NOT-A-FIT (explicit):**
- **llmgateway.io** — redundant as an upstream (overlaps Charon's direct providers + OpenRouter, adds 5% fee + hop); its `auto` routing is context-size-based, weaker than Charon's target. Neither adopt nor borrow.
- **Not Diamond / OpenRouter `auto`** — capable but **closed SaaS black boxes**; adopting either violates Charon's self-hosted, provider-agnostic mandate and gives no pre-call model visibility. (Charon *could* expose `openrouter/auto` as an optional passthrough model-id for users who want it, but must not build its tier engine on it.)
- **Portkey / Kong / Cloudflare / TrueFoundry** — solid gateways but **zero quality/benchmark routing**; all "smart routing" is cost/latency/weight/uptime. Same architectural class as Charon's current static pools, not its target. (Portkey/Helicone are worth a glance for config ergonomics only.)

**Design conclusion:** Charon's target design does not exist as a self-hostable product — it must be built. The winning combination is **RouteLLM's quality-gradient methodology + Arch-Router's work-class classification + Unify's two-signal (benchmark-score × live-health) selection loop**, fed by public benchmark data (LMArena/MMLU/HumanEval per category) and validated with RouterBench — all self-hostable, no SaaS dependency, consistent with Charon's provider-agnostic mandate.
