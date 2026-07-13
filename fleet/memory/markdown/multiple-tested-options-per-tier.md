---
description: every routing tier should have a NUMBER of model options (no single points of failure); this requires testing MORE models — drives the real-outcomes benchmark + pools redesign
metadata: 
name: multiple-tested-options-per-tier
node_type: memory
originSessionId: aaf1f929-5adf-4f7f-862d-792cd64617af
type: project
tags: [test, tier]
last_referenced: 2026-07-13
---
DIRECTIVE (operator, 2026-07-08): every tier should have a NUMBER of model options, and "we need to test more." The operator explicitly does NOT want to hand-pick single models per tier — the system should offer several tested options per tier.

**Why it matters:** the fragility we hit (gpt-5.4 + nearly the whole catalog on ONE 2-member `[nanogpt, openrouter]` chain) is exactly the single-point-of-failure this rules out. Multiple tested options per tier = resilience + real choice.

**How to apply:**
- **Pools redesign** ([[charon-pools-redesign]]): each tier (low/med/high/frontier) must carry MULTIPLE capable members, not one — plus the free-tier + funded backends ([[use-free-tiers-to-their-limits]]).
- **Testing** ([[benchmark-not-a-valid-ranker]] real-outcomes pivot): "test more" = broaden the model set run through reds-replay / live-actuals so each tier's options are graded on real outcomes, not hand-picked. This is the ranking signal that decides which models qualify for a tier.
- **Catalog reconcile** ([[always-fix-catalog-mismatches]]): the gpt-5.4-vs-gpt-5.5 mismatch is NOT a single-pick — the high tier should list the real, TESTED option set; reconcile the catalog to live+tested reality, defer the "which is best" ranking to the testing pivot.

The operator does not yet know the models well enough to choose — so the SYSTEM must surface tested options, not require manual selection.
