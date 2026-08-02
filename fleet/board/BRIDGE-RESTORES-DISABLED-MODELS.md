repo: charon
tier: frontier
priority: 1
difficulty: 3
work_class: money-path
branch: fix/bridge-restores-disabled-models
depends_on:
owns: docs/review-log/BRIDGE-RESTORES-DISABLED-MODELS.md
serial_justified: |
  Single defect, single surface. Nothing to parallelise.
substrate: N/A
substrate-novel: |
  No tool adopted. The mechanism already exists and is misconfigured or mis-wired; the novel
  slice is the correction plus the assertion that keeps it corrected.
accept: |
  Found during the CATALOG-REFRESH-PERSIST adversarial review; PRE-EXISTING, from the original
  PROVIDER-CATALOG-REFRESH wiring. bind() snapshots static config into _base ONCE at build_server;
  bridge() rebuilds live routes from that snapshot every cycle. So a model an operator DISABLES
  after startup (dropped by _reload()) is RESTORED by the next bridge — operator disable does not
  stick on a running gateway until restart. This is why PR #211 is deliberately still DRAFT: its
  'propagates to EVERY consumer' bar is only PARTIAL until this lands.

## Dependencies & Sequence

No inbound deps. Independent of the P0 lanes; disjoint owns.
