tier: frontier
difficulty: 4
work_class: money-path
branch: feat/provider-catalog-refresh
repo: charon
depends_on:
owns: src/charon/routing_policy/catalog_refresh.py, tests/test_catalog_refresh.py
accept: |
  MECHANIZE the gateway's model->provider mapping + keep it current on a SCHEDULE (operator 2026-07-13). Today,
  making a model routable requires HAND-MAPPING it into the catalog (Phi-4/GLM-4.7/Gemini-2.5 this session) — that
  must be automatic. Supersedes/absorbs the parked+rejected PRICE-REFRESHER (same job: this does the CATALOG half +
  folds in price).
  DO (background, OFF THE HOT PATH — hard operator rule, same as PRICE-REFRESHER): a scheduled job that, per
  CONFIGURED provider (base_url+key in /data — openrouter/deepinfra/nanogpt/google-ai-studio/…), polls its
  OpenAI-compatible `/models` on a TTL and refreshes a LOCAL catalog cache: normalized model-id -> [providers that
  serve it] + per-(provider,model) price (from the LiteLLM/OpenRouter price sources). The gateway's EXISTING
  cheapest-live-provider-first router (pool-is-single-source-already) reads this cache ONLY and auto-includes newly
  discovered models/providers — NO hand-mapping. Routing NEVER calls the poll; degrade to STALE-BUT-USABLE last-good
  on any refresh failure (log a red). Adding a provider (key+base_url) => next refresh auto-discovers its models.
  SCHEDULE: run on a TTL/cron (sensible sequence — hourly/daily), and on-demand; mechanized like sync-checkouts.
  ANTI-INERT (PRICE-REFRESHER was REJECTED for exactly this): the writer must be WIRED (imported + registered +
  its cache bridged to srv.model_pricing/catalog on the real routing path) and a NON-vacuous test must assert a
  freshly-discovered provider/model becomes ROUTABLE via the real router with NO hand edit. Meter-observed
  per-(model,provider) cost still SUPERSEDES quoted price once traffic exists.
  FAIL-ON-REVERT (tests/test_catalog_refresh.py): a mock provider /models listing a NEW model -> after a refresh the
  router can route that model to that provider with zero manual mapping; the poll is asserted OFF forward_with_failover
  (background only); stale-but-usable on provider-down. Revert the refresh->catalog bridge -> the new model is
  unroutable -> RED. Revert the off-path guard (routing calls the poll) -> RED.
scope: |
  ROUTER capability/catalog engine — the auto model<->provider mapping the whole cheapest-first design assumes.
  Absorbs PRICE-REFRESHER (parked, rejected). [[charon-pools-redesign]] [[pool-is-single-source-already]]
  [[charon-work-engine-vision]] [[always-fix-catalog-mismatches]] [[charon-gateway-host]]
ds: |
  depends_on: none (new disjoint file). Reuses the price sources from the PRICE-REFRESHER eval (LiteLLM vendored +
  OpenRouter live). REPLACES PRICE-REFRESHER (retire that ticket). Money-path: adversarial review REQUIRED; design
  it grounded FIRST (do NOT rebuild blind — PRICE-REFRESHER shipped inert+doctored). Off-hot-path is non-negotiable.
note: HIGH — kills manual model mapping; the properly-built catalog+price refresher on a schedule. Design-first, then build.
