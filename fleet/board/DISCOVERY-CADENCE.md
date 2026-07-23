repo: charon-private
tier: economy
difficulty: 1
work_class: ci-infra
priority: 1
branch: feat/discovery-cadence
depends_on: DISCOVERY-APPROVAL-WIRE
dep-kind: build
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
scope: |
  Schedule the daily pull + weekly digest (systemd timer / rig cron), off-hot-path, stale-but-usable on
  source-down, immediate OUTAGE-RISK escalation. Reuses catalog_refresh's TTL/degrade doctrine.
ds: |
  ## Dependencies & sequence
  - depends_on: DISCOVERY-APPROVAL-WIRE (D5) — transitively sequences after D1-D4; schedules the whole
    now-built loop. Real build dep.
  - reuse: catalog_refresh TTL/degrade doctrine; rig timer/cron.
  - concurrency: disjoint new file fleet/discovery/schedule.sh.
