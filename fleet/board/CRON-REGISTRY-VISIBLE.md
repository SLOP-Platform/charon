repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: feat/cron-registry-visible
depends_on:
owns: fleet/checks/cron-registry-reconcile.sh, fleet/tests/cron-registry-reconcile.test.sh, fleet/checks/sg-worker-liveness.sh, fleet/tests/sg-worker-liveness.test.sh
serial_justified: |
  One registry, one reconciler, one surfacing point. Splitting them yields a registry nothing
  reconciles or a reconciler nothing surfaces - both are the inert-check failure this prevents.
substrate: N/A
substrate-novel: |
  Nothing external to adopt - cron IS the adopted scheduler (chosen over monit on 2026-08-02 after
  monit was proven a paper adoption: `command -v monit` fails on this box AND on 4-LOM). The
  registry substrate ALSO already exists - `fleet/state/service-registry.tsv` declares itself the
  "DECLARATIVE SSOT of every supervised service" and already carries a `.gitignore` negation. The
  novel slice is a `supervisor` column plus the two-way reconciler; deliberately NOT a new file,
  because a fifth list surface would ADD to the very invisibility this ticket fixes.
execution: |
  Off-Claude, SG tab. Extend the EXISTING registry. Do not create a parallel CRON-REGISTRY file.
source: |
  Operator, 2026-08-02 - "I need all the crons we create to be visible to me (at least at session
  start) and to future sessions so they don't have to rediscover them."
note: |
  ## MEASURED TODAY — the gap is real
  - `fleet/hooks/session-start.sh` has **ZERO** references to cron, crontab or heartbeat. Crons
    are invisible at session start. A session must run `crontab -l` by hand to discover them, and
    a manager session may not even be permitted to (raw `crontab -l` was DENIED to the manager on
    2026-08-02 - so a human-invisible job is also agent-invisible).
  - Only ONE cron script exists in-tree - `fleet/checks/stranded-work-cron.sh`. But there are at
    least TWO cron jobs; the rescue-push half was installed as a RAW crontab line (operator action
    #32) with no in-tree artifact at all. **An installed job with no repo artifact cannot be
    reviewed, tested, or rediscovered.**
  - `fleet/state/service-registry.tsv` (5 rows) exists and is the natural home, but its only
    consumers render MONIT config - and monit is NOT INSTALLED anywhere. So the registry is real
    and its consumer is a paper adoption.

  ## WHAT TO BUILD
  ### 1. ONE registry, extended — not a new file
  Add a `supervisor` column to `fleet/state/service-registry.tsv` with values `cron|monit|systemd`.
  Existing rows become `supervisor=monit`. `fleet/watchdog/generate-monit-config.sh` must FILTER to
  `supervisor=monit` so it is unaffected - assert that in a test, because silently feeding cron rows
  into a monit renderer is the obvious way to break it.
  Every scheduled job carries - name, supervisor, schedule, script path, heartbeat file, max
  heartbeat age, escalation path, purpose, added-date.

  ### 2. Two-way reconciler `fleet/checks/cron-registry-reconcile.sh`
  Same drift shape as the EVAL-REGISTRY work - report BOTH directions -
    C1 **REGISTERED-NOT-INSTALLED** - a row exists, `crontab -l` has no matching entry. The job we
       believe is protecting us is not scheduled.
    C2 **INSTALLED-NOT-REGISTERED** - a crontab entry with no row. An unreviewed job is running on
       a cadence and nobody knows why. This is how the raw rescue-push line came to exist.
    C3 **STALE HEARTBEAT** - registered AND installed, but its heartbeat is older than the row's
       declared max age. **This is LEG B and it is the one that matters** - a registered job that
       never executes reads as clean, and that is the documented failure mode.
  Exit codes MUST be distinct - 0 clean, 1 drift found, 8 could-not-check (crontab unreadable /
  registry missing). "Could not check" must NEVER read as "all fine".

  ### 3. SURFACE IT AT SESSION START — the operator's actual ask
  `fleet/hooks/session-start.sh` (the TRACKED hook, not a machine-local settings file) prints a
  compact block - one line per scheduled job with its schedule, its heartbeat age, and a clear
  OK/STALE/MISSING marker. Print it UNCONDITIONALLY and EARLY. It must not sit behind a long
  reconcile dump - operator action #15 went unread for THREE sessions because a late leg never
  printed. Keep it short enough that it is always read.

  ### 4. Register `sg-worker-liveness.sh`
  Built 2026-08-02, currently unregistered and unscheduled. It measures whether SG worker sessions
  are PROGRESSING (session `time.updated` age), because `/api/health` proves only that the server
  is up. Add it as a `cron` row and schedule it. Its own red-proof is part of this ticket.
accept: |
  a. `service-registry.tsv` carries `supervisor` and every existing row is `monit`; a test asserts
     `generate-monit-config.sh` output is BYTE-IDENTICAL before and after the column is added.
  b. Reconciler detects C1, C2 and C3, each with a RED-PROOF - a fixture registry+crontab pair
     where each class fires, then passes once corrected. Each must be SEEN to fail.
  c. ANTI-FALSE-POSITIVE - a clean fixture yields ZERO findings and exit 0.
  d. UNREADABLE-INPUT PROOF - crontab unreadable or registry missing exits 8 with a distinct
     message and does NOT report "no drift".
  e. Session-start block prints every job with heartbeat age and OK/STALE/MISSING, verified by
     RUNNING the hook, not by reading it.
  f. Both current crons (stranded-work, rescue-push) are registered as rows; the rescue-push job
     gains an in-tree script artifact so it stops being a raw untracked crontab line.
  g. `sg-worker-liveness.sh` registered, scheduled, and its BOTH LEGS verified - installed AND
     heartbeat fresh.
  h. Reconciler in the LITERAL `CI_SUITES` allowlist in `fleet/checks/rig-ci-scope.sh`.
  i. C1/C2 findings escalate via `fleet/pending.sh`.
  j. `bash fleet/validate_board.sh` GREEN.
scope: |
  The registry column, the reconciler, the session-start surfacing, and registering the three
  known jobs. Does NOT install monit and does NOT change what any existing job DOES.

## Dependencies & Sequence

- **depends_on: none.** cron is already the adopted scheduler and both jobs already run.
- Same drift-reconciliation pattern as `EVAL-REGISTRY-DERIVE` (tools) and `PRIORITY-DROPOUT-AUDIT`
  (work items). THREE surfaces, ONE class - "the list and reality disagree, silently". Reuse their
  finding/exit-code shape so the three read identically to an operator.
- `MONIT-INSTALL-OR-RETIRE` is SUBMITTED and adjacent - if monit is retired, the `supervisor`
  column is what lets those rows be reclassified instead of deleted. Not a blocker.
