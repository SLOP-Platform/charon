# Model → Role Evaluation for Building Charon + SLOP

**Purpose:** decide which LLMs the build rig routes work to, broken down by role, scored on quality-at-the-highest-level. This is **build-rig planning** (which models to point droid/fleet sessions at), NOT product code and NOT a Charon feature spec.

**Date:** 2026-07-03 · **Author:** fleet manager session · **Status:** durable planning doc

> **Read the Caveats section before hard-coding anything.** Claude-family facts here are authoritative (from the Anthropic API skill). Every non-Claude benchmark number is drawn from vendor launch posts and third-party blogs (llm-stats, morphllm, benchlm, kilo, etc.), which in mid-2026 are noisy and partly SEO-driven — treat those scores as **directional, ±a few points**, not settled fact. Scores below are my synthesized judgement for *these two projects*, not a leaderboard copy.

---

## 1. Project job-profiles — what the work actually demands of a model

**Charon** (`/home/stack/code/charon`) — a local OpenAI-compatible failover **gateway** plus an in-tree work-orchestration engine. The shipping core is **pure Python stdlib only** (no deps), pipx-installable, and **security-sensitive** (it holds provider keys; loopback-by-default). The work is not raw code generation — it is subtle concurrency/networking (proxy, failover, SQLite), supply-chain/CI hardening, and careful refactors, all under an **ADR-driven, decision-register, adversarial-review / debate-to-consensus (DTC)** culture with disjoint-`owns` file discipline and hermetic test suites. This session's representative bug — a silent-downgrade double-bill hidden behind `count_usage=False` — rewarded **deep multi-file code tracing and skepticism**, not fluent output. So Charon over-weights: reasoning depth, low hallucination, literal instruction-following, long-context whole-repo tracing, and security judgement. Cheap raw throughput is nearly worthless here; a confident-but-wrong model is actively harmful because it must pass an adversarial gate.

**SLOP / mediastack** (`/home/stack/code/mediastack`) — a media pipeline plus a `tracking/tracking.db` ticket system, bash + Python, more operational and scripting-heavy, ~31 open tickets, less stdlib-purist than Charon. The work is broader and shallower per unit: glue scripts, ticket-driven fixes, pipeline ops, DB queries. It tolerates (and financially rewards) routing routine, well-specified units to cheaper/faster models, reserving frontier reasoning for the genuinely gnarly tickets. SLOP is where "cheap-work-to-cheap-models" pays off most.

Both run through Charon's `frontier` / `strong` / `economy` tier pools, which route to Anthropic / OpenAI / Google directly and to DeepSeek / Kimi / Qwen / Mistral / GLM / MiniMax via OpenRouter / opencode-zen aggregators.

---

## 2. Model shortlist (anchors used across all roles)

| Model | Access path | Cost tier | One-liner |
|---|---|---|---|
| **Claude Fable 5** (`claude-fable-5`) | Anthropic direct | frontier+ ($10/$50) | Anthropic's most capable widely-released model; always-on thinking; best long-horizon agentic + reasoning. Priced above Opus. |
| **Claude Opus 4.8** (`claude-opus-4-8`) | Anthropic direct | frontier ($5/$25) | Current flagship Opus; state-of-the-art long-horizon agentic, knowledge work, memory; 1M ctx at standard price. Best all-round fit for Charon. |
| **Claude Opus 4.7** (`claude-opus-4-7`) | Anthropic direct | frontier ($5/$25) | Previous-gen Opus; still frontier-class; useful as a second frontier voice for DTC diversity. |
| **Claude Sonnet 5** (`claude-sonnet-5`) | Anthropic direct | strong ($3/$15, $2/$10 intro→2026-08-31) | Near-Opus coding/agentic quality at Sonnet cost; the default implementer. |
| **Claude Haiku 4.5** (`claude-haiku-4-5`) | Anthropic direct | economy ($1/$5, 200K ctx) | Fast, strong instruction-following for its tier; the economy Claude. |
| **GPT-5.5** ("Spud", Apr 2026) | OpenAI direct | frontier | Strong agentic/terminal-workflow model; leads some agentic-CLI benchmarks; good second-vendor frontier. |
| **Gemini 3.1 Pro** | Google direct | frontier | Top-tier reasoning + very large context; strong whole-repo tracing. |
| **Gemini 3 Flash** | Google direct | economy/strong | Punches above its tier on SWE-bench Verified (~78%) at ~¼ Pro price; excellent economy pick. |
| **DeepSeek V4-Pro** (open weights, Apr 2026) | OpenRouter / opencode-zen | strong | Strongest open-weight coder; ~within a few pts of frontier on SWE-bench Verified; very cheap. |
| **DeepSeek V4-Flash** | OpenRouter / opencode-zen | economy | Cheap open-weight workhorse, long context. |
| **Kimi K2.6** (Moonshot, open) | OpenRouter / opencode-zen | strong | Agentic-tuned open model; strong SWE-bench Pro; long-horizon sub-agent work. |
| **Qwen3-Coder-Next** (open) | OpenRouter / opencode-zen | economy/strong | Agentic-RL-trained open coder (~71% Verified); good cheap implementer. |
| **GLM-5 / MiniMax M2.5–M3** (open) | OpenRouter / opencode-zen | strong | Open coders ~80% Verified; viable strong-tier alternates to DeepSeek/Kimi. |
| **Mistral Large 3 / Codestral** | Mistral / OpenRouter | economy/strong | Solid single-file/refactor coder; weaker multi-file coordination. |

Scoring rubric (per role, 1-100, **cost excluded**): agentic coding ability · reasoning depth · instruction-following / low hallucination · long-context · tool-use · fit to Charon's stdlib/security/test-heavy domain. A model can score very differently across roles — noted where it matters.

---

## 3. Per-role rankings

### Role 1 — Architect / Planner
*ADRs, decomposition, work-composition-intelligence, dependency design, tier abstractions. Rewards reasoning depth, systems judgement, and restraint (not over-engineering). Charon's ADR/DECISIONS culture punishes plausible-but-wrong architecture.*

| Model | Score | Rationale | Access | Cost tier |
|---|---:|---|---|---|
| Claude Fable 5 | 98 | Best long-horizon reasoning + navigating ambiguity; excels at "scope the problem, ask, then execute." Ideal for hard ADRs. | Anthropic | frontier+ |
| Claude Opus 4.8 | 96 | State-of-the-art planning; warmer, clearer prose for ADR writeups; better restraint than 4.7. Best price/quality frontier. | Anthropic | frontier |
| Gemini 3.1 Pro | 92 | Deep reasoning + huge context to hold the whole design surface; good independent architectural voice. | Google | frontier |
| GPT-5.5 | 91 | Strong systems planner and agentic decomposition; a different failure distribution than Claude (good for DTC diversity). | OpenAI | frontier |

*Note:* Fable/Opus tend to over-plan at high effort — prompt with the anti-overplanning snippet. Open models are **not** recommended as lead architect for Charon (weaker on subtle security/systems trade-offs); fine for SLOP ticket decomposition.

### Role 2 — Implementer / Builder
*Feature code + hermetic tests under strict `owns`/stdlib discipline. Rewards agentic coding, instruction-following (respect `owns` boundaries, no deps), and test-writing.*

| Model | Score | Rationale | Access | Cost tier |
|---|---:|---|---|---|
| Claude Opus 4.8 | 96 | Best agentic execution; follows stdlib/`owns` constraints literally; strong self-verification. Use for the gnarly concurrency/networking units. | Anthropic | frontier |
| Claude Sonnet 5 | 91 | Near-Opus coding at strong-tier; the **default implementer** for most Charon/SLOP units. `xhigh` effort for hard coding. | Anthropic | strong |
| GPT-5.5 | 90 | Excellent agentic coder, strong terminal/tool workflows; good for SLOP bash-heavy units. | OpenAI | frontier |
| DeepSeek V4-Pro | 87 | Strongest open-weight coder; great value implementer for well-specified units, esp. SLOP. Watch stdlib-purism drift. | OpenRouter/zen | strong |
| Kimi K2.6 | 86 | Agentic-tuned, long-horizon sub-agent builds; solid open alternate. | OpenRouter/zen | strong |

*Note:* open models occasionally reach for a convenient dependency — for Charon's **stdlib-only core** give them an explicit "stdlib only, no imports outside the standard library" guardrail and let the test/CI gate catch violations.

### Role 3 — Adversarial Reviewer / DTC panelist
*Refute changes, find real bugs, security lens, verify claims. The load-bearing gate. Rewards skepticism, bug-finding recall+precision, security judgement, and independence from the author model.*

| Model | Score | Rationale | Access | Cost tier |
|---|---:|---|---|---|
| Claude Opus 4.8 | 97 | Best real-bug finder in the family; clearer explanations; catches intermittent/edge issues. Primary reviewer. | Anthropic | frontier |
| Claude Fable 5 | 96 | Deepest reasoning for hard refutation; strong at verifying claims against evidence. Reserve for high-blast-radius reviews. | Anthropic | frontier+ |
| GPT-5.5 | 92 | **Different vendor = independent failure modes** — highest value as the *second* DTC voice to avoid Claude monoculture. | OpenAI | frontier |
| Gemini 3.1 Pro | 90 | Long-context lets it review across the whole changeset + surrounding code; good third panelist. | Google | frontier |

*Critical prompt note:* Opus 4.8 / Sonnet 5 follow "only report high-severity / be conservative" **literally** and will silently drop findings, depressing measured recall. For DTC, prompt reviewers to **report everything with confidence+severity and filter downstream** — don't let the model self-censor. Security-flavored work: Fable 5's safety classifiers can refuse benign security tooling (`stop_reason: "refusal"`) — keep an Opus 4.8 fallback.

### Role 4 — Debugger / Root-cause analyst
*Trace subtle behavior across a codebase — the leak-hunt / silent-double-bill profile. Rewards long-context whole-repo tracing, reasoning depth, and refusal to declare "fixed" prematurely.*

| Model | Score | Rationale | Access | Cost tier |
|---|---:|---|---|---|
| Claude Opus 4.8 | 97 | Explicitly better than 4.7 at intermittent flakes vs "one clean run = fixed"; best trace-and-verify. The double-bill-class bug is its sweet spot. | Anthropic | frontier |
| Claude Fable 5 | 96 | Sustains very long traces, repository-history search, memory of what's been ruled out. Best for the hardest hunts. | Anthropic | frontier+ |
| Gemini 3.1 Pro | 92 | Massive context to hold the whole failover/proxy/SQLite path at once; strong causal reasoning. | Google | frontier |
| GPT-5.5 | 90 | Strong agentic debugging with tool loops; independent second opinion when Claude is stuck. | OpenAI | frontier |

*Note:* this is the role where economy models are **least** acceptable — a wrong root cause wastes a whole DTC cycle. Keep debugging on frontier.

### Role 5 — Refactorer / Simplifier
*Reuse / altitude cleanups without behavior change. Rewards restraint (no unrequested rewrites), instruction-following, and test-backed safety.*

| Model | Score | Rationale | Access | Cost tier |
|---|---:|---|---|---|
| Claude Sonnet 5 | 92 | Sweet spot: strong code understanding + literal scope-following; won't gold-plate if told not to. Default refactorer. | Anthropic | strong |
| Claude Opus 4.8 | 94 | Best judgement on *what* to simplify; use `no-tidying` prompt to prevent over-refactor at high effort. | Anthropic | frontier |
| DeepSeek V4-Pro | 85 | Capable structural refactors at low cost; pair with strong tests since it's less conservative about scope. | OpenRouter/zen | strong |
| Gemini 3 Flash | 83 | Cheap, competent mechanical refactors for SLOP; keep behavior-change guardrails. | Google | economy |

*Note:* Fable/Opus at high effort add abstractions beyond the ask — the no-tidying / "simplest thing that works" prompt is mandatory for this role. Score reflects with-guardrails behavior.

### Role 6 — Test / CI engineer
*Hermetic tests, CI + supply-chain hardening. Rewards correctness, security lens, and understanding of build/packaging.*

| Model | Score | Rationale | Access | Cost tier |
|---|---:|---|---|---|
| Claude Opus 4.8 | 95 | Best at hermetic test design + supply-chain reasoning (pinning, provenance, the SUPPLY-CHAIN.md concerns). | Anthropic | frontier |
| Claude Sonnet 5 | 90 | Strong, cheaper test authorship for the bulk of coverage; good CI-yaml fluency. | Anthropic | strong |
| GPT-5.5 | 89 | Excellent at CI/tooling/terminal workflows; good for GitHub Actions + runner config. | OpenAI | frontier/strong |
| DeepSeek V4-Pro | 84 | Cheap high-volume test generation; verify hermeticity (may assume network/deps). | OpenRouter/zen | strong |

### Role 7 — Docs / technical writer
*DECISIONS / REVIEW-LOG / ADR prose, grounding docs, handoff docs. Rewards clear prose, faithfulness to source, low fabrication.*

| Model | Score | Rationale | Access | Cost tier |
|---|---:|---|---|---|
| Claude Opus 4.8 | 94 | Clearer, warmer, less-hedged prose than 4.7; faithful to source; great for ADRs/DECISIONS. | Anthropic | frontier |
| Claude Sonnet 5 | 90 | Excellent docs at strong-tier; the workhorse writer for REVIEW-LOG/handoffs. | Anthropic | strong |
| Claude Haiku 4.5 | 83 | Strong instruction-following for its tier; fine for mechanical doc updates, changelogs, ticket writeups. | Anthropic | economy |
| Gemini 3 Flash | 82 | Cheap, fluent; good for SLOP docs and bulk summaries; verify technical claims. | Google | economy |

*Note:* docs is the safest place to push down-tier — a prose slip is caught in review, unlike a concurrency bug. Route most docs to economy/strong.

### Role 8 — Orchestrator / Manager
*Gating, scheduling, judgement, work-composition. Per rig doctrine this is a **human + model blend** — the operator gates/merges/pushes; a model runs the manager's substantive sub-sessions (investigation, board, review synthesis).*

| Model | Score | Rationale | Access | Cost tier |
|---|---:|---|---|---|
| Claude Opus 4.8 | 95 | Best judgement + long-horizon coherence for scheduling/dependency reasoning and DTC synthesis; strong instruction-following for the manager doctrine. | Anthropic | frontier |
| Claude Fable 5 | 95 | Best for the hardest composition/WCI reasoning and sustaining long multi-agent coordination; reserve for genuinely complex scheduling. | Anthropic | frontier+ |
| Gemini 3.1 Pro | 89 | Large context to hold the whole board + handoff state; good for status synthesis. | Google | frontier |

*Note:* the human operator remains the authority (per "adversarial review must not silently override operator" and "manager never spawns droids"). The model here advises and drafts; it does not gate.

---

## 4. Recommended Charon pool mapping

Concrete assignment of models to Charon's tier pools **for building these two projects**:

| Pool | Put these models in it | Primary use |
|---|---|---|
| **`frontier`** | Claude **Opus 4.8** (lead), Claude **Fable 5** (hardest reasoning / reserve), **GPT-5.5** (independent DTC voice), Gemini 3.1 Pro (long-context tracing) | DTC panels, architecture/ADRs, root-cause debugging, high-blast-radius reviews, gnarly concurrency/security implementation |
| **`strong`** | Claude **Sonnet 5** (default), **DeepSeek V4-Pro**, **Kimi K2.6** / GLM-5 / MiniMax M2.5 | Bulk implementation, refactors, test authorship, most well-specified units |
| **`economy`** | Claude **Haiku 4.5**, **Gemini 3 Flash**, **DeepSeek V4-Flash**, Qwen3-Coder-Next | Docs, changelogs, mechanical edits, SLOP glue scripts, ticket writeups, bulk summaries |

### 4a. Operator-nominated options (added 2026-07-03) — ADDITIONAL selectable models per tier

These are **extra options** the operator flagged as good for Python / Linux-CLI / agentic
workflows. They do **not** displace the rankings above — they widen the menu of models a build
session (or a Charon end-user via the tier picker) can drop into a pool. **Provider-agnostic:** each
row lists the access paths a model is reachable through; a model is an *option across providers*, not
a vendor coupling. Every non-Claude score is **directional (±several pts)** per §5 caveat 1 — sourced
from vendor launch posts + third-party blogs (minimax.io, qwen.ai/blog, mistral.ai/news,
z.ai/Zhipu, VentureBeat, HuggingFace), noisy in 2026.

| Model | Real / current? | Provider / access path | ~Agentic-coding (1-100) | Best tier | Notes (source noise flagged) |
|---|---|---|---|---|---|
| **GLM-5.2** (Zhipu / Z.ai) | Yes — 2026-06-13, MIT | Z.ai API **direct** · open weights (self-host) · OpenRouter | ~89 (borderline frontier) | **strong** (lead open pick) | ~753B MoE, 1M ctx. Vendor: SWE-bench Pro 62.1, Terminal-Bench 2.1 81.0, GDPval-AA 1524 Elo (~GPT-5.5) at ~1/6 cost. Vendor+VentureBeat — verify. |
| **MiniMax M3** | Yes — 2026-06-01, open weights | MiniMax API **direct** · open weights · OpenRouter/aggregators | ~88 (frontier-adjacent per vendor) | **strong** (escalate hard units) | 428B MoE / ~22B active, MSA attn, 1M ctx, multimodal. Vendor: SWE-bench Pro 59.0 (claims > GPT-5.5 / Gemini 3.1 Pro). Vendor-only — verify. |
| **MiniMax M2.5** | Yes — 2026-02-12, open weights | MiniMax API **direct** · open weights · OpenRouter/aggregators | ~86 | **strong** | 230B/10B MoE. Vendor: SWE-bench Verified 80.2, 1st Multi-SWE-Bench; ~Opus 4.6 speed. Prior-gen vs M3; keep as the cheaper/faster strong alt. |
| **DeepSeek-V4-Pro** | Yes — 2026-04-24, MIT open weights | DeepSeek API **direct** · open weights (self-host) · OpenRouter | ~87 (top open-weight value) | **strong** | 1.6T MoE / 49B active, 1M ctx, $0.435/$0.87. Blog: SWE-bench Verified 80.6, Terminal-Bench 2.0 67.9 (strongest open-weight agentic), ~within striking distance of Opus 4.7 / GPT-5.5 at ~1/30 cost. **`-Pro-Max` = max-reasoning-effort mode** (the current R-series/reasoner successor; folds R1-2025 lineage into V4). Already the §4 `strong` open anchor. Blog/vendor — verify. |
| **DeepSeek-V4-Flash** | Yes — 2026-04-24, MIT open weights | DeepSeek API **direct** · open weights (self-host) · OpenRouter | ~83 | **economy** | 284B MoE / 13B active, 1M ctx, $0.14/$0.28. Blog: SWE-bench Verified 79.0 (~1.6 pts behind V4-Pro); `-Flash-Max` reaches near-Pro reasoning with a bigger thinking budget. Cheap open-weight workhorse. Already the §4 `economy` open anchor. Blog/vendor — verify. |
| **Devstral 2** (Mistral) | Yes — 2025-12-09; mod-MIT (123B) / Apache (Small 24B) | Mistral API **direct** · open weights · OpenRouter | ~82 (123B) / ~76 (Small 24B) | **strong** (123B) / **economy** (Small 24B) | Purpose-built agentic coder, 256K ctx, ships Vibe CLI. Vendor: SWE-bench Verified 72.2 (123B) / 68.0 (Small 24B). Small 24B runs on one 4090/32GB Mac. |
| **Qwen3.6-27B** | Yes — 2026-04-22, Apache 2.0 | open weights self-host (1×H200 / 2×A100 FP8) · OpenRouter · Qwen API | ~80 (punches above 27B) | **economy** (best self-host pick) | Dense 27B, 262K ctx (→~1M). Vendor: SWE-bench Verified 77.2, Pro 53.5, Terminal-Bench 2.0 59.3; within ~4 pts of Opus on Verified. Dense = cheap local. |
| **Qwen3-Coder-Next** | Yes — 2026-02/03, open weights | open weights (HF/Ollama/Unsloth) · OpenRouter · Qwen API | ~78 | **economy** / strong | 80B/3B-active hybrid MoE, 256K ctx, agentic-RL trained. Vendor: >70% SWE-bench Verified at 3B active. **Already listed in the §4 `economy` pool** — restated here for completeness. |
| **Claude Sonnet 5** (`claude-sonnet-5`) | Yes — **current** | Anthropic **direct** (+ Bedrock/Vertex) | 91 (per §3) | **strong** (default implementer) | The **current** Sonnet; $3/$15 ($2/$10 intro→2026-08-31). **This is the recommended pick over Sonnet 3.5.** Already the §4 `strong` anchor. |
| **Claude Sonnet 3.5** (`claude-3-5-sonnet`) | **Legacy — 2024 model** | Anthropic **direct** (+ Bedrock/Vertex) | ~76 (legacy) | strong (legacy option only) | ⚠ **2024-era model, superseded by Sonnet 5.** Include only as a legacy/compat option (pinned older client, cost/availability edge case). **Prefer Sonnet 5** for all new routing. |

**Placement confirmation vs the operator's preliminary map:** verified — `strong` = MiniMax
M2.5/M3, GLM-5.2, Devstral 2 (123B), **DeepSeek-V4-Pro**, Sonnet 5 (current) / Sonnet 3.5 (legacy);
`economy` = Qwen3-Coder-Next, Qwen3.6-27B, **DeepSeek-V4-Flash** (+ Devstral Small 2 as an economy
self-host alt). The DeepSeek V4 family (V4-Pro strong, V4-Flash economy) were already the §4 open-weight
anchors — restated here as explicit selectable options; the operator is actively running V4-Pro
sessions. **No V3-Pro entry** (V4 supersedes it; use V4-Pro). GLM-5.2 and
MiniMax M3 are borderline `frontier` on vendor numbers but are placed **strong** here pending an
own-eval (§5 caveats 1-2) rather than trusting SEO-heavy launch benchmarks.

**Role → tier routing rules:**
- **DTC + architecture + root-cause debugging → `frontier`, always.** These gate everything; a wrong answer costs a whole cycle. Never down-tier them. Use ≥2 vendors on DTC (Claude + GPT-5.5) to break monoculture.
- **Implementation → `strong` by default**, escalate the subtle concurrency/networking/security units to `frontier` (Opus 4.8).
- **Docs / refactors / mechanical → `economy`**, escalate only if review bounces it.
- **SLOP over-indexes to `strong`/`economy`**; Charon over-indexes to `frontier`/`strong`. Cheap-work-to-cheap-models applies most to SLOP tickets.
- **Charon stdlib-only core:** any `strong`/`economy` open model gets an explicit "stdlib only, no third-party imports" guardrail; the hermetic test + CI gate is the backstop.

---

## 5. Caveats — verify before hard-coding

1. **Benchmark provenance.** Only the Claude-family facts are authoritative (Anthropic API skill). Every GPT / Gemini / DeepSeek / Kimi / Qwen / Mistral / GLM / MiniMax number here comes from vendor launch posts and third-party blogs, which in 2026 are noisy and SEO-heavy. Some cited arxiv/blog items looked speculative. Treat non-Claude scores as **±several points** and re-verify against a source you trust (or your own eval) before committing routing.
2. **Benchmark vs real traffic gap.** SWE-bench Verified is Python-GitHub-issue shaped and has known flawed instances at the top; it does **not** measure Charon's actual demands (stdlib discipline, security judgement, DTC refutation, whole-repo tracing). Your **own** signal — how a model does on a representative Charon ticket behind the adversarial gate — outranks any leaderboard. Consider a small internal eval on 3-4 past tickets (incl. the double-bill bug) before locking pools.
3. **Access + availability.** Open models (DeepSeek/Kimi/Qwen/GLM/MiniMax) reach the rig only via OpenRouter / opencode-zen — their availability, rate limits, quantization, and context caps vary by aggregator and can differ from the vendor's own numbers. Confirm the aggregator serves the full-precision, full-context variant.
4. **Fable 5 refusals on security work.** Fable 5 runs safety classifiers that can decline benign security tooling with `stop_reason: "refusal"`. Charon is security-sensitive — keep an Opus 4.8 fallback wired for any Fable 5 security-adjacent unit (server-side `fallbacks` or a routing rule).
5. **Reviewer self-censoring.** Opus 4.8 / Sonnet 5 (and per notes GPT-5.5) follow "be conservative / only high-severity" review instructions literally and drop findings — a real risk for the DTC gate. Prompt reviewers to report everything with confidence + severity; filter downstream.
6. **Cost is deliberately excluded from scores** per the brief. When you actually route, fold cost back in — e.g. Fable 5 (98 architect) rarely beats Opus 4.8 (96) enough to justify $10/$50 vs $5/$25 except on the hardest units.
7. **Model churn.** GPT-5.x, Gemini 3.x, and the open lineups are iterating monthly. Re-run this eval whenever a pool member ships a new version; the *roles and routing rules* are stable, the *specific model IDs* are not.

---

## Top-line

- **Best overall model for this work:** **Claude Opus 4.8** — best balance of agentic execution, root-cause debugging, adversarial review, and instruction-following at a frontier price that's actually affordable, and the best all-round fit for Charon's stdlib/security/test-heavy domain. **Claude Fable 5** is the quality ceiling — reserve it for the hardest architecture, debugging, and DTC, where its extra reasoning justifies the premium.
- **Best-value model per tier:** `frontier` → **Opus 4.8** ($5/$25, near-Fable quality); `strong` → **Sonnet 5** (near-Opus coding at $3/$15, $2/$10 intro) with **DeepSeek V4-Pro** as the open-weight value pick; `economy` → **Gemini 3 Flash** (frontier-adjacent SWE-bench at ~¼ Pro cost), with **Haiku 4.5** the best-instruction-following economy Claude.
- **Pool mapping:** frontier = Opus 4.8 + Fable 5 + GPT-5.5 + Gemini 3.1 Pro (DTC/architecture/debug); strong = Sonnet 5 + DeepSeek V4-Pro + Kimi K2.6 (implementation/refactor/test); economy = Haiku 4.5 + Gemini 3 Flash + DeepSeek V4-Flash + Qwen3-Coder-Next (docs/mechanical/SLOP glue). DTC + architecture + debugging stay on frontier; use two vendors on DTC to break Claude monoculture.
