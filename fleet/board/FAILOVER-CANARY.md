repo: charon-private
tier: strong
difficulty: 4
priority: 0
work_class: routing
branch: feat/failover-canary
owns: fleet/failover-canary.sh, fleet/tests/failover-canary.test.sh
real-dep: PLANE-CANARY-REGISTRY seeds this plane's registry row at the exact
  fleet/failover-canary.sh / fleet/tests/failover-canary.test.sh paths this ticket owns, and its
  reconciliation leg is what this canary must satisfy to register as GREEN — a genuine build
  prereq, not a merge-order preference.
depends_on: PLANE-CANARY-REGISTRY
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 3 "P4 routing-brain/failover" spec +
  "PROPOSED TICKET LIST" row 3.
work_class_note: routing — this proves the routing-brain's failover-cascade behavior (an
  observable gateway effect), not a rig-meta gate script.
note: |
  GAP plane (design doc Phase 3, #4): no wired+passing failover canary exists today. Front the
  head-tier provider with Toxiproxy (ADOPT per Phase 1 tool-eval — the one plane genuinely
  needing real fault injection beyond a scenario-JSON rewrite; every SaaS/cloud synthetic monitor
  and reachability-only probe was REJECTED for asserting reachability, not Charon's own
  observable effects, per flow-canary's design-of-record anti-pattern). Mirrors
  fleet/flow-canary.sh's shape (run_tier-style stage function, observable-side-effect assertions,
  LOUD RED contract) — reuse that pattern, do not reinvent the harness shell.
  [[no-stiff-single-provider-tools]] [[sg-never-anthropic]]
accept: |
  - fleet/failover-canary.sh: (a) baseline — real request against the fronted head-tier provider
    -> assert normal leg serves (X-Charon-Provider == head) + meter delta (reuse the
    flow-canary.sh STAGE 2 pattern, do not reimplement the meter read); (b) cut the head provider
    via Toxiproxy (`timeout` or `reset_peer` toxic) -> assert the gateway returns 200 served by
    the NEXT leg, `X-Charon-Failover-Reasons` names the head as failed, and NO parked/drained leg
    was attempted (reuse flow-canary.sh STAGE 3's #188 park-exclusion assertion); (c) restore the
    toxic -> assert GREEN again. Fault seeds: head-429, head-timeout, head-500, all-legs-down (->
    assert a clean loud error to the client, never a hang or a raw 5xx passthrough).
  - Hermetic: Toxiproxy + a stdlib fake upstream (mirror fleet/tests/flow-canary.test.sh's
    `http.server` fake-gateway pattern) — no live network required for the dogfood_test.
  - fail-on-revert test (fleet/tests/failover-canary.test.sh): seed each of the four fault
    classes above -> assert RED (wrong leg served / reasons header missing or wrong / a
    parked leg attempted / a hang instead of a loud error); revert each seed -> GREEN. A
    revert-proof re-run (mirror flow-canary.test.sh:300-305) confirms green-is-not-a-fluke.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — this canary is the acceptance
    proof for the routing-brain's failover cascade (a money/availability-critical path: a wrong
    verdict here means silent client-facing 5xx or double-billing on failover); manager gates, PR
    does NOT merge on the builder's self-report.
scope: |
  Failover-cascade canary only. Does not touch GATEWAY-GRADE-ORDER-MVP / WIRE-BRAIN-INTO-GATEWAY
  (the parked grade-order overlay itself) — this ticket asserts failover behavior against
  whatever routing-brain code is live on master, it does not build routing logic.
ds: |
  ## Dependencies & sequence
  depends_on PLANE-CANARY-REGISTRY only (the registry pre-seeds this plane's row at the exact
  paths owned here). Disjoint owns from every other gap-canary ticket in this wave (EGRESS-KEY-,
  REVIEW-DISPENSATION-, TICKET-LIFECYCLE-, BALANCE-CANARY, CONFIG-SSOT-CANARY-REGISTER,
  LANDING-GATE-REGISTER) — parallelizable with all of them.
