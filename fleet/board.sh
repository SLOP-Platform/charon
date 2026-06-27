#!/usr/bin/env bash
# MANAGER status view of the board.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; B="$FLEET/board"; S="$FLEET/state"
source "$FLEET/_lib.sh"
meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2"; }
printf '%-6s %-8s %-22s %-10s %s\n' ID TIER BRANCH STATE DEP
for f in "$B"/*.md; do
  [ -e "$f" ] || continue; id="$(basename "$f" .md)"; dep="$(meta depends_on "$f")"
  if   [ -e "$S/done/$id" ];      then st=DONE
  elif [ -e "$S/submitted/$id" ]; then st=PR-OPEN
  elif [ -e "$S/needs-push/$id" ]; then st="NEEDS-PUSH"
  elif [ -e "$S/claims/$id" ];    then st="claimed:$(awk '{print $1}' "$S/claims/$id")"
  elif ! deps_done "$dep"; then st="blocked"
  else st=ready; fi
  printf '%-6s %-8s %-22s %-10s %s\n' "$id" "$(meta tier "$f")" "$(meta branch "$f")" "$st" "${dep:-—}"
done
