repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: rig-meta
branch: feat/plane-canary-registry
owns: fleet/plane-canary-registry.tsv, fleet/plane-canary.sh, fleet/tests/plane-canary.test.sh
serial_justified: The registry format, the runner that reads it, and the reconciliation leg that
  cross-checks it are one invariant — a registry with no runner is inert, a runner with no
  reconciliation leg can silently miss a declared-but-unwired plane (the exact FINAL-E2E-REVIEW
  phantom class this suite exists to kill). Splitting them across tickets would let one land
  without the other and reopen the gap.
depends_on:
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 4 (design-only, read-only investigation,
  no fleet code changed at design time) — "PROPOSED TICKET LIST" row 1. Mirrors
  fleet/checks/rig-ci-scope.sh's CI_SUITES allowlist-runner pattern and fleet/flow-canary.sh's
  RED-aggregation pattern (both cited file:line in the design doc).
work_class_note: rig-meta — this is fleet/rig test-infrastructure (the harness that proves other
  gates/canaries are real), not a product feature.
note: |
  Of 10 declared planes (design doc Phase 3 inventory), exactly ONE is GREEN today
  (data/serving — fleet/flow-canary.sh + fleet/tests/flow-canary.test.sh, already a CI_SUITES
  member). This ticket's registry MUST seed all 10 rows verbatim from the design doc's Phase 4.1
  example table (below), including rows whose canary_script/dogfood_test do not exist on master
  yet — that is the CORRECT initial state: the reconciliation leg (accept criteria below) is
  SUPPOSED to report those as RED/GAP until FAILOVER-CANARY, EGRESS-KEY-CANARY,
  REVIEW-DISPENSATION-CANARY, TICKET-LIFECYCLE-CANARY, BALANCE-CANARY, CONFIG-SSOT-CANARY-REGISTER
  and LANDING-GATE-REGISTER each land their file at the path this ticket already declares. This is
  deliberate: it lets those 7 follow-on tickets each own ONLY their new canary+test files (no
  further edits to this TSV), which is how their owns: stay disjoint from each other and from this
  ticket (see D&S below) — a shared-file collision resolved by NARROWING the shared surface to one
  ticket instead of a depends_on chain across seven siblings.

  Seed content for fleet/plane-canary-registry.tsv (tab-separated; header + 10 rows, verbatim from
  the design doc):
    # plane        canary_script                          dogfood_test                              wired_in            owner_ticket
    data/serving   fleet/flow-canary.sh                   fleet/tests/flow-canary.test.sh           ci,preflight        FLOW-CANARY
    failover       fleet/failover-canary.sh               fleet/tests/failover-canary.test.sh       ci,preflight        FAILOVER-CANARY
    egress-key     fleet/checks/egress-key-canary.sh      fleet/tests/egress-key-canary.test.sh     ci,preflight        EGRESS-KEY-CANARY
    review         fleet/checks/reconcile-review-gate.sh  fleet/tests/review-dispensation-canary.test.sh  preflight     REVIEW-DISPENSATION-CANARY
    lifecycle      fleet/checks/gate-parity.sh            fleet/tests/ticket-lifecycle-canary.test.sh    preflight,ci  TICKET-LIFECYCLE-CANARY
    landing        fleet/checks/substrate-first-gate.sh   fleet/tests/substrate-first-gate.test.sh  ci                  LANDING-GATE-REGISTER
    balance        fleet/balance-canary.sh                fleet/tests/balance-canary.test.sh        preflight           BALANCE-CANARY
    config-ssot    fleet/checks/config-ssot-gate.sh       fleet/tests/config-ssot-gate.test.sh      preflight           CONFIG-SSOT-CANARY-REGISTER
    map-freshness  fleet/checks/graphify-freshness.sh     fleet/tests/test_graphify_freshness.sh    preflight,land      WIRE-GRAPHIFY-FRESHNESS
    reconciliation fleet/checks/reconcile-gate-wired.sh   fleet/tests/reconcile-gate-wired.test.sh  preflight,timer     UNIFIED-RECONCILIATION-GATE

  data/serving and map-freshness rows point at scripts/tests that already exist
  (fleet/flow-canary.sh, fleet/checks/graphify-freshness.sh + their tests) — the reconciliation
  leg should find those two GREEN (or map-freshness GAP-until-wired per WIRE-GRAPHIFY-FRESHNESS,
  which is correct: it is 0-callers orphaned today). reconciliation's own row points at
  fleet/checks/reconcile-gate-wired.sh which is designed-but-unmerged (RECONCILE-GATE-WIRED
  ticket, branch feat/reconcile-gate-wired already has the built detector, not yet landed) — GAP
  until RECONCILE-GATE-WIRED-LAND (this wave) merges it. landing's row points at
  fleet/checks/substrate-first-gate.sh + fleet/checks/gate-parity.sh, both of which already exist
  and already have fault-seed tests — that row can be GREEN immediately once LANDING-GATE-REGISTER
  (this wave) adds the reconciliation-coverage row confirmation. [[gates-must-actually-run]]
  [[no-rig-as-product-adopt-dont-handroll]]
accept: |
  - fleet/plane-canary-registry.tsv: git-tracked TSV, tab-separated, header line + the 10 rows
    verbatim above. Every row has all 5 columns non-empty (plane, canary_script, dogfood_test,
    wired_in, owner_ticket) — a row with an empty canary_script or dogfood_test column is itself
    a RED per the reconciliation leg below (never a silently-blank field).
  - fleet/plane-canary.sh: hand-rolled runner (~80 lines per design doc §4.2), mirroring
    fleet/checks/rig-ci-scope.sh's cmd_tests allowlist-iteration + fleet/flow-canary.sh's RED
    aggregation (both reused patterns, not reinvented). Sub-commands:
      - `run [--live|--hermetic]`: iterate every registry row; `--live` launches canary_script,
        `--hermetic` launches dogfood_test. Aggregate: ANY non-zero exit -> suite RED. Print a
        per-plane GREEN/RED table + a loud RED banner on failure (mirror flow-canary.sh's banner
        shape). Never pipe-mask exit codes (no `| tee` / `| grep` swallowing $?; capture then
        check, per KS `no_pipe_mask`).
      - `reconcile`: the reconciliation leg (below) — separate from `run`, callable standalone.
      - `suites` / `tests`: print the hermetic dogfood_test path list (one per line) so
        fleet/checks/rig-ci-scope.sh's CI_SUITES can consume it without a second hand-maintained
        list (PLANE-CANARY-WIRE, this wave, is the ticket that actually wires the CI_SUITES
        membership — this ticket only exposes the accessor).
  - Reconciliation leg (`fleet/plane-canary.sh reconcile`) is RED if ANY of:
      1. a plane in a hardcoded `PLANES=(...)` constant (the 10 names above, owned by this
         script) has NO row in fleet/plane-canary-registry.tsv -> "plane X declared, no canary".
      2. a registry row's canary_script or dogfood_test column names a file that does not exist
         on disk, OR the dogfood_test did not exit 0 on its last run -> "proofless canary" (a
         canary with no passing fault-seed dogfood is untrusted, never silently trusted).
      3. a row's wired_in value names a layer (ci / preflight / land / timer) that, when
         grep'd, does not actually invoke canary_script or dogfood_test -> "unwired canary"
         (the FINAL-E2E-REVIEW-phantom guard; delegates to the #178 UNIFIED-RECONCILIATION-GATE
         reconciler's declared-vs-fired join where it already exists — fail CLOSED: an
         unrecognized wired_in value is "does not fire", never "assume it fires").
    Exit non-zero on any RED; exit 0 clean only when every declared plane is wired+passing+proven.
  - fail-on-revert test (fleet/tests/plane-canary.test.sh): (a) seed a registry row with an empty
    dogfood_test column -> reconcile RED ("proofless"), fill it in -> GREEN; (b) seed a
    canary_script path that doesn't exist -> reconcile RED, create it -> GREEN; (c) seed a
    wired_in value naming a layer that does NOT actually invoke the script (e.g. grep the
    firing-layer source and confirm absence) -> RED ("unwired"), add the invocation -> GREEN;
    (d) `run` aggregation: one hermetic dogfood exits non-zero -> `run --hermetic` exits non-zero
    + prints the RED banner (never silently swallowed). Revert any of (a)/(b)/(c)/(d) -> the
    corresponding assertion goes RED again (proving the test isn't a tautology).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — this IS gate code (the
    reconciliation leg that other gates/canaries are judged against); manager gates, PR does NOT
    merge on the builder's self-report.
scope: |
  Registry + runner + reconciliation leg only. Does NOT wire the runner into CI/preflight/cadence
  (PLANE-CANARY-WIRE, depends_on this) and does NOT build any of the 7 gap canaries (FAILOVER-,
  EGRESS-KEY-, REVIEW-DISPENSATION-, TICKET-LIFECYCLE-, BALANCE-CANARY, CONFIG-SSOT-CANARY-REGISTER,
  LANDING-GATE-REGISTER — all depends_on this, all own only their own new files). Hand-roll per
  the design doc's adopt-eval: no off-the-shelf tool provides Charon's own declared-vs-wired
  missing-canary semantics (Checkly/Grafana-SM/Sensu/blackbox_exporter all REJECTED in Phase 1).
ds: |
  ## Dependencies & sequence
  Wave-1, no build prereq — first ticket in the plane-canary wave; every other plane-canary
  ticket in this mint (PLANE-CANARY-WIRE, FAILOVER-CANARY, EGRESS-KEY-CANARY,
  REVIEW-DISPENSATION-CANARY, TICKET-LIFECYCLE-CANARY, BALANCE-CANARY,
  CONFIG-SSOT-CANARY-REGISTER, LANDING-GATE-REGISTER, RETIRE-FINAL-E2E-REVIEW) depends_on THIS.
  Collision-avoidance by design: the 7 gap-canary tickets do NOT list
  fleet/plane-canary-registry.tsv in their own owns: (their rows are pre-seeded here) — this
  keeps them mutually parallelizable after this ticket lands, instead of forcing a 7-deep
  depends_on chain over one shared TSV.
