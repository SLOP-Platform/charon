repo: charon-private
tier: strong
difficulty: 2
priority: 0
work_class: ci-infra
branch: feat/plane-canary-wire
owns: .github/workflows/plane-canary.yml, fleet/preflight.sh, fleet/foreman-cadence.sh,
  fleet/tests/plane-canary-wire.test.sh
real-dep: RECONCILE-WIRING owns fleet/preflight.sh and fleet/foreman-cadence.sh already (the last
  ticket in the existing preflight-anchor chain SYNC-SCHEDULE -> REPO-MAP-CONVERGE ->
  MARKER-PROOF-MECHANIZE -> RECONCILE-WIRING); sequencing after it avoids a parallel-edit
  collision on those two shared anchor files. [[anchor-lines-serialize-parallel-work]]
real-dep: PLANE-CANARY-REGISTRY creates fleet/plane-canary.sh (the `run`/`reconcile`/`tests`
  sub-commands this ticket's CI job, preflight line, and cadence entry all invoke) — a genuine
  build prereq, this ticket has nothing to call without it.
depends_on: PLANE-CANARY-REGISTRY, RECONCILE-WIRING
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 4.4 ("Wiring — one wiring, all planes
  ride it") + "PROPOSED TICKET LIST" row 2.
note: |
  A new SIBLING CI workflow (.github/workflows/plane-canary.yml) is used instead of editing the
  existing rig-ci-scope.sh CI_SUITES allowlist directly, to avoid ANOTHER owns-collision (that
  file already has a live owner — HANDOFF-GATE-NONBYPASSABLE). This mirrors the design doc's own
  named alternative ("or a sibling plane-canary job in .github/workflows/rig-ci.yml") and keeps
  this ticket's CI surface disjoint from HANDOFF-GATE-NONBYPASSABLE's. The new workflow calls
  `fleet/plane-canary.sh tests` (PLANE-CANARY-REGISTRY's accessor) to source the hermetic dogfood
  list, so there is still exactly ONE hand-maintained list, per rig-ci.yml's own header discipline
  (never a `for t in fleet/tests/*` sweep).
accept: |
  - .github/workflows/plane-canary.yml: a new job that runs `fleet/plane-canary.sh run --hermetic`
    (all dogfood tests, offline, under CI's time budget) on every PR, and fails the check on any
    non-zero exit. Sourced from `fleet/plane-canary.sh tests`, never a hardcoded duplicate list.
  - fleet/preflight.sh scan-dispatch (the existing chain at the anchor RECONCILE-WIRING extends):
    add `fleet/plane-canary.sh run --live && fleet/plane-canary.sh reconcile` to the scan chain so
    every manager preflight surfaces plane RED + registry gaps. Must be a REAL invocation (grep-
    verifiable), not a comment/TODO — this is exactly what the reconciliation leg's "unwired" R-G
    class would itself flag if skipped.
  - fleet/foreman-cadence.sh: add a cadence-timer entry (interval-gated, per the existing
    foreman-cadence.sh:87-102 pattern RECONCILE-WIRING already extends) that runs
    `fleet/plane-canary.sh run --live` on a schedule and surfaces RED via the foreman channel —
    the "no cadence exists yet" gap the design doc calls out (flow-canary never got one).
  - fail-on-revert test (fleet/tests/plane-canary-wire.test.sh): (a) grep-assert plane-canary.sh
    is actually invoked from fleet/preflight.sh's scan-dispatch list -> revert the line -> test
    goes RED; (b) grep-assert the cadence entry exists in foreman-cadence.sh with a real interval
    -> remove it -> RED; (c) `.github/workflows/plane-canary.yml` exists and its `run:` step
    literally calls `fleet/plane-canary.sh` (not a stub) -> delete the step -> RED. This test
    IS the reconciliation leg's own "unwired" check applied to itself — do not skip it because
    "reconcile already covers this," prove wiring at the CI-config-syntax level too.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — edits load-bearing
    fleet/preflight.sh + fleet/foreman-cadence.sh (the firing layers every gate on the board
    rides) and adds a new required CI job; manager gates, PR does NOT merge on the builder's
    self-report.
scope: |
  Wiring only — one wiring point per firing layer (CI job, preflight scan-dispatch, cadence
  timer), consumed by every plane's canary uniformly. Does not build any new canary logic
  (that is PLANE-CANARY-REGISTRY + the 7 gap-canary tickets). SessionStart/land hooks are
  explicitly OUT of scope for this ticket (narrower than the design doc's "+ hooks" phrase) to
  avoid a further collision with SYNC-SCHEDULE's fleet/hooks/session-start.sh ownership; a
  SessionStart hook for plane-canary is a small follow-on, not required for CI+preflight+cadence
  to be real.
ds: |
  ## Dependencies & sequence
  depends_on PLANE-CANARY-REGISTRY (needs `fleet/plane-canary.sh` + `tests` accessor to exist
  first) and RECONCILE-WIRING (shares fleet/preflight.sh + fleet/foreman-cadence.sh — sequenced
  after the existing anchor chain rather than forking a second collision). Disjoint from every
  gap-canary ticket (FAILOVER-CANARY etc.) — none of them touch CI/preflight/cadence files, so
  this ticket can build in parallel with all of them once PLANE-CANARY-REGISTRY lands.
