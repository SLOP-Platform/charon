#!/usr/bin/env bash
# THE on/off lever for full-autonomous mode. When ON, the manager may push to main via
# land-push.sh (closing the push-pause); when OFF, the manager asks you to push (the human
# checkpoint on main stays). The flag lives under state/ (git-ignored), so it's machine-local
# and never committed. Usage: autonomous.sh on | off | status
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLAG="$FLEET/state/AUTONOMOUS"; mkdir -p "$FLEET/state"
case "${1:-status}" in
  on)  date -u +%FT%TZ > "$FLAG"
       echo "AUTONOMOUS: ON — manager may push to main (full autonomous). Turn off: autonomous.sh off";;
  off) rm -f "$FLAG"
       echo "AUTONOMOUS: OFF — manager will ask you to push (human checkpoint on main).";;
  status) [ -e "$FLAG" ] && echo "AUTONOMOUS: ON (since $(cat "$FLAG"))" || echo "AUTONOMOUS: OFF";;
  *) echo "usage: autonomous.sh on|off|status"; exit 2;;
esac
