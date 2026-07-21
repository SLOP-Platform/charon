repo: charon
tier: strong
difficulty: 4
work_class: money-path
branch: feat/gw-bridge3-streaming-sse
parked: false
depends_on: GW-BRIDGE-1-DOWNGRADE-REHOST
dep-kind: build
note: |
  BRIDGE 3 of 4. Re-hosts streaming SSE byte-relay + the ADR-0016 exhaustion-envelope onto the
  litellm.Router path, additively, with its own fail-on-revert e2e. Preserves the streaming-head
  downgrade detection the forwarder does today (ADOPT-MAP KEEP-list, forwarder.py:837).
owns: src/charon/litellm_plane/streaming.py, tests/test_gw_bridge3_streaming.py
serial_justified: |
  One additive seam: an SSE relay module on the Router path. Own sibling module (streaming.py) so it
  does not re-edit BRIDGE-1's litellm_router.py; wires via BRIDGE-1's hook points.
accept: |
  RE-HOST streaming on the Router path (additive):
    - SSE byte-relay: a streaming completion is relayed chunk-for-chunk to the client, BYTE-COMPATIBLE
      with the current stdlib streaming path (OpenAI SSE contract preserved) [[gateway-client-agnostic]].
    - ADR-0016 EXHAUSTION-ENVELOPE preserved: when a chain leg is exhausted mid/pre-stream, the
      exhaustion envelope is emitted exactly as ADR-0016 specifies (not a silent hang / bare 500).
    - Streaming-head downgrade detection preserved (composes with GW-BRIDGE-1's D025 control on the
      first streamed head).

  ACCEPTANCE TESTS (observable, FAIL-ON-REVERT):
    (1) SSE BYTE-RELAY: a streamed fixture is relayed byte-identical to the pre-adopt SSE bytes.
        Revert -> RED.
    (2) EXHAUSTION ENVELOPE: exhausting all legs mid-stream emits the ADR-0016 envelope. Revert -> RED.
  Plus fail-on-revert e2e (Router -> streaming stub upstream -> client) + dogfood. Money path —
  adversarial review by default.
scope: |
  Preserve streaming SSE byte-relay and the ADR-0016 exhaustion-envelope on the litellm.Router path,
  additively, ahead of the live cutover. Third of the four additive bridges.
  [[gateway-client-agnostic]] [[adopt-substrate-build-only-novel-slice]] [[standing-blast-radius-lens]]
ds: |
  ## Dependencies & sequence
  depends_on: GW-BRIDGE-1-DOWNGRADE-REHOST — REAL BUILD PREREQ (dep-kind: build): streaming relay
    composes with BRIDGE-1's downgrade control on the streamed head and registers on the same Router
    hook points; disjoint owns (streaming.py) but a genuine build prereq.
  BLAST RADIUS: streaming clients — a relay regression corrupts or hangs streamed responses. Adversarial
    review. wave: gateway-adopt decomposition, bridge 3. repo: charon.
