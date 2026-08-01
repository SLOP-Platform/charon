repo: charon
tier: strong
difficulty: 3
work_class: money-path
priority: 0
branch: feat/catalog-completeness
depends_on:
owns: src/charon/providers/discover.py, tests/test_catalog_completeness.py
substrate: litellm — adopt — `model_prices_and_context_window.json` ships with litellm, a library we ALREADY depend on, and carries price + context for thousands of models. Use it as a price SOURCE before scraping or hand-maintaining anything. Cross-check against provider APIs; disagreement between sources is itself signal. See the PRICING-FEED scope note in the satele-shan handoff.
serial_justified: |
  One catalog, one write path. Splitting fields from persistence ships a schema nothing writes.
source: |
  Operator-approved (unstaged since 2026-07-31), promoted to P0 2026-08-01 after measuring that
  provider cost-ranking has no data to rank on.
note: |
  ## ⚠ PREMISE CORRECTED 2026-08-01 — READ THIS BEFORE THE SCOPE BELOW
  This ticket first claimed "**0 of 859** entries carry ANY price field". **That was WRONG** — the
  measurement grepped for `price`/`pricing`/`cost` as EXACT keys; the actual key is `cost_rank`.

  ## RE-MEASURED 2026-08-01 (live 4-LOM gateway)
  - `/data/models.json` — **212 of 859** carry `cost_rank`; **859 of 859** carry a `free` flag;
    4 carry `cost_class`; **88** are `enabled: false`.
  - **216 of 859** carry a context field.
  - `/data/cost_map.json` — ABSENT (never written); `discover.py:66 build_cost_map` is called only
    from `cli.py:423` and tests, so it is recomputed on demand and never persisted.

  ## THE REAL DEFECT — ORDERING IGNORES THE COST DATA IT ALREADY HAS
  Stored pool order for `deepseek-v4-flash` (positions as stored, top-down):
  ```
    1 -nv     nvidia        rank=-    free=True   enabled
    2 -go     opencode-go   rank=5    free=False  DISABLED
    3 -ng     nanogpt       rank=800  free=False  enabled
    4 -hf     huggingface   rank=30   free=False  enabled (parked)
    5 -or     openrouter    rank=50   free=False  enabled
    6 -ds     deepseek DIRECT rank=8  free=False  enabled
    7 -cline  cline         rank=900  free=False  enabled
  ```
  **The list is not sorted by cost_rank.** rank=800 sits at position 3; rank=50 (openrouter) sits
  at position 5, AHEAD of rank=8 (deepseek direct) at position 6. So when the OpenRouter key hit
  its cap on 2026-08-01, the whole fleet stalled while a funded, ~6x cheaper direct deepseek leg
  sat untried one position later. 18 provider keys are present and 16 providers configured; the
  depth exists and the ordering wastes it.

  ## WHY P0 (money-path)
  The directive is that cost carries heavy weight and the cheapest capable provider should win.
  The blocker is NOT missing data — it is that stored pool order was hand-authored and has drifted
  from the ranks, so cheapest-first is not actually happening. That is cheaper to fix than
  building a pricing pipeline, and it is the thing that actually costs money today.

  ## SCOPE — REVISED (do this, in this order)
  1. **Sort pool legs by cost: free-first, then `cost_rank` ASC.** Skip `enabled: false` and
     parked providers. This alone fixes the live defect.
  2. Treat the **647 entries with no `cost_rank`** as UNKNOWN cost — never silently ordered as if
     cheap. Surface the count; do not guess.
  3. Persist the cost map so ranks survive restart instead of being recomputed per call.
  4. Backfill missing ranks from litellm's `model_prices_and_context_window.json` (already a
     dependency) and provider APIs; record source disagreement rather than picking silently.
  5. `zai` is a funded first-party GLM provider with only 2 flash entries catalogued — cover it.

  ## SCOPE
  1. Make price (input/output per Mtok), context window, and free-tier flag REQUIRED catalog
     fields. Missing → loud, not silent.
  2. Persist the cost map (`build_cost_map`) instead of recomputing it per-call. It must exist
     on disk on 4-LOM.
  3. Populate from litellm's `model_prices_and_context_window.json` first (already a dependency),
     then provider APIs. Prefer MULTIPLE corroborating sources over one SSOT for observed facts;
     record disagreement rather than silently picking a winner.
  4. `zai` is a funded first-party GLM provider with only 2 flash entries catalogued — cover it.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
    a. **The live defect, reproduced then fixed:** a pool whose stored order puts a rank=50 leg
       ahead of a rank=8 leg is REORDERED so the cheaper one is tried first. Use the real
       `deepseek-v4-flash` shape above as the fixture. Revert the sort → RED.
    b. free-flagged legs precede paid legs; `enabled: false` and parked legs are skipped entirely.
    c. legs with NO `cost_rank` are classified UNKNOWN and never ordered ahead of a known-cheap
       leg. Revert → RED.
    d. `cost_map.json` exists on disk after a discovery run and is READ on restart, not recomputed.
    e. ANTI-OVER-BLOCK: a pool already in correct cost order is left byte-identical.
  Report before/after: the ordered leg list for `deepseek-v4-flash`, and the count of entries
  carrying `cost_rank` (baseline: 212 of 859).

  ## ADVERSARIAL REVIEW REQUIRED (money-path)
  Routing order decides real spend. This ticket does not land on a self-report — it needs an
  independent reviewer (reviewer != builder) confirming the reordering cannot silently route to a
  costlier leg, and that UNKNOWN-cost legs cannot be treated as cheap.

D&S — Deps & Sequence:
  - Depends on: nothing. Unblocks the cost directive and the PRICING-FEED work.
  - Product-side; blocked behind AMBIENT-COUPLED-TESTS only insofar as the product gate is red.
