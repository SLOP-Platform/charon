# orq.ai comparison — adoptable patterns for Charon's routing/gateway plane

> Independent research subsession, 2026-06-24. Question: what can Charon sanely and
> logically adopt from orq.ai (LLM gateway / LLMOps SaaS) for its routing/gateway
> plane? Full sourcing in the subsession; key URLs: orq.ai, gateway.orq.ai,
> gateway.orq.ai/orq.ai-vs-litellm, orq.ai/pricing.

## Verdict in one line

orq.ai is a **closed-source SaaS** ("AI Gateway" bundled with prompt mgmt, evals,
observability, RBAC; self-host is Enterprise-only). It is a **non-candidate for
integration** into Charon's privileged loop — routing through it egresses prompts
**and code diffs** to a third party, and it is unauditable + non-revocable, failing
`SUPPLY-CHAIN.md` criteria 1/2/6 outright. Take the **patterns**, not the vendor.

## Adopt (native) / Adapt / Skip

| Capability | Verdict | Rationale |
|---|---|---|
| Ordered fallback after retries exhausted | **ADOPT (pattern)** | Charon has cross-vendor handoff-via-exclude (H6); the *intra-attempt* "retries exhausted → emit handoff" trigger is implicit. Make it explicit router policy. Stdlib, durable. |
| OpenAI-compatible single endpoint, N models | **ADOPT (as protocol)** | Exactly the contract Charon's deferred gateway *port* should expose. Adopt the interface; satisfy it with a native/open/self-host adapter behind the gate — never the SaaS. |
| Per-task cost/success signal feeding routing | **ADAPT** | Add *offline* cost/success attribution from the Ledger to tune the static JSON policy. Not a live SaaS classifier. |
| Cost/token tracking + budget caps (token + €) | **ADAPT → Ledger + fence** | Durable, high value — but it belongs as recorded Ledger span fields and fence-enforced budget caps, not a gateway feature. |
| Per-step tracing of agent/tool calls | **ADAPT → Ledger** | Extend the Ledger (git+JSON) with per-turn token/latency/cost spans; no OTel/SaaS ingest. Survives sunset. |
| Response caching | **SKIP (mostly)** | Coding turns are stateful/diff-producing; stale-diff risk in the privileged loop. |
| Load balancing across keys/regions, RBAC, PII guardrails, prompt mgmt, evals suite | **SKIP** | Wrong layer / multi-tenant SaaS concerns / frontier-absorbed. Charon's "eval" is executable acceptance; consensus is Tier 3 via existing tools. |
| Auto Router (live semantic per-prompt routing) | **SKIP for the loop / WATCH** | Needs a live classifier in the request path → egress + latency + closed-source. Violates the gate; frontier agents will absorb per-turn model choice. |
| Managed SaaS gateway as integration target | **SKIP (hard)** | Closed-source SaaS in the diff-applying loop = data egress + non-revocable + non-auditable. |

## Top 3 worth an ADR (gateway tier, 2.5+)

1. **"Retries-exhausted → fallback/handoff" as a first-class router contract**
   (plane: router + handoff/fence). Define the budget/retry-exhaustion predicate
   that converts a stuck attempt into a handoff event. Extends `StaticRouter`/
   `Budget`; zero new deps. This is the ferryman's core job — sunset-proof.
2. **Ledger-native cost & token accounting + fence-enforced budget caps**
   (plane: ledger + fence). Add `tokens_in/out`, `cost`, `latency_ms` to ledger
   spans; fence aborts/hands off on cumulative spend > `Budget` cap. Stdlib JSON.
   Enables cost-aware routing (feeds #1) and outlives Charon.
3. **The OpenAI-compatible gateway *port* contract (interface, not vendor)**
   (plane: gateway port). Lock the interface in an ADR; enumerate acceptable
   backends behind the supply-chain gate — native first, an open self-host client
   (e.g. LiteLLM) as the first sign-off candidate, **orq.ai SaaS excluded**.

## Risks to avoid (recorded for the gateway ADR)

Closed-source-in-loop (unauditable/non-revocable); **data egress of code/diffs**;
platform-gravity lock-in; sales-gated self-host; sunset mismatch (most of the
surface is frontier-absorbable). Net: **reference design, not a dependency.**
