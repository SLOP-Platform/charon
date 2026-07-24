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
# USAGE
#   monit-selfwatch.sh            # check + relaunch-if-needed
#   monit-selfwatch.sh --check    # check only, never relaunch (report)
#
# EXIT: 0 monit HEALTHY · 1 monit was DOWN/HUNG (relaunch attempted, surfaced) · 2 usage
#       · 3 monit NOT INSTALLED (BLOCKED on operator — prints the exact install command)
#
# TEST SEAMS: SELFWATCH_MONIT_BIN (fake monit for offline tests), SELFWATCH_STATE (state file for
#   the freshness probe), SELFWATCH_TTL (default 300s), SELFWATCH_RELAUNCH_CMD (relaunch action),
#   SELFWATCH_SURFACE (issue-board.sh), WD_NOW.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WD_FLEET="$(cd "$HERE/.." && pwd)"; export WD_FLEET
# shellcheck source=/dev/null
source "$HERE/watchdog-lib.sh"

CHECK_ONLY=0
case "${1:-}" in
  --check) CHECK_ONLY=1;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
  "") : ;;
  *) echo "monit-selfwatch: unknown arg '$1'" >&2; exit 2;;
esac

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

# --- monit installed? -------------------------------------------------------
if [ -z "$MONIT_BIN" ]; then
  echo "monit-selfwatch: BLOCKED — monit is NOT installed on this box."
  echo "  OPERATOR (one-time, needs sudo — this rig cannot):"
  echo "    sudo apt-get install -y monit"
  echo "    fleet/watchdog/generate-monit-config.sh                 # render config from the registry"
  echo "    sudo cp fleet/watchdog/monit.d/*.conf /etc/monit/conf.d/ && sudo systemctl enable --now monit"
  echo "  Until then the monit-independent evaluator (discover-services.sh) carries detection."
  surface P1 "monit-not-installed" "watchdog: monit not installed — supervisor absent; run: sudo apt-get install -y monit && systemctl enable --now monit"
  exit 3
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
