#!/usr/bin/env bash
# report.sh — render the ONE canonical fleet roadmap report from ROADMAP.tsv.
#
# This is the single source of the status/task-list/handoff format. Do NOT hand-type
# roadmap status anywhere else — edit fleet/state/ROADMAP.tsv and re-run this.
#
# Usage:
#   fleet/report.sh            full grouped tree (grouped by PROGRAM, input order kept)
#   fleet/report.sh --terse    one line per item, flat (greppable)
#
# Data:  fleet/state/ROADMAP.tsv   (override with ROADMAP_TSV=/path for tests)
# Fields (tab-separated): project<TAB>id<TAB>status<TAB>phase<TAB>name<TAB>goal
# status: done in-review building queued designed parked not-started
# phase:  done -> "-"   building -> "now"   everything else -> "next"
#
# Output is ASCII except the status dots. Program numbers are assigned by
# project order-of-first-appearance. Reverting the renderer breaks
# fleet/tests/report-render.test.sh.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROADMAP="${ROADMAP_TSV:-$SELF_DIR/state/ROADMAP.tsv}"

TERSE=0
case "${1:-}" in
  --terse) TERSE=1 ;;
  -h|--help) echo "usage: report.sh [--terse]"; exit 0 ;;
  "") ;;
  *) echo "report.sh: unknown arg '$1' (use --terse)" >&2; exit 2 ;;
esac

[ -f "$ROADMAP" ] || { echo "report.sh: ROADMAP not found: $ROADMAP" >&2; exit 1; }

awk -F'\t' -v terse="$TERSE" '
function dot(s) {
  if (s=="done")        return "🟢"
  if (s=="in-review")   return "🔵"
  if (s=="building")    return "🟠"
  if (s=="queued")      return "🟡"
  if (s=="designed")    return "🟣"
  if (s=="parked")      return "🟤"
  if (s=="not-started") return "⚪"
  return "?"
}
/^[[:space:]]*#/ { next }   # comment lines
/^[[:space:]]*$/ { next }   # blank lines
{
  proj=$1; id=$2; st=$3; phase=$4; name=$5; goal=$6
  if (!(proj in seen)) { seen[proj]=1; order[++np]=proj }
  n = ++cnt[proj]
  P[proj,n,"id"]=id; P[proj,n,"st"]=st; P[proj,n,"phase"]=phase
  P[proj,n,"name"]=name; P[proj,n,"goal"]=goal
  tally[st]++
  if (length(id)    > widID)    widID    = length(id)
  if (length(name)  > widName)  widName  = length(name)
  if (length(proj)  > widProj)  widProj  = length(proj)
  if (length(phase) > widPhase) widPhase = length(phase)
}
END {
  if (np == 0) { print "report.sh: ROADMAP has no rows" > "/dev/stderr"; exit 1 }

  if (terse) {
    for (i=1; i<=np; i++) {
      proj = order[i]
      for (n=1; n<=cnt[proj]; n++) {
        printf "%s  %-*s  %-*s  %-*s   %-*s   %s\n", \
          dot(P[proj,n,"st"]), widPhase, P[proj,n,"phase"], \
          widProj, proj, widID, P[proj,n,"id"], \
          widName, P[proj,n,"name"], P[proj,n,"goal"]
      }
    }
    exit 0
  }

  print "CHARON FLEET ROADMAP"
  print "===================="
  for (i=1; i<=np; i++) {
    proj = order[i]
    hdr = sprintf("PROGRAM %d — %s", i, toupper(proj))
    printf "\n%s\n", hdr
    for (n=1; n<=cnt[proj]; n++) {
      printf "    %s  %-*s  %-*s   %-*s   %s\n", \
        dot(P[proj,n,"st"]), widPhase, P[proj,n,"phase"], \
        widID, P[proj,n,"id"], \
        widName, P[proj,n,"name"], P[proj,n,"goal"]
    }
  }

  # Legend + tally footer (order matches the status-dot legend).
  print ""
  split("done in-review building queued designed parked not-started", ord, " ")
  line = "Totals:"
  for (k=1; k<=7; k++) { s=ord[k]; c=(s in tally)?tally[s]:0; line = line sprintf("  %s %s=%d", dot(s), s, c) }
  print line
}
' "$ROADMAP"
