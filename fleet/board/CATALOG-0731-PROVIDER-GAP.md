repo: charon
tier: strong
priority: 1
difficulty: 3
work_class: routing
branch: fix/catalog-0731-provider-gap
depends_on:
owns: docs/review-log/CATALOG-0731-PROVIDER-GAP.md
serial_justified: |
  One discovery defect verified against one external source; splitting invites two partial
  catalogs.
substrate: N/A
substrate-novel: |
  No tool adopted. Discovery already exists; it is producing an INCOMPLETE provider set. The
  novel slice is finding why it under-discovers and proving coverage after.
accept: |
  MEASURED 2026-08-02 against the live gateway catalog (2585 models) and an independent feed.
  OUR catalog lists `deepseek-v4-flash-0731` under DeepInfra and Morph ONLY.
  TokenWatch lists THIRTEEN providers serving it, cheapest first:
    deepinfra $0.09/$0.18 · crof $0.12/$0.21 · gmicloud $0.133/$0.266 ·
    deepseek-direct / cloudflare / novita / parasail / siliconflow / atlascloud / fireworks
      $0.14/$0.28 · hyper $0.152/$0.305 · io-net $0.18/$0.34 · mancer-2 $0.25/$1.00
  The operator independently confirmed OpenRouter serves it
  (openrouter.ai/deepseek/deepseek-v4-flash-0731) — we have `deepseek-v4-flash-or` but NO
  `-0731-or`, and `deepseek-v4-flash-ds` but no 0731 variant.
  CONSEQUENCE: anything pinned to -0731 routes to a SINGLE provider with NO failover, and we
  cannot see that DeepInfra is 36% cheaper on input than DeepSeek direct.
  Done contract:
  1. Root-cause the UNDER-DISCOVERY: why do dated snapshots not enumerate for openrouter and
     deepseek-direct when the unsuffixed model does? Fix the discovery, not the one entry.
  2. Coverage is the acceptance metric — state provider-count-per-model before and after for a
     sample, not just for 0731.
  3. Catalog is LIVE DATA (doctrine sec.14): assert re-discovery on a cadence, not a one-off seed.
  4. Fail-on-revert on the discovery fix.

## Dependencies & Sequence

P1. Independent of the cost tickets but feeds them — a missing provider is a missing price and a
missing failover leg. Cross-check against PRICING-FEED's chosen sources once they land.
