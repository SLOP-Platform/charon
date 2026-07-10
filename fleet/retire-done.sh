#!/usr/bin/env bash
# retire-done.sh — MECHANIZES ticket CLOSURE so done tickets can never accumulate
# as "active" on the board (90 had piled up by 2026-07-10).
#
# For every state/done/<id> marker (written by done.sh ONLY on a VERIFIED merged PR),
# move the still-active board/<id>.md into board/archive/ so `board/*.md` reflects ONLY
# OPEN work. Idempotent and safe to run repeatedly.
#
# Called from TWO places so closure is mechanical, not manual:
#   - done.sh  — retires a ticket the instant it is marked done (the transition point).
#   - preflight.sh — backfill / safety-net every session (catches --no-verify closes,
#     manual markers, or anything that slipped).
#
# Done tickets remain valid depends_on targets: validate_board.sh reads state/done into
# `done_ids`, so archiving does NOT break dependents.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DONE="$FLEET/state/done"; BOARD="$FLEET/board"; ARCHIVE="$BOARD/archive"
[ -d "$DONE" ] || { echo "retire-done: no state/done dir — nothing to do"; exit 0; }
mkdir -p "$ARCHIVE"
n=0
for m in "$DONE"/*; do
  [ -f "$m" ] || continue
  id="$(basename "$m")"
  if [ -f "$BOARD/$id.md" ]; then
    if git -C "$FLEET" mv "board/$id.md" "board/archive/$id.md" 2>/dev/null; then :; else
      mv "$BOARD/$id.md" "$ARCHIVE/$id.md"; fi
    n=$((n+1)); echo "  retired: $id -> board/archive/"
  fi
done
if [ "$n" -gt 0 ]; then echo "retire-done: archived $n done ticket(s) off the active board"
else echo "retire-done: clean (no done ticket left on the active board)"; fi
exit 0
