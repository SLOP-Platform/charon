tier: strong
difficulty: 3
work_class: money-path
branch: feat/pricing-limits-checker
depends_on:
owns: fleet/pricing-limits-check.sh, fleet/state/provider-pricing-limits.tsv, src/charon/gateway.py
accept: |
  A MECHANIZED checker (run on a schedule / at preflight) that:
  1. VERIFIES each provider's LIMITS (RPM/RPD/TPM/TPD/quota) and PRICING against source (provider API or a
     maintained source table with URLs), from ONE canonical data file — not a prose doc.
  2. FLAGS a CHANGE that shifts the routing decision (e.g. a price move > X%, or a limit cut) as a tracked
     red + an operator alert ("NeuralWatt $5->$10/kWh — re-rank"). Ties into the router's degradation
     alert (R16) and drain/cost-rank.
  3. Supports NON-TOKEN pricing models — per-kWh (NeuralWatt), flat-rate/seat (Featherless), request-capped
     (Synthetic) — converting them into a comparable marginal-cost signal so the cost-sort is apples-to-apples.
  4. FEEDS cost-rank (R5), the capability/pricing matrix (R3), and the free-tier order (R15).
  Fail-on-revert: inject a changed price/limit in the source table -> the checker flags it (red + alert);
  revert the change -> green.
scope: |
  Operator 2026-07-10: provider limits AND pricing drift constantly (NeuralWatt just DOUBLED $5->$10/kWh),
  and those changes change the router's decision algorithm. Today limits live in a MANUAL doc
  (FREE-TIER-ROUTING.md) and pricing is HAND-SET per-model cost_input/cost_output (goes stale; the meter
  falls back to it when a provider returns no cost field). This is the pricing/limits analog of catalog-drift
  detection (CATALOG-SYNC-DRIFT). [[always-fix-catalog-mismatches]] [[charon-free-tier-routing]]
ds: money-path; feeds R3/R5/R15/R16. PROJECT ROUTER. No product-routing behavior change on its own.

## Also in scope (operator 2026-07-10)
- CONFIRM EVERY API provider's pricing+limits (not just free tiers). Pricing is often AUTH-GATED
  (NeuralWatt portal 403) -> the checker needs authed access (provider API/dashboard token) OR an
  operator-supplied number; a public web fetch is not enough.
- PLAN SELECTION: for providers with BOTH PAYG and monthly/subscription plans, evaluate which plan is
  best for our usage and record the chosen plan per provider (feeds cost-rank). NeuralWatt example:
  energy(per-kWh, ~95% cheaper on efficient MoE) vs per-token(predictable, dearer) vs subscription(+~35% off).
- NON-TOKEN metering: NeuralWatt bills by ENERGY (kWh consumed per request, returned in its Usage&Energy
  API) -> meter must PARSE that returned cost, not assume a fixed per-token price (today it records $0).
- EVALUATE standardcompute.com (tiered-by-speed plans; never assessed — 0 mentions in fleet). Needs the
  correct pricing URL / API to confirm.
