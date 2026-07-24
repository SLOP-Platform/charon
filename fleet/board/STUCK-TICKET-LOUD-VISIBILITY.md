repo: charon-private
tier: strong
difficulty: 2
priority: 0
work_class: rig-meta
branch: feat/stuck-ticket-loud-visibility
owns: fleet/checks/stuck-ticket-loud.sh, fleet/tests/stuck-ticket-loud.test.sh
depends_on:
source: operator directive 2026-07-23 (deadlock RCA) — silent parking/quarantine hid the wedge
note: |
  A ticket that goes through the process and is NOT claimable for ANY reason must NEVER be silently
  parked. On 2026-07-23 a P0 keystone was loop-guard-quarantined ("repeated zero-commit re-claims") and
  NOTHING was loud about it — the pool just went dry (deadlock). [[stuck-tickets-loud-never-silent]]
  [[sg-never-deadlocks]]
accept: |
  - fleet/checks/stuck-ticket-loud.sh: detect every board ticket that is UNCLAIMABLE (not done, not
    submitted, not actively claimed, yet no droid can claim it — quarantined, all-deps-dead, orphaned
    residue, or landed-unlaunchable) and surface it LOUDLY: a distinct STUCK/UNCLAIMABLE category that
    is emitted every status.sh / report.sh / preflight run and STAYS loud until cleared. Not a quiet
    state marker.
  - QUARANTINE narrowing: quarantine may fire ONLY for genuine repeated MODEL-ATTRIBUTABLE failure, NOT
    for structural causes (a lands-but-unlaunchable ticket must be caught at LAND by gate-parity, never
    quarantined). Document/enforce the narrow trigger; a structurally-wedged ticket surfaces as STUCK,
    not silently quarantined.
  - fail-on-revert test: seed a quarantined/unclaimable fixture ticket => stuck-ticket-loud.sh emits it
    LOUD (non-zero / prominent) and status/report show it; revert the detection => it goes silent (RED).
  - bash fleet/validate_board.sh GREEN.
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder).
scope: |
  Make stuck/quarantined tickets impossible to miss (LOUD, persistent, self-surfacing) + narrow the
  quarantine trigger. Half of the anti-deadlock guarantee (the other half = GATE-PARITY prevention).
ds: |
  ## Dependencies & sequence
  P0, no build prereq. Disjoint owns (new files). Composes with GATE-PARITY-LAND-VS-LAUNCH +
  LAUNCHER-CRASH-PARTIAL-DETECT.
