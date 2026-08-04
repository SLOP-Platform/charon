# GATE-PARITY-TIMEOUT-FLAKE (#375)

## Decision
Inline the parallelizability check in `cmd_scan` instead of delegating per-ticket to `parallelizability-gate.sh check` (N+1 subprocess spawns → 1-process, two-pass). Keep `cmd_check` delegating for single-ticket fidelity. Exit code 8 for UNKNOWN (timeout/crash), matching AUTH-302-SILENT-FAILURE / EVAL-REGISTRY-DERIVE.

## Reasons
- Measured: 33s baseline, 4.1s after inline. Under validate_board's 30s budget with margin.
- The O(n²) was `is_decomposed()` walking all board files per ticket inside the per-ticket subprocess. Solved with one-pass parent→children map.
- Exit 8 is the canonical UNKNOWN code in this rig (sg-worker-liveness.sh, land-push.sh, reconcile-stale-claims.sh).
- `GATE_PARITY_TIMEOUT` default 120s (4x the new measured worst case of ~4s on full board) gives generous headroom. Timeout check is in both pass 1 and pass 2 per-iteration.

## Evidence
- `bash fleet/tests/gate-parity.test.sh` — 20/20 pass (zero regression)
- `bash fleet/tests/gate-parity-timeout.test.sh` — 28/28 pass
- `GATE_PARITY_TIMEOUT=1` → exit 8, output "UNKNOWN" (red-proofed)
- `GATE_PARITY_TIMEOUT=120` + splittable unjustified ticket → exit 1, "PARITY GAP" (anti-regression)
- `GATE_PARITY_TIMEOUT=120` + empty board → exit 0, "parity holds" (normal GREEN)

## Has gate-parity ever completed inside validate_board?
The audit handoff (AUDIT-LATENCY-BUDGETS, line 382) records `gate-parity.sh scan` at 13.10s rc=0. That is a successful completion. Whether that was INSIDE a validate_board run or standalone is not distinguished by that record. Given the 30s timeout and the measured 31s wall clock, a load-free run would succeed at 33s real time, be killed by validate_board's 30s timeout, and read as RED. The handoff note "gate-parity may effectively never complete during validate_board" is consistent with measured behavior.

## CI
Suite `gate-parity-timeout.test.sh` registered in `CI_SUITES` allowlist in `fleet/checks/rig-ci-scope.sh`.
