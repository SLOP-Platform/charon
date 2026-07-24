repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/watchdog-restart-cmds-verify
owns: fleet/watchdog/verify-restart-cmds.sh, fleet/watchdog/units, fleet/tests/verify-restart-cmds.test.sh, fleet/state/service-registry.tsv
depends_on: SERVICE-LIVENESS-WATCHDOG
serial_justified: real restart commands + a pre-enable verify gate are ONE safety unit — enabling monit with
  broken restarts recreates the exact incident, and a verify step with nothing real to verify is theater.
source: |
  SERVICE-LIVENESS-WATCHDOG adversarial review (2026-07-24), HIGH findings. Every seed restart_cmd is broken:
  grader -> `systemctl restart bench-grader-daemon` (NO such unit; live grader is a bare user-shell python, not
  systemd); roci -> `fleet/bridge-reconnect.sh` (file missing + relative path, monit runs cwd=/); session-bridge
  -> `systemctl --user` (no user unit, monit runs as root); gateway -> `ssh 4-LOM ...` (alias in user ~/.ssh, not
  root's). So once monit is enabled, on a service death monit runs a command that FAILS -> auto-recovery misfires
  = the exact 9-day-stale-grader incident, just at the RESTART step. And the runbook enables monit with no verify.
note: |
  1. Fix EVERY restart_cmd in service-registry.tsv to a REAL, root-context-safe command that actually restarts
     the service on THIS box (create a real bench-grader-daemon.service pointing at the true launch path; absolute
     paths to scripts that exist; units/ssh that work as root). Ground on real checks (systemctl cat, test -x).
  2. Add fleet/watchdog/verify-restart-cmds.sh — a hard gate that confirms every restart_cmd's unit/script EXISTS
     and is runnable under monit's root context. The operator runbook AND monit-selfwatch must REFUSE
     `monit enable --now` until this passes (this is the missing runbook gate).
accept: |
  - every restart_cmd resolves to a REAL runnable command under monit's root context — PROVEN (systemctl cat /
    test -x transcript per service), not asserted.
  - verify-restart-cmds.sh fails-CLOSED if any restart_cmd target is missing/unrunnable.
  - the runbook + monit-selfwatch BLOCK `enable --now monit` until verify passes.
  - dogfood: break one restart_cmd -> verify REDs -> enable is refused; fix it -> verify GREEN -> enable allowed.
  - fail-on-revert test; ADVERSARIAL REVIEW (reviewer != builder).
scope: |
  The restart layer + the pre-enable verify gate ONLY. Detection / anti-staleness / discovery already landed with
  SERVICE-LIVENESS-WATCHDOG. This is the gate that must pass before the operator's monit-install (#4) goes live.
ds: |
  ## Dependencies & sequence
  P0. depends_on SERVICE-LIVENESS-WATCHDOG — edits its service-registry.tsv AFTER it lands (sequenced hand-off,
  not a live collision). BLOCKS the operator `monit enable --now` step until it passes.
