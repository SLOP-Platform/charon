# MODEL-GRADE-PRESEED — Cold-start external-benchmark prior (decaying, real-overridden)

**Date:** 2026-07-23
**Ticket:** MODEL-GRADE-PRESEED
**Branch:** feat/model-grade-preseed
**Gate:** 2249 passed (170 new), ruff clean, mypy clean, boundary/version/arch/test-patterns clean

## Scope

Cold-start bridge for the outcome-graded brain (ADR-0017 §Cold-start). Today
`CapabilityMatrix.get_grade()` returns `"unknown"` for every `(model, work_class)`
on a fresh install → the gateway has NO usable ranking to route on. ADR-0017
(lines 49-54, 121-123) names a "seed scorecard / importable scorecard" as the
bootstrap path but marked it "required design, not yet designed"; a
`grades_import`/`product_grades` seed path is named. This ticket IS that path.

## Decision

Seed a **PROVISIONAL** per-`(model, work_class)` prior from legitimate external
benchmarks (aider-polyglot, LMArena, Artificial Analysis, models.dev) structured
as a **DECAYING PRIOR** that real graded outcomes override — NOT a fixed
leaderboard rank. This resolves the doctrinal tension
([benchmark-not-a-valid-ranker] / MODEL-ROLE-EVALUATION.md:203 "your own signal
outranks any leaderboard"): the prior is explicitly provisional and loses weight
as real outcomes accumulate, so own-signal still wins once it exists.

The override rule is **structural**, not configurational:
- prior entries land in the existing `CapabilityMatrix` at `confidence < 1.0`
  (DEFAULT_PRIOR_WEIGHT = 0.5);
- `reconcile_with_real()` REPLACE s the prior entry (confidence → 1.0) — the
  prior is overwritten, never blended;
- a re-seed NEVER clobbers a real graded outcome.

The prior lands in the EXISTING `CapabilityMatrix` (no parallel store invented
— the ADR-0017 `grades_import`/`product_grades` seed path). The
provisional/real tag + provenance are tracked in an importer sidecar because
`ModelCapability` (owned by another ticket) carries no metadata field; the
sidecar keeps this module self-contained and within its `owns:`.

## Files (owns:)

- `src/charon/capability/grades_import.py` — the import path + decay/override rule
- `tests/test_grades_import.py` — 170 tests incl. the day-1 ordering proof

## Proof CG ranks day-1 (acceptance §3)

`seed_matrix()` returns a populated `CapabilityMatrix`; `rank_for_work_class()`
returns a NON-EMPTY best-first ordering for EVERY taxonomy class (`reasoning`,
`coding`, `translation`, `creative`, `analysis`, `general`) — parametrized in
`TestDayOneOrdering`. CG can now produce a non-empty ordering to route on day-1
even with zero real outcomes.

## Self-check

- Every seeded entry: `0.0 < weight < 1.0` (provisional guard, parametrized).
- Every work class covered (no routing hole, parametrized).
- Stdlib + charon only (no third-party deps; verified by an AST self-test).
- `check_arch` product-clean: `capability/` is not in the engine/gateway scope
  of the vendor-name literal scan; the seed uses MODEL names as data, not
  vendor imports.
- `check_boundary`: no host-project references.

## Downstream unblock

Consumer is GATEWAY-GRADE-ORDER-MVP (blocked on GW-CUTOVER-LIVE-WIRE) — that is
what actually routes on the ranking. This ticket is the cold-start half; pairs
with EVAL-CONTROL-GATE-FIX (fixes the real-outcome LOOP). Both are needed.