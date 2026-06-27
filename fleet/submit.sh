#!/usr/bin/env bash
# Mark a ticket as submitted (PR opened). Run by the droid as its last step.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$FLEET/state"; BOARD="$FLEET/board"
# Canonicalize the id to the exact board basename (case-insensitive) so a case
# mismatch can never fork the marker namespace (audit 2026-06-27, THEME 1).
canon(){ local w="$1" f b; for f in "$BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  echo "submit.sh: no board ticket matching '$w'" >&2; return 1; }
id="$(canon "${1:?usage: submit.sh <id>}")" || exit 2
mkdir -p "$S/submitted"; date -u +%FT%TZ > "$S/submitted/$id"; rm -f "$S/claims/$id"
echo "submitted $id (PR open; awaiting operator merge)"
