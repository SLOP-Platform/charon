repo: charon
tier: strong
difficulty: 4
work_class: money-path
priority: 1
branch: feat/gw-bridge2-metering-spend
parked: false
depends_on: GW-BRIDGE-1-DOWNGRADE-REHOST
dep-kind: build
adr_gate: ADR-0020-litellm-metering-bridge ACCEPTED — VERIFY-ONLY (operator 2026-07-23). UNGATED/CLAIMABLE.
  The callback is adopted as a CROSS-CHECK ONLY; Charon's own cost computation REMAINS the source of record.
  Only GW-BRIDGE-1 remains as a real build prereq.
note: |
  BRIDGE 2 of 4. ADR-0020 ACCEPTED verify-only — the litellm cost callback runs ALONGSIDE Charon's
  authoritative accounting as a cross-check, NOT as the money source of record. It must surface divergence
  (callback cost vs Charon cost) without ever overriding or corrupting Charon's own spend/drain-then-park.
  Claimable once GW-BRIDGE-1 lands.
owns: src/charon/litellm_plane/metering.py, tests/test_gw_bridge2_metering.py
serial_justified: |
  One additive seam: a single litellm cost-callback module that feeds BalanceTracker on the Router path.
  Kept in its own sibling module (metering.py) so it does not re-edit BRIDGE-1's litellm_router.py; it
  registers via the hook points BRIDGE-1 establishes.
accept: |
  Wire the litellm cost callback as a VERIFY-ONLY CROSS-CHECK on the Router path (ADR-0020 Accepted
  verify-only). Charon's own per-request cost computation REMAINS the source of record; the callback runs
  alongside and its ONLY job is to surface divergence — it must NEVER become the money authority:
    - Charon's existing cost path advances BalanceTracker EXACTLY as today (authority unchanged); the
      litellm callback computes its own per-request cost alongside and is compared to Charon's.
    - DIVERGENCE (callback cost != Charon cost beyond tolerance) is emitted as a log/alert; it never
      overrides, corrects, freezes, or reorders Charon's authoritative spend / drain-then-park.
    - NON-TOKEN / ENERGY metering untouched — Charon's rule stays authoritative; the $/token callback does
      not zero it [[charon-meter-inert]].
    - drain-then-park + funding-class ordering fire off Charon's authoritative spend, unchanged
      [[charon-drain-then-park-provider-class]]; D025 no-double-bill unchanged (Charon still bills once).

  ACCEPTANCE TESTS (observable, FAIL-ON-REVERT):
    (1) AUTHORITY UNCHANGED: BalanceTracker spend + drain-then-park outcomes are byte-for-byte identical
        with the callback wired vs not — the callback changes NO billing/parking outcome. Revert the wire
        -> outcomes identical, only the divergence signal disappears -> proves non-authoritative.
    (2) DIVERGENCE SURFACED: a request where callback cost != Charon cost emits a divergence alert/log.
        Revert -> no alert -> RED (the defense-in-depth value is real, not vacuous).
    (3) NO CORRUPTION: an energy-billed provider + a served downgrade are metered/billed by Charon exactly
        as without the bridge; the callback never zeroes or double-counts them.
  Plus fail-on-revert e2e + dogfood. GREEN-IS-NOT-PROOF: assert Charon's authoritative ledger is UNCHANGED
  and the divergence signal fires. Money path — adversarial review by default.
scope: |
  Wire the litellm cost callback as a VERIFY-ONLY cross-check on the Router path — Charon's own cost stays
  the source of record advancing BalanceTracker + drain-then-park; the callback only surfaces divergence,
  never overrides. Per ADR-0020 (Accepted verify-only); promotion to callback-as-authority is a future ADR.
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
