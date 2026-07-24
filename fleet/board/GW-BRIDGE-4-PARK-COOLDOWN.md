repo: charon
tier: frontier
difficulty: 4
work_class: money-path
priority: 1
branch: feat/gw-bridge4-park-cooldown
parked: false
depends_on: GW-BRIDGE-1-DOWNGRADE-REHOST
dep-kind: build
bounce_rebrief: |
  ⛔ BOUNCED (2026-07-23, adversarial review of PR #188). The cooldown union read `router._failed_calls`
  — an attribute that DOES NOT EXIST in the installed litellm → the union was a DEAD NO-OP in production
  (silently degraded to park-only), and the fail-on-revert test only asserted against a fabricated mock,
  green-lighting a feature that never fires against a real Router. FIX: read the PUBLIC
  `router.cooldown_cache` (CooldownCache) / `_get_cooldown_deployments`, map model_id→provider. The test
  MUST exercise a REAL litellm Router's cooldown state (not a hand-rolled mock) and prove a really-cooled
  provider is actually excluded. Re-verify the union fires in prod, not just in the fixture.
note: |
  BRIDGE 4 of 4. Unifies Charon's park state with litellm.Router's native model-cooldown so the two
  do not disagree, preserving the sole-leg guard. Additive, own fail-on-revert e2e. Charon's park (funding
  drain / free-tier window) feeds the Router pre-order; the Router's cooldown/allowed_fails handle
  transient failure — this bridge makes them ONE coherent exclusion set.
owns: src/charon/litellm_plane/park_cooldown.py, tests/test_gw_bridge4_park_cooldown.py
serial_justified: |
  One additive seam: the park<->cooldown unification module on the Router path. Own sibling module so it
  does not re-edit BRIDGE-1's litellm_router.py; wires via BRIDGE-1's hook points.
accept: |
  UNIFY park <-> litellm.Router-cooldown (additive):
    - A Charon-PARKED provider (funding-drained / outside free-tier window) is excluded from the Router's
      selectable model_list — parked == not-selected, the same way cooldown removes a leg.
    - A Router cooldown (transient allowed_fails breach) and a Charon park compose into ONE exclusion set
      (no leg is "cooled down" yet still offered, and no parked leg leaks back in on cooldown expiry).
    - SOLE-LEG GUARD preserved: the last remaining viable leg is NOT parked/cooled into a
      no-workers-left state — never strand while >=1 viable leg exists
      [[charon-north-star-engine-mechanism]] [[charon-drain-then-park-provider-class]].

  ACCEPTANCE TESTS (observable, FAIL-ON-REVERT):
    (1) PARKED EXCLUDED: a parked provider is absent from the Router's resolved model_list. Revert -> RED.
    (2) SOLE-LEG GUARD: with one viable leg left, park/cooldown does NOT remove it — request still routes.
        Revert the guard -> RED.
    (3) RE-ARM: a provider re-armed on top-up returns to the selectable set. Revert -> RED.
  Plus fail-on-revert e2e + dogfood. Money path — adversarial review by default.
scope: |
  Unify Charon park state with litellm.Router cooldown into one coherent exclusion set, preserving the
  sole-leg never-strand guard, additively, ahead of the live cutover. Fourth of the four additive bridges.
  [[charon-drain-then-park-provider-class]] [[charon-north-star-engine-mechanism]]
  [[adopt-substrate-build-only-novel-slice]] [[standing-blast-radius-lens]]
ds: |
  ## Dependencies & sequence
  depends_on: GW-BRIDGE-1-DOWNGRADE-REHOST — REAL BUILD PREREQ (dep-kind: build): the park<->cooldown
    unification registers on the Router hook/pre-order points BRIDGE-1 establishes; disjoint owns
    (park_cooldown.py) but a genuine build prereq.
  BLAST RADIUS: routing availability — a bad unification can strand (no workers) or leak a drained
    provider. Sole-leg guard + never-strand + adversarial review. wave: gateway-adopt decomposition,
    bridge 4. repo: charon.
