repo: charon
tier: strong
difficulty: 5
work_class: money-path
priority: 1
branch: feat/gw-cutover-live-wire
parked: false
depends_on: GW-BRIDGE-1-DOWNGRADE-REHOST, GW-BRIDGE-2-METERING-SPEND, GW-BRIDGE-3-STREAMING-SSE, GW-BRIDGE-4-PARK-COOLDOWN
dep-kind: build
note: |
  THE CUTOVER (highest blast-radius step of the gateway-adopt decomposition). Only claimable after ALL
  four additive bridges (GW-BRIDGE-1..4) have landed their re-hosted policy on the Router path. Replaces
  the hand-rolled money-path with litellm.Router serving LIVE traffic and DELETES ~650-750 LOC. This is
  the step that finally realizes the parked GATEWAY-LITELLM-ADOPT. Adversarial review by default,
  never-strand invariant required.
owns: src/charon/forwarder.py, src/charon/proxy_server.py, pyproject.toml, tests/test_gw_cutover_live_wire.py
serial_justified: |
  The live money-path is ONE seam at cutover: forwarder.forward_with_failover + the stdlib http.server
  request loop are replaced in a single coherent swap so the path is never half-migrated. The four
  bridges pre-hosted the policy additively; this ticket flips the live route and deletes the dead
  hand-roll in one pass. tests/test_gw_cutover_live_wire.py is the fail-on-revert proof for that seam.
accept: |
  CUT OVER the live money-path to litellm.Router (this deletes code — it is not additive):
    - Replace forwarder.forward_with_failover + the stdlib http.server data-plane (proxy_server.py:20/
      207/454) so litellm.Router serves LIVE traffic, with all four bridges' re-hosted policy active.
    - DELETE ~650-750 LOC of hand-rolled money-path (the adopt is real, not a wrapper beside dead code).
    - PROMOTE litellm from the optional `router` extra to CORE `dependencies` in pyproject.toml
      (accepting the ~218MB + native deps ADR-0017 names; the stdlib-gate rationale was already removed).

  ACCEPTANCE TESTS — ALL of the original GATEWAY-LITELLM-ADOPT accept set, now on the LIVE path
  (observable, FAIL-ON-REVERT, ALL go RED on revert):
    (1) OPENAI-CONTRACT BYTE-COMPAT: a fixture OpenAI request through the live Router path returns the
        same external response shape/bytes as the pre-adopt path (assert the wire contract; assert the
        Router IS the code path taken).
    (2) FAILOVER PRESERVED: first provider errors -> fails over to the next chain leg via Router
        cooldown/allowed_fails. Revert -> RED.
    (3) MECHANICAL ORDERING PRESERVED: the cheapest-capable chain order (with the funding-class /
        park pre-order from GW-BRIDGE-4) is honored. Revert -> RED.
    (4) LOC-DELETE GUARD: the hand-rolled money-path modules shrank by the promised ~650-750 LOC
        (guard against wrapper-added-but-hand-roll-kept). Revert -> RED.
    (5) NEVER-ANTHROPIC GUARD SURVIVES: the resolved model set contains no Anthropic leg for SG work.
        Revert -> RED [[sg-never-anthropic]].
    (6) D025 / METERING / STREAMING / PARK still hold end-to-end on the LIVE path (the four bridges'
        proofs re-run against the live route, not just the shadow path).
  Full e2e + dogfood on the LIVE gateway. GREEN-IS-NOT-PROOF: "Router constructed" proves nothing;
  tests (1)+(4) are the minimum bar. Router constructed ONCE (not per-request); provider keys never
  leave the custody path [[security-is-a-ratchet-gate]]. HIGHEST BLAST — adversarial review by default.
scope: |
  Replace forwarder.forward_with_failover + the stdlib http.server data-plane with litellm.Router serving
  LIVE traffic, delete ~650-750 LOC of hand-rolled money-path, and promote litellm to core dependencies,
  preserving the full original GATEWAY-LITELLM-ADOPT accept set (OpenAI byte-compat, failover, mechanical
  ordering, LOC-delete guard, never-Anthropic) plus the four bridges' invariants on the live path. The
  final, highest-blast step of the gateway-adopt decomposition; it realizes the parked GATEWAY-LITELLM-ADOPT.
  [[charon-strategy-outcome-graded-gateway]] [[adopt-substrate-build-only-novel-slice]]
  [[gateway-client-agnostic]] [[sg-never-anthropic]] [[security-is-a-ratchet-gate]]
  [[standing-blast-radius-lens]] [[gates-must-actually-run]]
ds: |
  ## Dependencies & sequence
  depends_on: GW-BRIDGE-1..4 — ALL FOUR are REAL BUILD PREREQS (dep-kind: build). The cutover flips the
    live route onto the Router; doing so before each bridge has re-hosted its policy (downgrade, metering,
    streaming, park/cooldown) would ship a half-migrated / policy-missing money-path — the exact hazard
    the decomposition exists to prevent. Disjoint owns (forwarder.py/proxy_server.py/pyproject.toml vs
    the bridges' litellm_plane/*), so the deps are genuine build prereqs, not merge-order.
  reads-only (no owns claim, coordinated): src/charon/gateway.py — the external wiring that swaps the
    live route to the Router is edited in coordination with the live gateway.py owners
    (GATEWAY-NONTOKEN-METERING / METER-KWH-USD-FIX), not owned here, to avoid an owns-collision.
  BLAST RADIUS: MAXIMUM — every gateway request flows the live money-path this ticket rewires and the
    LOC it deletes. A regression degrades EVERY request. Adversarial review by default
    [[adversarial-review-default-for-droid-prs]] + never-strand + the full original accept set on the
    live path. wave: gateway-adopt decomposition, CUTOVER (last). repo: charon.
