repo: charon-private
tier: strong
priority: 1
difficulty: 3
work_class: ci-infra
branch: fix/preflight-late-leg-starvation
depends_on:
owns: fleet/state/PREFLIGHT-LATE-LEG-STARVATION.md, docs/review-log/PREFLIGHT-LATE-LEG-STARVATION.md
serial_justified: |
  One dispatch order in one file. There is nothing to parallelise and two tabs would reorder the
  same list against each other.
substrate: N/A
substrate-novel: |
  No tool adopted or built. Every detector already exists and is already dispatched; the defect
  is purely that an early noisy leg starves the later ones of wall-clock and of the operator's
  attention. The novel slice is ordering and output discipline.
accept: |
  MEASURED 2026-08-02: `bash fleet/preflight.sh` emits HUNDREDS of reconcile-merged AMBIGUOUS /
  UNRESOLVABLE lines. `detect_stranded_work` — which prints the stranded-work-cadence verdict, the
  gate for the work-loss class — is dispatched at line 884, AFTER that flood. A 200s-capped run
  never reached it at all; the operator's uncapped run surfaced the line only after a long wait
  and a screen of noise.
  Detectors after the flood, all effectively unread: detect_stranded_work, detect_cg_drift,
  detect_gateway_token_drift, detect_config_drift, detect_service_watchdog, detect_fixture_bypass,
  detect_gate_integrity.
  A check nobody reaches is a check nobody has, which is the built-but-inert class wearing a
  different hat.
  Done contract:
  1. Cap or summarise repeated reconcile-merged findings (they are one CLASS, not N findings) —
     print the count and the distinct shapes, not every row.
  2. Guarantee the verdict lines are reachable: emit a compact SUMMARY of every leg's verdict at
     the END regardless of upstream volume, so no leg can be starved by another's output.
  3. Fail-on-revert: with the fix reverted, a run capped at 200s must NOT reach the cadence
     verdict; with it, it must.

## Dependencies & Sequence

P1. Depends on nothing, but is the natural COMPANION to OWNS-OVERLAP-DISAMBIGUATE: that ticket
removes the CAUSE of the flood, this one ensures no future noisy leg can starve the late ones
again. Land either order; landing both is what makes preflight trustworthy.
