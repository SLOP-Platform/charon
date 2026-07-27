repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 1
branch: feat/monit-install-enable
depends_on: WATCHDOG-RESTART-CMDS-VERIFY
real-dep: WATCHDOG-RESTART-CMDS-VERIFY — TRUE build/correctness prereq, not merge order
  [[disjoint-owns-not-no-dependency]]. It owns `fleet/watchdog/units` (which does NOT exist yet — it
  creates it) and `fleet/watchdog/verify-restart-cmds.sh`, the thing that PROVES each service's
  restart command actually restarts that service. Installing a supervisor whose restart commands are
  unverified is worse than having no supervisor: monit will loop-restart a service that is failing
  for a real reason, burning the box and masking the true fault. The verify step is the whole safety
  argument for turning monit on.
dep-kind: build
owns: fleet/state/MONIT-INSTALL-RUNBOOK.md
serial_justified: |
  This ticket deliberately owns NO executable and NOT `fleet/watchdog/units` — that directory belongs
  to WATCHDOG-RESTART-CMDS-VERIFY, and claiming it would make this a second concurrent writer of a
  seam that does not exist yet. The deliverable is a runbook plus the operator's sudo execution;
  the automation it installs is already built (`generate-monit-config.sh`, `monit-selfwatch.sh`,
  `discover-services.sh`, all present and executable in fleet/watchdog/).
execution: |
  The BUILD half (runbook + dry-run proof) is assignable to a NON-ANTHROPIC model via an `opencode`
  session. The INSTALL half requires operator sudo on the LOCAL box and cannot be delegated.
source: |
  Operator action item Z, carried unresolved across sessions. Ticketed 2026-07-26 at operator request
  ("I need to make sure we don't forget monit") because it kept living only in the pending list.
note: |
  ## WHAT
  Put the bench-grader under supervision so it restarts on failure instead of dying silently:
  1. Install the bench-grader **systemd unit** from `fleet/watchdog/units/` (created by
     WATCHDOG-RESTART-CMDS-VERIFY — it does not exist yet).
  2. Install **monit**, generate its config via the already-built `fleet/watchdog/generate-monit-config.sh`,
     and enable it.
  Both steps are on the **LOCAL WSL box — NOT 4-LOM.** Getting this wrong supervises the wrong host.

  ## WHY (this is not housekeeping)
  `fleet/model-scorecard.tsv` is THE ledger — model ranking, promote/demote (`model-detention.sh`),
  tier assignment (`assign.py`) and the cold-start prior all read it. It is written by the
  out-of-band `bench-grader` daemon running as a dedicated unix user for anti-gaming isolation.
  **If that daemon dies, nothing tells us.** The scorecard simply stops gaining rows, and every
  downstream ranking silently ages into fiction while looking perfectly healthy — the exact
  failure-shape as the inert meter and the dead grading read (B1/B2), both of which went unnoticed for
  weeks. A sensor with no liveness alarm is a sensor you cannot trust.
  Evidence it is a real risk: the grader daemon has been restarted by hand before, and
  `model-scorecard.sh --due` has been firing with `last review 2026-07-07`.

  ## WHEN — the trigger, so this is not judgement-by-memory
  Start the moment this is true:
  ```
  ls /home/stack/charon-private/fleet/state/done/WATCHDOG-RESTART-CMDS-VERIFY && echo GO || echo WAIT
  ```
  **Do NOT run `monit enable --now` before that gate passes** — explicitly warned against in the
  original operator note, for the loop-restart reason in `real-dep` above.

  ## SUDO STEPS (operator-only; the runbook must state these verbatim and in order)
  Both LOCAL, not 4-LOM. The runbook is the deliverable precisely so these are not reconstructed from
  memory at 2am. Note the class of error already seen today: a documented command
  (`sudo <script>`) failed with a misleading "command not found" purely because the script lacked
  `+x` — the runbook must give commands that are verified RUNNABLE, not merely present.
accept: |
  DONE-CONTRACT:
  - `fleet/state/MONIT-INSTALL-RUNBOOK.md` exists with: the exact, VERIFIED-RUNNABLE sudo commands in
    order; which host each runs on (LOCAL, explicitly not 4-LOM); the gate check above; and a
    rollback (how to disable monit and remove the unit if it misbehaves).
  - Every command in the runbook is proven runnable BEFORE being written down — check the executable
    bit and shebang of each script it invokes, and say which you verified how.
  - A DRY-RUN of `fleet/watchdog/generate-monit-config.sh` with its output shown, so the config monit
    would actually get is reviewed before it is installed.
  - The runbook states what monit will DO on failure (restart command per service) and cites where
    each restart command was verified — an unverified restart command in the config is a RED.
  - NON-VACUOUS: a runbook that supervises zero services is RED.
  - **Installing/enabling monit is NOT in this ticket's done-contract** — the ticket completes when
    the runbook is proven correct. The operator executes it. Do not attempt sudo.

## Dependencies & sequence

- **Depends on: WATCHDOG-RESTART-CMDS-VERIFY** (build prereq — see `real-dep`). Blocked until its
  done-marker exists.
- **Blocks:** nothing on the board. Operationally it removes a silent-failure mode under the ledger
  that model ranking depends on.
- **Concurrency safety:** owns ONE new state file. Deliberately does not own `fleet/watchdog/units`
  or any script in `fleet/watchdog/` — those belong to the dep.
- **Wave:** parallel lane, P1, gated.
