repo: charon
tier: strong
priority: 2
difficulty: 3
work_class: money-path
branch: fix/models-json-structural-limits
depends_on:
owns: docs/review-log/MODELS-JSON-STRUCTURAL-LIMITS.md
serial_justified: |
  Single defect, single surface. Nothing to parallelise.
substrate: N/A
substrate-novel: |
  No tool adopted. The mechanism already exists and is misconfigured or mis-wired; the novel
  slice is the correction plus the assertion that keeps it corrected.
accept: |
  Documented but NOT fixed by the CATALOG-REFRESH-PERSIST work:
  (1) models.json holds ONE provider per model id, so the multi-provider failover chain cannot be
      expressed on disk — the persisted catalog cannot represent the routing structure the gateway
      actually uses;
  (2) the read-modify-write is not mutually excluded against the other writers (discover.py,
      config/models.py) — last writer wins.
  Both bite once PRICE-REFRESHER makes that file the cost-ordering source.

## Dependencies & Sequence

No inbound deps. Independent of the P0 lanes; disjoint owns.
