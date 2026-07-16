tier: frontier
priority: P0  # ADR-0016 gateway deploy — TOP frontier priority (operator 2026-07-15): restores the demand-driven switchboard
difficulty: 4
work_class: money-path
branch: feat/delete-static-rank
repo: charon
parked: false
depends_on:
real-dep: PRICE-REFRESHER build — the hand-typed cost_rank cannot be deleted until a LIVE/sourced cost
  magnitude exists to order on; PRICE-REFRESHER supplies the cold-start pull that replaces it. Genuine
  correctness prereq (removing the fallback before the replacement is live = an unordered chain).
real-dep: DRAIN-THEN-PARK build — deletion may only land after the demand-driven ordering (price-pull + meter +
  drain-then-park) is LIVE-VERIFIED end-to-end, so static rank is never removed while anything still reads it.
owns: src/charon/routing_policy/cost_rank.py, src/charon/pools.py, src/charon/config.py, tests/test_delete_static_rank.py
accept: |
  ADR-0016 step #6 (docs/adr/0016-demand-driven-capability-match.md, "Build decomposition" row 6 + Decision §5).
  DELETE the hand-typed `cost_rank` integer as a config INPUT — ordering must derive from live/sourced/meter price
  only. Lands LAST so ordering never regresses mid-migration.
  VERIFIED CURRENT STATE (2026-07-12, do NOT re-research — file:line):
    - Schema/validator INPUT sites (config.py): the `cost_rank: int | None` param (config.py:268), persisted at
      config.py:287-288, and the import-path persist at config.py:328-330. These are the HAND-TYPED entry points.
    - Model sites: PoolEntry.cost_rank field (pools.py:35), set via `derived_cost_rank(...)` (pools.py:67), used
      as the tie-break sort key (pools.py:121 `(not e.free, e.cost_class_priority, e.cost_rank)`).
    - Derivation: routing_policy/cost_rank.py:32 `derived_cost_rank` — currently returns an EXPLICIT cost_rank
      when set, else derives from pricing.
  DO: remove `cost_rank` as an accepted config INPUT — drop the `cost_rank` param + persistence from config.py
    (268/287-288/328-330), and remove the "explicit cost_rank override" branch from derived_cost_rank so ordering
    is ALWAYS derived from live/sourced/meter price. Keep an internal derived magnitude for the sort if needed, but
    it must be COMPUTED, never read from config. Add a one-release DEPRECATION WARNING in the validator when an
    external config still sets `cost_rank` (per ADR Consequences: "one-release deprecation warning in the
    validator"). Purge `cost_rank` integers from the `.60` /data/models.json as a DEPLOY-side edit (operator-gated,
    NOT in this repo diff — note it in the ticket close).
  RETAIN cost_class (DO NOT DELETE — ADR Decision §5, single-biggest-risk section): `cost_class` is the funding-
    class CATEGORY axis a scalar cannot express (free-daily / expiring / prepaid / metered). It is an operator-set
    ENUMERATED category validated against the reactive signal — the ADR's honest floor — NOT a decaying magnitude.
    Leave cost_class + cost_class_priority (pools.py:121) fully intact; only the cost_rank MAGNITUDE goes.
  FAIL-ON-REVERT (add tests/test_delete_static_rank.py): (1) a config that sets `cost_rank: N` no longer produces
    a PoolEntry whose order depends on N — ordering is identical to the same config WITHOUT cost_rank (derived from
    price only), and the validator emits the deprecation warning. (2) cost_class STILL orders pools by funding class
    (a prepaid provider still sorts ahead of a metered one). Revert the deletion (re-honor explicit cost_rank) →
    assertion (1) RED; accidentally drop cost_class → assertion (2) RED.
  GREEN-IS-NOT-PROOF: the gateway/pools suites pass TODAY with cost_rank honored, so their green proves the OLD
    behavior — REQUIRE (1) a test proving a set cost_rank is IGNORED for ordering, (2) a test proving cost_class is
    RETAINED and still orders, and (3) a reviewer confirming NO code path still reads a config-supplied cost_rank
    and that the .60 /data purge is captured as a deploy action.
  ADVERSARIAL REVIEW REQUIRED (money-path, high blast radius): deleting the last static ordering input while live
    ordering must fully cover it. Reviewer confirms PRICE-REFRESHER + DRAIN-THEN-PARK are live-verified first and
    that cost_class is untouched.
scope: |
  ADR-0016 "Demand-driven capability match" step #6 — the deletion that bans hand-typed rank outright. Removes
  the rot-prone MAGNITUDE (cost_rank integer); keeps the drift-checked CATEGORY (cost_class). Lands LAST, after
  the live/sourced/meter ordering it replaces is verified on .60. [[always-fix-catalog-mismatches]] [[charon-pools-redesign]]
ds: |
  ## Dependencies & sequence
  depends_on: PRICE-REFRESHER (live cost magnitude must exist first), DRAIN-THEN-PARK (full demand-driven match
    live-verified first) — both real build/correctness prereqs (see real-dep above), NOT merge-order.
  concurrency: PARKED — lands LAST. Owns config.py (shared with the live F29-CONFIG-PKG / PROVIDER-PROBE-FIX /
    PROVIDER-URL-HELPER chain) and pools.py + cost_rank.py (disjoint). Parked keeps it inactive so it does not
    collide; un-park ONLY after #3 (PRICE-REFRESHER) and #4 (DRAIN-THEN-PARK) are live-verified, and re-sequence
    it behind whatever still owns config.py at that time (config may be a package post-F29-CONFIG-PKG).
  repo: charon (product).
note: Activated 2026-07-15 (operator directive - ADR-0016 deploy is P0). Prior stage-gate referenced a fabricated dep (PRICE-REFRESHER, PR #104 closed) plus a now-live one (auto-park-on-402); both moot. Droid builds the code PR; the live 4-LOM deploy is a separate manager step.
  .60 (static rank must never be removed while anything still reads it). Filed 2026-07-12.
