repo: charon-private
tier: strong
difficulty: 2
priority: 0
work_class: rig-meta
branch: feat/stuck-ticket-loud-visibility
owns: fleet/checks/stuck-ticket-loud.sh, fleet/tests/stuck-ticket-loud.test.sh
depends_on: LOOP-GUARD-INFRA-FAULT-EXEMPT
real-dep: LOOP-GUARD-INFRA-FAULT-EXEMPT owns fleet/loop-guard.sh and already CLASSIFIES zero-commit
  reasons (infra-fault-exempt). The reason-classification below EXTENDS that same mechanism (adds
  launch-refused / blocked-dep / model-flailed) — reuse-first, do NOT fork a second classifier. This
  ticket consumes the classified reasons to route non-model causes to LOUD STUCK.
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
  - ZERO-COMMIT REASON CLASSIFICATION (folded per operator 2026-07-23): the zero-commit release path
    (loop-guard.sh, called by fleet-droid.sh) must CLASSIFY why zero commits happened and route
    accordingly — only ONE class may reach quarantine:
      * LAUNCH-REFUSED (parallelizability / no-such-ticket / admission) → NOT quarantine; this should not
        even occur once gate-parity lands (caught at LAND). If seen, surface LOUD STUCK + point at the gate.
      * BLOCKED-DEP / structural (unmet dep, parked, hard block) → NOT quarantine; surface LOUD STUCK.
      * MODEL-FLAILED (the model genuinely ran on an actionable ticket and produced nothing) → the ONLY
        class that increments toward quarantine. This is the narrow, legitimate trigger.
    loop-guard.sh must accept/derive the reason and quarantine ONLY on MODEL-FLAILED; the reason string
    (currently the blanket "repeated zero-commit re-claims") is replaced by the classified reason. The
    loop-guard.sh classification is IMPLEMENTED BY / EXTENDS LOOP-GUARD-INFRA-FAULT-EXEMPT (#214, owns
    loop-guard.sh, already exempts infra-fault) — reuse it, add these classes there; this ticket only
    CONSUMES the classified reason for LOUD-stuck routing. The fleet-droid.sh call site passing the
    reason is a one-line anchor owned by LAUNCHER-CRASH-PARTIAL-DETECT — coordinate, do not rewrite.
  - fail-on-revert test additions: a LAUNCH-REFUSED zero-commit release does NOT quarantine (asserts the
    classification); a MODEL-FLAILED one DOES after threshold. Revert the classification → a structural
    zero-commit wrongly quarantines again (RED).
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
