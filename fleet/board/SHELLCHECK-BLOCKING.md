repo: charon-private
tier: economy
difficulty: 2
work_class: ci-infra
branch: feat/shellcheck-blocking
depends_on:
owns: fleet/gate.sh, fleet/tests/shellcheck-blocking.test.sh
serial_justified: The single behavioural change is flipping ONE advisory branch in fleet/gate.sh to
  gate-blocking; its fail-on-revert test is the paired unit. Splitting per-script "cleaning" from the
  flip would let the flip land against still-dirty scripts (green-but-broken) or leave the advisory
  in place — the clean-then-flip must be one ticket so the gate never lies.
accept: |
  UMBRELLA: KS31/KS32 tool-adoption sweep (adopt best-in-class; retire hand-rolls / stop under-using
  maintained tools). shellcheck is ALREADY adopted but pinned at ADVISORY-only.

  PROBLEM (verified, do NOT re-research): fleet/gate.sh runs shellcheck over fleet/*.sh but treats
  findings as ADVISORY — fleet/gate.sh:88-104 prints "shellcheck: ADVISORY — findings above are
  non-blocking (shellcheck-clean tracked separately)" and the gate's pass/fail is driven ONLY by the
  behavioural bash tests. So a shellcheck regression can land green. The code comment at
  fleet/gate.sh:91 literally says "Flipping shellcheck to gate-blocking is tracked separately (clean
  fleet/*.sh first)" — THIS ticket is that tracked work.

  DO:
    (a) Clean the real shellcheck findings across fleet/*.sh (or annotate genuine false positives with
        scoped `# shellcheck disable=SCxxxx` + a one-line reason — the embedded-python heredocs /
        sourced _lib.sh SC1091/SC2148 class is the known noise; suppress precisely, do not blanket).
    (b) Flip fleet/gate.sh:97-101 so a non-zero shellcheck rc INCREMENTS $FAIL (gate-blocking), not a
        printf-only advisory. shellcheck stays SKIPPED-not-failing when the binary is absent (keep the
        `command -v shellcheck` guard) so the gate is portable.

  FAIL-ON-REVERT (fleet/tests/shellcheck-blocking.test.sh — REQUIRED): feed the gate a FIXTURE shell
  script with a real shellcheck violation -> gate RED (exit 1). A clean fixture -> gate green. Revert
  the fleet/gate.sh flip (back to advisory) -> the dirty fixture stops failing -> the test FAILS. This
  proves the promotion actually blocks, per [[gates-must-actually-run]] ("verify a gate EXECUTED").

  NOTE: no ticket F26 SHELLCHECK-CLEAN exists on the board/archive/parked/done (searched 2026-07-21) —
  this ticket is not a duplicate; it IS the promotion the gate.sh comment defers.
scope: |
  Promote the already-adopted shellcheck from advisory (fleet/gate.sh:88-104) to BLOCKING in the fleet
  gate: clean/annotate fleet/*.sh, flip the advisory branch to increment $FAIL, keep the binary-absent
  skip, and add a fail-on-revert fixture test proving it blocks. [[gates-must-actually-run]]
  [[adopt-substrate-build-only-novel-slice]] [[reviews-use-our-own-tools]]
ds: |
  ## Dependencies & sequence
  depends_on: (none). Independent of the SEMGREP/gitleaks/bandit CI-adoption chain — this touches the
    LOCAL fleet gate (fleet/gate.sh), a different surface, and can land in parallel.
  concurrency: sole writer of fleet/gate.sh (no live ticket owns it — verified 2026-07-21) and its new
    test file. Runs alone.
  wave: economy — small, mechanical (one advisory->blocking flip + cleanup + one fixture test).
  repo: charon-private (rig).
note: Created 2026-07-21 from the KS31/KS32 sweep. Realises the deferral at fleet/gate.sh:91
  ("Flipping shellcheck to gate-blocking is tracked separately"). No F26 SHELLCHECK-CLEAN ticket
  exists, so this is created fresh (not a duplicate).
