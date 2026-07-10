# ADVERSARIAL DESIGN REVIEW — one-big-pool + fund-portfolio + drain-then-park

**Reviewer:** flash (adversarial, read-only)
**Date:** 2026-07-10
**Inputs:** POOLS-REDESIGN-ADR-v2.md, POOLS-REDESIGN-REVIEW.md, FREE-TIER-ROUTING.md,
  OBOL-PHASE-1-DESIGN.md, REVIEW-17-balance-drain.md, METER diff (wt-meter master..HEAD)

---

## VERDICT

**QUALIFIED YES — one-big-pool WITH capability pre-filtering is the right design for a single-user
gateway, but it is DANGEROUS without the capability catalog (max_context, max_concurrency, tools)
that the METER alone does not provide. Confidence: 70%.** The ADR-v2 tier-sets (Phase 1) are a
viable fallback if capability cataloging proves too heavy.

---

## 1. ONE-BIG-POOL vs TIER-SETS (ADR-v2)

### Side-by-side comparison

| Axis | One-big-pool | Tier-sets (ADR-v2 Phase 1) |
|------|-------------|---------------------------|
| Routing machinery | One ranking function + capability pre-filter | Tier lookup → cascade → rank |
| Capability isolation | Dynamic per-request (filter by task context) | Static per-tier (model tier pre-assigned) |
| Capability grades (Phase 2) | Not needed — pre-filter subsumes it | Optional, gated, may never ship |
| Work-class classifier | Not needed | Phase 2, unproven (review #4) |
| Complexity | Low: 1 pool, 1 ranker | Medium: ~4 pools, cascade logic, live-health ledger |
| Single-user fit | BETTER — one user doesn't need persona-tier separation | OVERBUILT — designed for multi-user product (per ADR-0014 "tier vid") |
| Sole-provider stranding risk | HIGHER — no tier cascade fallthrough | LOWER — tier cascade provides graceful degradation |
| Capability catalog required | YES (pre-filter) | YES (tier seed + context cap check) |

### Recommendation

**ONE-BIG-POOL WINS for single-user, but only WITH capability pre-filtering.** The ADR-v2 reviewer
already found that Option A+ (template + real cost + health ledger) was the right first step
(POOLS-REDESIGN-REVIEW.md L5–6: "the cheaper subset it explicitly rejects delivers ~90% of the
realizable value on data that actually exists today"). One-big-pool IS Option A+ with the tier
labels collapsed — same structural win, less machinery.

The tier-sets design was optimized for a multi-user product (per ADR-0014's "tier vid" — the engine
consumes gateway failover for *tier* selection, meaning different users get different tier pools).
The operator has confirmed this is a PERSONAL gateway. The cascade-through-tiers logic and work-class
classifier (Arch-Router, Phase 2) are over-engineering for a single user who can see the output and
retry manually.

**What one-big-pool loses compared to tier-sets:**
- Predictable degradation via tier cascade (Frontier→Strong→Capable→Basic). Mitigation: capability
  pre-filtering + cost ranking already produces a natural degradation path — cheapest capable first,
  then next cheapest, etc. The order IS the cascade.
- Quality anchoring: a primary model choice anchors quality expectations. Mitigation: the primary
  model is always tried first (ADR-0004 D5). Failover to a cheaper model is the user's implicit
  choice (they'd rather have a response from Groq 8B than a hard failure).

**What one-big-pool gains over tier-sets:**
- Eliminates the tier-seeding problem entirely (ADR-v2's tier was undefined for ~197/201 routes —
  see POOLS-REDESIGN-REVIEW.md L21–25). One pool has no tier to seed.
- Eliminates the cascade-through-tiers complexity (ADR-v2 L84–98) — a single pass through candidates
  replaces the multi-tier loop.
- Adapts per request: a 2K-context coding task and a 100K-context refactor naturally select different
  providers from the same pool because the pre-filter changes per request.

---

## 2. FAILOVER SIGNAL DESIGN

### The concrete "advance to next" rule

```
INPUT:  model, context_size, tools_needed, latency_tolerance

┌─ PRE-FILTER (capability gate — required, not optional) ───────────┐
│ candidates = pool[model]  # all providers serving this model       │
│ candidates = filter(candidates, context_size ≤ max_context)        │
│ candidates = filter(candidates, tools_needed → has_tools)          │
│ candidates = filter(candidates, not on_cooldown)                   │
│ candidates = filter(candidates, has_concurrency_slot)              │
└───────────────────────────────────────────────────────────────────┘

┌─ DRAIN-THEN-PARK RANK ────────────────────────────────────────────┐
│ tier0 = [p for p in candidates if p.mode == "flat"               │
│           and not is_drained(p)]   # marginal ≈ $0               │
│ tier1 = [p for p in candidates if should_drain(p)]                │
│ tier2 = [p for p in candidates if remaining(p, fallback=True)>0]  │
│ tier3 = [p for p in candidates if remaining(p) is None]           │
│        # poll providers with unknown balance                      │
│ tier4 = [p for p in candidates if is_drained(p, floor=0.50)]      │
│        # SOLE-LEG RESERVE: kept with cost_rank = MAX             │
│                                                                    │
│ rank(within each tier): cost_rank asc, then live_health desc      │
│ ordered_candidates = tier0 + tier1 + tier2 + tier3 + tier4        │
└───────────────────────────────────────────────────────────────────┘

for candidate in ordered_candidates:
    response = try_request(candidate)
    if fallback_candidate ← classify_failure(response):
        match fallback_reason:
            case 402:        mark_drained(candidate)        # HARD advance
            case 403:        mark_drained(candidate); alert  # HARD advance
            case 429:        mark_cooldown(candidate, 60s)   # SOFT advance
            case 5xx:        mark_cooldown(candidate, 30s)   # SOFT advance
            case quality_low: demote(candidate)              # SOFT advance
        continue
    else:
        # Served — fold cost into METER
        record_spend(candidate.provider, cost_usd, model=model)
        record_health(candidate, latency, status_code)
        return response

# ALL EXHAUSTED
terminal_failure  # per ADR-0004 R2
```

### How the METER feeds this

- **Pre-drain ranking** (`should_drain`, `is_drained`): reads from BalanceTracker, which consumes
  `record_spend(provider, usd, model=model)` — the METER's new kwarg (balance.py:216-236). The
  BalanceTracker decrements fixed balances per-provider, not per-model. Model-level spend is
  available via `model_spend(model, provider)` but is NOT used for the drain/park decision in
  this design — only provider-level remaining balance is.

- **Cost ranking** (`cost_rank`): already in models.json as `cost_input`/`cost_output` (where
  populated). The METER adds per-(model,provider) cumulative cost via `model_provider_cost()`
  (proxy.py:512–515) which COULD feed an effective burn-rate forecast but is NOT needed for
  the simple "cheapest available" rank.

- **Cooldown + health ledger**: NOT fed by the METER. Requires a separate live-health ledger
  (ADR-v2 Phase 1.5 scope). The METER's `_model_provider_cost` dict tracks spend only, not
  error rates or latency.

- **Post-402 learning**: after a 402, `record_spend` with the 402's cost ($0) advances the
  meter but does NOT update fixed balance (that only happens on actual cost_usd > 0). The
  ️⃣‑driven `mark_drained()` is the trigger — the METER is passive here.

### What breaks if the signal is wrong

| Failure | Effect | Blast radius |
|---------|--------|-------------|
| False `is_drained` (balance persists but tracker says $0) | Skips cheapest provider → routes to more expensive | Cost overrun, tolerable but compound |
| False `should_drain` (no balance but should_drain=True) | Routes to drained provider → 402 → wastes round-trip | Latency added, tolerable |
| Missing max_context pre-filter | Routes 65K task to Featherless (32K cap per FREE-TIER-ROUTING.md L78) | Silent truncation or error |
| Missing tools pre-filter | Routes agent task to non-tool model | Silent failure |
| Missing cooldown on 429 | Harass provider → potentially banned or rate-limit locked | Service degradation |
| Balance persistence gap (REVIEW-17 finding #1) | On restart, drained providers appear full → false drain-first routing | Wasted attempts until 402s arrive |

---

## 3. FUND STRATEGY VERDICT

### Endorsed with three corrections

**CORRECT:** Drain prepaid cheapest-first (DeepSeek ~$9.93 before Together ~$9.83 before
OpenRouter ~$9.90). Marginal cost per 1M tokens is the right comparator, enabled by real
per-token pricing (once located — POOLS-REDESIGN-ADR-v2 L79–80 makes this an explicit
prerequisite). Flat anchors as primary volume (opencode-Go $10/mo, NanoGPT $12/mo) is
correct — marginal $0 should absorb routine load.

**CORRECTION 1 — CommandCode $15/mo is a flat anchor, not prepaid.** The Provider plan
gives $15 credit, then PAYG at cost with no markup. The credit drains fast, but the
ongoing cost-plus path means adding $ AFTER credit is gone still beats adding $ to any
provider that marks up. Treatment: drain the $15 credit (treat as prepaid), then treat
the PAYG path as a flat anchor (cost floor for comparison). See FREE-TIER-ROUTING.md L113.

**CORRECTION 2 — "Only add new $ where marginal beats idle credit" has a SOLE-LEG caveat.**
If a drained provider is the ONLY one capable of serving a model (e.g., only DeepSeek direct
has 1M context for a massive file), draining it to $0 strands that model. The rule must be:
*never drain the sole capable leg below a reserve floor ($0.50–$1.00), even if marginal cost
would route elsewhere, because the alternative is not-to-higher-cost — it's NOT-AVAILABLE.*

**CORRECTION 3 — NeuralWatt should drain LAST, not earlier.** Energy-metered PAYG with rising
rate ($5→$10/kWh per FREE-TIER-ROUTING.md row 33) + only $22 credit makes it declining value.
Every additional request on NeuralWatt costs MORE than the previous one (rising kWh rate on
energy-metered). Deprioritize behind all flat-rate and fixed-price prepaid, ahead of only idle
or unconfigured providers.

### Concrete drain order

| Priority | Provider | Type | Effective cost | Rationale |
|----------|----------|------|---------------|-----------|
| 0 | opencode-Go ($10/mo) | Flat anchor | ~$0 marginal | Absorb routine (FREE-TIER-ROUTING.md L108) |
| 0 | NanoGPT ($12/mo) | Flat anchor | ~$0 marginal | Absorb routine |
| 0 | CommandCode ($15/mo, after credit) | Flat anchor | ~$0 marginal (cost-plus no-markup) | Cost floor comparison |
| 1 | Groq free | Free rate-limited | $0 | Zero cost, use while quota lasts (FREE-TIER-ROUTING.md L55) |
| 1 | CommandCode MiMo 99%-off | Near-free | ~$0.01/req | Near-free, rate-limited |
| 2 | DeepSeek prepaid (~$9.93) | Finite prepaid | $0.14/$0.28 Flash, $0.435/$0.87 Pro per 1M | Cheapest prepaid per-1M (FREE-TIER-ROUTING.md L102) |
| 3 | Together (~$9.83) | Finite prepaid | Unknown per-1M | Drain next |
| 4 | OpenRouter (~$9.90) | Finite prepaid | Has $10 lifetime unlock | Drain credits, free models already unlocked |
| 5 | NeuralWatt (~$22 credit) | Declining value | Rising $5→$10/kWh | Drain last, declining value per request |
| 6 | Cline Pass | Exhaustible quota | Unknown | Last resort |

### When concentrating beats spreading

Concentrating all volume into the cheapest provider is correct WHEN that provider can serve ALL
required models with adequate context/concurrency. For a single model hosted by multiple providers
(e.g., DeepSeek V4 Flash on DeepSeek direct + opencode Zen + OpenRouter), concentrate on the
cheapest (DeepSeek direct) until drained, then spill to next cheapest.

**Counterexample where spreading is forced:** if model A has a 1M context requirement, only
DeepSeek direct has 1M context. All other providers (opencode Zen, OpenRouter) max at 128K.
You CANNOT concentrate because capability forces spread.

---

## 4. SAFETY — DRAIN-THEN-PARK HARD GUARD IN ONE-BIG-POOL

### One-pool makes the guard EASIER (one guard, not N tiers)

In tier-sets, you'd need to check before parking: "is this the last capable leg of Frontier
tier? Of Strong tier? Of Capable? Of Basic?" That is 4 separate guards. In one-big-pool,
there is one guard:

```
def may_drain(provider, pool):
    """Return True if draining this provider is safe (no model left stranded)."""
    affected_models = {route.model for route in pool if route.provider == provider}
    for model in affected_models:
        alternatives = [p for p in pool if p != provider
                        and p.capable_of(model, context_size=model.max_needed_context)]
        if not alternatives:
            return False  # This provider is the ONLY way to serve this model
    return True
```

### But capability gating is harder in one-big-pool

The guard above requires knowing:
1. Which models a provider serves
2. Whether another provider can SUBSTITUTE for the same model at equivalent quality

The operator's quality-equivalence requirement (ADR-v2 L228–231: "~2–4 quality-equivalent
models per tier, each on an independent provider/quota, drain-ordered") is the data this
guard needs. Without it, the guard can only check SAME-MODEL alternatives, not
EQUIVALENT-MODEL substitution. This is a real gap: if DeepSeek V4 Flash on opencode-Go
($10/mo flat) is the only provider, AND you also have DeepSeek V4 Pro on DeepSeek direct
(prepaid, ~$9.93), those are DIFFERENT models. Without an equivalence cluster declaration,
the guard won't know that V4 Pro can substitute for Flash.

### Required engine inputs (minimum set)

| Field | Type | Source | Purpose |
|-------|------|--------|---------|
| `max_context` | int (tokens) | Provider metadata | Pre-filter: skip if context > cap |
| `max_concurrency` | int | Provider metadata | Pre-filter: skip if saturated |
| `supports_tools` | bool | Provider metadata | Pre-filter: agent tasks need tools |
| `supports_streaming` | bool | Provider metadata | Pre-filter: streaming required |
| `mode` | "fixed"\|"poll"\|"flat"\|"passthrough" | Config | Determines balance tracking mode |
| `starting_usd` | float | Config | For `remaining()` calculation |
| `cost_input` / `cost_output` | float (per 1M) | Config/pricing import | Real cost_rank |
| `free` | bool | Config | Free tier → route-first |
| `quality_equivalence_class` | string | Operator/benchmark | Cross-model substitution cluster |
| `model_capabilities` | list\[string\] | Config | e.g. ["coding", "chat", "reasoning"] |

**The METER provides only `cost_usd` and accumulates it into `model_provider_cost` and
`model_spend`. It provides NONE of the capability fields above.** These must come from a
SEPARATE capability catalog (models.json / providers.json). The router architect MUST NOT
assume the METER can feed capability signals — it is a cost meter, not a capability catalog.

### One-big-pool's sole-provider stranding risk vs tier-sets

| Scenario | One-big-pool | Tier-sets |
|----------|-------------|-----------|
| Park the only 1M-context provider | ALL large-context requests fail | All tiers using that provider fail, but Capable/Basic might survive with smaller models |
| Park the only tool-calling provider | ALL agent tasks fail | Agent tier (Frontier/Strong) fails, but background tasks (Basic) survive |
| Graceful degradation | HARDER — no natural cascade fallthrough | EASIER — tier cascade provides predictable degradation |

---

## 5. OVER-ABSTRACTION RISK

### When "one capability engine" becomes lowest-common-denominator

**RISK REALIZED if:** the ranking function is GLOBAL and CONTEXT-FREE (same ordering for every
request). Evidence this is the operator's default thinking: "pick the cheapest capable provider
that currently has balance" — this is a GLOBAL cheapest-first sort with no task-type
parameterization.

**Specific failure modes:**

1. **Task-blind routing.** A coding-specialist model (Codestral) and a chat model (Gemini Flash)
   both serve the same request. Cheapest wins. The operator's coding task goes to a weaker model.
   **Mitigation:** the primary model is tried first (ADR-0004 D5) — failover only happens on
   exhaustion, so the primary anchors quality. But for models the operator runs under a role
   rather than a specific model id, the failover IS the primary.

2. **Context-size blind routing.** 100K token refactor and 500-token summarization use the same
   pool ranking. The cheapest provider that can handle 100K is selected for BOTH — the
   summarization overpays for context capacity.
   **Mitigation:** pre-filter candidates by the REQUEST's context size, not the model's maximum.
   A 500-token request should consider Featherless (cheap flat) even though it caps at 32K,
   because 500 < 32K. A 100K request should exclude Featherless.

3. **Latency-blind routing.** Background classification (batch, 5s timeout OK) and interactive
   coding (sub-500ms first token needed) use the same ranking. The fastest provider (Cerebras)
   loses to the cheapest (Groq 8B) on pure cost rank, so interactive coding is slow.
   **Mitigation:** add `latency_tolerance` as a ranking parameter. Interactive tasks weight
   `p50_latency` higher; batch tasks weight `cost_rank` higher.

4. **Privacy/ToS-blind routing.** Gemini free ($0, 1K RPD) ranks above DeepSeek prepaid
   ($0.14/$0.28 per 1M). Sensitive code flows through Gemini, which trains on free-tier data
   (FREE-TIER-ROUTING.md L51: "free tier uses your prompts+outputs to improve products").
   **Mitigation:** add a `data_sensitivity` flag per request. Sensitive requests exclude
   providers tagged `trains_on_data`.

### Where's the line?

**The line** is: does the ranking function take request context as a parameter, or is it a
single global sort?

- Global sort → lowest-common-denominator for everyone: FAIL
- Parameterized sort with pre-filter → works for everyone: PASS

The minimum viable parameterization:
- `context_size` (for max_context filter)
- `tools_needed` (for tools filter)
- `task_role` (for quality-appropriate selection — purely optional, the primary model already
  anchors quality)

---

## TOP 3 RISKS

| # | Risk | Impact | Source | Mitigation |
|---|------|--------|--------|------------|
| 1 | **Capability-blind routing** — one-big-pool without max_context/max_concurrency/tools pre-filter routes to incapable providers | Silent truncation (Featherless 32K cap), tool-less failures, concurrency deadlock | FREE-TIER-ROUTING.md L78; FREE-TIER-ROUTING.md L24 | Add capability catalog OR reject one-big-pool in favor of ADR-v2 tier-sets (which also need capability data, but isolate blast radius per tier) |
| 2 | **Balance persistence gap** — BalanceTracker fixed balances are in-memory only; on restart, drained providers reset to full starting_usd | False drain-first routing after restart → wasted round-trips until 402s arrive | REVIEW-17-balance-drain.md L46 | Persist `_fixed_balances` and `_model_provider_cost` to `/data` volume before any proxy wiring |
| 3 | **Sole-provider stranding without equivalence clusters** — draining last provider for a model with no quality-equivalent substitute creates dead-end for all tasks needing that model | One drained provider can strand an entire model family | ADR-v2 L228–231 (operator quality-equivalence requirement, data doesn't exist yet) | Implement same-model HARD guard first; seed equivalence clusters manually by operator judgment; refine with benchmark data when available |

---

## TOP 3 RECOMMENDATIONS

| # | Recommendation | Why | Priority |
|---|---------------|-----|----------|
| 1 | **Add capability catalog to provider metadata** — every provider entry must carry `max_context`, `max_concurrency`, `supports_tools`, `supports_streaming` before one-big-pool goes live. The METER provides cost, not capability. | Without this, capability-blind routing is the #1 risk — silent failures that the operator won't detect until they hit a Featherless 32K wall mid-session. | **PREREQUISITE.** Block one-big-pool otherwise. |
| 2 | **Persist BalanceTracker + METER model_provider_cost to disk** — the in-memory-only balance from REVIEW-17 finding #1 means drained state is lost on restart. Write to `/data/balance.json` or the existing JSONL ledger on every `record_spend` call. | Without persistence, drain-then-park is a session-level feature only — every restart resets to "everything is full," routing through drained prepaid providers first. | **BEFORE PROXY WIRING.** |
| 3 | **Implement the HARD sole-provider guard before drain-then-park** — `may_drain(provider)` must enumerate all models served and verify ≥1 alternative provider exists (same model or operator-declared equivalence cluster) before allowing `is_drained=True`. Never park the last capable leg. | Prevents the most catastrophic failure mode of drain-then-park: total model unavailability because the last provider was drained. | **SHIP WITH DRAIN-THEN-PARK.** |

---

## REFERENCES

- METER diff: `model_provider_cost()` at proxy.py:512–515, `record_spend(provider, usd, model=model)` at balance.py:216–236
- METER does NOT provide: max_context, max_concurrency, tools, streaming, latency, quality — only cumulative cost_usd
- REVIEW-17 finding #1 (balance persistence gap): REVIEW-17-balance-drain.md L46
- Featherless 32K cap: FREE-TIER-ROUTING.md L78
- Groq 8B 6K TPM bottleneck: FREE-TIER-ROUTING.md L24
- Operator quality-equivalence requirement: ADR-v2 L228–231
- ADR-v2 Phase 1 routing algorithm (no capability): ADR-v2 L93–98
- Previous review REWORK verdict (Option A+): POOLS-REDESIGN-REVIEW.md L5–6
- CommandCode $15/mo Provider plan: FREE-TIER-ROUTING.md L113
- Gemini free-tier trains on data: FREE-TIER-ROUTING.md L51
- OpenRouter $10 lifetime unlock: FREE-TIER-ROUTING.md L71
