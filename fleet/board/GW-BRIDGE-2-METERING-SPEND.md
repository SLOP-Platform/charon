repo: charon
tier: strong
difficulty: 4
work_class: money-path
branch: feat/gw-bridge2-metering-spend
parked: false
depends_on: GW-BRIDGE-1-DOWNGRADE-REHOST
dep-kind: build
adr_gate: ADR-0020-litellm-metering-bridge (Proposed/Pending — DO NOT CLAIM until the ADR is Accepted;
  it changes the money-accounting SOURCE OF RECORD). The ADR is a PRODUCT doc, not a board ticket, so it
  cannot sit in the machine depends_on (validate_board would false-RED an unresolvable id); the gate is
  enforced here + at claim time by the manager.
note: |
  BRIDGE 2 of 4. GATED behind ADR-0020-litellm-metering-bridge (Proposed/Pending) because routing cost
  accounting through litellm callbacks changes the money-accounting SOURCE OF RECORD. Bridges the litellm
  cost callback to the existing BalanceTracker without regressing non-token/energy metering or
  drain-then-park. Do NOT claim before ADR-0020 is Accepted AND GW-BRIDGE-1 lands.
owns: src/charon/litellm_plane/metering.py, tests/test_gw_bridge2_metering.py
serial_justified: |
  One additive seam: a single litellm cost-callback module that feeds BalanceTracker on the Router path.
  Kept in its own sibling module (metering.py) so it does not re-edit BRIDGE-1's litellm_router.py; it
  registers via the hook points BRIDGE-1 establishes.
accept: |
  BRIDGE the litellm cost callback -> BalanceTracker on the Router path (ADOPT-MAP: cost metering =
  litellm cost callback + already-vendored price JSON, ADR-0016):
    - The Router's completion cost callback advances the SAME BalanceTracker the hand-rolled
      forwarder/proxy.observe path advances — spend for drain-then-park moves forward per request.
    - drain-then-park + funding-class ordering still fires off the advanced spend (a drained provider
      parks; re-arms on top-up) [[charon-drain-then-park-provider-class]].
    - NON-TOKEN / ENERGY metering is PRESERVED (providers billed by energy/other units, not tokens, are
      still metered correctly — not silently zeroed by the token-cost callback) [[charon-meter-inert]].
    - D025 no-double-bill invariant HOLDS end-to-end with BRIDGE-1 (a downgrade served once is billed
      once; the callback does not double-count).

  ACCEPTANCE TESTS (observable, FAIL-ON-REVERT):
    (1) SPEND ADVANCES: N Router completions advance BalanceTracker spend by the vendored-price sum;
        a provider crossing its drain threshold PARKS. Revert the callback wire -> spend frozen -> RED.
    (2) ENERGY METERING PRESERVED: an energy-billed provider is metered by its energy rule, not zeroed.
        Revert -> RED.
    (3) NO DOUBLE-BILL WITH BRIDGE-1: a served downgrade is billed exactly once through the callback.
  Plus fail-on-revert e2e + dogfood. GREEN-IS-NOT-PROOF: assert the ledger DELTA, not that the callback
  fired. Money path — adversarial review by default. GATED on ADR-0020 (source-of-record change).
scope: |
  Wire the litellm cost callback to the existing BalanceTracker on the Router path so drain-then-park
  spend advances, preserving non-token/energy metering and the D025 no-double-bill invariant. GATED on
  ADR-0020-litellm-metering-bridge because it moves the money-accounting source of record.
  [[charon-meter-inert]] [[charon-drain-then-park-provider-class]] [[security-is-a-ratchet-gate]]
  [[adopt-substrate-build-only-novel-slice]] [[standing-blast-radius-lens]]
ds: |
  ## Dependencies & sequence
  depends_on: GW-BRIDGE-1-DOWNGRADE-REHOST — REAL BUILD PREREQ (dep-kind: build): the metering callback
    registers on the Router hook points BRIDGE-1 establishes; disjoint owns (metering.py vs
    litellm_router.py) but a genuine build/correctness prereq, not merge-order.
  ADR GATE: additionally gated on ADR-0020-litellm-metering-bridge being Accepted (source-of-record
    change) — see adr_gate field. Manager enforces at claim time.
  BLAST RADIUS: money-accounting — a metering regression mis-bills or mis-parks providers. Adversarial
    review + never-strand. wave: gateway-adopt decomposition, bridge 2. repo: charon.
