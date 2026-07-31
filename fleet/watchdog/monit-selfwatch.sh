#!/usr/bin/env bash
# monit-selfwatch.sh — "who watches monit". A supervisor that is its own only watcher is the exact
# silent-death gap this ticket closes, so monit itself must be watched by something OUTSIDE monit.
#
# Two independent checks (a monit that DIED or one that HUNG must both be caught):
#   1. ALIVE   — `monit status` (or a live monit process) responds.
#   2. FRESH   — monit's state file has ticked within the TTL (a hung monit stops updating it).
# On either failure -> relaunch (systemd if this box is systemd-init — VERIFIED at build time it is
# — else the @reboot/manual setup path) AND surface to the issue-board.
#
# This is a SEPARATE minimal check by design: it runs in preflight + on a cadence, never inside
# monit. See fleet/board/SERVICE-LIVENESS-WATCHDOG.md self-watch clause.
#
# ENABLE GATE (WATCHDOG-RESTART-CMDS-VERIFY): monit runs as root with cwd=/. If any restart_cmd in
# the registry is not runnable in THAT context, enabling monit means "service dies -> monit runs a
# failing command -> auto-recovery misfires" — the 9-day-stale-grader incident at the restart step.
# So this script will NOT hand the operator the `systemctl enable --now monit` line, and
# `--gate-enable` REFUSES, until fleet/watchdog/verify-restart-cmds.sh is GREEN. Fail-closed: a
# missing/unrunnable verify script counts as RED.
#
# USAGE
#   monit-selfwatch.sh              # check + relaunch-if-needed
#   monit-selfwatch.sh --check      # check only, never relaunch (report)
#   monit-selfwatch.sh --gate-enable  # THE pre-enable gate: 0 = monit may be enabled, 1 = REFUSED
#
# EXIT: 0 monit HEALTHY · 1 monit was DOWN/HUNG (relaunch attempted, surfaced) · 2 usage
#       · 3 monit NOT INSTALLED (BLOCKED on operator — prints the exact install command)
#       (--gate-enable: 0 allowed · 1 REFUSED)
#
# TEST SEAMS: SELFWATCH_MONIT_BIN (fake monit for offline tests), SELFWATCH_STATE (state file for
#   the freshness probe), SELFWATCH_TTL (default 300s), SELFWATCH_RELAUNCH_CMD (relaunch action),
#   SELFWATCH_SURFACE (issue-board.sh), SELFWATCH_VERIFY (verify-restart-cmds.sh path), WD_NOW.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WD_FLEET="$(cd "$HERE/.." && pwd)"; export WD_FLEET
# shellcheck source=/dev/null
source "$HERE/watchdog-lib.sh"

CHECK_ONLY=0
GATE_ONLY=0
case "${1:-}" in
  --check) CHECK_ONLY=1;;
  --gate-enable) GATE_ONLY=1;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
  "") : ;;
  *) echo "monit-selfwatch: unknown arg '$1'" >&2; exit 2;;
esac

# --- PRE-ENABLE GATE: every restart_cmd must be runnable in monit's ROOT context ---------------
VERIFY="${SELFWATCH_VERIFY:-$HERE/verify-restart-cmds.sh}"
VERIFY_OUT=""
# restart_cmds_ok -> 0 GREEN (monit may be enabled) / 1 RED (REFUSE). Fail-CLOSED: if the verify
# script is absent or not runnable, that is RED, never an implicit pass.
restart_cmds_ok(){
  if [ ! -f "$VERIFY" ]; then
    VERIFY_OUT="verify-restart-cmds.sh not found at $VERIFY"
    return 1
  fi
  VERIFY_OUT="$(bash "$VERIFY" --quiet 2>&1)"
  return $?
}

print_enable_runbook(){
  echo "  OPERATOR (one-time, needs sudo — this rig cannot):"
  echo "    sudo apt-get install -y monit"
  echo "    fleet/watchdog/generate-monit-config.sh                 # render config from the registry"
  echo "    fleet/watchdog/verify-restart-cmds.sh                   # MUST be GREEN (it is)"
  echo "    sudo cp fleet/watchdog/monit.d/*.conf /etc/monit/conf.d/ && sudo systemctl enable --now monit"
}
print_enable_refused(){
  echo "  ENABLE REFUSED — fleet/watchdog/verify-restart-cmds.sh is RED:"
  printf '%s\n' "$VERIFY_OUT" | sed 's/^/      /'
  echo "  Enabling monit now would make it run FAILING restart commands on a service death"
  echo "  (auto-recovery misfires = the 9-day-stale-grader incident at the restart step)."
  echo "  FIX fleet/state/service-registry.tsv column 6, then re-run:"
  echo "      fleet/watchdog/verify-restart-cmds.sh"
  echo "  The install/enable sequence is deliberately NOT printed while this is RED."
}

MONIT_BIN="${SELFWATCH_MONIT_BIN:-$(command -v monit 2>/dev/null || true)}"
STATE_FILE="${SELFWATCH_STATE:-${HOME}/.monit.state}"
TTL="${SELFWATCH_TTL:-300}"
SURFACE="${SELFWATCH_SURFACE-$WD_FLEET/issue-board.sh}"
# Default relaunch: systemd (pid 1 is systemd on this box — verified). Falls back to `monit`
# (its own config re-daemonizes) if systemctl is absent.
if command -v systemctl >/dev/null 2>&1; then
  DEFAULT_RELAUNCH="systemctl restart monit"
else
  DEFAULT_RELAUNCH="${MONIT_BIN:-monit}"
fi
RELAUNCH_CMD="${SELFWATCH_RELAUNCH_CMD:-$DEFAULT_RELAUNCH}"

surface(){ [ -n "$SURFACE" ] && [ -x "$SURFACE" ] || return 0; bash "$SURFACE" add "$2" "$1" "$3" >/dev/null 2>&1 || true; }

# --- --gate-enable: the pre-enable gate (runs BEFORE anything monit-specific) ----------------
if [ "$GATE_ONLY" -eq 1 ]; then
  if restart_cmds_ok; then
    echo "monit-selfwatch: ENABLE ALLOWED — every restart_cmd is runnable under monit's root context"
    print_enable_runbook
    exit 0
  fi
  echo "monit-selfwatch: ENABLE REFUSED — restart_cmd verification FAILED" >&2
  print_enable_refused >&2
  surface P0 "monit-enable-blocked" "watchdog: monit enable BLOCKED — a restart_cmd is not runnable as root (fleet/watchdog/verify-restart-cmds.sh RED)"
  exit 1
fi

# --- monit installed? -------------------------------------------------------
if [ -z "$MONIT_BIN" ]; then
  echo "monit-selfwatch: BLOCKED — monit is NOT installed on this box."
  if restart_cmds_ok; then
    print_enable_runbook
  else
    print_enable_refused
    surface P0 "monit-enable-blocked" "watchdog: monit enable BLOCKED — a restart_cmd is not runnable as root (fleet/watchdog/verify-restart-cmds.sh RED)"
  fi
  echo "  Until then the monit-independent evaluator (discover-services.sh) carries detection."
  surface P1 "monit-not-installed" "watchdog: monit not installed — supervisor absent; run: sudo apt-get install -y monit"
  exit 3
fi

# monit IS installed: a RED restart_cmd set means its recovery action would FAIL on every death.
# Loud + surfaced (this script never enables monit itself, so it does not exit here).
if ! restart_cmds_ok; then
  echo "monit-selfwatch: WARNING — restart_cmd verification is RED; monit's recovery WILL misfire." >&2
  print_enable_refused >&2
  surface P0 "monit-restart-cmds-red" "watchdog: monit is installed but a restart_cmd is NOT runnable as root — recovery would misfire"
fi

# --- ALIVE check ------------------------------------------------------------
alive=0
if timeout 10 "$MONIT_BIN" status >/dev/null 2>&1; then alive=1
elif pgrep -f -- "$(basename "$MONIT_BIN")" >/dev/null 2>&1; then alive=1; fi

# --- FRESH check (state file ticked within TTL) -----------------------------
fresh=1  # default "fresh" when we cannot locate a state file (don't false-relaunch)
if [ -e "$STATE_FILE" ]; then
  wd_probe_fresh "file:$STATE_FILE" "$TTL" && fresh=1 || fresh=0
fi

healthy=1
[ "$alive" -eq 1 ] || healthy=0
[ "$fresh" -eq 1 ] || healthy=0

if [ "$healthy" -eq 1 ]; then
  echo "monit-selfwatch: monit HEALTHY (alive + state fresh <= ${TTL}s)"
  exit 0
fi

reason=""
[ "$alive" -eq 0 ] && reason="DOWN (no response)"
[ "$fresh" -eq 0 ] && reason="${reason:+$reason; }HUNG (state stale > ${TTL}s)"
echo "monit-selfwatch: monit UNHEALTHY — $reason"
surface P0 "monit-unhealthy" "watchdog: monit $reason — relaunching"

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "monit-selfwatch: --check mode, NOT relaunching (would run: $RELAUNCH_CMD)"
  exit 1
fi

echo "monit-selfwatch: relaunching monit -> $RELAUNCH_CMD"
if ( eval "$RELAUNCH_CMD" ) >/dev/null 2>&1; then
  echo "monit-selfwatch: relaunch command exited 0"
else
  echo "monit-selfwatch: relaunch command FAILED (rc=$?) — may need sudo; surfaced to the board"
  surface P0 "monit-relaunch-failed" "watchdog: monit relaunch FAILED ($RELAUNCH_CMD) — needs operator"
fi
exit 1
