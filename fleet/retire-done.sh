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
# shellcheck source=/dev/null
source "$FLEET/_lib.sh"   # verify_merged — G3c: never retire an UNVERIFIED done marker off the board.
[ -d "$DONE" ] || { echo "retire-done: no state/done dir — nothing to do"; exit 0; }
mkdir -p "$ARCHIVE"

# G3c guard: a marker is safe to retire (archive board + remove worktree) ONLY when it is
# merge-verified OR carries an explicit operator override. An unverified `done` over stranded/
# unlanded work must stay VISIBLE on the active board (and its worktree kept) so preflight's
# done_merge_gate red is actionable, never hidden by archival.
retire_safe(){
  local mk="$1" tid="$2"
  grep -q 'override:' "$mk" 2>/dev/null && return 0
  verify_merged "$tid" && return 0
  return 1
}

# FAST PATH: an optional <id> arg retires ONLY that ticket, skipping the full
# O(all-markers) re-verify sweep. done.sh passes its own id so one done-mark is O(1)
# instead of re-checking every historical marker — many of which carry only merged:#PR
# (no sha), forcing a network `gh` round-trip in verify_merged. No arg = full reconcile.
ONLY_ID="${1:-}"
if [ -n "$ONLY_ID" ]; then DONE_MARKERS=("$DONE/$ONLY_ID"); else DONE_MARKERS=("$DONE"/*); fi

n=0
for m in "${DONE_MARKERS[@]}"; do
  [ -f "$m" ] || continue
  id="$(basename "$m")"
  if ! retire_safe "$m" "$id"; then
    echo "  HELD (not retired): $id — done marker NOT merge-verified (see preflight done-merge-gate: done-unmerged-*)"
    continue
  fi
  if [ -f "$BOARD/$id.md" ]; then
    if git -C "$FLEET" mv "board/$id.md" "board/archive/$id.md" 2>/dev/null; then :; else
      mv "$BOARD/$id.md" "$ARCHIVE/$id.md"; fi
    n=$((n+1)); echo "  retired: $id -> board/archive/"
  fi
done
if [ "$n" -gt 0 ]; then echo "retire-done: archived $n done ticket(s) off the active board"
else echo "retire-done: clean (no done ticket left on the active board)"; fi

# WORKTREE CLEANUP (guarded, #3): a done ticket's PR is merged, so its `charon-fleet-<id>`
# worktree's commits are in master and it is safe to remove — this also feeds the force-remove-
# destroys-needs-push hazard when left around. safe_worktree_remove (leak-guard.sh) REFUSES to
# remove any worktree that still has a live state/needs-push/<id> marker, so committed-but-
# unlanded work is never destroyed. Idempotent: no-op when the worktree is already gone.
CHARON="/home/stack/code/charon"
NPDIR="$FLEET/state/needs-push"
if [ -f "$FLEET/leak-guard.sh" ]; then
  source "$FLEET/leak-guard.sh"
  wtn=0
  for m in "${DONE_MARKERS[@]}"; do
    [ -f "$m" ] || continue
    id="$(basename "$m")"; wt="$CHARON-fleet-$id"
    [ -e "$wt" ] || continue
    retire_safe "$m" "$id" || { echo "  worktree kept: $wt — $id done marker NOT merge-verified"; continue; }
    if safe_worktree_remove "$CHARON" "$wt" "$id" "$NPDIR"; then
      wtn=$((wtn+1)); echo "  worktree removed: $wt (ticket done)"
    fi
  done
  [ "$wtn" -gt 0 ] && echo "retire-done: cleaned $wtn done-ticket worktree(s)"
fi
exit 0
