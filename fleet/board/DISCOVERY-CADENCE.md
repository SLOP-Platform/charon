repo: charon-private
tier: economy
difficulty: 1
work_class: ci-infra
priority: 1
branch: feat/discovery-cadence
depends_on:
owns: fleet/discovery/schedule.sh
note: |
  D6 of the DISCOVERY leg (FREE-PROVIDER-DISCOVERY-DESIGN §3d, operator-approved P1, 2026-07-23). SCHEDULE
  the daily pull + weekly digest, OFF the hot path. REUSE-FIRST: adopt catalog_refresh's TTL/degrade
  doctrine (stale-but-usable on source-down); a rig timer/cron, not a new scheduler. Sequenced last — it
  schedules D1-D5's now-built modules. [[latency-is-a-failure-class]]
accept: |
  A scheduler entrypoint wiring the discovery loop off-hot-path:
    1. **Daily pull** — models.dev + OpenRouter (single cheap GET each; daily-fresh) and cheahjs (~06:00
       UTC, AFTER its 00:00 UTC CI run). zukixa: weekly, manual/reference.
    2. **Weekly digest** — batched review to the board (don't page daily).
    3. **Escalation** — an OUTAGE-RISK RED breaks the weekly cadence and alerts immediately.
    4. **Degrade** — stale-but-usable on any source-down (adopt catalog_refresh's degrade doctrine); the
       loop writes TSVs + a queue, routing NEVER calls it (off-hot-path by construction).
  FAIL-ON-REVERT: simulate a source-down -> loop degrades to last-good, does not block; remove the degrade
  guard -> RED.
  NON-VACUOUS: a scheduled run that invoked ZERO legs must RED, never report a clean cycle.
  RUNNER-REACHABLE: the red-proof must be EXECUTED by a real runner (fleet/gate.sh's
  `fleet/tests/*.test.sh` glob or rig-ci-scope.sh CI_SUITES).
scope: |
  Schedule the daily pull + weekly digest (systemd timer / rig cron), off-hot-path, stale-but-usable on
  source-down, immediate OUTAGE-RISK escalation. Reuses catalog_refresh's TTL/degrade doctrine.
ds: |
  ## Dependencies & sequence
  - depends_on: NONE. The DISCOVERY-APPROVAL-WIRE edge was REMOVED 2026-07-24 and it was NOT a real build
    prereq: the scheduler invokes the other legs by ENTRYPOINT PATH (fleet/discovery/*.py|sh) on a timer,
    and its red-proof simulates a SOURCE-DOWN and asserts stale-but-usable degrade — it executes no leg's
    implementation. Owns are disjoint (schedule.sh only). What the original edge really encoded was
    "there is nothing to schedule until the legs exist", which is a RELEASE-ORDER statement, not a build
    prereq: this ticket ships a timer whose targets are declared by path, and the loop simply has nothing
    to do until the other legs land. Blocking a 1-difficulty timer behind four other tickets bought
    nothing and cost the whole wave a serial tail.
  - reuse: catalog_refresh TTL/degrade doctrine; rig timer/cron.
  - concurrency: disjoint new file fleet/discovery/schedule.sh. Safe to build in parallel with D2-D5.
  - UN-BUNDLED 2026-07-24: briefly absorbed into a DISCOVERY-PIPELINE mega-ticket; reverted. Grouping is
    one ROADMAP wave (`discovery-leg`) at one priority, not one serial ticket.
