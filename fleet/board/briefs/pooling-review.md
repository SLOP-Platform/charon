# BRIEF — ADVERSARIAL DESIGN REVIEW: one-big-pool + fund-portfolio + drain-then-park routing

ROLE: Independent adversarial reviewer/architect. READ-ONLY. Write exactly ONE findings file, no code, no commit.

## THE DECISION TO PRESSURE-TEST
Operator wants to collapse Charon's tiered model pools into essentially ONE big pool where routing
"smartly selects by what's available": pick the cheapest capable provider that currently has
balance/quota; when it taps out, advance to the next — instead of rigid per-model tier chains
(today those chains exhausted and a build DIED with nowhere to go).

Evaluate ADVERSARIALLY. REFUTE where weak. Then give a concrete design.

## GROUND TRUTH (read these)
- **The METER build just landed** — real per-(model,provider) cost metering: `/home/stack/code/wt-meter`
  (run `git -C /home/stack/code/wt-meter diff master..HEAD`). This UNBLOCKS balance-aware routing.
  Judge: does this metering output give enough to drive drain-then-park (per-provider spend/balance)?
- `/home/stack/charon-private/fleet/FREE-TIER-ROUTING.md` — provider limits/ToS/constraints (note the
  Featherless 32K-context cap; per-provider max_context + max_concurrency matter, not just price).
- `/home/stack/charon-private/fleet/archive/POOLS-REDESIGN-ADR.md` — the prior "~50 pools → ~4 tier-sets" design (ADR-v2).
- `/home/stack/charon-private/fleet/OBOL-PHASE-1-DESIGN.md` — portable engine context.

## OPERATOR'S PROVIDER PORTFOLIO (real, 2026-07-10)
- FLAT-RATE anchors (marginal ~$0 → concentrate routine volume): **opencode-Go** ($10/mo ~$60 cap), **NanoGPT** ($12/mo).
- FINITE PREPAID CREDIT (drain-then-park, drain cheapest-first before adding new $): DeepSeek ~$9.93, OpenRouter ~$9.90, Together ~$9.83.
- **NeuralWatt** — was flat, now ENERGY-metered ($5→$10/kWh rising) PAYG + $22 credit → declining value, lower priority.
- **CommandCode $15/mo Provider** (confirmed add): DeepSeek V4 Pro + 99%-off MiMo, ~15–25k req.
- Free rate-limited: Groq (select models). Cline Pass (usage left).

## REVIEW AXES (be concrete)
1. One-big-pool vs tier-sets (ADR-v2): which serves a SINGLE-USER gateway better? Does one-pool lose
   anything tiers gave (capability isolation, quality gating, premium-model gating)? Argue BOTH sides.
2. Availability-aware failover: what's the RIGHT signal to "advance to next"? (429/limit vs $0 balance
   vs latency vs quality). How does the METER feed this? What breaks if the signal is wrong?
3. Fund strategy: is "drain prepaid cheapest-first + concentrate on flat anchors + only add new $ where
   marginal beats idle credit" correct? Refute it. When (if ever) is concentrating funds into one cheap
   provider better than spreading?
4. Safety: the drain-then-park HARD guard (never park the SOLE remaining leg of a pool). Does one-big-pool
   make this easier or harder? Capability gating: a flat cheap leg can still be ineligible (context > cap,
   concurrency full) — how must the engine encode max_context + max_concurrency?
5. Over-abstraction risk: could "one capability engine" become a lowest-common-denominator that routes
   badly for everyone? Where's the line?

## DELIVERABLE — write ONE file: `/home/stack/charon-private/fleet/reviews/POOLING-DESIGN-REVIEW-flash.md`
- VERDICT (one line): one-big-pool YES/NO/QUALIFIED + confidence.
- ONE-POOL vs TIER-SETS: SxS with a recommendation.
- FAILOVER SIGNAL DESIGN: the concrete rule for "advance to next" + how METER feeds it.
- FUND STRATEGY VERDICT: refute-or-endorse the drain-cheapest-first + flat-anchor plan; concrete order.
- REQUIRED ENGINE INPUTS: the per-provider fields the router MUST have (price/class/balance/max_context/max_concurrency/quality).
- TOP 3 RISKS + TOP 3 RECOMMENDATIONS (ranked, one-line rationale each).
Cite specific files/lines as evidence. Tight, decision-grade, no fluff.

## LAST STEP (required)
Print the findings file path. Do NOT commit, push, or edit any other file.
