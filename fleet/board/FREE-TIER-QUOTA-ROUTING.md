repo: charon
tier: strong
priority: 0
difficulty: 4
work_class: money-path
branch: feat/free-tier-quota-routing
depends_on:
owns: src/charon/routing_policy/free_tier.py, tests/test_free_tier_quota.py
substrate: N/A
substrate-novel: |
  Reuses the existing routing_policy package, the `free` flag already on all 859 catalog entries,
  and `cost_class_priority` which already separates free from paid. No external tool models OUR
  providers' per-tier quotas. What does NOT exist anywhere is the quota LEDGER — that is the
  novel slice.
serial_justified: |
  A quota ledger with no consumer routes nothing; a router keyed on quota with no ledger routes on
  nothing. One axis, one mechanism.
source: |
  Operator, 2026-08-01: "nvidia/mistral/google-aistudio have free tiers with some limits. We are
  supposed to use those based on LIMITS not cost since it's a free tier. We just need to stay
  within those limits."
note: |
  ## THE INSIGHT — FREE TIERS NEED A DIFFERENT AXIS
  Cost-first ordering is the right rule for PAID legs. It is meaningless for FREE ones: every
  free leg is $0, so `cost_rank` cannot discriminate between them, and a leg with quota remaining
  is indistinguishable from one that is exhausted. **The correct selector for a free tier is
  REMAINING QUOTA, not price.**

  Today the gateway has no concept of remaining quota. It discovers exhaustion only by BEING
  REFUSED — which is how a whole class of provider failures shows up as "model error" instead of
  "quota spent". That is the same conflation that let a 402 park all of OpenRouter and falsely
  quarantine five tickets on 2026-08-01.

  ## MEASURED SURFACE (2026-08-01, live gateway)
  Free-tier providers with substantial catalogs and NO quota tracking:
  ```
    nvidia           113 enabled models   free tier, limits unknown to the gateway
    mistral           62                  free tier, limits unknown
    google-aistudio   56                  free tier, limits unknown
    groq              18   (free-groq, gpt-oss-120b-groq, deepseek-v4-pro-groq all free=True)
    cerebras           2   (free-cerebras, gemma-4-31b-cb)
    zai                2   (glm-4.5-flash-zai, glm-4.7-flash-zai)
  ```
  **231+ free models the router cannot prefer**, because it has no way to know which have headroom.
  Note also: only 212 of 859 catalog entries carry `cost_rank` at all, so most of these cannot be
  ordered by price either — they are invisible to BOTH axes today.

  ## SCOPE
  1. **A quota ledger per (provider, window)** — requests and/or tokens used against the tier's
     limit, with the window the provider actually uses (per-minute / per-day / per-month differ by
     provider — do NOT assume one shape).
  2. **Selection rule**: among capable legs, prefer FREE legs with headroom, ordered by remaining
     quota (most headroom first); fall back to paid legs ordered by `cost_rank` when free legs are
     exhausted or absent. This composes with, and does not replace, cost-first for paid legs.
  3. **Stay WITHIN limits** — the operator's explicit requirement. Approaching a limit must
     de-prioritise the leg BEFORE it 429s, not after. Being refused is a failure, not a signal.
  4. **Distinguish quota-exhausted from broken.** A quota-exhausted leg is healthy and will
     recover at window rollover; it must NOT be parked as faulty or counted against a ticket.
     See PARK-REARM-FUNDED-PROVIDER and LOOP-GUARD-REASON-WIRE — same conflation, other places.
  5. Limits must be DATA (per-provider config), not hardcoded — providers change them
     [[charon-modular-agent-and-provider-agnostic]].

  ## DO NOT
  - Do not scrape provider dashboards. Prefer response headers (many return remaining/limit) and
    our own accounting; record which providers expose what and where the gaps are.
  - Do not guess a limit. An UNKNOWN limit must be treated as unknown and surfaced, never assumed
    generous — guessing high is how you blow a tier.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, offline, stubbed upstream:
    a. two free legs, one with headroom and one near its limit -> the one with headroom is chosen.
       Revert the selector -> RED.
    b. a free leg at its limit is skipped BEFORE the request is sent (no 429 incurred). Revert -> RED.
    c. all free legs exhausted -> falls back to the cheapest PAID leg by cost_rank (ANTI-OVER-BLOCK:
       free-first must never strand a request that a paid leg could serve).
    d. a quota-exhausted leg is classified distinctly from a faulty one, and is re-admitted at
       window rollover without manual intervention.
    e. a provider with an UNKNOWN limit is neither preferred as if unlimited nor silently dropped —
       it is surfaced.
  Then dogfood: report per-provider headroom for nvidia, mistral, google-aistudio, groq, cerebras.

  ## ADVERSARIAL REVIEW REQUIRED (money-path)
  Reviewer != builder. This decides which provider serves every request; a wrong free-first rule
  either blows a free tier or silently pushes traffic onto paid legs.

D&S — Deps & Sequence:
  - Pairs with FORWARDER-COST-ORDER-FALLBACK (cost axis for PAID legs) and
    SPEND-METRIC-TRUSTWORTHY (honest spend). This adds the FREE axis. Check owns collisions on
    the forwarder/routing_policy surface before starting.
