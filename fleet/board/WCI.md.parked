tier: opus
branch: feat/wci-mvp
depends_on: ADR-0015
real-dep: ADR-0015 WCI must build against a SIGNED, written design — not an unsigned/unwritten one. The ADR-0015 sign-off is a true build/correctness prereq, not merge-order. Owns are DISJOINT by design (WCI = engine/{reconcile,scheduler,board}.py + tests/test_reconcile.py; ADR-0015 = docs/adr/0015-* + docs/DECISIONS.md); the dep is JUSTIFIED, not assumed.
owns: src/charon/engine/reconcile.py, src/charon/engine/scheduler.py, src/charon/engine/board.py, tests/test_reconcile.py
prompt: /home/stack/charon-private/prompts/wci-mvp.md
scope: WCI-1 static reconciler + WCI-2 depth pre-sort ONLY (the adversarial-blessed MVP).
  WCI-1 = engine/reconcile.py::reconcile_static — consolidate/re-port the existing
  validate_board.sh + board.claimable + intake.analyze redundancy / contradiction / overlap
  checks into ONE deterministic function, wired as a pre-drain preflight (re-port per R8/M1;
  no new intelligence). WCI-2 = critical-path depth pre-sort of the ready set in
  board.claimable_units() ordering with id kept as the FINAL injective tiebreak; the
  claimability/serialization RULE is untouched (per R5/B2). EXCLUDES WCI-4 (merge_after edge
  type — under a separate reshape-fix) and WCI-6 (auto-slice / semantic-independence proof —
  PARKED behind §5.1 + ADR-0008 Phase 2 tripwire). owns is PROVISIONAL: reconcile.py is the
  design-named new module (DSGN-WCI-reshape.md §6); board.py carries the WCI-2 pre-sort.
note: PRODUCT-LEVEL WCI — ACTIVE / PRIORITIZED (operator 2026-06-27). HARD design constraint
  (unchanged): when built it MUST be opt-in-orchestrator-only + advisory/override for users —
  NEVER imposed on gateway-only / single-task fresh installs. A fresh gateway-only install sees
  ZERO WCI behaviour. (Charon ships standalone; WCI adds no required dependency.)
  TYPE droid-build (the adversarial-blessed MVP = WCI-1 + WCI-2). Claimable once ADR-0015 is
  DONE — it shows BLOCKED behind ADR-0015 until then (correct sequencing: do not build against
  an unsigned/unwritten design). depends_on points at ADR-0015 (2026-06-27): the ADR-0015
  sign-off is the REAL build/correctness prereq; it is NOT gated on TIER7B — owns are DISJOINT
  (WCI = engine/{reconcile,scheduler,board}.py; TIER7B = router/api/acp/failover.py), so WCI-MVP
  may build CONCURRENTLY with TIER7B. The ADR-0015 -> WCI edge is a justified disjoint-owns
  build-dep (see real-dep: above), not merge-order.

## NOTE — ACTIVE (un-parked 2026-06-27); blocks behind ADR-0015

Un-parked by operator decision 2026-06-27 (WCI now prioritized). It shows **BLOCKED** until
`ADR-0015` is DONE, then becomes **ready** — that is the correct sequencing: `depends_on:
ADR-0015` is the genuine build/correctness gate (do not build against an unsigned/unwritten
design). See the `real-dep:` marker above — the disjoint-owns dep is JUSTIFIED, so the WCI
enforcer treats it as `justified-disjoint-dep (ok)`, not a false-block.

**It is NOT gated on TIER7B:** the owns sets are disjoint (WCI owns
`engine/{reconcile,scheduler,board}.py`; TIER7B owns `router/api/adapters.acp/failover.py`), so
WCI-MVP can build **concurrently with TIER7B**. The earlier `depends_on: TIER7B` was a mere
ordering relation (the exact disjoint-owns ≠ build-dependency mislabel the WCI reconciler is
meant to catch) and has been dropped.

Design source: ADR-0015 (`docs/adr/0015-*`) once landed; reshape rationale in the rig's
`DSGN-WCI-reshape.md`. Adversarial review blessed the MVP as **WCI-1 (static reconciler —
re-port/consolidate the existing redundancy/contradiction checks) + WCI-2 (depth pre-sort of the
ready set)** as clean and shippable. WCI-4 (`merge_after` edge type) and WCI-6 (auto-slice) are
EXCLUDED here — they live in `WCI-FOLLOWON`, held behind the §5.1 semantic-independence proof.

Claimable checklist (all required before a droid claims it):
1. ADR-0015 written, reviewed, and merged (its `state/done/ADR-0015` marker exists → unblocks).
2. Operator sign-off on the WCI reshape carried in ADR-0015.
3. Build prompt exists at the `prompt:` path above (it does — `prompts/wci-mvp.md`).
