repo: charon-private
tier: economy
difficulty: 2
work_class: rig-meta
branch: feat/foreman-multi-trigger
serial_justified: One cohesive trigger-wiring pass for one tool + its test; nothing independent to parallelize.
owns: fleet/handoff.sh, fleet/foreman-cadence.sh, fleet/tests/test_foreman_triggers.sh
depends_on:
note: |
  Applies [[dynamic-tools-never-on-demand]] to the foreman. FOREMAN-WIRE wired it into preflight ONLY —
  a dynamic-data tool needs a CADENCE + MULTIPLE smart triggers, not one. Add the missing triggers:
  (a) SessionStart hook (boot tier-health surface); (b) post-land refresh (the board just changed);
  (c) handoff.sh (the next session inherits the tier picture); (d) a scheduled cadence backstop.
  preflight is already done (report-only). NEVER --fix in an automated trigger (report-only there;
  acting stays a manager decision).
accept: |
  - foreman runs at SessionStart (surfaces STARVE/LOW/COLLISION at boot), after a land (board changed),
    and in handoff.sh — each report-only. A cadence backstop (cron/timer or SessionStart-interval) exists.
  - fleet/tests/test_foreman_triggers.sh: a starving fixture -> each wired trigger surfaces the loud verdict;
    a fed board -> no false alarm. Fail-on-revert (removing a trigger makes its case go RED).
  - DOGFOOD: prove the SessionStart + post-land triggers fire on the real fleet.
  - No automated path calls `foreman.sh --fix`.
