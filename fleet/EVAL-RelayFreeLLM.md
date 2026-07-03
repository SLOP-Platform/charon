# RelayFreeLLM Evaluation — Comparative Analysis vs Charon

**Date:** 2026-07-02
**Source:** https://github.com/msmarkgu/RelayFreeLLM
**Purpose:** Reusable evaluation template for comparing LLM gateway/proxy projects to Charon.

---

## Summary

RelayFreeLLM is a free-tier-focused OpenAI-compatible proxy with built-in chat UI, preemptive
rate limiting, and 4-mode context management. It shares the same core concept as Charon (route
requests across multiple providers with failover) but targets a different audience (end users
who want free tier aggregation with a chat interface vs Charon's operator/developer gateway +
autonomous agent orchestration).

---

## Feature Comparison Matrix

### RelayFreeLLM does better than Charon (+ indicates Charon should adopt)

| # | Feature | + | Details |
|---|---|---|---|
| 1 | **Preemptive rate limiting** | + | 7-dimension sliding-window tracker (reqs/tokens per sec/min/hr/day). Catches limits before sending — no wasted upstream calls. Charon is reactive (waits for 429). |
| 2 | **Visual admin dashboard** | + | Collapsible provider cards, inline-editable limits, add/remove models, hot-reload. Charon has read-only console + clunky setup page. |
| 3 | **Context management** | + | 4 modes: Static, Dynamic, Reservoir (TF-based extractive summarization), Adaptive (coding vs chat detection). Charon delegates to ACP agents. |
| 4 | **Image-aware routing** | + | Auto-detects `image_url` content parts, restricts routing to vision-capable models. Charon has `vision` metadata but no request inspection. |
| 5 | **Built-in chat UI** | + | Streaming `/chat` with conversation history, dark/light mode, provider attribution. Charon has no chat client. |
| 6 | **Response normalization** | + | Strips "As an AI…", "Certainly!", fixes JSON, standardizes markdown. Charon passes raw upstream responses. |
| 7 | **Plug-and-play provider** | + | ~50 lines to add a new provider: subclass `ApiInterface`, implement `call_model_api()`. |
| 8 | **Session affinity** | + | `X-Session-ID` pins conversations to a provider for context caching; migrates on failover. |
| 9 | **Agent framework support** | + | `X-Use-ServerSide-System-Prompt: false` — forwards client messages verbatim. |
| 10 | **Conversation storage** | + | Browser `localStorage` or server-side `conversations.json` — search/rename/copy/delete. |

### Charon does better than RelayFreeLLM

| # | Feature | Details |
|---|---|---|
| 1 | **Silent downgrade detection** | Every 200 response checked for `returned_model ≠ expected_model`; triggers failover. RelayFreeLLM accepts any 200. |
| 2 | **Streaming failover buffering** | 64KB SSE head buffer — failover possible *before committing bytes* to client. RelayFreeLLM streams blindly. |
| 3 | **Cost-ranked failover** | Free → flat → cheap PTK → premium ordering (deliberate, not random). |
| 4 | **Provider-keyed cooldown** | 429 on one model cools entire provider's `upstream_base` — prevents wasted retries on same account. RelayFreeLLM cooldowns per-model. |
| 5 | **Flat-rate / paid provider support** | NanoGPT, OpenCode Go, featherless.ai. RelayFreeLLM is free-tier only. |
| 6 | **400/401/403 non-failover guard** | Client/auth errors returned immediately. RelayFreeLLM retries on any Exception. |
| 7 | **Autonomous orchestrator** | `charon run` — drives ACP agents through Ledger + fence + gate. |
| 8 | **Failover visibility** | `X-Charon-Provider` + `X-Charon-Failovers` headers; JSONL failover log. |
| 9 | **Pure stdlib gateway** | `http.server` + `urllib` only. RelayFreeLLM depends on FastAPI + uvicorn. |
| 10 | **Windows .exe packaging** | PyInstaller single-file binary. |
| 11 | **DNS rebinding protection** | Loopback Host header rejection. |
| 12 | **Code-safe flag** | Per-model `code_safe` boolean for proprietary code safety. |
| 13 | **Tier-based routing** | `low`/`med`/`high` tiers with alias mapping, ordered free-first. |
| 14 | **Web setup page** | Write-capable web UI for providers/models/pools/tiers/fallback. |
| 15 | **Provider presets** | 24+ built-in provider presets with per-provider quirks. |
| 16 | **Cost accounting** | Per-request cost tracking, cumulative usage, budget caps. |

### Same between them

- OpenAI-compatible `/v1/chat/completions` + `/v1/models`
- Automatic failover across multiple providers in-request
- MIT-licensed Python projects
- SSE streaming pass-through
- Server-side API key holding
- Specific model routing (`provider/model_name`)
- Usage tracking across providers
- Web console/dashboard
- Circuit breaker/cooldown mechanisms
- Single-user, local-first security posture
- Local upstream support (Ollama/LM Studio)
- Provider registry abstraction
- Metadata in `/v1/models`

---

## Weaknesses in RelayFreeLLM

| Weakness | Impact |
|---|---|
| No silent downgrade detection | Flat-plan downgrades look like success — wrong model, wrong cost |
| Streaming failover naive | Once streaming starts, can't retract a bad response |
| Model-keyed cooldown only | 429 on one model → still try others on same provider → wasted retries |
| No cost-ranked ordering | Failover sequence is random/availability-based |
| 400/401/403 retried | Bad requests waste attempts on subsequent providers |
| No failover audit trail | Can't see which provider served or why failover happened |
| FastAPI dependency | Larger attack surface, harder to package |
| Free-tier only | No flat-rate plans, no paid provider support |

---

## Transformative Gaps (neither project does these)

| # | Idea | Value |
|---|---|---|
| 1 | **Speculative parallel execution** | Fire prompt to 3 providers simultaneously, return fastest, cancel rest. Transforms latency. |
| 2 | **Semantic response caching** | Cache by normalized prompt hash. Eliminate redundant spend on similar/identical prompts. |
| 3 | **Token budgeting / spend caps** | "Never exceed $X/month" — per-session or per-gateway enforced limits. |
| 4 | **Provider quality scoring (RL)** | Track latency, output quality, hallucination rate per model. Route by quality-per-dollar. |
| 5 | **Prompt caching layer across providers** | Deduplicate shared system prompts, tool definitions across providers. |
| 6 | **Cross-provider consensus routing** | Verify critical outputs against N providers, flag disagreements. |

---

## Evaluation Template

When evaluating a new project against Charon, use this checklist:

### Must-check dimensions
- [ ] OpenAI-compatible endpoint? (blocker if no)
- [ ] Flat-rate or per-token pricing?
- [ ] Free tier?
- [ ] Failover behavior (what triggers it? is it visible?)
- [ ] Streaming support (with or without buffered failover?)
- [ ] Cost tracking / accounting?
- [ ] Dependencies (stdlib-only or framework-heavy?)
- [ ] Provider registry (how easy to add new ones?)
- [ ] Model routing (specific model or random?)
- [ ] Security posture (loopback? DNS rebinding? key handling?)
- [ ] Agent/orchestrator integration?
- [ ] Config surface (file-based? web UI? CLI?)

### Gap detection
- [ ] What does it do that Charon doesn't? (→ potential feature to adopt)
- [ ] What does Charon do that it doesn't? (→ competitive moat)
- [ ] What does neither do? (→ transformative opportunity)
- [ ] What design decisions are clearly worse? (→ avoid adopting)
- [ ] What design decisions are clearly better? (→ adopt)

---

## Decision Record

**Evaluated:** 2026-07-02
**Action:** Created BRIDGE-RELAYFEATURES ticket to incorporate RelayFreeLLM features A1–A6 and transformative gaps B1–B3. See `/home/stack/charon-private/prompts/bridge-relay-features.md`.
