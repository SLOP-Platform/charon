repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: rig-meta
branch: fix/tab-reliability
owns: fleet/checks/tab-liveness.sh, fleet/tests/tab-liveness.test.sh
depends_on: LAUNCHER-CRASH-PARTIAL-DETECT
real-dep: LAUNCHER-CRASH-PARTIAL-DETECT — TRUE BUILD PREREQ despite disjoint owns. The liveness
  probe this ticket builds reads a HEARTBEAT that the worker must emit, and the launcher
  (fleet/fleet-droid.sh) is the only thing that can emit it. That file is owned by
  LAUNCHER-CRASH-PARTIAL-DETECT, which is already reworking the droid stand-down/exit path where
  the heartbeat and the verified-stop must live. Building the probe first would mean writing a
  detector against a signal that does not exist yet, then rewriting it — so the launcher-side
  change lands first and this consumes it.
dep-kind: build
dep-note: |
  OWNERSHIP NOTE: this ticket deliberately does NOT own fleet/fleet-droid.sh. Two live tickets
  already do (LAUNCHER-CRASH-PARTIAL-DETECT, BRIEF-ABSOLUTE-PATHS). Any launcher-side change
  (verified stop, process-group kill, heartbeat emission) belongs to LAUNCHER-CRASH-PARTIAL-DETECT
  and is sequenced behind it; this ticket owns the LIVENESS TRUTH probe and its red-proof, which
  nothing owns today.

  ⛔ A DONE TICKET DID NOT FIX THIS — DO NOT ASSUME IT IS COVERED.
  DROID-LIFECYCLE-REAP is marked DONE and archived, and its dependants SESSION-REPORT-WIRE and
  LOOP-GUARD-REASON-WIRE are DONE too. Despite that, 5 orphan fleet-droid loops were found ALIVE
  and ~2 DAYS OLD at the 2026-08-03 close, reparented to ppid=1, one of them claiming tickets.
  So the reaper is either inert or insufficient in production. VERIFY THE LANDED REAPER ACTUALLY
  RUNS AND ACTUALLY REAPS before writing anything new — this is the same shipped-but-never-worked
  class as retire-done.sh (landed, aborted on every run for weeks, found 2026-08-04).

  ⛔ SEQUENCING — READ D-008a BEFORE BUILDING. D-008a names the supervisor/reaper as the single
  best Go candidate in the estate, AND warns: if a durable-execution engine is adopted for the work
  queue (Lane B / LANE-C AXIS 2 category #1), THE ENGINE IS THE SUPERVISOR and a hand-written one
  rebuilds the thing we are about to adopt — rig-as-product again. Decide the queue question first,
  or deliberately scope this to the thin local agent that survives either outcome (liveness truth +
  reaping), not a full scheduler.
serial_justified: |
  One failure — "a tab's true state is unknowable" — plus the probe that detects it and its
  red-proof. The launcher, the liveness check and its test are the same guarantee; a liveness
  checker with no red-proof is precisely the unproven-gate class this project keeps shipping.
work_class_note: rig-meta — the execution substrate every other ticket runs on. The operator
  classes this a KEY SG feature, not rig housekeeping.
note: |
  ⛔ OPERATOR-SET HIGH PRIORITY, 2026-08-04, verbatim: "lets make tab reliablity a HIGH priority
  for the next session this is a KEY feature or SG that needs to be fixed."

  ## THE CORE DEFECT: A TAB'S STATE IS UNKNOWABLE
  An opencode tab that is working, finished, hung, or dead are INDISTINGUISHABLE from outside.
  Measured 2026-08-03/04:
    - "Stopping a tab's session does not stop the tab." The opencode server stays up and reverts to
      an idle prompt — which looks identical to a healthy idle worker.
    - 5 orphan `fleet-droid` loops were found alive at session close: ~2 DAYS old, reparented to
      ppid=1, invisible to the fleet's own status views. ONE CLAIMED A TICKET ~11 MINUTES AFTER IT
      WAS MINTED, for work already finished. Consequence on record: do not mint tickets while
      unaccounted-for workers are alive.
    - The droids IGNORED SIGTERM; they required kill -9.
    - The PRICEFEED tab was interrupted mid-work and left UNVERIFIED WIP (7dbdafa) that a later
      session had to rescue.

  ## THE DETECTION TOOLING IS ITSELF BROKEN — FIX THIS FIRST, IT IS CHEAP
    - `pgrep -f '<name>.sh'` matches OTHER processes' argument lists: it reported 6 droids when
      there were 5, because a shellcheck run had fleet-droid.sh in its argv.
    - `pgrep -f <pattern>` ALSO MATCHES ITSELF when the pattern appears in the waiting command's own
      argv. A subagent's `until ! pgrep -f 'status-board/generate'; do sleep 5; done` spun for 14
      minutes and BLOCKED THE OPERATOR'S /exit. Never wait on pgrep -f with a self-referential
      pattern; wait on a PID (kill -0), on `wait`, or on a sentinel file.
    - `kill -0` returns non-zero under EPERM, so a process owned by another user reads as DEAD when
      it is ALIVE. Confirm with `ps -p`.
    - MEASURED 2026-08-04: `fleet/work-lease.sh holds` dies with "line 195: $1: unbound variable"
      instead of printing usage — the command for "which leases are held" does not work at all.

  ## WHAT GOOD LOOKS LIKE (acceptance)
  (a) A single command answers, for every tab/worker, the TRUTH: alive / idle / working / hung /
      dead — by PID and by a heartbeat the worker itself writes, never by pgrep -f pattern matching.
  (b) A worker that stops heartbeating is reaped, and its claimed ticket is released — no ticket
      stays claimed by a dead worker.
  (c) Stopping a tab actually stops the tab (process group / session kill), and the launcher
      verifies the stop rather than assuming it.
  (d) An orphan (ppid=1) worker is detectable and reapable by an operator-runnable command.
  (e) `work-lease.sh holds` works and lists held leases.
  (f) Every assertion carries a red-proof, and the suite is in the CI_SUITES allowlist in
      fleet/checks/rig-ci-scope.sh or it will never execute.
  (g) 189 live worktrees currently have ZERO process/FS isolation (LANE-C gap audit). Isolation is
      OUT OF SCOPE here — record it, do not attempt it in this ticket.

  ## LANGUAGE
  Per D-008: bash is acceptable only for a short script that calls other programs and exits. This
  component must REMEMBER STATE, COORDINATE WITH OTHER PROCESSES and RUN FOR A LONG TIME, so per
  D-008 it must NOT be bash. D-008a puts it at ~500-1,000 lines of Go — subject to the sequencing
  warning in dep-kind above.
