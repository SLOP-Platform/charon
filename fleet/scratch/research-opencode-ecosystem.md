# opencode-ecosystem research: routing + observability contributions to Charon

Researched 2026-07-07. Web + GitHub only, no code pulled into the tree. Grounded
against current Charon internals: `src/charon/pools.py` (`PoolEntry`,
`derived_cost_rank`, free-first→cost_rank stable sort, `.charon/models.json` +
`.charon/pools.json` hand-authored pool data) and the benchmark-v2 effort
(`benchmark/lib/efficiency.py`, tokens>time>cost weighted `EFF_PCT` scoring,
per fleet/scratch/v2-scoring-build-report.md).

---

## 1. opencode model discovery / models.dev — could it replace hand-maintained pools?

**What it is.** opencode does not discover models itself at runtime for hosted
providers — it consumes **[models.dev](https://models.dev)**, a *separate*,
standalone, MIT-licensed open-source project (github.com/sst/models.dev,
mirrored as anomalyco/models.dev) that is a community-maintained database of
AI model specs. Data lives as **TOML files per provider/model** in the repo
and is served as a static JSON snapshot at `https://models.dev/api.json`
(confirmed by direct fetch — not a live per-request API, more a periodically
rebuilt static catalog). Per-model fields include `id`, capabilities
(`tool_call`, `attachment`/multimodal, `reasoning`, `structured_output`),
`limit.context` / `limit.output`, `open_weights`, `knowledge` cutoff, and
`cost.input` / `cost.output` / `cost.cache_read` / `cost.cache_write` (USD per
1M tokens). Example entry: `openai/gpt-5.4-pro` → `tool_call: true`,
`limit.context: 1050000`, `cost: {input: 30, output: 180, cache_read: 30}`.

opencode's own docs (opencode.ai/docs/models) say only: "Most popular
providers are preloaded by default... if you've added credentials via
`/connect` they'll be available." That's opencode bundling the models.dev
catalog + credential presence check — **not** live endpoint probing.
**True runtime auto-discovery from an OpenAI-compatible `/v1/models` endpoint
is still an open feature request** (anomalyco/opencode#6231, open, assigned,
references a linked PR #8359, precedent from a third-party plugin
`opencode-lmstudio` that already does this for LM Studio only). So opencode
itself has two separate mechanisms: (a) a curated static metadata catalog
(models.dev) for pricing/capabilities of known hosted models, and (b) an
unfinished/community-plugin-only mechanism for probing local/self-hosted
OpenAI-compatible servers.

**Freshness.** models.dev keeps current via **GitHub PRs from the community**
— "the project needs help keeping it up to date" per its own README. No
automated pricing-scrape/freshness guarantee found. This matters: it is
crowd-maintained, same failure mode Charon is trying to avoid (a hand list),
just maintained by a bigger crowd instead of one operator.

**Verdict for Charon.** Two separable ideas, don't conflate them:
- **Pricing/capability metadata** (replace hand-typed `cost_input`/`cost_output`
  in `.charon/models.json`): models.dev's static `api.json` is a genuinely
  useful **one-time or periodic import source** — pull it, map provider/model
  IDs Charon already tracks, backfill `cost_input`/`cost_output` so
  `derived_cost_rank()` computes automatically instead of being hand-typed
  per entry. This is additive, offline, and doesn't add a live dependency —
  fits "ships standalone": vendor a snapshot or make refresh an opt-in
  `charon models refresh-pricing` command, never a runtime fetch on the hot
  path. Low effort, concrete win for the cost_rank half of the routing design.
- **Discovering the *pool membership itself*** (which agent+model+provider
  combos are routable, e.g. the ~50 pool entries in pools.json): models.dev
  does NOT solve this — it only enriches models Charon already knows about
  with pricing/capability data; it doesn't know which providers/keys the
  operator has, which agent backends (opencode/codex/etc.) support which
  model, or Charon-specific fields (`code_safe`, `upstream_base`, `key_env`,
  `agent`). The opencode `/v1/models`-probing feature (#6231) is the piece
  that's actually about *that* kind of discovery, and it's unfinished
  upstream, single-provider-shape (OpenAI-compatible `/v1/models` list only,
  no cost/capability info in that response), and not yet in opencode core.
  **Do not wait on it or copy it 1:1** — but the pattern (probe configured
  providers' `/v1/models` at startup, merge into candidate pool, still
  require an explicit opt-in/allowlist per role) is a legitimate design for
  Charon's own pool-population step, decoupled from models.dev.

**Bottom line:** auto-discovery does not replace the hand-maintained pool
*list* (which agent/provider/role combos are wired up is inherently an
operator/credential decision), but a models.dev snapshot import can kill the
hand-typed *pricing fields* that already exist as a `derived_cost_rank()`
input, which is the more mechanical, currently-manual part.

---

## 2. github.com/agostinilabsrl/opencode-telemetry

Note: this exact org/repo did not surface via GitHub/web search (searches for
"agostinilabsrl opencode-telemetry" return nothing under that org name); the
closest and evidently-intended match, matching the "opencode-telemetry"
name/description exactly (local SQLite session telemetry plugin), returned by
WebFetch on the given URL is described below — flagging the org-name mismatch
as a fact-check gap rather than silently substituting.

**What it does.** A TypeScript opencode plugin providing "continuous local
telemetry for opencode sessions," logging to a local SQLite DB
(`~/.local/share/opencode-telemetry/data.db`). Captures: token consumption
(counts + composition, byte-based ±15% accuracy, not exact tokenizer),
per-conductor-chain cost roll-ups (parent/child session cost aggregation),
turn-by-turn token trajectory / context-growth forensics (e.g. "turn 32
consumed 20k tokens from bash output"), session metadata (duration, agent
name, model id), and tool/skill usage counts. Explicitly does **not** log
prompt content by default (metadata-only DB; optional content cache,
disabled in server deployments) — a reasonable privacy default.

**Hook-in mechanism.** Standard opencode plugin system: install via
npm/bun, add `"opencode-telemetry"` to the `plugins` array in
`~/.config/opencode/config.json`. Ships 3 slash commands
(`/telemetry-report`, `/telemetry-inspect`, `/telemetry-db-analyst`) plus a
CLI binary `octm` to query the DB without burning model tokens.

**Maturity/license.** MIT. Very small/early: 2 stars, 0 forks, ~75 commits,
19 tags/releases (rapid tagging, not necessarily rapid adoption). Zero
external runtime dependencies for core capture — no cloud/OTel infra
required, which is nice for footprint but also means "maturity" here is
really "one maintainer's own tool," not something battle-tested.

**Adoptability into Charon.** Architecturally opencode-plugin-specific (hooks
opencode's plugin lifecycle API directly) — **not portable as-is**; Charon is
provider/agent-agnostic and can't depend on the opencode plugin runtime for
its own gateway observability. What IS portable as a *pattern*, not code:
(1) local-first SQLite session/turn ledger instead of an external
OTel/Prometheus dependency — matches Charon's "ships standalone" constraint
better than the sibling `opencode-plugin-otel` project (which pushes to
Datadog/Honeycomb/Grafana via OTLP — heavier, external-service-coupled, not
appropriate for a solo-dev standalone gateway); (2) "don't log prompt content
by default" as a default worth carrying into any Charon routing/observability
log design; (3) the specific idea of tracking cost/tokens *per orchestration
chain* (parent→child sessions), which maps directly onto Charon's own
tiered/multi-agent work — currently nothing in `pools.py`/gateway surfaces
this. **Net: dead-end as a dependency, useful as a 30-minute design reference
for "what fields should a local SQLite routing-health ledger have."**

---

## 3. github.com/itsarbit/tokenwise

**What it does.** TokenWise is a Python LLM task planner/router with explicit
cost governance — decomposes a task, assigns each subtask to a model tier via
`Router.route()` (escalation strategies: cheapest → balanced → best_quality),
executes via async DAG (`Executor`), and escalates to a stronger tier on
validation failure. It is NOT primarily an observability/telemetry tool for
an existing gateway — it's a planner that makes its own routing decisions,
closer to Charon's tiering logic than to an add-on you bolt onto one.

**Cost/token accounting (the relevant piece).** Every routing decision
produces a `RoutingTrace`: request_id, initial/final model selection,
escalation records with reason codes, termination state, budget tracking.
Actual per-call cost/tokens/failures/retries are persisted to a **JSONL cost
ledger** (`~/.config/tokenwise/ledger.jsonl`); a `CostLedger` also tracks
*wasted* cost from failed attempts separately from successful spend — a
detail Charon's cost_rank does not currently distinguish (derived_cost_rank
is static list-price only, not actuals). Caveat: token counts feeding the
*budget ceiling* are heuristic (`chars/4 * 1.2` safety margin), not real
tokenizer counts — the ledger's *recorded actuals* come from provider
responses where available, but the pre-flight budget check is an estimate,
so don't treat "budget enforcement" as exact.

**Architecture/coupling.** Library + CLI + OpenAI-compatible proxy server
(`tokenwise serve` — drop-in). Explicitly provider-agnostic: default gateway
is OpenRouter, but direct OpenAI/Anthropic/Google supported via env vars,
behind a `ProviderResolver` abstraction with a registry-driven model-metadata
system. Zero opencode coupling — this is a standalone Python project, not an
opencode plugin, which is the opposite dependency shape from #2 above and
much closer to something Charon could actually reuse or crib from.

**Maturity/license.** MIT-equivalent-permissive (need final confirm — repo
states permissive OSS), PyPI package `tokenwise-llm`, v0.5.0 (Feb 2026), 8
releases, 64 commits, 7 stars, has a `tests/` dir with pytest, 1 open PR.
Small and young — do not take a runtime dependency on it, but it's Python
(same language as Charon) which lowers the cost of reading its source for
patterns.

**Adoptability into Charon — this is the most directly relevant of the
three.** Two concrete, portable ideas map onto stated Charon design gaps:
1. **`cost_rank` → actuals feedback loop.** Today `derived_cost_rank()` in
   `pools.py` is purely static (list-price `cost_input`/`cost_output` blended
   3:1). TokenWise's pattern — a persistent per-call ledger of *actual*
   cost/tokens/success-failure, separating wasted-cost-from-failures — is
   exactly the missing half. Charon could add a local JSONL/SQLite ledger
   (same local-first, no-external-service shape as tokenwise's
   `~/.config/tokenwise/ledger.jsonl`) recording each pool-entry attempt's
   actual tokens/cost/outcome, then let `cost_rank` blend static price with
   observed reliability — without adding a network dependency.
2. **benchmark-v2's tokens>time>cost weighting** already scores model
   efficiency; TokenWise's `RoutingTrace` (escalation reason codes +
   termination state) is a good schema reference for what a Charon
   "why did routing pick/reject this pool entry" trace record should capture
   for post-hoc analysis — currently pools.py has no trace/log of routing
   decisions at all, only the final sorted list.

**Not adoptable as-is:** the `Router`/`Planner`/task-decomposition layer
overlaps with Charon's own tiering — pulling in TokenWise's planner would be
redundant/competing logic, not a fit. Treat it as a reference for the ledger
schema and trace shape only, not as a dependency.

---

## Summary table

| Tool | Type | License | Maturity | Adopt as dependency? | Adopt as pattern? |
|---|---|---|---|---|---|
| opencode model discovery / models.dev | static metadata catalog (crowd-sourced) + unfinished live-probe feature | MIT | models.dev: established/community; live-probe: unmerged issue | No (don't add live dep) | Yes — one-time/periodic pricing import to auto-fill `cost_input`/`cost_output`; `/v1/models` probe pattern for pool *candidate* discovery (still needs operator allowlist) |
| agostinilabsrl/opencode-telemetry (name unverified, closest match fetched) | opencode plugin, local SQLite session ledger | MIT | Very early (2 stars) | No (opencode-plugin-locked) | Yes — local-first ledger shape, no-prompt-content-by-default, per-orchestration-chain cost rollup |
| itsarbit/tokenwise | Python router/planner + cost ledger + proxy | Permissive (MIT-like) | Early (7 stars, v0.5.0) | No (competing planner logic) | Yes — actuals-based cost ledger to feed `cost_rank`; `RoutingTrace` schema for a routing-decision log Charon currently lacks |

**Overall for the "simpler/cleaner routing + observability design" goal:**
none of the three are drop-in dependencies without violating standalone/
provider-agnostic constraints. The concrete, low-effort next steps they
point to: (a) periodic models.dev snapshot import to stop hand-typing
pricing into `.charon/models.json`, (b) a local JSONL/SQLite per-attempt
ledger (actual tokens/cost/outcome) feeding `derived_cost_rank` and giving
Charon the pool-health visibility it currently lacks, (c) a routing-decision
trace record (why a pool entry was picked/skipped) modeled loosely on
TokenWise's `RoutingTrace`. All three are buildable in-tree with zero new
runtime dependencies.
