---
description: "The single-source cheapest-provider-per-model + roll-on-exhaust router is BUILT + LIVE; \"-ds/-go/-ng variants\" are provider-pinned aliases over one base model, NOT separate pools. Failures were stale config DATA (dead providers ranked cheapest), not a missing design"
metadata: 
name: pool-is-single-source-already
node_type: memory
originSessionId: fffc7f6f-75c2-4588-b70e-1d3885da5281
type: project
tags: [pool, routing]
last_referenced: 2026-07-13
---
Verified 2026-07-12 (fleet/state/POOL-INVESTIGATION.md). Correcting a recurring confusion (including the manager's) that Charon has "multiple pools / pool nonsense":

- The operator's design — ONE provider source, per model pick the cheapest provider that serves it acceptably, roll to next-cheapest on exhaustion — **is built and live** (v0.4.1). `_build_routes_and_pools` sorts by `(not free, cost_rank)`; requesting a base model (e.g. `deepseek-v4-pro`) rides the cheapest-first chain. The `-ds`/`-go`/`-ng`/`-or` suffixes are **provider-pinned aliases over the SAME base model**, not separate models or literal pools.
- It only LOOKED broken because the config DATA was stale: for `deepseek-v4-pro` the dead providers were ranked cheapest (`opencode-go`=5 [401], `nanogpt`=10 [429]) and funded `deepseek.com`(-ds) was 4th (60); plus `fallback.json=["opencode-go"]` appended the dead provider to every chain. Under load it exhausted the dead ones first → "POOL TOO THIN". Fix = config-data retune on .60, NOT a redesign.
- Two real gaps: **cost-rank-AUTO** (derive rank from real pricing, v0.5.0 R2/R5) is built in-repo but **NOT deployed** (live = v0.4.1 dead tag → [[charon-project-state]] release FAILED); the **~4 tier-set unification** ([[charon-pools-redesign]]) is design-only, never built — but it is an optimization, not required for cheapest-first to work.

**How to apply:** don't describe Charon routing as "pools to be removed" — cheapest-first-per-model already works; the levers are (1) the per-model provider ranking DATA + enabled flags on .60 `/data/{models,pools,fallback}.json`, (2) deploying v0.5.0 for auto-pricing, (3) wiring funded providers (deepseek.com everywhere, together/neuralwatt) + parking dead ones ([[charon-drain-then-park-provider-class]]). Live .60 config is deploy-drifted from repo — read the container's /data, not just the repo.
