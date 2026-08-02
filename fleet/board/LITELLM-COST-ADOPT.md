repo: charon
tier: strong
priority: 0
difficulty: 4
work_class: money-path
branch: feat/litellm-cost-adopt
depends_on:
owns: docs/review-log/LITELLM-COST-ADOPT.md
serial_justified: |
  One adoption decision over one vendored plane. Splitting it lands half a cost path beside a
  hand-rolled one, which is the current state and the defect.
substrate: |
  LiteLLM — ADOPT. It ships mature per-request cost tracking and budget enforcement, and we have
  ALREADY VENDORED IT: src/charon/litellm_plane/{metering,litellm_router,park_cooldown,streaming}.py
  are in-tree. The registry carries LiteLLM-as-data-source ADOPT (2026-07-12). We are not
  choosing whether to adopt; we adopted and never wired it.
accept: |
  MEASURED 2026-08-02: `grep -rn litellm_plane src/ | grep -v src/charon/litellm_plane/` returns
  ZERO production importers. The whole plane is merged, marked done, and imported by nothing —
  the largest single instance of the built-but-inert class on the board.
  Meanwhile we hand-roll a meter that reports $1,185 for two days of August against ~$1.34 of
  measured real spend, with a fabricated est_cost floor and no per-provider attribution.
  Done contract:
  1. Enumerate what LiteLLM's cost/budget surface actually gives us — per-request cost,
     per-key/user budgets, spend logs — and which of our hand-rolled pieces it REPLACES.
  2. Wire it, or delete the plane with evidence. Vendored-and-unused is the worst of both: it
     reads as adopted and provides nothing.
  3. Prove reachability from a real entrypoint (this is exactly what WIRING-DONE-CONTRACT gates).
  4. Cross-check LiteLLM-reported cost against provider-reported cost on a sample; disagreement
     is a finding about the layer, not a rounding error.
  5. Fail-on-revert proving the cost path is live — a test that fails if the importer disappears.

## Dependencies & Sequence

P0 money-path. Pairs with SPEND-METRIC-TRUSTWORTHY: that ticket defines the METRIC
(provider-reported, per-provider, cost per accepted task); this one asks whether the mechanism we
already vendored should be the one computing it. Do this evaluation BEFORE hand-building more
metering, or we hand-roll a third meter beside two unused ones.
