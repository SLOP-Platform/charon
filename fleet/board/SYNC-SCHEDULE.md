tier: economy
difficulty: 1
work_class: ci-infra
branch: feat/sync-schedule
repo: charon-private
depends_on:
owns: fleet/preflight.sh, fleet/hooks/session-start.sh
accept: |
  Keep LOCAL main checkouts' master current with origin on a SENSIBLE SCHEDULE so they never drift stale (the
  recurring bug: builders branch off origin, but the manager's board work + the rig's runtime engine-invocation use
  the LOCAL checkout — a stale local master shipped un-mergeable state + a runtime "engine not found" this session).
  The mechanism EXISTS: fleet/sync-checkouts.sh (FF-only, dirty-safe, divergence-guarded). WIRE it to run:
    (1) at SessionStart (the hook that already cats MANAGER-RULES + roadmap) — so every session starts current;
    (2) at the top of fleet/preflight.sh — so a build wave never fires against a stale local master.
  Idempotent + fast (a fetch + FF); skips loudly on dirty/diverged (never destructive).
  FAIL-ON-REVERT: a stale-local fixture repo → after the hook runs, local master == origin/master; a DIRTY fixture
  → hook SKIPS (no data loss). Revert the wiring → stale local persists → RED.
scope: mechanize local-checkout freshness (operator directive 2026-07-13). [[investigate-and-backup-before-data-loss]]
ds: |
  depends_on: none (sync-checkouts.sh already built). Small rig chore; Sonnet/economy.
note: script done; this ticket just wires it to SessionStart + preflight for the automatic schedule.
