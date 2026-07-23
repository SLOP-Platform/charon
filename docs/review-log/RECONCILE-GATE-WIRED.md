# RECONCILE-GATE-WIRED — review note

**Ticket:** RECONCILE-GATE-WIRED (§1.3 of UNIFIED-RECONCILIATION-GATE-DESIGN.md, PR #178)
**Class:** rig-meta — built-but-inert meta-gate
**drift-primitive:** graph-reachability (KS29 leg)
**Build:** 2026-07-23

## What was built

1. **`fleet/checks/reconcile-gate-wired.sh`** — standalone bash+Python check that:
   - Collects **declared checks** from: `fleet/checks/*.sh + *.py`, `tools/check_*.py + *.sh` (cross-repo), `RULE-REGISTRY.tsv` mechanized rows, `EVAL-REGISTRY.md` ADOPT rows with check paths
   - Collects **fired checks** by substring-matching declared basenames across firing-layer files (preflight.sh, land.sh, validate_board.sh, hooks/, foreman-cadence.sh, product-side gate_runner.py + workflows/*.yml)
   - Computes **R-G** (declared but not fired → built-but-inert RED) and **R-H** (fired but not declared → unregistered RED)
   - Reports **UNVERIFIED** (fail-closed) when product repo checkout is absent
   - Reuses the rule-coverage.sh pattern (bash+embedded Python; env-var test seams)

2. **`fleet/tests/reconcile-gate-wired.test.sh`** — fail-on-revert test with 4 cases:
   - (a) declared-but-unwired → R-G RED
   - (b) wire into firing layer → rig-side GREEN
   - (c) unregistered checks/ invocation → R-H RED
   - (d) product repo absent → UNVERIFIED (fail-closed)

## WLS-7 validation

The stass-allie WLS-7 review (2026-07-23) validated the implement-as-pattern posture:
"no external tool reconciles Charon's own state; K8s/Terraform desired-vs-observed is the pattern."
This check implements that validated pattern — graph-reachability over declared-vs-fired nodes.

## Known R-G (pre-existing, not this ticket's responsibility)

The gate currently reports ~19 R-G items from the live fleet. These are pre-existing
built-but-inert checks that were known before this gate shipped. They will be resolved by
subsequent `RECONCILE-WIRING` tickets (wiring into preflight.sh:841, land.sh, etc.).
This ticket only builds the detector; it does not auto-wire.

## Accept verification

- [x] Standalone `bash fleet/checks/reconcile-gate-wired.sh` runs (exit 1 = RED, reflecting pre-existing unwired checks)
- [x] Isolated via RCW_* env vars for test fixtures
- [x] Product-repo-absent → UNVERIFIED, fail-closed (exit non-zero)
- [x] fail-on-revert test passes (8/8)
- [x] All owned files in scope: `fleet/checks/reconcile-gate-wired.sh`, `fleet/tests/reconcile-gate-wired.test.sh`
- [x] Reuses rule-coverage.sh pattern (embedded Python, env-var test seams)
