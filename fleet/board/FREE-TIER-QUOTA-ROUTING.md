repo: charon
tier: strong
priority: 0
difficulty: 4
work_class: money-path
branch: feat/free-tier-quota-routing
depends_on: FT-LIMITS-GROQ-RECONCILE
real-dep: FT-LIMITS-GROQ-RECONCILE owns fleet/state/FREE-TIER-LIMITS.tsv and resolves the _MISMATCH_UNRECONCILED groq row — it is built (PR #116, 16/16 fail-on-revert tests) and needs only a rebase; land it first so this ticket consumes a reconciled SSOT
owns: src/charon/routing_policy/free_tier.py, tests/test_free_tier_quota.py, fleet/state/FREE-TIER-LIMITS.tsv
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

  ## ⚠ THE LIMITS ALREADY EXIST AND ARE ALREADY RESEARCHED — DO NOT RE-DERIVE THEM
  `fleet/state/FREE-TIER-LIMITS.tsv` (dated 2026-07-22) is the SSOT and is ACCURATE. Verified
  2026-08-01 against operator-supplied figures — they match, and the file carries MORE than the
  operator's summary: per-model `rpd/rpm/tpm/tpd`, `context_cap`, `trains_on_data`,
  `personal_only`, and a per-provider `exhaustion_signal`.
  ```
    groq  llama-3.1-8b-instant      rpd=14400
    groq  llama-3.3-70b-versatile   rpd=1000   tpd=100000
    cerebras                        tpd=1000000            (~1M tokens/day)
    mistral free-mistral-code       1000000000_per_month   (~1B tokens/month — LARGEST budget)
    openrouter any :free suffix     rpd=1000 (with $10 lifetime credit; else 50)
    google-gemini flash-lite        rpd=1000 | flash rpd=250 | pro rpd=100
    zai / nanogpt                   exhaustion_signal recorded, limits unpublished
  ```
  **THE DEFECT IS THAT NOTHING READS IT.** Measured 2026-08-01:
    - rig consumers of `FREE-TIER-LIMITS.tsv`: **0**
    - the gateway's `/data` contains **NO limits/quota file at all**
  So the gateway cannot stay within quotas it has never been told about. The research was done ten
  days ago and was never wired — [[dynamic-tools-never-on-demand]].
  **This ticket's job is the WIRE, not the research.** Re-deriving these numbers is out of scope
  and is a failure of the reuse-check. If a figure looks wrong, RECONCILE against a provider
  header and update the TSV — do not start a fresh survey.

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

  ## LIMITS MUST BE DISCOVERED, NOT HAND-MAINTAINED (operator, 2026-08-01)
  "These free tiers can change — how much you get, which models, etc. We need an API method to get
  updates for these."
  A hand-maintained TSV rots. `FREE-TIER-LIMITS.tsv` is dated 2026-07-22 and already carries
  `_MISMATCH_UNRECONCILED` and `unpublished` markers. Treat it as SEED + FALLBACK, never as truth.

  **OBSERVED BEATS DECLARED.** Discover live limits on a cadence and reconcile:
  1. **Response headers** — the primary source, free on every request we already make. Most
     OpenAI-compatible providers return some of: `x-ratelimit-limit-requests`,
     `x-ratelimit-remaining-requests`, `x-ratelimit-limit-tokens`,
     `x-ratelimit-remaining-tokens`, `x-ratelimit-reset-*`, `retry-after`. **Record which
     providers actually emit which headers** — that inventory is itself a deliverable, because it
     tells us where we are flying blind.
  2. **Provider key/usage endpoints** where they exist (e.g. OpenRouter exposes key usage +
     remaining credit). Poll on a TTL like the catalog refresher does.
  3. **Our own accounting** as the floor: count requests/tokens per (provider, window) ourselves.
     This works even for providers that publish nothing, and is the ONLY way to cover the
     `unpublished` rows.
  Precedence: live header/endpoint > our own accounting > the TSV seed. A disagreement between
  the TSV and an observed value is a SIGNAL — update the TSV and surface the drift, do not
  silently prefer either.

  **Composes with CATALOG-REFRESH-PERSIST** — that ticket polls every provider's `/models` on a
  6h TTL and (once fixed) persists it. The same cadence should carry limit discovery; do NOT
  build a second poller [[no-rig-as-product-adopt-dont-handroll]]. Model AVAILABILITY and model
  QUOTA are two fields of one refresh.

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
