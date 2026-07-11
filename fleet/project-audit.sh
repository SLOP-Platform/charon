#!/usr/bin/env bash
# project-audit.sh — SCAN before you BUILD.
#
# Mechanizes the standing directive [project-start-audit-and-resequence]: before
# authoring a brief, un-parking a ticket, or launching a build, confirm the work
# is not ALREADY scheduled (board ticket / open branch) or DONE (merged commits /
# existing brief). Stops a session from re-speccing or colliding with prior work.
#
#   project-audit.sh <TICKET-or-keyword> [repo]   # collision scan for ONE work-item
#   project-audit.sh                              # landscape: active tickets + open feat/ branches
#
# Exit: 0 = clean (safe to author/build) · 2 = PRIOR WORK found (reconcile first) · 3 = usage
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET="$HERE"
BOARD="$FLEET/board"
PROMPTS="$(dirname "$FLEET")/prompts"
REPO="${2:-/home/stack/code/charon}"

# lowercase + spaces/underscores -> dashes (TICKET name -> branch/brief form)
lc(){ printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr ' _' '--'; }

branch_state(){ # <branch> -> "MERGED/stale" | "<n> AHEAD (unmerged!)"
  local b="$1" out ahead
  out="$(git -C "$REPO" rev-list --left-right --count "origin/master...$b" 2>/dev/null)" || { echo "?"; return; }
  ahead="$(printf '%s' "$out" | awk '{print $2}')"
  [ "${ahead:-0}" = "0" ] && echo "MERGED/stale" || echo "$ahead AHEAD (unmerged!)"
}

landscape(){
  echo "== IN-FLIGHT LANDSCAPE =="
  echo "-- active board tickets (unparked) --"
  local any=0
  if [ -d "$BOARD" ]; then
    while IFS= read -r f; do any=1; echo "   ${f%.md}"; done < <(ls "$BOARD" 2>/dev/null | grep '\.md$' | grep -v '\.parked$' | sort)
  fi
  [ "$any" = 0 ] && echo "   (none)"
  echo "-- open feat/ branches in $REPO --"
  any=0
  while IFS= read -r b; do
    [ -z "$b" ] && continue; any=1
    printf '   %-42s %s\n' "$b" "$(branch_state "$b")"
  done < <(git -C "$REPO" for-each-ref --format='%(refname:short)' refs/heads/feat 2>/dev/null)
  [ "$any" = 0 ] && echo "   (none)"
  echo
  echo "Before authoring a brief: project-audit.sh <TICKET>"
}

audit_one(){
  local name="$1" lcname; lcname="$(lc "$name")"
  local found=0
  echo "== AUDIT: $name   (repo $REPO) =="
  printf '%-12s %s\n' "SIGNAL" "FINDING"

  # 1) board ticket (active or parked)
  local bt=""; [ -d "$BOARD" ] && bt="$(ls "$BOARD" 2>/dev/null | grep -i "^${name}\(\.\|-\|_\)" | head -1)"
  if [ -n "$bt" ]; then printf '%-12s %s\n' "board" "TICKET EXISTS -> board/$bt"; found=1
  else printf '%-12s %s\n' "board" "none"; fi

  # 2) existing brief in prompts/
  local pb=""; [ -d "$PROMPTS" ] && pb="$(ls "$PROMPTS" 2>/dev/null | grep -i "$lcname" | head -1)"
  if [ -n "$pb" ]; then printf '%-12s %s\n' "brief" "BRIEF EXISTS -> prompts/$pb"; found=1
  else printf '%-12s %s\n' "brief" "none"; fi

  # 3) branch (any name containing the keyword)
  local br=""; br="$(git -C "$REPO" for-each-ref --format='%(refname:short)' refs/heads 2>/dev/null | grep -i "$lcname" | head -1)"
  if [ -n "$br" ]; then printf '%-12s %s\n' "branch" "BRANCH EXISTS -> $br [$(branch_state "$br")]"; found=1
  else printf '%-12s %s\n' "branch" "none"; fi

  # 4) prior commits referencing the name (and whether any are on master)
  local commits; commits="$(git -C "$REPO" log --oneline --all -i --grep="$name" 2>/dev/null | head -8)"
  if [ -n "$commits" ]; then
    printf '%-12s %s\n' "commits" "PRIOR COMMITS reference this name:"
    while IFS= read -r l; do echo "             $l"; done <<< "$commits"
    if [ -n "$(git -C "$REPO" log --oneline master -i --grep="$name" 2>/dev/null | head -1)" ]; then
      echo "             ^ at least one is ON MASTER (work already shipped)"
    fi
    found=1
  else printf '%-12s %s\n' "commits" "none"; fi

  echo
  if [ "$found" = 1 ]; then
    echo "RESULT: PRIOR WORK FOUND — reconcile against it before authoring/launching (do NOT redo/collide)."
    return 2
  fi
  echo "RESULT: clean — no scheduled/done work for '$name'. Safe to author."
  return 0
}

case "${1:-}" in
  "")        landscape; exit 0;;
  -h|--help) echo "usage: project-audit.sh <TICKET-or-keyword> [repo]"; exit 3;;
  *)         audit_one "$1"; exit $?;;
esac
