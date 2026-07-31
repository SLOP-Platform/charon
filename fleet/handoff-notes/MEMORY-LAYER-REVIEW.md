# MEMORY-LAYER REVIEW (Lane 2) — deepseek-v4-pro

## NAME RESOLUTIONS FIRST
- **Hindsight** → resolved to **Lucid** (DomLynch, 2,130 LOC, MIT, stars=1, last commit Apr 2026). Hindsight proper (Vectorize AI, 239K LOC cloud product) is deprecated/enterprise. Lucid strips its memory kernel to SQLite-only. I also found the **a0-hindsight** Agent Zero plugin and **gbrain/Hermes-Hindsight** ecosystem.
- **Evermind** → **MNEMON SDK** (pforge-ai, PyPI 0.1.0, Apache-2.0, fully self-hosted). LLM-backed memory: ingest/query/maintenance pipeline with RRIF retrieval (relevance+recency+importance+frequency), knowledge graph via LangChain graph store, LLM-driven reflection cycle. Health-check stage is STUB. No MCP server, pure library. **Dependency conflict**: installs langchain-core 0.2.43, breaking langchain 1.x in this env.
- **Hypabase** → Python hypergraph library with agent-memory module (hypabase, PyPI 0.2.3, Apache-2.0, self-hosted SQLite). Generic hypergraph engine + PENMAN-notation agent memory layer. **NO LLM processing at all** — zero LLM calls. Embedding for search only. Temporal edges with valid_at/expired_at + supersede_edge(). Ran it: commitment tracking as temporal edges VERIFIED.
- **Forgetful** → ScottRBK/forgetful (PyPI 0.5.0, MIT, 287 stars, 225 commits, active Jul 2026). Self-hosted MCP memory server. SQLite+Postgres. FastEmbed for local-only embeddings. **Installed and RAN**: created memory, ran search. Plans+tasks with state machines (feature-gated, default OFF). Skills (Agent Skills standard). 42 tools behind meta-tool pattern.

## SUMMARY TABLE

| Target | Ran it? | LOC | Self-host | Last commit | Verdict |
|---|---|---|---|---|---|
| **Mem0** | Installed, API test ran (LLM 401), code read | ~35K+ | Yes (24 backends) | v2.0.14 Jul 2026 | REJECT — cloud-upsell telemetry, no auto-extraction |
| **Zep+Graphiti** | Zep cloned, Graphiti installed, code read | Graphiti ~15K, Zep ~100K+ | Graphiti:Yes, Zep:SaaS | Graphiti 0.29.3, Zep 3.25.0 | REJECT — Zep=SaaS egress; Graphiti alone needs Neo4j |
| **LangMem** | Installed, code read, imports verified | ~3K langmem core | Yes | 0.0.30 Jul 2026 | REJECT — LangChain/LangGraph lock-in, no auto-extraction |
| **Lucid (Hindsight)** | Installed (2,130 LOC), code read, ran test (LLM 401) | 2,130 | Yes (SQLite) | Apr 2026 | WATCH — clean, small, but no active maintenance |
| **Evermind** | Installed, code read (conflict with langchain 1.x) | ~520 core | Yes | 0.1.0 (unknown date) | REJECT — alpha, health-check STUB, version conflicts |
| **Hypabase** | Installed, RAN commitment test | ~4,800 | Yes (SQLite) | 0.2.3 (active) | WATCH — temporal hypergraph works, but zero LLM integration |
| **Forgetful** | Installed, RAN memory save+search | ~13,700 | Yes (SQLite+PG) | 0.5.0 Jul 2026 | WATCH-TOP — plans+tasks with state machines closest to need |

## PER-TARGET CAPABILITIES (derived from CODE, not pitch)

### Mem0 (mem0ai 2.0.14, Apache-2.0, 62K GitHub stars)
FULL INVENTORY: 24 vector stores · SQLite history/messages · lazy entity store (separate vector collection) · 18 LLM providers · 12 embedders · 5 rerankers · hybrid search (semantic+BM25+entity) · metadata filtering · memory expiration · procedural memory summaries · hash dedup · vision support · `linked_memory_ids` logical graph.
WHAT basic-memory LACKS: **None of these.** Mem0 has zero capabilities basic-memory lacks — both do explicit-add-then-semantic-search. Mem0 adds multi-backend support and cloud API, which we don't need.
EGRESS: Telemetry to PostHog (`phc_hgJkUVJFYtmaJqrvf6CYN67TIQ8yhXAkWzUn9AMU4yX`) even in OSS mode. Cloud `MemoryClient` sends ALL data to `api.mem0.ai`.
CRITICAL FINDING: NO automatic extraction. `add()` is 100% explicit. `infer=True` is just "LLM parses vs stores raw" — you still call `add()`. **The failure mode is agents not calling add(). Mem0 depends on agents calling add().**
TIMESTAMP/REFERENCE_DATE: **Rejected in OSS** with ValueError — cloud upsell.

### Zep+Graphiti: WHICH LAYER?
**Zep** = SaaS platform at api.getzep.com. SDK (`zep-cloud`) is an API client only — ALL data sent to their cloud. Legacy self-hosted CE is deprecated. **Egress: hard yes.**
**Graphiti** = temporal KG engine (Apache-2.0, 29K GitHub stars, 0.29.3). Requires Neo4j/FalkorDB/Kuzu/Neptune. **Temporal invalidation IS real**: edges carry valid_at/invalid_at/expired_at. LLM-driven contradiction detection during add_episode(). Four-strategy search (semantic+BM25+BFS+RRF/MMR/cross-encoder). Community detection+summarization via label propagation. Saga incremental summarization. Entity resolution with cosine+LLM dedup. Episode-to-entity MENTIONS linking. Fully self-hostable (Kuzu embedded option).
WHAT basic-memory LACKS: **Temporal invalidation** (valid_at→invalid_at→expired_at). **Community/saga summarization**. **LLM-driven contradiction detection**. **Graph-native search (BFS)**.
BUT: requires a graph DB — Kuzu embedded works but adds 7.6MB dependency. No automatic extraction — add_episode() is explicit. No plans/tasks/commitments.
COULD NOT RUN cross-session test: NanoGPT key invalid, no local LLM available.

### LangMem (langmem 0.0.30, MIT, 1,589 stars)
FULL INVENTORY: `MemoryStoreManager` (memory extraction+consolidation+update) · `ReflectionExecutor` (background thread with after_seconds scheduling) · `create_manage_memory_tool` + `create_search_memory_tool` (LangGraph tools) · Three prompt optimizers (gradient/metaprompt/prompt_memory) · token-based conversation summarization · namespace templating · dilated window search · TTL support · custom Pydantic schemas for typed memories.
WHAT basic-memory LACKS: **Background memory formation via ReflectionExecutor** (submit-and-forget with delay, dedup by thread_id). **Prompt optimization/feedback loop** (gradient/metaprompt strategies). **Token-budget conversation summarization** (incremental RunningSummary).
LANGCHAIN COUPLING: **Total.** Every class implements `Runnable`. Storage requires `langgraph.store.base.BaseStore`. LLM calls require `langchain_core.language_models`. Cannot work without LangChain + LangGraph. This is a framework plugin, not a drop-in library.
CRITICAL FINDING: ReflectionExecutor requires explicit `submit()` — no auto-trigger on message arrival. **It still depends on someone calling submit().**
Memory types (semantic/episodic/procedural) are LLM-driven via prompt, not distinct storage paths.

### Lucid (Hindsight kernel, MIT, 1 star, 2,130 LOC)
FULL INVENTORY: retain() with LLM fact extraction (5 dimensions: what/when/where/who/why) · recall() with 4-strategy RRF fusion (semantic+keyword+entity-graph+temporal decay) · reflect() multi-turn agent with tool-calling loop · SQLiteMemoryStore · Bank disposition knobs · entity resolution across retain calls · temporal inference (12 regex patterns for "yesterday"/"last week") · exponential-decay temporal search.
WHAT basic-memory LACKS: **Entity resolution across sessions** (cross-retain entity merging). **RRF multi-strategy fusion** (basic-memory does single-strategy search). **Multi-turn reflect agent** (basic-memory has no synthesis). **Causal links between facts**.
LIMITS: No auto-extraction (retain() is explicit). No temporal invalidation (no valid_at/invalid_at). No contradiction detection. No plans/tasks. SQLite-only — 2,130 LOC, zero dependencies beyond numpy+httpx. 1 GitHub star, last commit Apr 2026. **Maintenance liveness: effectively abandoned.**

### Evermind (MNEMON SDK, Apache-2.0, ~520 core LOC)
What it IS: LLM pipeline library. Ingest → importance-rate → embed → store. Query → plan → hybrid search → RRIF rerank → synthesize. Maintenance → LLM reflection (insights+knowledge triplets) → graph write. **Health-check stage (consolidation/compression/archiving) is STUB** — `pass` after logging.
WHAT basic-memory LACKS: **LLM-driven reflection** (extracts insights from top-100 memories, fuses knowledge triplets into graph). **RRIF multi-axis ranking** (relevance+recency+importance+frequency per task type).
LIMITS: Version 0.1.0 alpha. Health check not implemented. Dependency conflict (downgrades langchain-core). No temporal reasoning. No automatic extraction. No MCP server. Pure library — no agent integration story.

### Hypabase (Apache-2.0, ~4,800 LOC)
What it IS: Generic hypergraph library + PENMAN agent-memory module. HypergraphCore (1,526 LOC) — in-memory engine with O(1) vertex-set lookup, BFS path finding, HIF serialization. Temporal edges with valid_at/expired_at. Memory module: remember/recall/consolidate/forget with strength decay formula.
RAN IT: Commitment as typed, temporally-valid hyperedge — WORKS. Edge supersession via expire_edge()+new edge. Point-in-time queries (`.edges(at=t)`) filter correctly.
WHAT basic-memory LACKS: **Hypergraph model** (n-ary edges connecting >2 nodes, not just pairs). **Temporal validity** (valid_at/expired_at on every edge). **Point-in-time queries.** **Edge supersession** (atomic expire+replace). **Provenance tracking** (every edge has source+confidence). **HIF standard compliance**.
BUT: **Zero LLM processing.** No extraction, no embedding generation (has embedder for search only), no summarization. It is a data structure, not an agent memory system. You must model everything yourself. PENMAN grammar is a manual notation, not NLP.

### Forgetful (MIT, 287 stars, 13,700 LOC, installed+RAN)
What it IS: MCP memory server with Zettelkasten atomic memories, auto-linking knowledge graph, **plans+tasks with state machines** (feature-gated), procedural skills, typed entities with relationships, documents/code/files, token-budget retrieval, FastEmbed for zero-cloud embeddings.
RAN IT: `forgetful memory save` created memory with importance=10, local embeddings generated (BAAI/bge-small-en-v1.5, no API key), data in SQLite. Search works. Tool discovery shows 42+ MCP tools across 7 categories.
WHAT basic-memory LACKS: **Plans + tasks with state machines** (TODO→DOING→DONE, acceptance criteria gating, dependency gating, optimistic locking, cycle detection). **Entity relationships** (typed, directional, weighted, with metadata). **Mark-memory-obsolete** (soft-delete with superseded_by). **Skills** (Agent Skills standard, SKILL.md import/export). **Token-budget retrieval** (importance-sorted, budget-capped, with truncation flag). **Meta-tools pattern** (3 tools exposed to LLM). **Auto-linking knowledge graph** (bidirectional links on memory creation via embedding similarity).
LIMITS: No auto-extraction (agent must call create_memory). No temporal reasoning/decay. No contradiction detection. No deadlines/reminders in tasks (states only). Plans/tasks feature-gated OFF by default. All operations are explicit MCP calls.

## A-E SCORING (LETTA-REVIEW.md failures mapped)

| Target | A (Substitution) | B (Leverage) | C (Verification) | D (Throughput) | E (Product) |
|---|---|---|---|---|---|
| Mem0 | 0 — nothing to delete | 0 — same shape as basic-memory | 0 — no new verification | -1 — cloud upsell telemetry | 0 |
| Graphiti | 0 | +1 — temporal invalidation | +1 — contradiction detection | -1 — graph DB overhead | 0 |
| LangMem | 0 | +1 — background ReflectionExecutor | 0 | -2 — LangChain lock-in | 0 |
| Lucid | 0 | 0 | 0 | 0 | 0 |
| Evermind | 0 | 0 | 0 | -1 — runtime conflicts | 0 |
| Hypabase | 0 | +1 — temporal edges | 0 | 0 | 0 |
| **Forgetful** | 0 | **+2 — plans+tasks state machine, token budget** | 0 | 0 | +1 — MCP-native |

B-Score rationale: Forgetful's plans+tasks state machine (with acceptance criteria, dependencies, optimistic locking) creates a place where an agent CAN record a commitment and the system enforces its lifecycle. This is the only mechanism in any target that addresses the "26 branches stranded" shape of failure — not by remembering better, but by having a structured work-tracking layer that agents can populate.

## CAPABILITIES WITH NO ANALOGUE IN basic-memory

| Capability | Tool | Value |
|---|---|---|
| Temporal invalidation (valid_at/invalid_at/expired_at) | Graphiti, Hypabase | Facts know when they stopped being true |
| LLM contradiction detection during ingestion | Graphiti | New facts auto-invalidate contradictory old ones |
| Background ReflectionExecutor (submit-and-forget with delay) | LangMem | Memory formation scheduled, not fire-and-forget |
| Plans+tasks state machine with dependencies+criteria | **Forgetful** | Structured work tracking across sessions |
| Hypergraph (n-ary edges) with point-in-time queries | Hypabase | Multi-entity relationships with temporal validity |
| RRIF multi-axis retrieval (relevance+recency+importance+freq) | Mem0, Evermind | Ranking that decays stale memories |
| Multi-turn reflect agent with tool-calling | Lucid | Synthesis over retrieved facts |
| Prompt optimization feedback loop | LangMem | Prompts improve from usage data |
| Meta-tools pattern (3 exposed, 42 discoverable) | Forgetful | Token-efficient MCP surface |
| Mark-memory-obsolete with superseded_by chain | Forgetful | Lifecycle beyond create/delete |
| Auto-linking knowledge graph on create | Forgetful | Graph grows without explicit link calls |

## ZEP VS GRAPHITI — WHICH LAYER

**Graphiti (library).** Zep is the SaaS on top — all data to api.getzep.com. Legacy self-hosted CE is abandoned. Graphiti alone is self-hostable but needs a graph DB (Kuzu embedded works). Adoption would mean: integrate graphiti_core as a library, run Kuzu embedded, call add_episode() after each session. No egress. But we'd still need agents to remember to call it — same failure mode.

## DOES ANYTHING BEAT FINISHING basic-memory (MEMORY-INDEX-COMPACTION)?

**No.** Every target requires explicit write calls. The measured failure — agents not writing things down, not blocking on unfinished commitments — is not solved by any memory-layer tool we studied. Finishing basic-memory's compaction pipeline would improve recall quality. But the actual gap (26 branches stranded despite 60+ loaded memories) requires something none of these provide: **a structured work-tracking layer that makes unfinished work VISIBLE and queryable by the manager session, with lifecycle enforcement.**

Forgetful's plans+tasks (feature-gated, default OFF) is the single mechanism across all 7 targets that comes closest — **not as a memory system, but as a work-tracking system layered on top of basic-memory.** If we turn on PLANNING_ENABLED and wire tasks into the manager's pre-session board check, unfinished commitments become structured data that the board query can surface.

## ADOPT-CANDIDATES: NONE
Forgetful's plans+tasks is the most relevant mechanism and the only one among all 7 targets that has state-machine-enforced work tracking. But finishing basic-memory compaction and adding a simple commitment/checklist data structure to the manager's pre-session prompt is more direct and avoids a new dependency. Graphiti's temporal invalidation is real but requires Neo4j/Kuzu maintenance. Hypabase's temporal hypergraph is clean but has zero LLM integration. LangMem's ReflectionExecutor is the closest to "automatic" memory but still depends on explicit submit() and requires adopting LangChain.

**What I tried hardest**: Mem0's "automatic extraction" claim — it does not exist. Graphiti's temporal invalidation — real but untested (no LLM accessible). Forgetful's plans+tasks — the only structured work-tracking mechanism found.
