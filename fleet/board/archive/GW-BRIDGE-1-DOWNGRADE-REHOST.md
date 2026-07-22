repo: charon
tier: strong
difficulty: 4
work_class: money-path
branch: feat/gw-bridge1-downgrade-rehost
parked: false
note: |
  BRIDGE 1 of 4 (+ GW-CUTOVER-LIVE-WIRE) decomposing the DEFERRED live wire-in of the now-parked
  GATEWAY-LITELLM-ADOPT. The opt-in first slice already LANDED (product master 7e16e4a:
  src/charon/litellm_plane/). This bridge re-hosts the SETTLED-decision D025 silent-downgrade
  double-bill fix ON the litellm.Router path — additive, no LOC deletion, its own fail-on-revert e2e.
  IN-FLIGHT: a build for this bridge is underway THIS session — coordinate before re-claiming.
depends_on:
owns: src/charon/litellm_plane/litellm_router.py, tests/test_gw_bridge1_downgrade.py
serial_justified: |
  One additive seam: the SR-1/SR-2 silent-downgrade comparison must be REUSED (one canonical path,
  not a second copy) and re-hosted onto the Router response path. litellm_router.py is the single
  Router wrapper the landed slice created; its fail-on-revert test is the proof.
accept: |
  RE-HOST (additive, on the Router path) the D025 no-double-bill / silent-downgrade control:
    - SR-1/SR-2 downgrade DETECTION + gating runs on the litellm.Router response, REUSING the existing
      forwarder SR-1/SR-2 comparison (ADOPT-MAP KEEP-list, forwarder.py:788/:878) — ONE canonical
      comparison path, never a forked second copy.
    - A genuine downgrade is SERVED-WITH `X-Charon-Downgrade` (per D025), and an already-billed 200 is
      NEVER re-billed/discarded-and-rebilled (D025 no-double-bill invariant; model-id equality stays
      namespace/segment-tolerant, final-`/`-segment compare).
    - ADDITIVE ONLY: forwarder.py and proxy_server.py are UNTOUCHED; ZERO LOC deleted this bridge (the
      LOC-delete is deferred to GW-CUTOVER-LIVE-WIRE). Default-OFF path stays byte-identical.

  ACCEPTANCE TESTS (observable, FAIL-ON-REVERT — go RED when the re-host is reverted):
    (1) DOWNGRADE SERVED, NOT RE-BILLED: a Router response whose resolved model id differs (real
        downgrade) is served with `X-Charon-Downgrade` and billed EXACTLY ONCE. Revert -> RED.
    (2) SEGMENT-TOLERANT EQUALITY: a namespace/version/date-suffix-only id difference is NOT treated as
        a downgrade (final-`/`-segment compare) — no spurious header, no re-bill. Revert -> RED.
    (3) ONE CANONICAL PATH: assert the Router path calls the SAME SR-1/SR-2 comparison the forwarder
        uses (no duplicated heuristic). Revert to a forked copy -> RED.
    (4) ADDITIVE GUARD: forwarder.py + proxy_server.py byte-unchanged; no net LOC deletion this bridge.
  Plus a fail-on-revert e2e (real gateway config -> Router -> stub upstream that downgrades) and a
  runnable dogfood capture. GREEN-IS-NOT-PROOF: "downgrade-detector constructed" proves nothing —
  tests (1)+(4) are the bar. Money path — adversarial review by default; provider-key custody must not
  regress [[security-is-a-ratchet-gate]].
scope: |
  Re-host the D025 silent-downgrade double-bill control onto the litellm.Router response path, additively
  and reusing the single canonical SR-1/SR-2 comparison, so the Router path preserves the no-double-bill
  invariant BEFORE any live cutover. First of the four additive bridges that make GW-CUTOVER-LIVE-WIRE
  safe. [[charon-silent-downgrade-leak]] [[security-is-a-ratchet-gate]] [[adopt-substrate-build-only-novel-slice]]
  [[gateway-client-agnostic]] [[standing-blast-radius-lens]]
ds: |
  ## Dependencies & sequence
  depends_on: NONE — first bridge; builds directly on the landed litellm_plane/ slice (7e16e4a).
  BLAST RADIUS: touches the Router wrapper only, additive, default-OFF — live money-path byte-identical
    until GW-CUTOVER-LIVE-WIRE. GW-BRIDGE-2/3/4 all hard-depend on this (they re-host their policy onto
    the hook points this bridge establishes). wave: gateway-adopt decomposition, bridge 1. repo: charon.
