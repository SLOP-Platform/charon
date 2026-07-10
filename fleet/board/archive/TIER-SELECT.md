tier: strong
difficulty: 3  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: greenfield-feature
branch: feat/tier-select-catalog
depends_on: SR-8
real-dep: SR-8 build — TIER-SELECT edits src/charon/proxy_server.py (the web `/charon/setup`
  Tiers fieldset). proxy_server.py has a SINGLE-owner chain in the SR series (SR-2 → SR-6 → SR-7
  → SR-8, W2/W3); this ticket must land AFTER the last SR proxy_server.py owner (SR-8) so it
  rebases onto the final file, never a concurrent second writer. Shared-owns dep, JUSTIFIED (not
  merge-order-only). The catalog module + CLI picker portions are independent of the SR chain and
  could ship as an earlier phase (see prompt §Dependencies & sequence) if the web edit is split out.
owns: src/charon/model_catalog.py, src/charon/cli.py, src/charon/proxy_server.py, src/charon/gateway.py, tests/test_model_catalog.py, tests/test_tier_select.py
prompt: /home/stack/charon-private/prompts/tier-select.md
scope: PRODUCTION-READINESS / end-user tier→model selection. Give the Charon END-USER a curated,
  provider-agnostic model CATALOG (recommended options) and a PICKER — at BOTH the CLI and the web
  `/charon/setup` — so they assign specific model(s) to frontier/strong/economy by CHOOSING from
  real recommended ids OR entering their OWN off-catalog id (arbitrary model id + provider/base_url;
  pick-from-catalog OR enter-your-own, permissive/advisory validation so power users aren't fenced —
  Charon is provider-agnostic, never a hardcoded whitelist), persisted to the existing tiers.json
  store and routed by the existing _tier_pools compiler. Catalog is stdlib-safe DATA (no deps, no vendor
  hardcoding in logic). Complements (does NOT duplicate) parked TIER-RECS: TIER-RECS Phase B is an
  LLM-judge over a provider's LIVE /models; this ticket is a human-curated STATIC catalog (the
  MODEL-ROLE-EVALUATION.md list). Cross-ref, keep disjoint.
