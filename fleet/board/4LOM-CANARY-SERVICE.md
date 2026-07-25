repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/4lom-canary-service
owns: fleet/canary-service/run-canary.sh, fleet/canary-service/deploy-4lom.sh, fleet/state/canary-report.tsv, fleet/tests/canary-service.test.sh
depends_on:
serial_justified: the service + its cached report + slow-vs-broken attribution + the SessionStart surface are
  ONE sensor — a suite that runs but nobody reads, or a report with no freshness/attribution, is the exact
  "canary that didn't catch the problem and got forgotten" gap this closes.
source: |
  operator directive 2026-07-24 — TOP of the P0s. Handoff #4/#4b want that was NEVER built (checked live: no
  service script, no cached report, no ticket — it got lost between sessions, the exact failure we keep hitting).
  The gate-test suite (~74 tests) must run as an ALWAYS-ON service on 4-LOM; the manager must NEVER run 74 tests
  inline. The demo surfaced 12 RED (8 genuine, 4 slow-timeout false-reds) but there is no live sensor.
note: |
  - Run the gate-test suite on a cadence on 4-LOM (10.0.1.60) as a SUPERVISED service (systemd). Cache a
    token-lean report: fleet/state/canary-report.tsv (test|status|last_run|attribution).
  - Report carries a last_run TIMESTAMP; the manager ALARMS if the report is STALE (anti-staleness on the
    reporter itself — else a dead sensor looks green).
  - Server-side SLOW-vs-BROKEN attribution: rc=124 timeout -> SLOW (not a model/gate verdict) vs a genuine
    failure -> BROKEN. This fixes the 4 slow-timeout FALSE-reds.
  - Service pulls latest master before each run.
  - REGISTER the canary service in SERVICE-LIVENESS-WATCHDOG's service-registry (the sensor itself is
    supervised — who-watches-the-canary).
  - SURFACE a token-lean canary status line at SessionStart (the one-liner: "canary: N green / M red (K slow) @
    <last_run>") via the existing SessionStart surface — so it is never forgotten again.
accept: |
  - suite runs as a supervised, reboot-persistent service on 4-LOM; manager reads the CACHED report, never runs
    74 tests inline.
  - report carries last_run + is a SERVICE-LIVENESS-WATCHDOG registry entry (stale report -> watchdog alarms).
  - slow-vs-broken attribution PROVEN on a seeded slow (rc=124) test + a seeded real red -> classified correctly.
  - SessionStart emits the token-lean canary status line (wired, not manual).
  - service git-pulls latest master before each run.
  - fail-on-revert; ADVERSARIAL REVIEW.
scope: |
  The service + cached report + slow-vs-broken attribution + SessionStart surface + watchdog registration. Does
  NOT fix the individual gate-test reds (separate work) — it SURFACES them with honest attribution. The build is
  rig-side; the 4-LOM systemd deploy is an operator step (like the grader/monit) — the ticket produces the deploy
  script + the exact operator command, does not assume sudo on 4-LOM.
ds: |
  ## Dependencies & sequence
  P0 — TOP priority (operator). Soft-couples to SERVICE-LIVENESS-WATCHDOG (registers there) + the SessionStart
  surface family (ISSUE-BOARD-SURFACE / LENS-REGISTRY-AND-REPORT). First build step: confirm 4-LOM systemd +
  the gate-test suite's real runtime (so the cadence + timeout budgets are grounded, not guessed).
