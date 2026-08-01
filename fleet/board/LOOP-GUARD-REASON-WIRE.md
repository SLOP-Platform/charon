repo: charon-private
tier: economy
difficulty: 1
work_class: bugfix
priority: 0
branch: fix/loop-guard-reason-wire
depends_on: SESSION-REPORT-WIRE
owns: fleet/fleet-droid.sh, fleet/tests/loop-guard-reason-wire.test.sh
serial_justified: |
  Two call sites, one flag, one test. Nothing to split.
source: |
  Found 2026-08-01 (session tott-doneeta): an OpenRouter key cap quarantined three P0 tickets as
  if the work were bad, stalling the fleet. The exemption that should have prevented it exists and
  is marked DONE.
note: |
  ## THE DEFECT (measured)
  `fleet/loop-guard.sh:23-44` implements an INFRA-FAULT EXEMPTION: `record` accepts
  `--reason <reason>`, and reasons matching `infra|infra-fault|exhausted|all-exhausted|
  pool-exhausted|pool-too-thin|gateway-reset|...` are counted in a separate infra counter under
  `state/loop-guard/infra/<id>` that NEVER quarantines.

  **No caller passes `--reason`.** `fleet/fleet-droid.sh:928` and `:945` both call
  `loop-guard.sh record "$id" "$DROID"` bare, and a repo-wide grep for `loop-guard.sh record`
  outside loop-guard.sh itself finds no `--reason` anywhere. So the exemption is structurally
  incapable of firing — built, merged, marked DONE (LOOP-GUARD-INFRA-FAULT-EXEMPT), inert.

  ## WHAT IT COST (2026-08-01)
  The OpenRouter key hit its total cap. Every leg returned 403. `charon-run.sh` correctly reported
  `CHARON_RUN_RESULT=EXHAUSTED` — a reason ALREADY on the exemption list. Because the reason was
  never passed, three P0 tickets (AMBIENT-COUPLED-TESTS, SESSION-REPORT-WIRE,
  RUNTIME-INERT-DETECTION) reached `count=2` in the QUARANTINE counter and became unclaimable.
  The manager had to delete `state/loop-guard/<id>` by hand to restart the fleet. A provider
  billing limit should never look like bad work.

  ## SCOPE
  Pass the reason at both call sites. `charon-run.sh` already surfaces the outcome
  (`CHARON_RUN_RESULT` = SUCCESS / EXHAUSTED / rc=124 timeout, plus the
  leg-fault/too-slow/infra-fault classifications written to
  `fleet/state/provider-exhaustion-ledger.tsv`). Map that to the reason string the exemption
  already understands — do NOT invent a new vocabulary, and do NOT widen the exemption list.

  **Reuse-check:** the classification ALREADY exists — the ledger distinguishes
  `infra-fault-failover`, `leg-fault-failover`, `too-slow-failover` and `error-failover`, and
  the last is explicitly "genuine model-attributable". That distinction is the whole point: a
  model that produces bad work MUST still quarantine. Only infra passes free.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline. Each RED on the named revert, then GREEN:
    a. a release with `CHARON_RUN_RESULT=EXHAUSTED` lands in the INFRA counter and does NOT
       quarantine, even after more attempts than the threshold. Revert the wire -> RED.
    b. a release from a genuine model failure (`error-failover`, non-limit non-infra) STILL
       counts toward quarantine. This is the anti-over-exempt case — if everything becomes
       "infra", the loop guard is dead. Revert -> RED.
    c. a timeout (rc=124) is classified per the ledger's existing rule, not lumped in blindly.
    d. ANTI-OVER-BLOCK: a successful run records nothing and quarantines nothing.
  Then reproduce the real incident: simulate an all-legs-403 and show the ticket stays claimable.

D&S — Deps & Sequence:
  - Depends on SESSION-REPORT-WIRE: both edit `fleet/fleet-droid.sh` (LAUNCHER-CRASH-PARTIAL-DETECT
    is the third owner, sequenced last). Collision ordering, not a build prereq.
  - MITIGATION until this lands: a false quarantine clears with
    `rm fleet/state/loop-guard/<TICKET>`. The manager did this by hand on 2026-08-01.
