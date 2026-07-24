repo: charon-private
tier: strong
difficulty: 5
priority: 0
work_class: rig-meta
branch: feat/unified-plane-canary-framework
owns: fleet/plane-canary-registry.tsv, fleet/plane-canary.sh, fleet/checks/plane-canary-conformance.sh, fleet/checks/plane-canary-discovery.sh, fleet/checks/plane-canary-drift.sh, fleet/plane-canary-monitor.sh, fleet/state/DESIGN-UNIFIED-PLANE-CANARY.md
extend_not_create: EXTEND the EXISTING fleet/plane-canary-registry.tsv (10 planes) + fleet/plane-canary.sh (PLANES=()) — do NOT mint a parallel registry (anti-accretion KS20). The 12 gap planes become new registry ROWS.
depends_on:
serial_justified: DESIGN-FIRST umbrella — the DESIGN doc + registry schema are one coherent first unit and must land before the legs, which the design itself decomposes into per-leg sub-tickets. Superseded/reshaped by the running DESIGN-SG-ISSUE-CONTROL-PLANE adopt-first investigation; not a parallel build yet.
source: operator 2026-07-24 — "I need the plane-canary suite to be a UNIFIED FRAMEWORK that covers ALL
  planes, DISCOVERS new planes and automatically rolls them into a canary test, has ANTI-STALENESS
  automation, is FULLY and COMPLETELY wired, and makes issues visible to manager sessions." Motivating
  instance: a stale board-correctness test fixture silently redded the ENTIRE rig merge queue for days
  (no canary caught it; plane-canaries only cover product/routing planes). Fixed the fixture (af9d8e6);
  this ticket prevents the CLASS.
note: |
  ADOPT-FIRST design: build on the KS29 REGISTRY PRIMITIVE (declare a registry -> auto conformance +
  discovery + drift for free) + KS22 FIRING-LAYER (every registered check actually runs) — do NOT
  hand-roll a bespoke canary framework. This UNIFIES + supersedes the piecemeal plane-canary tickets
  (PLANE-CANARY-REGISTRY[landed], PLANE-CANARY-WIRE, DESIGN-PLANE-CANARY-SUITE) and the newly-surfaced
  gate-test-health + loud-failure-monitor gaps into ONE framework. The 5 operator requirements =
  5 legs of the KS29 registry primitive applied to the PLANE->CANARY mapping.
accept: |
  1. ALL-PLANES COVERAGE — a single `fleet/plane-registry.tsv` (schema+scope) enumerating every
     load-bearing plane across BOTH repos + gateway: product (routing/failover/balance/egress/metering/
     streaming/grading/catalog), FLEET (claim-lease pool, THE GATE-TEST SUITE ITSELF, land/push path,
     reconcile, loop-guard, done/retire lifecycle, launcher auto-commit, CI allowlist), gateway/infra
     (live serving, SG off-Claude dispatch, Faktory). Seeded from the all-planes review (running).
  2. AUTO-DISCOVERY — a discovery leg that scans for NEW planes (new subsystem/gate/entrypoint) and
     FAILS CLOSED on an un-registered plane that should be in the registry (KS29 discovery leg). A new
     plane cannot ship without either a canary or an explicit registered exemption. No silent gaps.
  3. ANTI-STALENESS — a drift leg (KS24) that catches a canary/fixture that has gone stale vs the code
     it guards (the board-correctness class: a hermetic fixture missing a dep validate_board now needs).
     Each canary carries a freshness assertion; a canary that can no longer exercise its plane is RED,
     not silently green. Runs against MASTER on a cadence, not only PR-diff-scoped.
  4. FULLY + COMPLETELY WIRED (firing layer, KS22) — every registered plane's canary MUST be invoked
     in a real firing layer (rig-ci + a scheduled master run); registered-but-never-run = RED. No
     built-but-inert canaries. fail-on-revert proof that unwiring any canary goes RED.
  5. MANAGER-VISIBLE — a loud-failure MONITOR that aggregates ALL canary/gate reds (across repos +
     master + the scheduled run) into one surface loaded at SessionStart for manager sessions, so a
     loud failure can NEVER again sit un-acted-on (the board-correctness normalization). Wire into the
     SessionStart hook alongside the existing reds surfacer.
  - DESIGN doc first (fleet/state/DESIGN-UNIFIED-PLANE-CANARY.md): map each of the 5 legs to KS29/KS22/
     KS24 primitives + the adopt-vs-extend call. ADVERSARIAL REVIEW before build (reviewer != builder).
scope: |
  The unified framework (registry + 4 legs: conformance/discovery/drift/firing + the manager-visible
  monitor). Individual per-plane canaries are DATA ROWS in the registry, not new code (anti-accretion,
  KS20). Composes existing landed pieces; does not rebuild them.
ds: |
  ## Dependencies & sequence
  P0 (operator north-star for SG-readiness: a broken plane must be caught + visible, or SG can't be
  trusted to do good work). No hard prereq (KS29 primitive may be built inline or adopted). Design-first;
  seeded by the all-planes-needing-canaries review. Absorbs: PLANE-CANARY-WIRE, gate-test-health-on-master,
  loud-failure-monitor. Coordinate with KS29 (registry primitive) + KS22 (firing) + KS24 (drift).
