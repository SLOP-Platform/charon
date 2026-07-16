#!/usr/bin/env bash
# foreman-cadence.sh — Multi-trigger cadence dispatcher for fleet/foreman.sh
#
# FOREMAN-WIRE wired foreman into preflight ONLY. A dynamic-data tool (tier-health
# surface) needs CADENCE + MULTIPLE smart triggers — not one. This provides:
#
#   session-start   — boot tier-health surface (for SessionStart hook)
#   post-land       — after a merge/land (board just changed)
#   handoff         — the next session inherits the tier picture (for handoff.sh)
#   cadence         — scheduled backstop with interval gate (cron/timer)
#
# Every subcommand runs foreman.sh report-only (NEVER --fix). Acting stays a
# manager decision.
#
# Usage:
#   bash fleet/foreman-cadence.sh session-start
#   bash fleet/foreman-cadence.sh post-land
#   bash fleet/foreman-cadence.sh handoff
#   bash fleet/foreman-cadence.sh cadence [--interval-minutes 30]
#
# Test seam: FOREMAN_FLEET=<dir> overrides the fleet root (like foreman.sh).
set -uo pipefail

FLEET="${FOREMAN_CADENCE_FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
FOREMAN_SH="$FLEET/foreman.sh"
STATE_DIR="$FLEET/state"
CADENCE_MARKER="$STATE_DIR/.foreman-cadence-ts"

say(){ printf '%s\n' "$*"; }
die(){ say "foreman-cadence: $*" >&2; exit 1; }

_ensure_state_dir(){
  [ -d "$STATE_DIR" ] || mkdir -p "$STATE_DIR"
}

_run_foreman(){
  local label="$1"
  [ -x "$FOREMAN_SH" ] || { say "foreman-cadence: foreman.sh not found at $FOREMAN_SH (skip $label)"; return 0; }
  say "== FOREMAN CADENCE: $label =="
  local out rc
  out="$(FOREMAN_FLEET="$FOREMAN_FLEET" bash "$FOREMAN_SH" 2>&1)" || rc=$?
  printf '%s\n' "$out"
  if [ -n "${rc:-}" ]; then
    say "== FOREMAN CADENCE VERDICT ($label): FAIL (rc=$rc) =="
    return "$rc"
  fi
  # Check verdict line in output
  if printf '%s\n' "$out" | grep -qiE '\[STARVE\]|\[COLLISION\]'; then
    say "== FOREMAN CADENCE VERDICT ($label): ISSUES DETECTED =="
    return 1
  fi
  say "== FOREMAN CADENCE VERDICT ($label): OK =="
  return 0
}

cmd_session_start(){
  say "--- foreman session-start ---"
  _run_foreman "session-start"
}

cmd_post_land(){
  say "--- foreman post-land ---"
  _run_foreman "post-land"
}

cmd_handoff(){
  say "--- foreman handoff ---"
  [ -x "$FOREMAN_SH" ] || { say "foreman-cadence: foreman.sh not found (skip handoff section)"; return 0; }
  local out
  out="$(FOREMAN_FLEET="$FOREMAN_FLEET" bash "$FOREMAN_SH" 2>&1)" || true
  say ""
  say "### Foreman tier-health (auto)"
  say ""
  say '```'
  printf '%s\n' "$out"
  say '```'
  say ""
}

cmd_cadence(){
  local interval_minutes="${FOREMAN_CADENCE_INTERVAL:-30}"
  case "${1:-}" in --interval-minutes) interval_minutes="$2"; shift 2;; esac
  _ensure_state_dir
  local now last_ts
  now="$(date +%s)"
  if [ -f "$CADENCE_MARKER" ]; then
    last_ts="$(cat "$CADENCE_MARKER" 2>/dev/null || echo 0)"
    local elapsed=$(( now - last_ts ))
    local interval_seconds=$(( interval_minutes * 60 ))
    if [ "$elapsed" -lt "$interval_seconds" ]; then
      say "foreman cadence: skipped ($elapsed s since last run, interval=${interval_minutes}m)"
      return 0
    fi
  fi
  printf '%s' "$now" > "$CADENCE_MARKER"
  say "--- foreman cadence (interval=${interval_minutes}m) ---"
  _run_foreman "cadence"
}

case "${1:-help}" in
  session-start) shift; cmd_session_start "$@" ;;
  post-land)     shift; cmd_post_land "$@" ;;
  handoff)       shift; cmd_handoff "$@" ;;
  cadence)       shift; cmd_cadence "$@" ;;
  help|--help|-h)
    say "Usage: bash foreman-cadence.sh <subcommand> [args]"
    say ""
    say "Subcommands:"
    say "  session-start              Boot tier-health surface (report-only)"
    say "  post-land                  Refresh tier picture after a land/merge"
    say "  handoff                    Emit tier picture for handoff markdown"
    say "  cadence [--interval-min N] Scheduled backstop with interval gate"
    say ""
    say "Env: FOREMAN_FLEET=<dir>     Override fleet root (test seam)"
    say "     FOREMAN_CADENCE_INTERVAL  Minutes between cadence runs (default 30)"
    ;;
  *) die "unknown subcommand: $1 (try: help)" ;;
esac
