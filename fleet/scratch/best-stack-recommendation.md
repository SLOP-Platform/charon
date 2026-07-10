# Best Provider-Stack Recommendation — Refined & Verified Conclusion

Date: 2026-07-08. Refines the analysis in `coding-agent-subs-research.md` for the operator's
**actual measured load: ~18.9M input tokens over 19h, ~234:1 input-heavy** (heavy agentic /
long-context coding, not chat). Pricing/facts cross-checked against `coding-agent-subs-research.md`.
(`provider-pricing.md` referenced in the task does not exist in this scratch dir — cross-check was
against `coding-agent-subs-research.md` only.)

---

## Verification performed this pass

- **Featherless now lists `Kimi-K2.7-Code`** — CONFIRMED via `featherless.ai/models` (fetched
  2026-07-08). It appears as a featured model published by `moonshotai`, and the catalog's model-family
  filters carry Kimi 2 / Kimi 2.5 / Kimi Linear families. Total catalog ~45,362 models. This matches the
  operator's report that K2.7 Code was added ~2026-06-12. (Breadth is ~45K models, well above the
  "~30K" round-number used in earlier notes.)

---

## Refined conclusion

### 1. Cline Pass is discounted-but-METERED / quota-capped — NOT unlimited
Cline Pass ($9.99/mo flat, $4.99 first month) advertises only "generous quota" and **2–5× standard API
rate limits**; hard caps and concurrency limits are **undisclosed**. Under the operator's heavy agentic
load (18.9M input tokens / 19h) a 2–5× multiplier on standard rate limits **drains fast** — this is a
discounted-per-token meter, not a flat firehose. **It cannot be a sole or primary backend for this
load.** It is a cheap *quota to burn*, not a backbone.

### 2. Featherless is the unlimited BACKBONE — and now strictly dominates Cline Pass on MODELS
Featherless is **flat-rate and unlimited, throttled only by concurrency** (never by a token/quota wall),
so it **never walls on sustained heavy load** — exactly the property Cline Pass lacks. And with
`Kimi-K2.7-Code` now in its catalog (verified above), Featherless carries the **same fresh coding models
Cline Pass leans on (K2.7 Code, and the wider open-weight coding tier) plus ~45K-model breadth**.
Therefore Featherless **strictly dominates Cline Pass on model coverage**. Cline Pass's **only remaining
edge is price** (discounted per-token while its quota lasts), not models.

### 3. Recommended composition = LAYERED, not a switch
Do **not** pick one. Layer them by cost, spilling on drain:

> **Route to Cline Pass FIRST** (burn its cheap, discounted quota) **→ spill to Featherless**
> (unlimited backbone) **the moment Cline Pass throttles / drains / rate-limits.**

This is the standing **"use the cheap tiers to their limits, then spill to unlimited" routing policy**.
Frame it as **ROUTING POLICY that feeds the pools cost logic** — it is institutionalized here and in the
pools-redesign cost reasoning (`POOLS-REDESIGN-ADR-v2.md`), **not** a memory. The pools engine's
cost/health ranking should treat Cline Pass as a cheap-but-exhaustible leg that cascades to the
Featherless flat-rate leg on 429/quota signals.

### 4. Standing caveats (unchanged)
- **ToS:** both Cline Pass and Featherless are **personal / single-user only** — clean as the operator's
  own backend legs, prohibited as a resold or multi-user gateway front. (Cline ToS §2.2 forbids
  selling/transferring keys and sharing the subscription.)
- **Kilo Gateway** = zero-markup metered reseller → **no cost edge vs. hitting providers direct**;
  it is a **no-op** for this decision.
- **gpt-5.4 frontier is unaffected** — it stays **direct / cache-aware** (neither Cline Pass nor
  Featherless fronts a frontier Claude/GPT tier; the layered open-weight legs never replace the
  frontier failover fabric).

---

## One-line summary
Cline Pass = **cheap but exhaustible meter**; Featherless = **unlimited backbone that now also
out-models it**. Layer them: **Cline Pass first (cheap quota) → spill to Featherless (unlimited)** —
a routing policy, wired into the pools cost logic, not a memory. Frontier stays direct.

---
*Verification: `featherless.ai/models` fetched 2026-07-08 (K2.7 Code confirmed present). Pricing/model
facts per `coding-agent-subs-research.md` (2026-07-08). Load figures operator-provided
(~18.9M input tokens / 19h, ~234:1 input-heavy).*
