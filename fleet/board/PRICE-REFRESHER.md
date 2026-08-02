tier: strong
priority: 2
difficulty: 3
work_class: money-path
branch: feat/price-refresher
repo: charon
depends_on:
owns: src/charon/routing_policy/price_refresher.py, tests/test_price_refresher.py
accept: |
  ADR-0016 step #3, REVISED to ADOPT-NOT-BUILD (evidence: fleet/state/PRICING-TOOLS-EVAL.md, 2026-07-12 — every
  repo cloned + code-read). NO bespoke scraper, NO hand-typed table. A thin background refresher that WRAPS
  best-in-class sources and writes the local `model_pricing` cache; `order_pool_by_live_cost` reads the cache ONLY.
  VERIFIED CURRENT STATE (do NOT re-research — file:line): the cheapest-first reorder already runs at request time
  (`order_pool_by_live_cost` routing_policy/__init__.py:244, called from forwarder.py's R2 block ~375-395, reading
  `srv.model_pricing`); `derived_cost_rank` (routing_policy/cost_rank.py:32) blends input/output price. THE GAP is
  only the SOURCE that fills `model_pricing` — this ticket adopts it instead of building it.
  HARD REQUIREMENT — OFF THE PER-REQUEST HOT PATH (operator, non-negotiable): the refresher is a BACKGROUND
  process; it must NEVER be called from forward_with_failover / the routing path. Routing reads a LOCAL cached value
  only. Degrade to STALE-BUT-USABLE on any refresh failure (keep last-good, log a red, never block/slow a route).
  DO (new file only, disjoint): src/charon/routing_policy/price_refresher.py with three cache-writers, all feeding
  the local `model_pricing` map (keyed per (provider, model) — pitfall #4: the SAME model is priced differently per
  provider, so a model-level key is WRONG):
    (a) VENDOR LiteLLM `model_prices_and_context_window.json` (BerriAI, MIT) as the SOURCED price table, REPLACING
        R17's hand-typed TSV. Git-vendor the JSON (one static file, ~2963 entries, provider-keyed deepseek/…,
        openrouter/…, together_ai/…); load once into `model_pricing`. Per-entry schema already carries
        input_cost_per_token / output_cost_per_token / cache_read / cache_creation / max_input_tokens /
        litellm_provider / `source` (URL → feeds R17 drift). Map litellm_provider keys → Charon pool labels.
    (b) POLL OpenRouter `/api/v1/models` — ONE unauthenticated GET returns the WHOLE catalog — on a TTL (suggest
        hourly) as the LIVE layer for the openrouter pool AND the drift oracle for the vendored LiteLLM snapshot
        (OpenRouter IS LiteLLM's own upstream, so the numbers must agree). Parse the string per-token pricing
        (prompt/completion/input_cache_read/…). Background poller only; writes the cache.
    (c) INGEST changedetection.io webhooks (Apache-2.0 JSON POST `{provider,url,old,new}`) for the ZERO-COVERAGE
        providers (nanogpt, neuralwatt, opencode-zen — no tool covers these) as out-of-band sourced-price updates +
        drift signal into the same cache / R17 drift-red path. Just the ingest endpoint/handler; the detector is
        self-hosted infra, not this repo.
  ANTI-ROT (ADR §Adversarial stress-test #1 + eval "Bottom line"): every writer is cold-start/advisory only. The
  METER-OBSERVED per-(model,provider) cost (`observer.all_model_provider_costs` proxy.py:549) supersedes any quoted
  price inside `order_pool_by_live_cost` the moment traffic exists — the only defense against thinking-token
  undercount. Assert this precedence.
  FAIL-ON-REVERT (add tests/test_price_refresher.py): (1) the refresher populates `model_pricing` from the VENDORED
  LiteLLM snapshot (per (provider,model)) such that `order_pool_by_live_cost` orders the cheaper-sourced provider
  first with an EMPTY meter; (2) ROUTING READS CACHE ONLY — assert NO network call occurs on the hot path (the
  OpenRouter poll is exercised as a background call that writes the cache, mock-asserted OFF forward_with_failover).
  Revert the vendored-snapshot load → `model_pricing` unseeded, cold-start order arbitrary → test (1) RED. Revert the
  background/cache split (make routing call the network) → test (2) RED. Third invariant: a non-empty meter overrides
  the sourced/pulled quote (precedence test above).
  GREEN-IS-NOT-PROOF: existing routing/forwarder suites pass with `model_pricing` empty (they exercise "meter or
  static order"), so green proves NOTHING about the adopted sources — REQUIRE (1) the vendored-snapshot→order test,
  (2) the NO-network-on-hot-path assertion, (3) the meter-supersedes precedence test, and (4) a reviewer confirming
  the LiteLLM JSON is VENDORED (checked-in file, not fetched at request time), keys are (provider,model), and the
  OpenRouter poll + webhook ingest are strictly background/off-path.
  ADVERSARIAL REVIEW REQUIRED (money-path): a wrong/stale price mis-orders spend, and a hot-path network call is a
  latency regression. Reviewer confirms the OFF-hot-path guarantee + meter precedence + provider-keyed schema.
scope: |
  ADR-0016 "Demand-driven capability match" step #3 — REVISED ADOPT-NOT-BUILD (PRICING-TOOLS-EVAL.md). Wrap
  LiteLLM's MIT provider-keyed price JSON (replaces R17's hand-typed TSV) + OpenRouter's one-GET live catalog +
  changedetection.io webhooks for the no-API tail. All background writers into one local `model_pricing` cache that
  routing reads. No bespoke scraper. Meter still supersedes all quoted prices once traffic exists.
  [[charon-free-tier-routing]] [[charon-pools-redesign]] [[ksf-modular-plugin-best-in-class]] [[always-fix-catalog-mismatches]]
ds: |
  ## Dependencies & sequence
  depends_on: (none hard) — disjoint NEW file src/charon/routing_policy/price_refresher.py. No god-file owned.
  adopts: LiteLLM model_prices_and_context_window.json (MIT, vendored), OpenRouter /api/v1/models (live, off-path
    poll), changedetection.io (Apache-2.0, webhook ingest). REPLACES the hand-typed R17 TSV as the sourced table.
  feeds: order_pool_by_live_cost (routing_policy/__init__.py:244) via the model_pricing cache — DATA feed only, no
    code edit to that file, so no owns overlap / no build dep on it.
  concurrency: RUNS NOW. Parallel-safe with FAIL-LOUD-CONTRACT (disjoint files) and the whole F29/R46/gateway.py
    serial chain (owns no shared file). Hard axis: refresher is BACKGROUND — off the per-request routing path.
  soft-follow-on: background-poller registration rides F29-REGISTRY-SLICE's MODULE_SPECS after F29 lands (deferred,
    not owned here). DELETE-STATIC-RANK (#6) depends_on THIS ticket (must be live-verified first).
  repo: charon (product).
note: |
  ADR-0016 #3, ADOPT-NOT-BUILD (renamed from LIVE-PRICE-PULL 2026-07-12 per PRICING-TOOLS-EVAL.md). NEW disjoint
  file — READY, runs now (concurrent with FAIL-LOUD-CONTRACT).
  UN-PARKED 2026-07-16 (operator-approved, crash-recovery session): the `parked: true` flag contradicted this
  note ("READY, runs now") and its own concurrency condition was already met — FAIL-LOUD-CONTRACT was submitted
  as PR #151. Stale flag, not a live directive. Owns a NEW disjoint file, so no collision risk.

## RE-SCOPE 2026-08-02 (operator-directed): THIS IS THE FALLBACK PATH, NOT THE PRIMARY

Operator: "why are costs not being derived directly from the providers?" The answer reorders
this ticket's place in the money path.

PRIMARY is now provider-reported cost, owned by SPEND-METRIC-TRUSTWORTHY: take the number the
provider itself returns (OpenRouter /api/v1/generation gives actual cost per request; most
OpenAI-compatible providers return real `usage` in the response body). That is authoritative and
has NO price table to rot.

THIS TICKET becomes the FALLBACK: a live-fetched price feed used only when the provider does not
report cost. That is still necessary — not every provider reports — but it is no longer the
thing the money path stands on, and it must not be built as if it were.

CONSEQUENCE FOR THE DESIGN:
 1. An unpriced model must resolve to UNKNOWN, never to a synthesised floor. The existing
    fabricated est_cost floor is exactly how the meter reported ~$223 once and $1,185 for two
    days of August against ~$1.34 of real spend. Removing the floor is part of this ticket even
    though the floor lives elsewhere — a feed that lands while the floor survives changes nothing.
 2. Price data is LIVE DATA (doctrine sec.14): model names and free status rot. Verified today —
    `minimax-m3-free` billed $0.1542 despite `-free` in its name. The feed must re-read free
    status and price EVERY cycle, not seed once.
 3. Coverage is the acceptance metric, not existence: today 10 of 861 models are priced. State
    the coverage number before and after, and gate on it.

DEPENDENCY DIRECTION (was implicit, now explicit): SPEND-METRIC-TRUSTWORTHY consumes this feed,
not the reverse. Neither blocks the other — provider-reported cost works today for the providers
that report it, and should not wait on full price coverage.
