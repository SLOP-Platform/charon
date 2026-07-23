repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 1
branch: feat/claim-ladder-health
depends_on:
owns: fleet/ladder-health.sh, fleet/tests/ladder-health.test.sh
serial_justified: one surfacer + its fail-on-revert test are one coupled change.
work_class_note: |
  GENERAL fix for the silent-starvation class (root-caused 2026-07-23: loop-guard quarantine silently
  excluded P0s; tabs dropped to economy work with NO signal). The lesson is NOT "fix quarantine" — it's
  that claim.sh excludes tickets for MANY reasons and NONE is surfaced, so a top-priority ticket can be
  invisibly un-claimable for any of them. Make every exclusion VISIBLE so it can never be silent again,
  regardless of cause. [[gates-must-actually-run]] [[monitored-preflight-failure-attribution]]
  [[keep-the-hopper-full]] [[charon-strategy-outcome-graded-gateway]]
accept: |
  Build `fleet/ladder-health.sh`: for the top-K (default 10) priority tickets, print CLAIMABLE or the exact
  EXCLUSION REASON. It must enumerate EVERY reason claim.sh can silently drop a candidate — audit claim.sh
  and cover all of them, e.g.:
    - loop-guard QUARANTINED (with the quarantine's age/reason)
    - CLAIMED (by which droid; and whether that droid is still alive — a stale claim from a dead droid is
      the same silent-exclusion, flag it)
    - SUBMITTED (with PR # and its state — a submitted marker whose PR is CLOSED/merged-unretired is stale)
    - BLOCKED on undone dep(s) (name them; flag if a dep is actually done but mis-marked)
    - PARKED / note-unclaimable
    - BOARD RED (validate_board failing blocks ALL claims — surface this loudly; it's a total silent stall)
    - repo/owns-mismatch or other validation exclusion
    - parallelizability-refused (needs serial_justified/decompose)
  Wire it into the session-start/status surface (and optionally preflight) so a starved P0 is reported
  every session — the harm was invisibility, so visibility IS the fix. A P0/P1 that is un-claimable for a
  reason it shouldn't be must show up RED, not vanish.
  PROVE IT (fail-on-revert): fixtures — a quarantined P0, a stale-claim P0, a submitted-but-closed P0, a
  dep-blocked P0 — each must be reported with its reason; a genuinely-claimable P0 reports CLAIMABLE. Revert
  the surfacer → the starved ticket goes invisible again → test RED.
scope: |
  A ladder-health surfacer that reports, for the top-K priority tickets, CLAIMABLE-or-why-not across EVERY
  claim.sh exclusion cause — so silent priority-starvation (any cause) becomes impossible. Wired into
  session status. Pairs with LOOP-GUARD-INFRA-FAULT-EXEMPT (that fixes one cause; this surfaces all).
ds: |
  ## Dependencies & sequence
  - depends_on: none. Read-only over claim.sh's exclusion logic + state markers; owns its own surfacer.
  - pairs-with: LOOP-GUARD-INFRA-FAULT-EXEMPT (cause-fix) — this is the visibility meta-guard over all causes.
