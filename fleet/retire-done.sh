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
# NO-LOCAL-MASTER-COMMITS FIX: archive moves must be STAGED and committed so they do not leave
# the main checkout dirty (which blocks sync-checkouts.sh's FF guard). Collect staged paths so
# board-lock.sh can commit them atomically.
STAGED_PATHS=""
for m in "${DONE_MARKERS[@]}"; do
  [ -f "$m" ] || continue
  id="$(basename "$m")"
  if ! retire_safe "$m" "$id"; then
    echo "  HELD (not retired): $id — done marker NOT merge-verified (see preflight done-merge-gate: done-unmerged-*)"
    continue
  fi
  if [ -f "$BOARD/$id.md" ]; then
    # PLAIN FILESYSTEM mv — deliberately NOT `git mv` (BOARD-WRITE-LOCK, 2026-07-24).
    # `git mv` STAGED the rename into the SHARED main-checkout index and left it sitting there for
    # an arbitrary time. retire-done.sh runs from done.sh AND from preflight.sh, i.e. constantly,
    # under whichever lane happens to be closing a ticket. The next lane to run a bare `git commit`
    # (which takes the WHOLE index, not just its own `git add`ed paths) swept that staged rename
    # into an unrelated commit — that is exactly how a lane's rename was lost on 2026-07-24.
    # An UNSTAGED rename cannot be swept by a bare `git commit`, and the archive move is then
    # committed deliberately through the locked, pathspec-limited choke point (board-lock.sh).
    #
    # NO-LOCAL-MASTER-COMMITS: the UNSTAGED move left fleet/board/ dirty (deleted from board/,
    # new in archive/, not staged). This dirty state blocked sync-checkouts.sh on the next run
    # (DIVERGENCE or TRACKED CHANGES), preventing FF and perpetuating the divergence ratchet.
    # FIX: stage the new archived files immediately so the tree returns to clean.
    # Only stage a file that is genuinely NEW in archive/ — re-retiring an already-archived
    # ticket must not stage an already-tracked file.
    local src="$BOARD/$id.md" dst="$ARCHIVE/$id.md"
    local rel_dst; rel_dst="fleet/board/archive/$id.md"
    [ -f "$dst" ] && ! git ls-files --error-unmatch "$dst" >/dev/null 2>&1 && {
      mv "$src" "$dst"
      git add "$dst"
      STAGED_PATHS="$STAGED_PATHS $rel_dst"
      n=$((n+1)); echo "  retired: $id -> board/archive/ (staged)"
    } || {
      mv "$src" "$dst"
      n=$((n+1)); echo "  retired: $id -> board/archive/ (already tracked)"
    }
  fi
done
if [ "$n" -gt 0 ]; then
  echo "retire-done: archived $n done ticket(s) off the active board"
  # NO-LOCAL-MASTER-COMMITS: commit through board-lock so the tree is left CLEAN (no dirty
  # tracked changes), which allows sync-checkouts.sh to FF on the next run.
  if [ -n "$STAGED_PATHS" ] && [ -x "$FLEET/board-lock.sh" ]; then
    # Use the fleet session so the commit is attributed to the fleet automation.
    # RETIRE_DONE_BYPASS: this auto-admin operation bypasses the main-checkout advisory but still
    # goes through the board lock (which protects the shared index). The archive moves are mechanical
    # cleanup of already-landed work, not board edits that cause the divergence ratchet.
    RETIRE_DONE_BYPASS=1 bash "$FLEET/board-lock.sh" commit \
      --session "fleet-retire-done" \
      -m "board-hygiene: retire done tickets" -- \
      $STAGED_PATHS 2>&1 | sed 's/^/  retire-done: /'
  fi
else echo "retire-done: clean (no done ticket left on the active board)"; fi

# WORKTREE CLEANUP (guarded, #3): a done ticket's PR is merged, so its `charon-fleet-<id>`
# worktree's commits are in master and it is safe to remove — this also feeds the force-remove-
# destroys-needs-push hazard when left around. safe_worktree_remove (leak-guard.sh) REFUSES to
# remove any worktree that still has a live state/needs-push/<id> marker, so committed-but-
# unlanded work is never destroyed. Idempotent: no-op when the worktree is already gone.
#
# REPO-AWARE (2026-07-18): this used to hardcode CHARON=/home/stack/code/charon and derive
# "$CHARON-fleet-$id". The repo-aware verify_merged fix landed in _lib.sh/done.sh but NOT here —
# and this is the DESTRUCTIVE sweep. A `repo: charon-private` ticket's worktree lives at
# /home/stack/charon-private-wt/<id>, so the sweep silently skipped every rig ticket while
# pointing `git -C` at the product repo. Both the repo and the worktree path now come from the
# SAME canonical per-ticket resolution (_lib.sh ticket_repo_path/ticket_worktree_path ->
# repo-registry.sh repo_resolve). NO new map here — a second map IS the drift class just fixed.
# FAIL CLOSED: an unresolvable repo removes NOTHING.
NPDIR="$FLEET/state/needs-push"
if [ -f "$FLEET/leak-guard.sh" ]; then
  source "$FLEET/leak-guard.sh"
  wtn=0
  for m in "${DONE_MARKERS[@]}"; do
    [ -f "$m" ] || continue
    id="$(basename "$m")"
    if ! repo="$(ticket_repo_path "$id")" || [ -z "$repo" ]; then
      echo "  worktree SKIPPED (fail-closed): $id — repo unresolvable (unknown 'repo:' key or no board file); removing nothing" >&2
      continue
    fi
    if ! wt="$(ticket_worktree_path "$id")" || [ -z "$wt" ]; then
      echo "  worktree SKIPPED (fail-closed): $id — worktree path unresolvable for repo $repo; removing nothing" >&2
      continue
    fi
    [ -e "$wt" ] || continue
    retire_safe "$m" "$id" || { echo "  worktree kept: $wt — $id done marker NOT merge-verified"; continue; }
    if safe_worktree_remove "$repo" "$wt" "$id" "$NPDIR"; then
      wtn=$((wtn+1)); echo "  worktree removed: $wt (ticket done)"
    fi
  done
  [ "$wtn" -gt 0 ] && echo "retire-done: cleaned $wtn done-ticket worktree(s)"
fi
exit 0
