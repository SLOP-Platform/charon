repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: rig-meta
branch: feat/service-liveness-watchdog
owns: fleet/watchdog/generate-monit-config.sh, fleet/watchdog/monit.d, fleet/watchdog/monit-selfwatch.sh, fleet/watchdog/discover-services.sh, fleet/state/service-registry.tsv, fleet/tests/service-watchdog.test.sh, fleet/dark-work-check.sh
depends_on:
serial_justified: the supervisor, its auto-discovery, the anti-staleness checks, the self-watch, and
  the e2e dogfood are ONE capability — a watchdog that isn't itself supervised, or one that only checks
  a hand-listed subset, ships the exact silent-death gap this ticket exists to close.
source: |
  operator directive 2026-07-24. ROOT INCIDENT: the OOB grader-daemon (sole writer of model-scorecard.tsv,
  runs as unix user bench-grader) died on a box reboot with NO supervisor and never restarted, silently
  killing the whole grade->route chain for 9 days (the broker fell back to static free-first and droids
  hammered exhausted free providers). Same reboot silently killed the session-bridge daemon too. NOTHING
  owns checking that key processes/services are alive AND fresh. Adopt-first survey (operator-approved):
  MONIT — best-in-class, purpose-built for process-alive + file-freshness + restart + alert in one config
  (a stanza per service = the registry). Consolidates today's scattered per-service scripts (dark-work-check.sh,
  status.sh liveness, bench-grader liveness). See also handoff #4b watchdog-gate + KS29 registry primitive.
note: |
  ADOPT MONIT as the single supervisor for all key services (grader-daemon, session-bridge daemon,
  gateway@4-LOM, roci tunnel, droid launchers, ...). No hand-rolled liveness loop.

  1. AUTO-DISCOVERY REGISTRY (KS29 pattern, Backstage software-catalog model): a declarative
     fleet/state/service-registry.tsv (row per service: name|kind|alive-probe|freshness-probe|freshness-ttl|
     restart-cmd|owner) is the SINGLE source; generate-monit-config.sh renders monit.d/*.conf FROM it (never
     hand-edit monit config). discover-services.sh is the DISCOVERY leg: finds running/critical services NOT
     in the registry -> fail-closed alarm, so newly-added services/lenses get incorporated automatically.
  2. CONSOLIDATE the per-service scripts into monit checks (fold dark-work-check.sh; have status.sh call the
     watchdog rather than re-implement liveness) and retire the scattered one-offs.
  3. ANTI-STALENESS PER SERVICE: monit checks not just process-alive but FRESH — file mtime / heartbeat within
     TTL (e.g. model-scorecard.tsv < N min, session-bridge lease active). A hung service producing nothing
     alarms + restarts just like a dead one (this is the 9-day-stale-grader case).
  4. SELF-WATCH ("who watches monit"): monit runs reboot-persistent under systemd Restart=always if systemd is
     the init here (VERIFY at build start — WSL2 varies), else @reboot cron; PLUS monit-selfwatch.sh — a
     separate minimal check (in preflight + a cadence) that monit's own last-run/heartbeat is fresh, so monit
     dying OR hanging is itself caught. Never let the watcher be its own only watcher.
  5. SURFACE: service failures + restarts flow to fleet/issue-board.sh (SG SURFACE leg) -> SessionStart, so
     the manager sees a dead/stale service automatically, never by tripping over the symptom.
accept: |
  - MONIT installed + adopted (or a justified reject-record if unavailable on this box after a real test).
  - service-registry.tsv drives everything; generate-monit-config.sh renders monit config from it (no hand-edited
    monit stanzas). Adding a registry row -> that service is monitored on next render (proven in the test).
  - discovery leg: a running critical service absent from the registry -> discover-services.sh fails-closed (alarm).
  - anti-staleness proven: freeze a monitored service's output (stop it writing) while its PROCESS stays alive
    -> monit stale-alarms + restarts it. (Real dogfood, not a mock.)
  - self-watch proven: kill monit -> the self-watch (systemd or selfwatch cadence) brings it back; and a stale
    monit heartbeat is detected.
  - e2e DOGFOOD: kill a real registered service (a disposable canary daemon) -> monit restarts it AND the issue
    appears on the issue-board SessionStart line. On a REAL run.
  - FULLY WIRED (firing layer): monit is enabled + reboot-persistent, generate/discover/selfwatch run on a real
    cadence (preflight + foreman-cadence), NOT built-but-inert. A gate executes service-watchdog.test.sh.
  - fail-on-revert test: remove a service's freshness-probe (or the self-watch) -> the test that proves stale/dead
    detection goes RED.
  - ADVERSARIAL REVIEW REQUIRED (reviewer != builder) — supervises money-path infra (the grader/broker).
scope: |
  The Monit adoption + registry + auto-discovery + anti-staleness + self-watch + issue-board surface + e2e.
  The initial registry seeds: grader-daemon, session-bridge daemon, gateway, roci tunnel. Does NOT build the
  issue-board itself (ISSUE-BOARD-SURFACE owns that; this ticket WRITES to it — soft-couples, no hard dep so
  it isn't blocked; degrade gracefully if the board isn't present yet). Does NOT re-implement restart logic
  monit already provides.
ds: |
  ## Dependencies & sequence
  P0 do-now. No hard prereq. Soft-couples to ISSUE-BOARD-SURFACE for the SURFACE leg (write-if-present).
  Supervises the broker's grader-daemon, so it closes the recurrence path for FLEET-DEMAND-DRIVEN-ROUTING
  cripple #1. First build step: VERIFY systemd-vs-cron init + monit availability on this box.
