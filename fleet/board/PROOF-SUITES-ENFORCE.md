repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: ci-infra
branch: fix/proof-suites-enforce
depends_on:
owns: fleet/state/PROOF-SUITES-ENFORCE.md, docs/review-log/PROOF-SUITES-ENFORCE.md
serial_justified: |
  The inflow gate and the burn-down are one change, not two. Gating the inflow while 101 suites
  are already outside CI_SUITES means the gate reds on day one and gets switched off — the exact
  fate of the shellcheck advisory ramp. The gate and the first burn-down batch must land together.
substrate: N/A
substrate-novel: |
  The ratchet ALREADY EXISTS and is adopted as-is — fleet/checks/gate-integrity.sh:119 G5 reports
  this population against a floor. Nothing is built. The novel slice is the INFLOW assertion the
  ratchet lacks: it counts the backlog but does not stop it growing.
accept: |
  MEASURED LIVE 2026-08-02: G5 UNENFORCED-PROOF reports **101 suites declare themselves
  red-proofs but are NOT in CI_SUITES**, against a ratchet floor of 88 — and the count went UP
  from 91 earlier the same day, meaning new proof suites are still being written that will never
  run in CI.
  Each one asserts "this guard has been seen to fail" and is NEVER EXECUTED on a PR. That is not
  a backlog, it is 101 unverified claims of protection — the purest form of the built-but-inert
  class this fleet keeps rediscovering.
  Done contract:
  1. GATE THE INFLOW FIRST (approved shape D+B): a NEW suite declaring itself a red-proof and not
     registered in CI_SUITES must RED at authoring time. Without this the burn-down never
     converges — proven, the count rose 91 -> 101 during a single session of burning down.
  2. Then ratchet the 101 down in BATCHES, lowering GI_UNENFORCED_MAX with each batch so it can
     never rise again. Fold triage into each batch: a suite that cannot pass in CI gets fixed or
     explicitly deleted, never silently left out.
  3. PR #317 attempted this and was BOUNCED for recording the backlog instead of gating inflow —
     its own suite was in neither list, so it RAISED the backlog it claimed to bound. Read that
     bounce before starting; consider retargeting it as "add the inflow assertion to G5" rather
     than a parallel mechanism.
  4. Fail-on-revert on BOTH halves: removing the inflow assertion must red, and re-adding a
     burned-down suite to the unenforced set must red.

## Dependencies & Sequence

P0 and no inbound deps. This is the highest-leverage verification item on the board: until it
lands, every "red-proof" claim in the rig is unverified, so every other gate's green is worth
less than it appears. Runs concurrently with the landing lanes (disjoint owns).
Sequence inside is strict: inflow gate + first batch land TOGETHER (see serial_justified), then
batches until GI_UNENFORCED_MAX reaches 0.
