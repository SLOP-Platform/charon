# RelayFreeLLM vs Charon — Feature Comparison & Adoption Analysis

**Date:** 2026-07-03
**Mode:** READ-ONLY research. No product code modified.
**Target:** https://github.com/msmarkgu/RelayFreeLLM (~164★, 19 forks, Python/FastAPI)
**Purpose:** Find features worth incorporating into Charon (the local, stdlib-only, OpenAI-compatible failover gateway).

---

## 1. What RelayFreeLLM is

RelayFreeLLM is an open-source **API gateway that aggregates multiple free-tier LLM providers** (Gemini, Groq, Mistral, DeepSeek, NVIDIA, Cerebras, Cloudflare, Ollama) behind a single **OpenAI-compatible endpoint**, with automatic failover when a provider hits its free-tier rate limit. Same core pitch as Charon: point any OpenAI client at it, get free capacity + failover, no SDK rewrite.

**Who it's for:** indie devs dodging API costs, students/hobbyists, self-hosters mixing Ollama + cloud, researchers doing high-throughput batch.

**Architecture / stack:**
- Python (77%) + JS (14%) + CSS (7%). **FastAPI + Pydantic + httpx** (async).
- Request flow: `router.py` → `model_selector.py` (picks provider/model) → `model_dispatcher.py` (retry/failover loop) → `context_manager.py` (history shaping) → `api_clients/*` (per-provider clients).
- Supporting modules: `api_limits_tracker.py` (quota tracking), `usage_tracker.py`, `conversation_store.py`, `provider_registry.py` (auto-discovery), `response_normalizer.py`, `admin.py` (dashboard), `/chat` UI.
- Config: `.env` for keys (`GEMINI_APIKEY`, `GROQ_APIKEY`, ...), `provider_model_limits.json` for per-model limits, `settings.json` for behavior.

**Headline features (from README + source):**
1. OpenAI-compatible drop-in API + SSE streaming + multi-turn.
2. **Proactive free-tier rate-limit tracking** — sliding-window RPM/RPD/TPM per provider/model, pre-flight "can this provider handle this request?" check.
3. Automatic failover + circuit-breaker cooldown on rate-limit/error.
4. **Intent-based routing** — request filters `model_type` (text/coding/image/speech), `model_scale` (large/medium/small), `model_name`.
5. **Image-aware routing** — routes vision requests to vision-capable models.
6. **Session affinity** via `X-Session-ID` (sticky provider for cache warmth).
7. **Four context-management modes** (Static / Dynamic / Reservoir / Adaptive) + **extractive summarization** (stdlib TF-scoring, no LLM call) for long conversations.
8. **Conversation store** (browser localStorage or server-side).
9. **Admin dashboard** (`/admin`): visual per-provider limit editor, inline edit, hot-reload, usage stats.
10. **Chat playground UI** (`/chat`): streaming, provider attribution, drag-drop images, dark/light mode.
11. **Plugin-style provider onboarding** — drop a `XxxClient(ApiInterface)` file in `api_clients/`, auto-discovered via `pkgutil`.
12. Model-name heuristic scoring (`+100` latest, `+50` pro, `+40` large/reasoner, `-20` lite) to auto-rank discovered models, top-10 per provider.

---

## 2. Feature gap analysis

Legend: **Equivalent** = Charon has parity · **Better** = Charon does it better · **Worse** = Charon has it but weaker · **Absent** = Charon lacks it.

| # | RelayFreeLLM feature | Charon status | Notes |
|---|---|---|---|
| 1 | OpenAI-compatible `/v1/*` proxy + SSE | **Equivalent** | Both are drop-in. Charon on `http.server` (stdlib), RFL on FastAPI. |
| 2 | Multi-provider pools + availability failover | **Equivalent** | Charon: pool router, cross-model failover, `order_by_cooldown`. |
| 3 | **Proactive free-tier quota tracking (sliding-window RPM/TPM/RPD)** | **Absent** | RFL tracks per-provider/model request+token deques over 1s/60s/1h/24h windows and does a **pre-flight `can_handle()`** so it never sends a doomed request; `get_wait_time()` computes exact seconds to availability. **Charon is purely reactive** — it only learns a provider is exhausted *after* a 429 (`set_cooldown` keyed by provider, honoring `Retry-After`). This is the single biggest gap for a *free-tier* gateway. |
| 4 | Circuit breaker / cooldown | **Equivalent** | Charon has provider-keyed cooldown (Retry-After aware) + `ReviewerCircuitBreaker`. RFL fixed 60s (rate) / 30s (other). Charon's is arguably better (respects Retry-After, account-level keying). |
| 5 | Cost-aware routing (per-token pricing) | **Better** | Charon captures real per-token pricing in discovery + cost/quality routing with a reliability floor. RFL has **no cost model** — only free-tier quota. |
| 6 | Quality-aware routing | **Better** | Charon: `quality_scorer.py` + reliability floor. RFL: crude model-name heuristic (`+100 latest`) only. |
| 7 | Namespace-tolerant model-id matching (no double-bill) | **Better** | Charon-specific; RFL has no equivalent concern. |
| 8 | Intent-based routing (`model_type`/`model_scale`/`model_name`) | **Worse/Partial** | Charon has `policy_router` + tier vids, but RFL's explicit request-level `model_type`/`model_scale` filter dimensions (coding/speech/image; large/medium/small) are a clean UX Charon doesn't fully expose. |
| 9 | **Image-aware / capability routing** | **Worse** | Charon **already detects `has_images`** in `request_inspector.py` and carries `vision` metadata per model — but doesn't appear to *exclude non-vision models* from routing when images present. Small wiring gap. |
| 10 | Session affinity | **Equivalent** | Charon `session_affinity.py` pins session→provider for prompt-cache warmth (ADOPT B3.1). |
| 11 | **Context-management modes (Static/Dynamic/Reservoir/Adaptive)** | **Absent** | Charon is a **stateless proxy** — no conversation history shaping. RFL reshapes history to fit context windows / save tokens. |
| 12 | **Extractive summarization (stdlib TF-scoring, no LLM)** | **Absent** | RFL compresses old turns with term-frequency sentence ranking + position bias, token-budgeted. Pure stdlib, no extra call. |
| 13 | Conversation store (server-side history) | **Absent** | Charon deliberately stateless. RFL persists conversations. |
| 14 | Response normalization across providers | **Equivalent** | Charon `response_normalizer.py`. |
| 15 | Semantic (exact-match) response cache | **Better** | Charon has it; RFL does not (only session affinity for cache warmth). |
| 16 | Universal spend limiter + guardrails + virtual keys | **Better** | Charon: spend caps, guardrails, virtual keys with per-key model allowlist/spend/`max_rpm`/`max_tpm`/permissions. RFL has none of this — it's single-tenant, no auth. |
| 17 | Admin dashboard w/ visual limit editor + hot-reload | **Worse** | Charon has a token-gated console showing providers/cooldown/cost/errors, but RFL's **inline per-limit editor with hot-reload** is a nicer ops UX. |
| 18 | **Chat playground UI** (`/chat`, streaming, drag-drop images, dark mode) | **Absent** | Charon has admin console + setup GUI but **no interactive chat page** to smoke-test failover live. |
| 19 | Provider onboarding | **Different** | RFL: plugin drop-in `ApiInterface` class, `pkgutil` auto-discovery. Charon: config-driven `/v1/models` discovery (`discover.py`) — most OpenAI-compatible providers "just work" via base URL, so Charon needs less plugin machinery, but has no formal plugin interface for *non*-OpenAI-shaped providers. |
| 20 | ACP "work engine" driving coding agents | **Better (unique)** | Entirely absent in RFL. Charon-only. |
| 21 | Secrets handling / security scanning | **Better** | Charon has secrets mgmt + scanners; RFL just reads `.env`. |
| 22 | Deployment | **Equivalent-ish** | Both have Dockerfiles. Charon ships stdlib-only (zero pip deps in core); RFL needs FastAPI/pydantic/httpx. Charon wins on standalone/Windows-native. |
| 23 | Server-side system-prompt injection | **Absent (intentionally)** | RFL can inject a server system prompt (per-request overridable). Questionable for a *transparent* gateway — see §4. |

---

## 3. Recommendations — top features worth incorporating (ranked)

### R1 — Proactive free-tier quota tracking (sliding-window RPM/TPM/RPD) ⭐ TOP PICK
- **What:** Per-(provider, model) sliding-window counters (request + token deques over 1s/60s/1h/24h), a pre-flight `can_handle(tokens)` check, and `get_wait_time()`. Route selection *skips a provider that would 429* instead of discovering it after the fact, and can compute the shortest wait across the pool.
- **Why for Charon:** Charon's whole reason to exist is **free-tier failover**, yet it's purely *reactive* — it burns a request + latency + a 429 to learn what a counter already knew. Proactive tracking cuts wasted round-trips, avoids tripping provider abuse heuristics, and lets Charon pick the provider with the most remaining quota (better than round-robin-until-429). Complements, not replaces, the existing Retry-After cooldown.
- **Approach:** New stdlib module (`collections.deque` + `time.monotonic`, thread-locked) mirroring RFL's `api_limits_tracker.py`. Populate limits from discovery / `provider_model_limits.json`-style config (Charon already captures model metadata + pricing). Hook into the pool router's exclude/order step alongside `order_by_cooldown`. Record usage on each response (token counts already available).
- **Effort:** **M** · **Blast radius:** routing/proxy_server + config (medium — touches the hot path, but additive/guarded). · **Stdlib:** ✅ perfect fit, zero deps.
- **Note:** Charon already declares `max_rpm`/`max_tpm` on virtual keys but that's *client-side* throttling; this is *upstream provider* quota — different axis, both worth having.

### R2 — Chat playground page in the web console
- **What:** A `/chat` page served by the existing console: prompt box, streaming output, **which provider/model actually served the request**, model picker, dark mode. Optional drag-drop image.
- **Why for Charon:** Home users need a zero-setup way to confirm "is my gateway working / who served this?" without wiring up a client. Cheap, high-perceived-value, great for the fresh-install experience (aligns with production-readiness north-star).
- **Approach:** Inline static HTML+JS (no framework), served from `proxy_server.py` like the existing admin console; calls Charon's own `/v1/chat/completions` with SSE. Reuse the token-gate already on the console.
- **Effort:** **S–M** · **Blast radius:** console only (low). · **Stdlib:** ✅ (inline assets).

### R3 — Capability-aware routing (finish the image-aware path)
- **What:** When the request contains images, **exclude models without `vision:true`** from candidate selection (and symmetric for other modalities). Optionally surface RFL-style `model_type`/`model_scale` request hints.
- **Why for Charon:** Charon already **detects `has_images`** (`request_inspector.py`) and stores `vision` metadata per model — the detection and data exist; only the *routing exclusion* is missing. Without it, an image request can be routed to a text-only model and fail. Small, high-correctness win.
- **Approach:** In the pool-exclude step, drop non-vision entries when `has_images`. Feed `vision`/`audio` metadata (already in `_META_KEYS`) into the router filter.
- **Effort:** **S** · **Blast radius:** router filter (low). · **Stdlib:** ✅.

### R4 — Admin console: inline limit editor + hot-reload
- **What:** Make the console's provider/limit view *editable* — edit RPM/TPM/cooldown/enabled inline, apply without restart.
- **Why for Charon:** Pairs naturally with R1 (you need to see/tune the quota numbers). Turns the console from read-only status into an ops surface. Good home-user ergonomics.
- **Approach:** Add POST endpoints behind the existing token gate that mutate the in-memory config + persist to the config file; the console already renders the provider table.
- **Effort:** **S–M** · **Blast radius:** console + config write path (low-medium). · **Stdlib:** ✅.

### R5 — Extractive summarization + optional Reservoir context mode (OPT-IN only)
- **What:** Stdlib TF-scoring extractive summarizer that compresses old conversation turns into a token-budgeted system message when a request would overflow the target model's context window. "Reservoir" mode = keep last N turns verbatim + summarize the rest.
- **Why for Charon:** Lets small-context free models handle long chats that would otherwise 400/truncate — genuinely useful for the free-tier audience. No extra LLM call (pure TF ranking), so it fits stdlib-only.
- **Why cautious / lower rank:** This **breaks Charon's stateless-proxy simplicity** — it mutates the user's messages, which can surprise clients and complicate debugging/caching. Must be strictly **opt-in per-request or per-virtual-key**, off by default, and clearly disclosed in the response. Charon doesn't need a conversation *store* to do this (operate on the messages array in-request), which keeps it stateless.
- **Approach:** New `context_shaper.py`; invoked only when enabled AND the request exceeds the resolved model's `context_window` (metadata already captured). TF-scoring + position bias, greedy to token budget.
- **Effort:** **M–L** · **Blast radius:** request path, message mutation (medium-high — behavior change). · **Stdlib:** ✅ but **conflicts with the "transparent proxy" design principle** — ship gated.

---

## 4. Do NOT copy / where Charon is already ahead

- **FastAPI + Pydantic + httpx stack** — violates Charon's hard stdlib-only / standalone constraint. RFL's async model is nice but Charon's `http.server` + `urllib` design is a deliberate feature (Windows-native, zero pip). Do not adopt.
- **Model-name heuristic scoring** (`+100 latest`, etc.) — Charon already has `quality_scorer` + **real per-token pricing** from discovery, which is strictly better than guessing capability from the model string. Skip.
- **Mandatory conversation store / server-side history** — Charon's statelessness is an asset (simpler, cacheable, no PII-at-rest). Adopt only the *in-request* summarization (R5), not persistent storage.
- **Server-side system-prompt injection** — risky for a *transparent* gateway; silently altering prompts breaks the "drop-in, behaves like the upstream" contract and can corrupt evals. Skip, or only behind an explicit per-key opt-in.
- **Plugin `ApiInterface` auto-discovery** — lower ROI for Charon: because Charon is an OpenAI-compatible *passthrough*, new providers usually work by adding a base URL + key, no code. RFL needs per-provider client classes precisely because it normalizes heterogeneous native SDKs. Only worth it if Charon wants first-class support for non-OpenAI-shaped providers.

**Charon is already ahead on:** stdlib-only/standalone deployment, cost + quality-aware routing with reliability floor, namespace-tolerant no-double-bill matching, semantic cache, universal spend limiter + guardrails + virtual keys (multi-tenant auth — RFL has none), secrets/security scanning, Retry-After-aware account-level cooldown, and the ACP work engine (no RFL analog).

---

## 5. One-line verdict

RelayFreeLLM and Charon are the same species; Charon is the more mature, security- and cost-aware, stdlib-pure one. RelayFreeLLM's one genuinely enviable idea is **proactive free-tier quota tracking** (R1) — adopt that first. After that, the **chat playground** (R2) and **finishing image-aware routing** (R3) are cheap UX/correctness wins; the **inline limit editor** (R4) pairs with R1; and **extractive summarization** (R5) is worth it only as an opt-in, disclosed feature that preserves statelessness.
