repo: charon
tier: strong
difficulty: 3
work_class: routing
parked: false
project: ROUTER
branch: feat/peak-pricing-aware
depends_on: PRICING-LIMITS-CHECK-SH
real-dep: PRICING-LIMITS-CHECK-SH — the peak/off-peak schedule data + its freshness check live in the pricing-limits checker; this ticket CONSUMES that data to resolve the effective current price. True build/correctness prereq though owns are disjoint.
owns: src/charon/routing_policy/pricing.py, tests/test_peak_pricing.py
note: |
  Operator 2026-07-21 (mace-windu): SG must be aware of providers/models/APIs with PEAK / time-varying
  pricing (off-peak discounts, surge windows). Price is the PRIMARY routing key, so a stale NOMINAL
  price causes mis-routing during peak windows — the router picks a "cheapest" leg that is not actually
  cheapest right now. Class: cost-signal accuracy / declared-vs-reality price drift.
accept: |
  - The pricing/cost signal the router consumes is TIME-AWARE: a provider/model entry can declare a
    pricing SCHEDULE (peak/off-peak windows + rates, or a surge multiplier), and the router resolves the
    EFFECTIVE price for the current time when ordering the chain.
  - Fail-on-revert: given a fixture provider with an off-peak rate active NOW and a peak rate at another
    time, the router orders it by the CURRENT effective price; freeze the clock to peak → the ordering
    changes. Revert the time-awareness → the test goes RED (router uses the stale nominal price).
  - Adopt-first: check whether the vendored pricing-data source (model_prices_and_context_window.json)
    or an industry pricing feed already models time-varying rates before hand-rolling a schedule format.
  - No provider without a schedule regresses (nominal price = a single all-day window).
ds: |
  depends_on PRICING-LIMITS-CHECK-SH (the pricing/limits data + drift checker is where the schedule
  data and its freshness live). Consumed by the cost-rank / router ordering (R5/R2). Reads-only the
  meter. BLAST RADIUS: routing ordering — a bad schedule mis-routes money-path traffic; adversarial
  review + fail-on-revert required. Folds into ROUTER (cost-sensor accuracy).
