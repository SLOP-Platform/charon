repo: charon-private
tier: frontier
difficulty: 4
work_class: routing
branch: feat/fleet-demand-driven-routing
owns: fleet/tier-models.tsv, fleet/fleet-droid.sh, fleet/tier-requirements.tsv, fleet/tests/test_demand_routing.sh
depends_on: DELETE-STATIC-RANK
real-dep: DELETE-STATIC-RANK exposes the gateway's demand-driven switchboard selection; the fleet queries it — a true build/correctness prereq.
dep-kind: build
serial_justified: One cohesive switch from static chain -> live demand query across the resolver + its data; splitting orphans the contract.
note: |
  ADR-0016 FLEET HALF (companion to DELETE-STATIC-RANK gateway half). Replace the hand-typed
  tier-models.tsv failover CHAINS with a live DEMAND query: the fleet posts a NEED (tier capability
  bar + work_class + context) and the gateway's demand-driven switchboard returns the cheapest-capable-
  AVAILABLE model live (capability grades from real outcomes, TTL cost, funded/park availability). No
  static per-tier model list. tier-models.tsv -> tier-requirements.tsv (the BAR per tier: min capability
  grade, min context, perf floor), NOT a model chain. Operator vision: a smart/learning/flexible
  switchboard wired to a mechanized cost/perf/availability source. Bans static rank/chains.
accept: |
  - fleet-droid.sh resolves a tier's worker by QUERYING the switchboard (demand -> cheapest-capable-available),
    not by reading a static model chain. tier-models.tsv is REMOVED (or reduced to the capability bar).
  - A single-provider outage does NOT collapse a tier (the switchboard routes to the next cheapest-capable
    available provider live) — proven by a test that marks one provider unavailable and asserts a different
    provider answers.
  - No hand-typed rank/chain reintroduced; test asserts tier resolution has zero static model-order data.
