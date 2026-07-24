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
  local out rc=0
  out="$(FOREMAN_FLEET="$FOREMAN_FLEET" bash "$FOREMAN_SH" 2>&1)" || rc=$?
  printf '%s\n' "$out"
  # Mirror foreman.sh's EXIT-CODE CONTRACT rather than re-deriving a verdict from the text.
  # This used to do BOTH: propagate any non-zero rc as "FAIL", and independently return 1 on a
  # bare [STARVE] match -- two overloads of the same signal, so a merely-unfed board made every
  # trigger (session-start / post-land / cadence) report FAIL.
  case "$rc" in
    0)  # includes the supply ADVISORY: report it loudly, but it is not a failure.
        if printf '%s\n' "$out" | grep -q '^== FOREMAN VERDICT: \[ADVISORY\]'; then
          say "== FOREMAN CADENCE VERDICT ($label): ADVISORY -- supply state (feed the board), not a failure =="
        else
          say "== FOREMAN CADENCE VERDICT ($label): OK =="
        fi
        return 0 ;;
    2)  say "== FOREMAN CADENCE VERDICT ($label): DEFECT (rc=$rc) -- board collisions, do not feed as-is =="
        return "$rc" ;;
    *)  say "== FOREMAN CADENCE VERDICT ($label): FAIL (rc=$rc) -- foreman could not run =="
        return "$rc" ;;
  esac
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
  out="$(FOREMAN_FLEET="${FOREMAN_FLEET:-$FLEET}" bash "$FOREMAN_SH" 2>&1)" || true
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
  # WIRE-GRAPHIFY-FRESHNESS: this is the REAL fired timer entrypoint (cron/systemd ->
  # `foreman-cadence.sh cadence`, per RECONCILE-* tickets' own assumption at :87-104).
  # A sibling `graphify` subcommand that nothing calls would be the exact
  # built-but-inert bug this ticket exists to fix — so call it from here too.
  # Independently interval-gated (its own marker file), so it never runs more often
  # than GRAPHIFY_CADENCE_INTERVAL regardless of the foreman interval above.
  cmd_graphify_cadence

  # WIRE-SERVICE-WATCHDOG (SERVICE-LIVENESS-WATCHDOG): the fired timer entrypoint. Same
  # rationale as graphify — a watchdog that nothing calls on a cadence is the built-but-inert
  # bug this ticket exists to close. Independently interval-gated (own marker).
  cmd_watchdog_cadence
  # REGISTRY-META-CATALOG: fire the registry discovery leg on the same cadence backstop.
  # A meta-catalog nobody reconciles just recreates the "can't find our registries" problem
  # it exists to solve — so the fail-closed disk->catalog discovery must actually RUN.
  cmd_registry_discovery
}

# --- watchdog cadence: keep monit config in sync + relaunch a dead monit + surface -----
# The ACTING leg of SERVICE-LIVENESS-WATCHDOG on a timer backstop:
#   1. re-render monit.d/*.conf from the registry (a new/edited service row takes effect), and
#      `monit reload` if monit is installed (so monit picks up the render).
#   2. monit-selfwatch: relaunch monit if it died/hung (who-watches-monit).
#   3. discover-services: evaluate registered alive+freshness + unregistered discovery, surfacing
#      any DEAD/STALE/uncovered service to the issue-board (write-if-present).
# Interval-gated with its own marker so it is independent of the foreman interval.
WATCHDOG_CADENCE_MARKER="$STATE_DIR/.watchdog-cadence-ts"

cmd_watchdog_cadence(){
  local interval_minutes="${WATCHDOG_CADENCE_INTERVAL:-15}"
  case "${1:-}" in --interval-minutes) interval_minutes="$2"; shift 2;; esac
  _ensure_state_dir
  local now last_ts
  now="$(date +%s)"
  if [ -f "$WATCHDOG_CADENCE_MARKER" ]; then
    last_ts="$(cat "$WATCHDOG_CADENCE_MARKER" 2>/dev/null || echo 0)"
    local elapsed=$(( now - last_ts ))
    local interval_seconds=$(( interval_minutes * 60 ))
    if [ "$elapsed" -lt "$interval_seconds" ]; then
      say "watchdog cadence: skipped ($elapsed s since last run, interval=${interval_minutes}m)"
      return 0
    fi
  fi
  printf '%s' "$now" > "$WATCHDOG_CADENCE_MARKER"
  say "--- watchdog cadence (interval=${interval_minutes}m) ---"
  local wdir="$FLEET/watchdog"
  [ -d "$wdir" ] || { say "watchdog cadence: $wdir not found"; return 0; }
  say "watchdog cadence: re-rendering monit config from registry..."
  bash "$wdir/generate-monit-config.sh" 2>&1 || true
  if command -v monit >/dev/null 2>&1; then bash -c 'monit reload' >/dev/null 2>&1 || true; fi
  say "watchdog cadence: self-watch (relaunch monit if dead)..."
  bash "$wdir/monit-selfwatch.sh" 2>&1 || true
  say "watchdog cadence: evaluating services (alive + freshness + discovery)..."
  bash "$wdir/discover-services.sh" 2>&1 || true
}

# --- registry discovery cadence: keep the registry META-CATALOG honest --------------
# Runs checks/discover-registries.sh so a registry that lands on disk but nobody catalogued
# is caught (fail-closed) rather than silently drifting. Interval-gated like the others.
REGISTRY_DISCOVERY_CADENCE_MARKER="$STATE_DIR/.registry-discovery-cadence-ts"

cmd_registry_discovery(){
  local interval_minutes="${REGISTRY_DISCOVERY_CADENCE_INTERVAL:-30}"
  case "${1:-}" in --interval-minutes) interval_minutes="$2"; shift 2;; esac
  _ensure_state_dir
  local now last_ts
  now="$(date +%s)"
  if [ -f "$REGISTRY_DISCOVERY_CADENCE_MARKER" ]; then
    last_ts="$(cat "$REGISTRY_DISCOVERY_CADENCE_MARKER" 2>/dev/null || echo 0)"
    local elapsed=$(( now - last_ts ))
    local interval_seconds=$(( interval_minutes * 60 ))
    if [ "$elapsed" -lt "$interval_seconds" ]; then
      say "registry discovery cadence: skipped ($elapsed s since last run, interval=${interval_minutes}m)"
      return 0
    fi
  fi
  printf '%s' "$now" > "$REGISTRY_DISCOVERY_CADENCE_MARKER"
  say "--- registry discovery cadence (interval=${interval_minutes}m) ---"
  local rd="$FLEET/checks/discover-registries.sh"
  [ -f "$rd" ] || { say "registry discovery cadence: discover-registries.sh not found at $rd"; return 0; }
  # Report-only from the cadence backstop (surface RED loudly; the manager/preflight acts).
  REGISTRY_CATALOG_FLEET="$FLEET" bash "$rd" 2>&1 || say "registry discovery cadence: RED — a registry on disk is not in the catalog (see above)"
}

# --- graphify cadence: keep the code map fresh on a timer backstop ------------------
# Runs checks/graphify-freshness.sh update + check as a cadence backstop so a map that
# goes stale between triggers (post-land, SessionStart) gets caught and refreshed.
# Interval-gated the same way as foreman's own cadence subcommand.
GRAPHIFY_CADENCE_MARKER="$STATE_DIR/.graphify-cadence-ts"

cmd_graphify_cadence(){
  local interval_minutes="${GRAPHIFY_CADENCE_INTERVAL:-30}"
  case "${1:-}" in --interval-minutes) interval_minutes="$2"; shift 2;; esac
  _ensure_state_dir
  local now last_ts
  now="$(date +%s)"
  if [ -f "$GRAPHIFY_CADENCE_MARKER" ]; then
    last_ts="$(cat "$GRAPHIFY_CADENCE_MARKER" 2>/dev/null || echo 0)"
    local elapsed=$(( now - last_ts ))
    local interval_seconds=$(( interval_minutes * 60 ))
    if [ "$elapsed" -lt "$interval_seconds" ]; then
      say "graphify cadence: skipped ($elapsed s since last run, interval=${interval_minutes}m)"
      return 0
    fi
  fi
  printf '%s' "$now" > "$GRAPHIFY_CADENCE_MARKER"
  say "--- graphify cadence (interval=${interval_minutes}m) ---"
  local gf="$FLEET/checks/graphify-freshness.sh"
  [ -f "$gf" ] || { say "graphify cadence: graphify-freshness.sh not found at $gf"; return 0; }
  say "graphify cadence: refreshing code maps via $gf update..."
  bash "$gf" update 2>&1 || true
  say "graphify cadence: re-checking freshness..."
  bash "$gf" check 2>&1 || true
}

case "${1:-help}" in
  session-start) shift; cmd_session_start "$@" ;;
  post-land)     shift; cmd_post_land "$@" ;;
  handoff)       shift; cmd_handoff "$@" ;;
  cadence)       shift; cmd_cadence "$@" ;;
  graphify)      shift; cmd_graphify_cadence "$@" ;;
  watchdog)      shift; cmd_watchdog_cadence "$@" ;;
  registry-discovery) shift; cmd_registry_discovery "$@" ;;
  help|--help|-h)
    say "Usage: bash foreman-cadence.sh <subcommand> [args]"
    say ""
    say "Subcommands:"
    say "  session-start              Boot tier-health surface (report-only)"
    say "  post-land                  Refresh tier picture after a land/merge"
    say "  handoff                    Emit tier picture for handoff markdown"
    say "  cadence [--interval-min N] Scheduled backstop with interval gate"
    say "  graphify [--interval-min N] Code-map freshness cadence backstop"
    say "  watchdog [--interval-min N] Service-liveness watchdog cadence (render+selfwatch+eval)"
    say "  registry-discovery [--interval-min N] Registry meta-catalog discovery backstop"
    say ""
    say "Env: FOREMAN_FLEET=<dir>     Override fleet root (test seam)"
    say "     FOREMAN_CADENCE_INTERVAL  Minutes between cadence runs (default 30)"
    ;;
  *) die "unknown subcommand: $1 (try: help)" ;;
esac
