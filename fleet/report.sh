#!/usr/bin/env bash
# report.sh — render the ONE canonical fleet roadmap report from ROADMAP.tsv.
#
# This is the single source of the status/task-list/handoff format. Do NOT hand-type
# roadmap status anywhere else — edit fleet/state/ROADMAP.tsv and re-run this.
#
# Usage:
#   fleet/report.sh            full grouped tree (grouped by PROJECT, input order kept)
#   fleet/report.sh --terse    one line per item, flat (greppable)
#
# Data:  fleet/state/ROADMAP.tsv   (override with ROADMAP_TSV=/path for tests)
# Fields (tab-separated): project<TAB>id<TAB>status<TAB>phase<TAB>name<TAB>goal<TAB>wave
#   - wave (7th field, optional): "Wave A" / "Wave B" / ... — groups items inside a project.
#     If ANY item in a project has a wave, that project renders with wave sub-headers and
#     wave-less items fall under an "Unscheduled" sub-header. Projects with NO waves render FLAT.
# status: done in-review building queued designed parked not-started
#
# The status column + phase word are DERIVED from status (single source of truth):
#   done     -> ✅ status symbol  +  "Done" phase word
#   building -> 🟠 + "now"
#   any other-> colored circle (🔵/🟡/🟣/🟤/⚪) + "next"
# The 4th TSV field (phase) is retained for back-compat/greppability but the renderer
# derives the displayed phase word from status.
#
# Output is ASCII except the status symbols. PROJECT numbers are assigned by project
# order-of-first-appearance. Reverting the renderer breaks
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
function statsym(s) {
  if (s=="done")        return "✅"
  if (s=="in-review")   return "🔵"
  if (s=="building")    return "🟠"
  if (s=="queued")      return "🟡"
  if (s=="designed")    return "🟣"
  if (s=="parked")      return "🟤"
  if (s=="not-started") return "⚪"
  return "?"
}
function phaseword(s) {
  if (s=="done")     return "Done"
  if (s=="building") return "now"
  return "next"
}
/^[[:space:]]*#/ { next }   # comment lines
/^[[:space:]]*$/ { next }   # blank lines
{
  proj=$1; id=$2; st=$3; phase=$4; name=$5; goal=$6; wave=$7
  if (!(proj in seen)) { seen[proj]=1; order[++np]=proj }
  n = ++cnt[proj]
  P[proj,n,"id"]=id; P[proj,n,"st"]=st
  P[proj,n,"name"]=name; P[proj,n,"goal"]=goal; P[proj,n,"wave"]=wave
  if (wave != "") haswave[proj]=1
  tally[st]++
  pw = phaseword(st)
  if (length(id)    > widID)    widID    = length(id)
  if (length(name)  > widName)  widName  = length(name)
  if (length(proj)  > widProj)  widProj  = length(proj)
  if (length(pw)    > widPhase) widPhase = length(pw)
}
END {
  if (np == 0) { print "report.sh: ROADMAP has no rows" > "/dev/stderr"; exit 1 }

  if (terse) {
    for (i=1; i<=np; i++) {
      proj = order[i]
      for (n=1; n<=cnt[proj]; n++) {
        st = P[proj,n,"st"]
        printf "%s  %-*s  %-*s  %-*s   %-*s   %s\n", \
          statsym(st), widPhase, phaseword(st), \
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
    printf "\n"                                     # blank line between projects
    printf "PROJECT %d — %s\n", i, toupper(proj)
    printf "\n"                                     # ONE blank line after EVERY header

    if (proj in haswave) {
      # ordered list of distinct wave labels (order-of-first-appearance; ""->Unscheduled)
      wc = 0
      delete worder
      delete wseen
      for (n=1; n<=cnt[proj]; n++) {
        w = P[proj,n,"wave"]
        label = (w=="") ? "Unscheduled" : w
        if (!(label in wseen)) { wseen[label]=1; worder[++wc]=label }
      }
      for (wi=1; wi<=wc; wi++) {
        label = worder[wi]
        printf "  %s\n", label
        for (n=1; n<=cnt[proj]; n++) {
          w = P[proj,n,"wave"]; il = (w=="") ? "Unscheduled" : w
          if (il == label) render_item(proj, n)
        }
      }
    } else {
      for (n=1; n<=cnt[proj]; n++) render_item(proj, n)
    }
  }

  # Legend + tally footer (order matches the status-symbol legend).
  print ""
  split("done in-review building queued designed parked not-started", ord, " ")
  line = "Totals:"
  for (k=1; k<=7; k++) { s=ord[k]; c=(s in tally)?tally[s]:0; line = line sprintf("  %s %s=%d", statsym(s), s, c) }
  print line
}
function render_item(proj, n,   st) {
  st = P[proj,n,"st"]
  printf "    %s  %-*s  %-*s   %-*s   %s\n", \
    statsym(st), widPhase, phaseword(st), \
    widID, P[proj,n,"id"], \
    widName, P[proj,n,"name"], P[proj,n,"goal"]
}
' "$ROADMAP"
