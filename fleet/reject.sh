#!/usr/bin/env bash
# Un-submit a ticket whose PR was CLOSED un-merged (rejected / needs re-run).
# Clears BOTH the claim and the submitted marker so the ticket returns to `ready`.
# This is the missing inverse of submit.sh — without it a closed-unmerged PR wedges
# the ticket permanently (audit 2026-06-27, THEME 5). Replaces the manual
# `rm state/submitted/<id>` workaround.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$FLEET/state"; BOARD="$FLEET/board"
canon(){ local w="$1" f b; for f in "$BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  echo "reject.sh: no board ticket matching '$w'" >&2; return 1; }
id="$(canon "${1:?usage: reject.sh <id>}")" || exit 2
if [ -e "$S/done/$id" ]; then
  echo "reject.sh: REFUSED — $id is already DONE (merged). Nothing to un-submit." >&2; exit 3
fi
rm -f "$S/submitted/$id" "$S/claims/$id"
echo "rejected $id (claim + submitted cleared, back to ready)"
