---
description: "Operator feature directive — provider funding classes; \"drain-then-park\" class drains finite prepaid credit first, auto-parks at zero, re-arms on top-up"
metadata: 
name: charon-drain-then-park-provider-class
node_type: memory
originSessionId: 02f0da30-0dc8-45ce-acbc-4cded96858db
type: project
tags: [charon, drain, provider, routing]
last_referenced: 2026-07-13
---
DIRECTIVE (2026-07-09): Charon routing should model providers by FUNDING CLASS, and add a first-class **drain-then-park** lifecycle for providers holding finite prepaid credit.

**Funding-class taxonomy (cheap-first ordering):**
1. **Free-tier (recurring quota)** — $0, rate/quota-limited, resets per period (groq/cerebras/etc.). Drain to limit, spill when throttled, auto-recover next period. Never permanently parks.
2. **Flat subscription ($0 marginal)** — opencode $10/mo, NanoGPT $12/mo. Already paid, ~$0 per call, OpenAI-shaped. Ideal always-drain-first legs; never zero out.
3. **Drain-then-park (finite prepaid credit)** — the operator's new class. OpenRouter (~$9.90), NeuralWatt ($22 PAYG credit), opencode-zen (prepaid). Finite balance, no auto-refill → **drain first, then auto-PARK (deactivate) when balance hits ~zero** so it stops erroring/failing over; **re-arm to ACTIVE when topped up** (toggle in console).
4. **True PAYG (metered)** — real per-token billing, last resort.

**Hard SAFETY guard (operator, 2026-07-09):** auto-park must NEVER park a provider that is the sole/only remaining leg of any pool — parking cannot leave a pool with no route. Before parking at $0, check pool membership; if it's the last leg, keep it (or alert) rather than orphan the pool. Applies to the whole drain-then-park lifecycle.

**Hard dependency:** drain-then-park needs a real per-provider BALANCE (starting credit − real spend), which REQUIRES the working METER. Currently blocked by the fabricated `est_cost` bug (forwarder.py:315/:400 stamps fake cost; spend.json's $223 is ~100% fiction). So: fix est_cost → real METER → balance tracking → auto drain-then-park.

**Concrete state today (2026-07-09):** NeuralWatt has **$22 PAYG credit** → DRAIN it (do NOT just disable, as an earlier plan said). **opencode-GO = flat $10/mo** ($0-marginal, class 2, the cheap leg — use upfront) + NanoGPT $12 flat = cheap-first. **opencode-ZEN = a monthly subscription the operator does NOT have active** → deactivate in routing, keep the provider entry for possible future re-activation (do NOT route to zen; it would fail). (An earlier routing pass wrongly wired zen as cheap-first — corrected 2026-07-09.) cline-pass → spill (broken non-stream envelope).

**Class-3 credit balances to drain (operator-supplied 2026-07-09, all finite prepaid; already-wired unless noted):** NeuralWatt $22.00 (blocked until proxy.py:247 normalize fix), OpenRouter $9.90 (1/10 fail = bug to fix, not drop), DeepSeek $9.99, Together.ai $9.83. New provider under consideration: **trae.ai** (research pricing/class/constraints). Record balances now; auto drain-then-park needs the METER.

**RESOLVED ordering (2026-07-09):** operator wants finite-credit (class 3) drained BEFORE flat-fee (class 2) — expiry is UNKNOWN (not stated on provider webpages), so drain-credit-first is the safe default (avoid losing credit to possible expiry; flat-fee is non-depleting so holding it costs nothing). Still worth an optional per-provider `expires` field later. **INTERIM CAVEAT:** credit legs are currently bug-blocked (neuralwatt 0/4 = proxy.py:247 normalize bug; openrouter 1/10), so credit-first routing would just fail-churn to flat-fee NOW. Therefore: apply **flat-fee-first as a safe interim**, then **flip to credit-drain-first once NORMALIZE-CASE-QUANT-FIX + the openrouter fix land**.

**Providers also carry non-cost CONSTRAINTS the router must gate on (capability dimension, not price):** e.g. **Featherless.ai** (confirmed by Featherless Discord mods 2026-07-09) = flat/unlimited calls BUT **32K context per session** and **concurrency = 1** (one in-flight call at a time). So a flat cheap-first leg can still be ineligible for a given request (context > cap) or moment (already 1 in-flight → queue/spill). The one capability engine must encode per-provider `max_context` + `max_concurrency`, not just funding class. Update `fleet/FREE-TIER-ROUTING.md` with the Featherless clarification.

**UPDATE 2026-07-10 (operator):**
- **True flat-rate anchors (concentrate routine volume; marginal ~$0): opencode-Go ($10/mo, ~$60 cap) + NanoGPT ($12/mo).** Operator loosely also named NeuralWatt "flat" but it is NOT anymore — see below.
- **NeuralWatt REPRICED:** now ENERGY-metered at **$5/kWh rising to ~$10/kWh** (doubling), OR a **$10 starter pack** for token-based plans. Unusual $/kWh (compute-energy) billing + a doubling rate = **declining cost-effectiveness** → reclassify from "flat" to energy-PAYG; still DRAIN the existing **$22 credit**, but LOWER its go-forward priority as rates climb.
- **CommandCode $15/mo Provider plan CONFIRMED (GO)** — class-4 metered API plan, un-parked ([[charon-commandcode-plan-gate]]); DeepSeek V4 Pro + 99%-off MiMo V2.5, ~15–25k req headroom.
- **Provider-review queue (still unreviewed):** Chutes, Trae (see line 24), haloon.ai, nousresearch.com.
- **Featherless flat-detail INCONSISTENCY to resolve by probe:** this note says concurrency=1 (Featherless Discord 2026-07-09); operator 2026-07-10 said "$25 = 4 tiny sessions OR 1 bigger." Agreed core (all sources): **32K context/session cap → unfit for heavy builds**. Exact concurrency (1 vs 4) needs a live probe.

**CANONICAL per-model source table (operator directive 2026-07-10 — stop re-analyzing):** `fleet/PROVIDER-BEST-PER-MODEL.md` (best/cheapest provider PER model → drives cost_rank), backed by live research `fleet/reviews/PROVIDER-REVIEW-2026-07-10.md`. Headlines: **GLM-5.2 → OpenRouter** (`glm-5.2-or`, cheapest + concurrency; already wired) — **Synthetic DROPPED** (1-concurrent-per-model). **Chutes = ADD** (Qwen/DeepSeek/GLM overflow, pending key). **CommandCode $15 = DeepSeek-Pro/MiMo lane only** (pending key). SKIP haloon/Nous/Trae/Devin/Ollama.

This IS the DRAIN-ROUTING / FREE-TIER-QUOTA-SPILL lane. See [[charon-free-tier-routing]], [[charon-pools-redesign]], [[use-free-tiers-to-their-limits]], [[always-fix-catalog-mismatches]]. Auto-park/re-arm should surface in the console (RFL-4 editable limits).
