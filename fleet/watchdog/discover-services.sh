#!/usr/bin/env bash
# discover-services.sh — the DISCOVERY leg + the monit-independent registry EVALUATOR.
#
# Two legs, one script (both read the SSOT registry via watchdog-lib.sh):
#
#   HEALTH (registered):  evaluate every registry row — alive_probe AND freshness_probe. A DEAD
#                         process OR a HUNG-but-alive one whose output mtime blew the TTL both go
#                         RED. This is what monit does continuously; we ALSO run it here so the
#                         9-day-stale-grader case is caught on a cadence even on a box where monit
#                         is not yet installed (the current box — see the env probe in the ticket).
#
#   DISCOVERY (unregistered):  find running CRITICAL services with NO registry row -> fail-closed
#                         alarm, so a newly-added daemon auto-incorporates (you either add its row
#                         or the alarm keeps firing). This is the "new service silently unsupervised"
#                         gap the ticket exists to close.
#
# Also folds the DARK-WORK leg (dark-work-check.sh) so all liveness/visibility runs under one
# watchdog entrypoint (see that script's header note).
#
# USAGE
#   discover-services.sh              # ALL legs (health + discovery [+ dark-work]); RED on any issue
#   discover-services.sh --health     # only the registered-service health leg
#   discover-services.sh --discover   # only the unregistered-service discovery leg
#   discover-services.sh --no-dark    # skip the folded dark-work leg
#   discover-services.sh --quiet      # only emit problems + the verdict line
#   discover-services.sh --json       # machine-readable summary
#
# EXIT: 0 CLEAN · 1 RED (dead/stale/missing/uncovered/dark) · 2 usage.
#
# TEST SEAMS: WD_REGISTRY, WD_NOW, WD_CRITICAL_REGEX (override the critical-process pattern),
#   WD_DARK_CHECK (path to dark-work-check.sh; empty string disables), WD_SURFACE (issue-board.sh).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WD_FLEET="$(cd "$HERE/.." && pwd)"; export WD_FLEET
# shellcheck source=/dev/null
source "$HERE/watchdog-lib.sh"

LEGS="all"; QUIET=0; JSON=0; DARK=1
while [ $# -gt 0 ]; do case "$1" in
  --health|--registered) LEGS="health"; shift;;
  --discover|--unregistered) LEGS="discover"; shift;;
  --no-dark) DARK=0; shift;;
  --quiet) QUIET=1; shift;;
  --json) JSON=1; shift;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
  *) echo "discover-services: unknown arg '$1'" >&2; exit 2;;
esac; done

# Critical-process pattern: what SHOULD be supervised. A live pid matching this but covered by NO
# registry alive_probe is an unregistered critical service -> alarm. Curated + env-overridable.
CRITICAL_REGEX="${WD_CRITICAL_REGEX:-bench-grader|session-bridge|charon.*gateway|coordinator-charon|droid-launcher|grader-daemon}"
DARK_CHECK="${WD_DARK_CHECK-$WD_FLEET/dark-work-check.sh}"
SURFACE="${WD_SURFACE-$WD_FLEET/issue-board.sh}"

say(){ [ "$QUIET" -eq 1 ] && return 0; printf '%s\n' "$*"; }
prob(){ printf '%s\n' "$*"; }   # problems always print
RED=0

# wd_surface <severity> <id> <msg> — write a failure to the issue-board IF present (soft-couple,
# no hard dep: ISSUE-BOARD-SURFACE owns the board; degrade silently if it isn't there yet).
wd_surface(){
  [ -n "$SURFACE" ] && [ -x "$SURFACE" ] || return 0
  bash "$SURFACE" add "$2" "$1" "$3" >/dev/null 2>&1 || true
}

leg_health(){
  say "-- watchdog HEALTH (registered services) --"
  local row name alive fresh ttl rc fr
  while IFS= read -r row; do
    name="$(wd_field "$row" 1)"; alive="$(wd_field "$row" 3)"
    fresh="$(wd_field "$row" 4)"; ttl="$(wd_field "$row" 5)"
    # alive
    wd_probe_alive "$alive"; rc=$?
    case $rc in
      0) say "  ok    $name — alive ($alive)";;
      1) prob "  DEAD  $name — alive_probe FAILED ($alive)"; RED=1
         wd_surface P0 "service-dead-$name" "watchdog: $name is DOWN (probe: $alive)";;
      3) say "  n/a   $name — no alive probe";;
    esac
    # freshness (only meaningful if alive, but a missing output file is itself a RED regardless)
    wd_probe_fresh "$fresh" "$ttl"; fr=$?
    case $fr in
      0) say "  ok    $name — fresh (<= ${ttl}s)";;
      1) prob "  STALE $name — output older than ${ttl}s (HUNG? probe: $fresh)"; RED=1
         wd_surface P0 "service-stale-$name" "watchdog: $name output STALE > ${ttl}s (hung); probe $fresh";;
      2) prob "  MISS  $name — freshness target MISSING ($fresh) — never produced output"; RED=1
         wd_surface P0 "service-missing-$name" "watchdog: $name freshness target absent ($fresh)";;
      3) : ;;
    esac
  done < <(wd_rows)
}

leg_discover(){
  say "-- watchdog DISCOVERY (unregistered critical services) --"
  # Build COVERAGE NEEDLES from every registry row (not just pgrep rows): a process is "covered"
  # if its cmdline matches any needle. Needles per row: the pgrep ERE, the service name, and the
  # identifying token of a non-pgrep probe (unixsock path, tcp host) — so a service supervised via
  # a socket/tcp probe (e.g. the roci ssh-tunnel) is NOT false-flagged as unregistered.
  local patterns=() row alive name arg
  while IFS= read -r row; do
    name="$(wd_field "$row" 1)"; alive="$(wd_field "$row" 3)"; arg="${alive#*:}"
    patterns+=("$name")
    case "$alive" in
      pgrep:*)    patterns+=("${alive#pgrep:}");;
      unixsock:*) patterns+=("$(wd_expand "$arg")");;
      tcp:*)      patterns+=("${arg%%:*}");;
      pidfile:*)  patterns+=("$(wd_expand "$arg")");;
    esac
  done < <(wd_rows)
  # Each live pid whose cmdline matches CRITICAL_REGEX but no registry needle -> uncovered.
  local pid args covered p uncovered=0
  while read -r pid args; do
    [ -n "$pid" ] || continue
    covered=0
    for p in "${patterns[@]}"; do
      [ -n "$p" ] || continue
      case "$args" in *"$p"*) covered=1; break;; esac
      # regex match (pgrep uses ERE): use grep -E for robustness
      printf '%s' "$args" | grep -Eq -- "$p" 2>/dev/null && { covered=1; break; }
    done
    if [ "$covered" -eq 0 ]; then
      prob "  UNCOVERED  pid $pid — critical service NOT in registry: ${args:0:70}"
      wd_surface P1 "service-unregistered-$pid" "watchdog: unregistered critical service pid $pid: ${args:0:70}"
      uncovered=$((uncovered+1)); RED=1
    fi
  done < <(ps -eo pid=,args= 2>/dev/null | grep -E -- "$CRITICAL_REGEX" | grep -Ev 'discover-services|generate-monit-config|watchdog|grep -E' )
  [ "$uncovered" -eq 0 ] && say "  ok    every running critical service has a registry row"
}

leg_dark(){
  [ "$DARK" -eq 1 ] || return 0
  [ -n "$DARK_CHECK" ] && [ -x "$DARK_CHECK" ] || { say "-- dark-work leg SKIPPED (dark-work-check.sh absent) --"; return 0; }
  say "-- watchdog DARK-WORK (folded dark-work-check.sh) --"
  if bash "$DARK_CHECK" >/dev/null 2>&1; then
    say "  ok    no dark sessions / stranded jobs"
  else
    prob "  DARK  dark-work-check.sh RED — dark session or stranded job (run: fleet/dark-work-check.sh)"
    wd_surface P1 "dark-work" "watchdog: dark-work-check.sh RED (dark session or stranded job)"
    RED=1
  fi
}

case "$LEGS" in
  health)   leg_health ;;
  discover) leg_discover ;;
  all)      leg_health; leg_discover; leg_dark ;;
esac

if [ "$JSON" -eq 1 ]; then printf '{"red":%s}\n' "$RED"; fi
if [ "$RED" -eq 0 ]; then say "== watchdog: CLEAN =="; exit 0
else printf '== watchdog: RED — see problems above ==\n'; exit 1; fi
