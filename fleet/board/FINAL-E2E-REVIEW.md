tier: frontier
priority: 2
difficulty: 3
work_class: ci-infra
branch: audit/final-e2e-review
repo: charon-private
parked: true
depends_on: DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT
real-dep: DECOMPOSE-DEFAULT-GATE — the E2E review exercises the auto-decompose intake path; cannot review it until it is live + green.
real-dep: MODEL-PREFLIGHT — the E2E review exercises the model-screening path; cannot review it until it is built + dogfooded. (DETENTION-REDLINE already landed; covered by the review, no board dep.)
owns: fleet/state/FINAL-E2E-REVIEW.md
accept: |
  CAPSTONE adversarial review (operator directive 2026-07-13): once ALL pieces are assembled and everything is
  GREEN + DOGFOODED, do a FINAL END-TO-END adversarial review of the ENTIRE work process:
    intake -> AUTO-DECOMPOSE (DECOMPOSE-DEFAULT-GATE) -> disjoint sub-tickets -> assign -> DETENTION filter
    (trusted models only) -> build -> PREFLIGHT-screened models -> adversarial review -> land -> handoff.
  Not a rubber-stamp — TRY TO BREAK IT. Look for: issues, gaps, seams that fail-open, un-dogfooded claims,
  green-but-inert wiring, blast-radius (what else this touches), and any step where a fabrication/false-success
  could still slip through the assembled pipeline. Verify the E2E acceptance actually EXERCISES real flow
  (production==test path), not proxies. Produce a findings doc + a go/no-go for returning to full fleet mode.
scope: Final process-integrity gate before resuming fleet mode on Charon Gateway. [[green-is-not-proof]] [[standing-blast-radius-lens]] [[gates-must-actually-run]]
ds: |
  depends_on: the full Model-Trust + decomposer chain green+dogfooded. Runs LAST. Adversarial by default; frontier model.
note: |
  SUPERSEDED 2026-07-31 by RETIRE-FINAL-E2E-REVIEW (chore/retire-final-e2e-review). PARKED — do not claim.

  Why this ticket is a phantom and the plane-canary suite is the real replacement: a single one-shot
  capstone review, even a thorough one, can only prove the pipeline worked ONCE, at the moment of
  review. It cannot detect regressions in the assembled pipeline between reviews, and it cannot
  catch the silent-failure anti-patterns (green-but-inert wiring, fabrications slipping through)
  that reappear later. The plane-canary suite (registry PLANE-CANARY-REGISTRY, wiring
  PLANE-CANARY-WIRE, plus the per-plane canary tickets those two reference and orchestrate) is the
  durable replacement: it runs on every PR AND on a cadence, so a green `bash fleet/plane-canary.sh
  run --live && fleet/plane-canary.sh reconcile` IS the comprehensive, always-on end-to-end proof
  that this one-shot capstone review only pretended to be — proven continuously rather than
  asserted once. See fleet/state/DESIGN-PLANE-CANARY-SUITE.md EXEC SUMMARY point 4 + PROPOSED
  TICKET LIST row 10.

  depends_on (DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT) is preserved as historical evidence —
  un-touched, their own status is out of scope for the retirement. Do not delete this file; git
  history is the audit trail per EVAL-REGISTRY's append-only convention. If the operator ever
  wants a one-shot capstone back, un-park this and reassess against the then-current plane-canary
  state — they may have moved past each other by then.
