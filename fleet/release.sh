#!/usr/bin/env bash
# Release a CLAIM so another droid can retry the ticket (abandon / blocker).
# Does NOT clear a `submitted` marker — for a rejected/closed PR use reject.sh.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$FLEET/state"; BOARD="$FLEET/board"
canon(){ local w="$1" f b; for f in "$BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  echo "release.sh: no board ticket matching '$w'" >&2; return 1; }
id="$(canon "${1:?usage: release.sh <id>}")" || exit 2
rm -f "$S/claims/$id"
echo "released $id (claim cleared, re-claimable)"
