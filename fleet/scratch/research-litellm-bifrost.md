# LiteLLM & Bifrost as reference architectures for collapsing Charon's pool sprawl

Date: 2026-07-07. Scope: web research only, no code changes.

## Context: what Charon does today

`src/charon/pools.py` + `.charon/{models.json,pools.json}`: `pools.json` maps
**role → ordered list of model ids**, hand-authored per role. `load_pools()`
resolves each id against `models.json` (the provider/cost/code_safe registry),
sorts free-first/cheapest-first (stable), and `failover.py::next_entry()` walks
the list excluding whatever the gateway proxy has flagged exhausted. This is
functionally close to LiteLLM's `model_name` grouping (a pool ~ a `model_name`
group) but the *membership* of each pool is 100% manual: every time a model or
provider is added, the operator must remember to append its id into every role
array that should be able to use it. With ~50 roles/pools that's ~50 hand-edits
per new provider, and nothing enforces "this role's pool actually contains
every model that satisfies its constraints."

## LiteLLM (BerriAI/litellm — Router + Proxy)

**1. Model grouping.** `model_list` entries share a `model_name` field; every
entry with the same `model_name` is treated as an interchangeable deployment
of that logical model. This *replaces* per-model pool arrays with grouping-by-
key: you don't maintain a separate list of "who can serve gpt-4o" — you just
give every deployment the same `model_name` and the router does the grouping.
Charon's role-keyed pools are one level higher (capability, not exact model),
so this doesn't map 1:1, but the "give it a shared name and stop hand-listing
membership" pattern is the transferable idea (see recommendations).

```yaml
model_list:
  - model_name: gpt-4.1-mini
    litellm_params: {model: azure/gpt-4.1-mini, api_base: ..., weight: 1}
  - model_name: gpt-4.1-mini
    litellm_params: {model: openai/gpt-4.1-mini, api_key: ..., weight: 1}
router_settings:
  routing_strategy: simple-shuffle
  enable_weighted_failover: true
```

**2. Fallback / retry / cooldown.** Three explicit fallback classes —
`fallbacks` (general), `content_policy_fallbacks`, `context_window_fallbacks`
— each an ordered `{model_name: [fallback_model_names]}` map, plus a catch-all
`default_fallbacks`. Within a `model_name` group, `enable_weighted_failover`
re-picks a sibling deployment (excluding the failed one, renormalizing
weights) before ever falling through to a cross-group fallback — i.e. it
exhausts same-model redundancy before downgrading model. Cooldowns are
per-deployment: `allowed_fails` (default 3/min) trips `cooldown_time` (default
30s); 429s trip cooldown immediately. Retries: `num_retries` + exponential
backoff, or a full `RetryPolicy` keyed by exception type. Multi-instance
deployments need Redis to share cooldown/rate-limit state.

**3. Cost/tier/priority routing.** Six `routing_strategy` values:
`simple-shuffle` (weighted random, default/recommended), `least-busy`,
`latency-based`, `usage-based-routing`/`v2` (TPM/RPM aware, Redis-backed),
`cost-based-routing` (cross-references `litellm_model_cost_map` or per-deployment
`input_cost_per_token`/`output_cost_per_token`), and a pluggable
`CustomRoutingStrategyBase`. A separate `order` field on `litellm_params` gives
static priority tiers (lower = tried first) orthogonal to the routing strategy
— this is the closest LiteLLM primitive to Charon's free-first/cheapest-first
stable sort.

**4. Config style.** Declarative YAML (`config.yaml`), no auto-discovery of
providers/models — every deployment is still hand-listed in `model_list`, just
grouped by name instead of duplicated per consumer. Upkeep is "add one
`model_list` entry" vs Charon's "find and edit N pool arrays."

**5. Observability/cost tracking.** Built-in: `/global/spend/report`,
`/user/info` spend endpoints, multi-layer budgets (org/team/project/user/key),
hard+soft limits, native Prometheus + OpenTelemetry, first-class Langfuse
integration for per-call token/cost/latency tracing.

**6. Adoptability.** MIT-licensed (majority of code), Python, pip-installable
or Docker. It's a full proxy server (FastAPI) with an optional Postgres +
Redis backing for multi-instance state, spend tracking, and virtual keys —
heavier than Charon's "single static binary/venv, OpenAI-compatible" identity.
Running it *as* Charon's gateway would mean adopting Python+FastAPI+Postgres/
Redis as a hard dependency, which conflicts with the "ships standalone, no
external runtime" constraint. Borrowing the **design** (group-by-name +
declarative fallback lists + per-deployment cooldown/order) into Charon's own
Python code is cheap; embedding the actual project is not.

## Bifrost (maximhq/bifrost)

**1. Model grouping.** No `model_name`-style grouping primitive; instead
routing is driven by **Virtual Keys**, each holding a `provider_configs` list.
Each provider entry has `allowed_models` (explicit list, `["*"]` wildcard
against a live Model Catalog, or `[]` = deny-all) and a `weight`. A request for
a bare model name (e.g. `gpt-4o`) is matched against every provider in the VK
whose `allowed_models` covers it; that set *is* the pool, computed at request
time rather than hand-listed per model. This is arguably a cleaner escape from
per-model pool sprawl than LiteLLM's: you configure capability at the
provider level once ("Azure can serve gpt-4o, Anthropic can serve claude-*")
and every model that provider supports is automatically groupable.

```json
{"provider_configs": [
  {"provider": "openai", "allowed_models": ["gpt-4o", "gpt-4o-mini"], "weight": 0.2},
  {"provider": "azure",  "allowed_models": ["gpt-4o"],                "weight": 0.8}
]}
```

**2. Fallback/retry/cooldown.** Automatic: providers matching the model are
sorted by weight (desc) and chained as fallbacks; on 429/5xx/timeout/model-
unavailable the chain retries the next provider. Explicit `fallbacks` array in
a request overrides the auto-generated chain. Enterprise-only **Adaptive Load
Balancing** adds a scored provider-selection layer (error rate 50%, latency
20%, utilization 5% weight, with recovery momentum) — the closest thing to a
circuit-breaker/cooldown model, but it's gated behind the paid tier; the OSS
docs don't detail an OSS-tier cooldown/backoff policy beyond "retry next in
chain."

**3. Cost/tier/priority routing.** Static weighted load balancing (weights
normalized to 1.0) is the OSS mechanism — no free/cheapest-first primitive out
of the box; you'd encode "prefer free tier" by weighting it near 1.0 and
everything else near 0, which is coarser than LiteLLM's explicit cost-based
strategy or Charon's cost_rank sort. Real performance/cost-aware adaptive
routing is enterprise-gated.

**4. Config style.** JSON, API-driven (PUT to `/api/governance/virtual-keys/{id}`)
or a `config.json` file; also has a web UI for dynamic provider config. No
YAML. Provider-level `allowed_models` wildcards give a form of auto-discovery
(new models a provider adds become usable without a config edit if `["*"]` is
set), which is a genuine upkeep win over both LiteLLM and Charon's current
scheme.

**5. Observability/cost tracking.** Native Prometheus metrics, OpenTelemetry
distributed tracing, hierarchical budgets/rate limits at virtual-key/team/
customer level, real-time monitoring dashboard (web UI). Less documented in
public OSS docs than LiteLLM's spend-tracking surface, but present.

**6. Adoptability.** Apache-2.0, Go, single static binary (`npx -y
@maximhq/bifrost` for a 30s local run, or Docker/Helm/embedded-Go-SDK),
~2 vCPU/4GB minimum footprint, claims <100µs overhead at 5k RPS and no
mandatory external DB for the OSS core. This is architecturally much closer to
Charon's own "single self-hosted OpenAI-compatible gateway" identity than
LiteLLM is — but embedding Bifrost itself would mean depending on a Go project
(Charon is Python) and would still cross the "don't add a heavy runtime
dependency" line, plus its most relevant routing intelligence (adaptive
load-balancing) is enterprise-only. Best used as a **design reference**, not a
dependency: provider-scoped `allowed_models` + weight, wildcard-driven
auto-discovery, and weight-sorted automatic fallback chains are all portable
ideas even though the code isn't.

## The "opencode + LiteLLM" integration — investigated explicitly

Bottom line: **there is no special opencode-LiteLLM edition, fork, or bundled
proxy.** opencode does not ship LiteLLM, and LiteLLM does not ship or fork
opencode. What exists is:

- A **LiteLLM-authored tutorial**
  (`docs.litellm.ai/docs/tutorials/opencode_integration`) showing how to point
  opencode at a LiteLLM proxy using opencode's *generic* custom-provider
  mechanism — the same mechanism used for any OpenAI-compatible backend:

  ```json
  {
    "$schema": "https://opencode.ai/config.json",
    "provider": {
      "litellm": {
        "npm": "@ai-sdk/openai-compatible",
        "name": "LiteLLM",
        "options": { "baseURL": "http://localhost:4000/v1" },
        "models": {
          "gpt-4": { "name": "GPT-4" },
          "claude-3-5-sonnet-20241022": { "name": "Claude 3.5 Sonnet" }
        }
      }
    }
  }
  ```
  Model keys in the `models` block must match LiteLLM's own `model_name`
  values; auth is via `LITELLM_API_KEY`/`LITELLM_MASTER_KEY` or
  `provider.litellm.options.apiKey`.

- opencode's own provider docs (`opencode.ai/docs/providers/`) confirm LiteLLM
  is **not** one of the 75+ first-class `/connect` providers. It's reached
  purely through the documented "add any OpenAI-compatible provider" path:
  `npm: "@ai-sdk/openai-compatible"` + a `baseURL`. This is *exactly* the slot
  Charon occupies for opencode users today — confirmed in Charon's own
  `src/charon/connect.py::_write_opencode()`, which writes
  `provider.charon = {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": ...}}`
  into the same `opencode.json`. **Charon and LiteLLM are interchangeable at
  this seam** — opencode cannot tell them apart; both just look like an
  OpenAI-compatible base URL with a model list. Charon is not "missing" an
  opencode-LiteLLM feature; it already implements the same integration
  contract LiteLLM's tutorial documents.

- A cluster of **third-party opencode plugins**
  (`opencode-plugin-litellm`, `yuseferi/opencode-litellm`,
  `BlakeHastings/opencode-litellm`, `i-dot-ai/coding-agent-litellm-config`) add
  one thing the raw tutorial config doesn't: **auto-discovery**. They query the
  LiteLLM proxy's `/v1/models` at opencode startup and merge discovered models
  into the config in memory (hand-curated entries win on key collision;
  discovered ones only fill gaps), so opencode's model picker stays in sync
  with `litellm config.yaml` without hand-editing `opencode.json` per model.
  One variant (`i-dot-ai/coding-agent-litellm-config`) goes further and
  auto-generates the LiteLLM-side config itself by mapping capabilities from
  models.dev.

**Relevance to Charon.** This is directly on-point but not in the direction
the coordinator's question implied — it's not "LiteLLM has a better opencode
connector Charon should copy," it's "Charon already sits in the identical
architectural seam LiteLLM occupies for opencode users, and already does the
discovery half of what the community LiteLLM plugins bolt on afterward":
`src/charon/discover.py::discover_provider()` already queries any provider's
`/v1/models` and Charon writes the merged opencode provider block from
`connect.py`. What Charon does **not** yet do — and where the plugin pattern
is genuinely instructive — is use that discovery to auto-populate/reconcile
`pools.json` membership the way the plugins auto-populate opencode's model
list: today `discover.py` builds a cost map, but pool *membership* (which role
can use which discovered model) is still the hand-maintained step. That's the
same gap pattern #1 and #4 below target, just confirmed by a second
independent source (the opencode plugin ecosystem solving the identical
"don't hand-list every model everywhere" problem on the opencode side of the
gateway, mirroring what's needed on the pools side).

## Comparison at a glance

| | LiteLLM | Bifrost |
|---|---|---|
| Grouping unit | `model_name` (per-deployment tag) | Virtual Key → provider `allowed_models` |
| Pool membership | Hand-listed per deployment, but shared name = shared pool | Computed per-request from provider capability + wildcard |
| Fallback config | Explicit ordered maps (3 classes) + `order` priority | Auto weight-sorted chain; explicit override optional |
| Cost-aware routing | Yes, first-class `cost-based-routing` strategy | No (OSS); adaptive scoring is enterprise |
| Cooldown/circuit-break | Yes, per-deployment, OSS | Sequential retry only in OSS; scored recovery is enterprise |
| Config format | YAML, manual | JSON, API/UI-driven, wildcard auto-discovery |
| License/lang/footprint | MIT (mostly), Python, FastAPI, wants Postgres+Redis at scale | Apache-2.0, Go, single binary, ~2vCPU/4GB, no DB required |
| Fit as a Charon dependency | Poor — wrong language, heavier runtime | Better runtime fit, wrong language, best routing gated behind paid tier |
| Fit as a design reference | High | High |
| opencode integration | Generic `@ai-sdk/openai-compatible` custom provider (LiteLLM-authored tutorial, not native); community plugins add `/v1/models` auto-discovery into `opencode.json` | Same generic mechanism; no LiteLLM-style tutorial/plugin ecosystem found |
| Charon's seam vs this | Charon already occupies the identical seam (`connect.py` writes the same provider block); discovery half already built in `discover.py` | n/a — Bifrost isn't positioned opencode-side, it's provider-side like Charon itself |

## Highest-value patterns to borrow into Charon (no new dependency)

1. **Group-by-capability instead of hand-listed membership** (LiteLLM
   `model_name` groups / Bifrost `allowed_models`). Today `pools.json` requires
   editing every relevant role array when a model/provider is added. Instead,
   tag each `models.json` entry with the capability/role tags it satisfies
   (already have `code_safe`, `cost_tier`; add e.g. `roles: ["coder",
   "reviewer"]` or a wildcard `roles: ["*"]`), and derive each role's pool at
   `load_pools()` time by filtering the registry — collapsing N hand-maintained
   arrays into one registry pass. This is the single highest-leverage change:
   it directly kills the "~50 pools to hand-edit" problem.

2. **Ordered fallback classes, not just one flat list** (LiteLLM's
   `fallbacks` / `content_policy_fallbacks` / `context_window_fallbacks`
   split). Charon's `next_entry()` currently treats all exclusions uniformly;
   distinguishing "rate-limited, try a same-tier sibling" from "context window
   exceeded, need a bigger-context model" from "content policy, need a
   different vendor" would let the free-first sort stay intact for the common
   case while still escaping correctly for the others.

3. **Per-entry cooldown with `allowed_fails`/`cooldown_time`, not just binary
   exhausted/live** (LiteLLM). Charon's `proxy_excluded_keys()` currently reads
   a boolean "exhausted" flag from the gateway proxy; borrowing LiteLLM's
   "N fails per minute trips a timed cooldown, then auto-recovers" would let a
   transiently-flaky provider un-exclude itself without an operator restart,
   and is a small, self-contained addition to `failover.py`.

4. **Wildcard/auto-discovery membership** (Bifrost `allowed_models: ["*"]`).
   Once pattern #1 lands, let a registry entry (or a provider block) opt a
   model into *every* role automatically (`roles: ["*"]`) rather than needing
   an explicit tag — this is what actually removes the "add a provider, then
   remember every place it needs to be listed" toil Bifrost's docs point at
   directly ("providers without configuration are blocked; empty model lists
   reject all requests" — deny-by-default, opt-in by wildcard, same spirit as
   Charon's INV-P0 loud-config-error stance).

Neither project should be added as a runtime dependency: LiteLLM is the wrong
language/stack and pulls in Postgres+Redis at any real scale; Bifrost is the
wrong language (Go vs Charon's Python) and gates its best routing intelligence
behind an enterprise tier. Both are safe, well-documented references to steal
the *shape* of the config from, not the binary.

## Sources
- https://docs.litellm.ai/docs/routing
- https://docs.litellm.ai/docs/proxy/reliability
- https://docs.litellm.ai/docs/routing-load-balancing
- https://docs.litellm.ai/docs/proxy/load_balancing
- https://docs.litellm.ai/docs/proxy/cost_tracking
- https://deepwiki.com/BerriAI/litellm/2.3-router-and-load-balancing
- https://deepwiki.com/BerriAI/litellm/3.3-budget-and-spend-tracking
- https://www.litellm.ai/
- https://github.com/maximhq/bifrost
- https://docs.getbifrost.ai/overview
- https://docs.getbifrost.ai/features/governance/routing
- https://github.com/maximhq/bifrost/blob/dev/docs/providers/provider-routing.mdx
- https://dev.to/kuldeep_paul/adaptive-model-routing-and-fallback-logic-routing-around-llm-provider-outages-with-bifrost-4g3m
- https://www.getmaxim.ai/bifrost/resources/buyers-guide
