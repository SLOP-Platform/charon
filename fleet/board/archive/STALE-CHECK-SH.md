tier: strong
difficulty: 2
work_class: ci-infra
branch: feat/stale-check-sh
repo: charon-private
parent: LAUNCH-PLAN-GATE
depends_on:
owns: /home/stack/charon-private/fleet/stale-check.sh, /home/stack/charon-private/fleet/tests/stale-check.test.sh
note: |
  Manually decomposed sub-ticket of LAUNCH-PLAN-GATE (fleet/decompose.sh's plan_decomposition
  engine was unavailable 2026-07-15 — whole model pool 429/exhausted). Disjointness verified by
  hand: this ticket owns only stale-check.sh + a NEW dedicated test file (split off the parent's
  single combined test file so it doesn't share a test-file surface with LAUNCH-PLAN-SH, the
  sibling); LAUNCH-PLAN-SH owns the unrelated launch-plan.sh — zero file overlap between the two.
accept: |
  fleet/stale-check.sh: read the session-bridge board (or status.sh) + state/loop-guard/* and FLAG any
  live session past a stall threshold (default 900s no-progress) or loop-guard-quarantined, one line
  each; exit nonzero if any stale so preflight/the manager surfaces it. (Do NOT edit preflight.sh — it
  is owned elsewhere; make stale-check.sh standalone and note in output that preflight should call it.)
  FAIL-ON-REVERT (fleet/tests/stale-check.test.sh): stale-check flags a fixture session past the
  threshold and exits nonzero (revert the check -> it stays silent/exits 0 -> test fails). Hermetic
  (session-bridge/board fixtures; no network).
scope: |
  Manually-decomposed single-domain sub-ticket of LAUNCH-PLAN-GATE (fleet/decompose.sh).
