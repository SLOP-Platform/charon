repo: charon-private
tier: strong
difficulty: 2
work_class: bugfix
priority: 1
branch: fix/loop-guard-infra-fault-exempt
depends_on:
owns: fleet/loop-guard.sh, fleet/tests/loop-guard-infra-exempt.test.sh
serial_justified: one behavior + its fail-on-revert test — the quarantine-suppression rule and the test asserting an infra-fault release does NOT quarantine are one coupled change.
work_class_note: |
  ROOT CAUSE found 2026-07-23: loop-guard SILENTLY STARVES the priority ladder. When a droid claims a
  ticket and stands down with ZERO commits, loop-guard quarantines it after 2 cycles — but it does NOT
  distinguish WHY. During the pool-exhaustion episode (CHARON_RUN_RESULT=EXHAUSTED) and a transient RED
  board, droids stood down with zero commits on GOOD tickets → those tickets got quarantined → claim.sh
  silently SKIPS quarantined tickets → tabs dropped past P0/P1 work (REVIEWER-TAB-POOL, EVAL-CONTROL-GATE-
  FIX, REPO-FIELD-REQUIRED, PROVIDER-CATALOG-REFRESH …) to un-quarantined economy work, with no visible
  signal. Same failure-attribution gap as [[monitored-preflight-failure-attribution]] (infra-fault ≠
  quality-fault). [[slowness-triggers-investigation]] [[never-ignore-preexisting-issues]]
accept: |
  Loop-guard must NOT quarantine a ticket when the droid's zero-commit stand-down was caused by an INFRA
  FAULT, not the ticket. Distinguish the cause (the launcher/charon-run already classifies it — reuse that
  attribution, don't re-derive):
    - INFRA/transient (CHARON_RUN_RESULT=EXHAUSTED / ALL-EXHAUSTED / pool-too-thin / gateway 5xx-reset /
      RED-board-blocked-claim / launcher-refused) → do NOT count toward quarantine; retry later. Optionally
      a separate infra-retry counter that never permanently excludes.
    - GENUINE ticket failure (gate red on the diff, real test failure, repeated no-progress with a healthy
      pool) → quarantine as today.
  Plus: when tickets ARE quarantined, SURFACE it (count in status/board so a starved P0 is visible, not
  silent) — silent exclusion is the actual harm here.
  PROVE IT (fail-on-revert): an infra-fault stand-down (fixture) does NOT quarantine; a genuine-failure
  stand-down still does. Revert → the infra case wrongly quarantines → test RED.
scope: |
  Stop loop-guard from quarantining good tickets on infra-fault (pool-exhaustion/RED-board) zero-commit
  stand-downs, and surface active quarantines so a starved priority ladder is never silent. Reuse the
  launcher's existing infra-vs-model failure attribution.
ds: |
  ## Dependencies & sequence
  - depends_on: none. owns fleet/loop-guard.sh — coordinate with fleet-droid.sh's stand-down/quarantine
    call site (reads the release reason); if that classification lives in fleet-droid.sh, reuse it via a
    shared signal rather than duplicating (flag if a fleet-droid.sh touch is needed → split or dep).
