tier: frontier
difficulty: 3
work_class: ci-infra
branch: audit/final-e2e-review
repo: charon-private
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
note: operator-requested final E2E adversarial review; run when the whole chain is green + dogfooded, before full fleet resume.
