repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: rig-meta
branch: feat/ks29-discovery-leg
owns: fleet/checks/registry-discovery.sh, fleet/state/component-registry.tsv, fleet/tests/registry-discovery.test.sh
depends_on:
serial_justified: the registry schema + the discovery gate + its fail-closed test are one primitive — a
  registry with no discovery gate is inert, a gate with no registry has nothing to check.
source: SG-ISSUE-CONTROL-PLANE slice 2 (DISCOVER leg) — the HIGHEST-RISK new build: the design flags that
  the KS29 discovery leg is DESIGNED-not-BUILT, so "un-registered component" detection is FAKE-GREEN until
  it ships. This closes that hole.
note: |
  The DISCOVER leg's registry PRIMITIVE (KS29): declare a component registry (schema + scope) and get, for
  free, a CONFORMANCE gate (entries valid) + a DISCOVERY gate (FAIL-CLOSED on an unknown component that
  SHOULD be registered) + a drift check. Uses graphify's code-relations graph (9786 links) to auto-detect a
  NEW load-bearing subsystem/plane/entrypoint and REFUSE it until it has a canary/detector or an explicit
  registered exemption. This is what makes the control plane SELF-EXTENDING (new planes auto-roll in) and
  is the anti-fake-green backbone for the whole DISCOVER leg. Adopt the k8s-controller reconcile shape.
accept: |
  - fleet/checks/registry-discovery.sh: given the component-registry + graphify's graph, FAILS CLOSED on a
    load-bearing component that is neither registered nor explicitly exempted (no silent gap).
  - conformance leg (registry entries valid) + drift leg (registered component vanished / went stale).
  - graphify integration: a genuinely new subsystem in the code graph is flagged as an un-registered plane.
  - e2e DOGFOOD: add a new fake subsystem to the graph -> discovery gate goes RED naming it; register it ->
    GREEN. Remove a registered component's canary -> drift RED.
  - fail-on-revert + ADVERSARIAL REVIEW (reviewer != builder) — this is the who-tests-the-tester primitive;
    a fake-green here silently blinds the whole control plane.
scope: |
  The KS29 registry primitive (conformance + discovery + drift) for the component/plane registry + graphify
  wiring. Individual components are DATA rows. Absorbs roadmap KS29.
ds: |
  ## Dependencies & sequence
  P0, slice 2 (highest-risk; do after ISSUE-BOARD-SURFACE so surfacing exists to show its findings).
  Composes graphify (relations) + the KS29 primitive.
