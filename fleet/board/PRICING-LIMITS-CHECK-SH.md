tier: strong
difficulty: 2
work_class: money-path
branch: feat/pricing-limits-check-sh
repo: charon-private
parent: PRICING-LIMITS-CHECKER
depends_on:
owns: fleet/pricing-limits-check.sh, fleet/state/provider-pricing-limits.tsv
note: |
  Manually decomposed sub-ticket of PRICING-LIMITS-CHECKER (fleet/decompose.sh's plan_decomposition
  engine was unavailable 2026-07-15 — whole model pool 429/exhausted). Disjointness verified by
  hand: this ticket owns only the RIG-side drift checker + its canonical data file — no
  src/charon/ files. It does NOT need PROVIDER-PROBE-FIX as a dependency (that dependency belongs
  only to GATEWAY-NONTOKEN-METERING, the sibling, which shares gateway.py with PROVIDER-PROBE-FIX
  — see that ticket's real-dep). This ticket can proceed now.
accept: |
  A MECHANIZED checker (run on a schedule / at preflight) that:
  1. VERIFIES each provider's LIMITS (RPM/RPD/TPM/TPD/quota) and PRICING against source (provider API or a
     maintained source table with URLs), from ONE canonical data file (fleet/state/provider-pricing-limits.tsv)
     — not a prose doc.
  2. FLAGS a CHANGE that shifts the routing decision (e.g. a price move > X%, or a limit cut) as a tracked
     red + an operator alert ("NeuralWatt $5->$10/kWh — re-rank"). Ties into the router's degradation
     alert (R16) and drain/cost-rank.
  3. Supports NON-TOKEN pricing models — per-kWh (NeuralWatt), flat-rate/seat (Featherless), request-capped
     (Synthetic) — converting them into a comparable marginal-cost signal so the cost-sort is apples-to-apples
     (this ticket owns the comparison/normalization logic; the separate live-meter parse fix for NeuralWatt's
     returned per-request energy cost is GATEWAY-NONTOKEN-METERING, the sibling).
  4. FEEDS cost-rank (R5), the capability/pricing matrix (R3), and the free-tier order (R15).
  Fail-on-revert: inject a changed price/limit in the source table -> the checker flags it (red + alert);
  revert the change -> green.

  ## Also in scope (operator 2026-07-10)
  - CONFIRM EVERY API provider's pricing+limits (not just free tiers). Pricing is often AUTH-GATED
    (NeuralWatt portal 403) -> the checker needs authed access (provider API/dashboard token) OR an
    operator-supplied number; a public web fetch is not enough.
  - PLAN SELECTION: for providers with BOTH PAYG and monthly/subscription plans, evaluate which plan is
    best for our usage and record the chosen plan per provider (feeds cost-rank).
  - EVALUATE standardcompute.com (tiered-by-speed plans; never assessed).
scope: |
  Manually-decomposed single-domain sub-ticket of PRICING-LIMITS-CHECKER (fleet/decompose.sh).
  money-path; feeds R3/R5/R15/R16. PROJECT ROUTER. No product-routing behavior change on its own.
