repo: charon
tier: strong
difficulty: 2
work_class: money-path
priority: 0
branch: fix/forwarder-cost-order-fallback
parked: true
parked_reason: |
  BLOCKED ON THE PRICE FEED — parked 2026-08-04 after adversarial review, with two independent
  executed proofs. It is not abandoned; it is unlandable until its prerequisite exists.
    1. NO-OP AGAINST THE LIVE GATEWAY. derived_cost_rank deliberately ignores the hand-typed
       cost_rank field (ADR-0016 step 6) and derives from cost_input/cost_output. Live
       /data/models.json on 4-LOM: 861 models, 10 carry cost_input, 214 carry the DEPRECATED
       cost_rank, and no deepseek-v4-flash leg is priced. Every paid leg therefore derives the
       neutral rank 1000, ties, and the stable sort returns the chain unchanged. A probe on the
       real live leg shape produced nv, or, ds, ng, cline — openrouter STILL ahead of deepseek,
       i.e. the 2026-08-01 incident order — and the identical probe against origin/master gave a
       byte-identical result. The branch's review-log asserted the opposite.
    2. ACTIVE REGRESSION. The empty-meter sort clobbers order_chain_by_funding_class
       (forwarder.py:438), silently overriding the operator's drain-then-park directive. Master's
       order_pool_by_live_cost returned the chain unchanged on an empty meter, so funding-class
       order survived to dispatch. 12 of 16 live providers are classified, so this is live: a PAYG
       leg cheaper per token would be tried before a prepaid class-3 credit policy says to drain
       first. Probe served payg on the branch and prepaid on master.
  UNPARK WHEN EITHER holds: (a) cost_input/cost_output are populated in the live catalog —
  models.dev/api.json is public, needs no key, carries 5,613 priced models and covers 17/17 of our
  providers; or (b) the fallback is made SUBORDINATE to funding class instead of overriding it.
  Until then this ticket must not hold a live owns: claim on src/charon/forwarder.py.
depends_on:
owns: src/charon/forwarder.py, tests/test_forwarder_cost_order.py
serial_justified: |
  One ordering decision in one function. The fallback and its proof are inseparable.
source: |
  Measured 2026-08-01 (session tott-doneeta) diagnosing why an OpenRouter key cap stalled the
  entire fleet while a funded, ~6x cheaper deepseek-direct leg sat untried.
note: |
  ## THE DEFECT — the money path ignores the cost data it already has
  `src/charon/forwarder.py:531-533` states it plainly:
  > "Reorder the provider chain at request time so the cheapest (by real cumulative metered
  >  spend) is tried first. **Empty meter -> the order is unchanged** (preserves the static
  >  configured order built at startup)."

  So chain order is driven by OBSERVED METERED SPEND, with a fallback to the static configured
  order. Measured on live 4-LOM:
    - `/data/spend.json` holds a GLOBAL aggregate only: `{"spent_usd": 7.99, "month_start":
      "2026-08", "monthly_limit_usd": 0.0}`. **No per-provider breakdown exists.**
    - So the meter is effectively always empty for ordering purposes -> the reorder NEVER fires
      -> the static hand-authored order governs every request.
    - That static order for `deepseek-v4-flash` is:
      `nv(free) -> go(rank 5, DISABLED) -> ng(rank 800) -> hf(rank 30, parked) -> or(rank 50)
       -> ds(rank 8) -> cline(rank 900)`.
      OpenRouter (50) is reached BEFORE deepseek-direct (8), and nanogpt (800) before both.

  **Result (2026-08-01): the OpenRouter key hit its cap, every leg 403'd, and the whole fleet
  stalled — while a funded leg ~6x cheaper sat one position further down, never tried.**

  ## WHY THE DATA IS NOT THE PROBLEM
  `cost_rank` EXISTS on the legs (212 of 859 catalog entries carry it; all the relevant deepseek
  legs do). `src/charon/pools.py:136` already sorts correctly —
  `entries.sort(key=lambda e: (not e.free, e.cost_class_priority, e.cost_rank))`. **The gateway
  forwarder simply does not use that path.** Two orderings exist; the money path uses the one
  that needs a meter that was never populated per-provider.

  ## SCOPE
  When per-provider metered spend is absent or empty, fall back to **cost_rank ASC (free-first)**
  — NOT to the static configured order. Precedence:
    1. free legs first
    2. real per-provider metered spend, when present
    3. `cost_rank` ASC
    4. static configured order (last-resort tiebreak only)
  Skip `enabled: false` and parked legs (`/data/balance_park.json` currently parks huggingface).
  Legs with NO `cost_rank` are UNKNOWN cost and must never sort ahead of a known-cheap leg.

  **Do NOT** rewrite the stored `pools.json` order, and do NOT re-implement pools.py's sort —
  reuse `routing_policy.derived_cost_rank`, which forwarder.py already imports siblings of.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, offline, no live gateway. Each RED on the named revert, then GREEN:
    a. **Reproduce the real incident**: chain in the stored order above, empty per-provider meter
       -> deepseek-direct (rank 8) is tried BEFORE openrouter (rank 50). Revert the fallback -> RED.
    b. free legs still precede all paid legs.
    c. when per-provider metered spend IS present, it wins over cost_rank (do not regress the
       existing behaviour).
    d. a leg with no cost_rank never sorts ahead of a priced cheaper leg.
    e. disabled/parked legs are skipped entirely.
    f. ANTI-OVER-BLOCK: a chain already in correct cost order is returned unchanged.
  Report the resulting order for the real `deepseek-v4-flash` leg set, before and after.

  ## ADVERSARIAL REVIEW REQUIRED (money-path)
  This decides real spend on every request. Reviewer != builder. The reviewer must confirm the
  fallback cannot route to a costlier leg than the previous behaviour in ANY case, and that
  unknown-cost legs cannot be treated as cheap.

D&S — Deps & Sequence:
  - Independent of CATALOG-COMPLETENESS (that completes catalog DATA; this fixes the ORDERING
    that ignores it). Both are money-path; this one is the live defect.
  - Product gate is currently RED (AMBIENT-COUPLED-TESTS) — that must land before this can merge.
