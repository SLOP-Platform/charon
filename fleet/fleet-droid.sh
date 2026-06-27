#!/usr/bin/env bash
# THE ONE COMMAND PER TAB.  Usage:  fleet-droid.sh <opus|sonnet|haiku> [--wait <min>] [--retries <n>]
# Loops: claim a ticket for this tier -> run ONE ephemeral claude session on it (worktree, work,
# DRAFT PR base=master, never merges) -> mark submitted -> claim the next. Stands down when no
# tier-eligible work remains.
#
# SELF-FEEDING POOL (--wait): instead of standing down on an empty claim, sleep <min> minutes and
# re-check, up to <n> CONSECUTIVE empty checks (default 6), THEN stand down. Finding work resets
# the counter. An idle tab is just a sleeping shell — no model session burns until it claims. So
# open the pool of tabs ONCE; each rides through dependency gaps (grabbing the next ticket the
# instant a merge unblocks it) and drains to a clean exit when the board is done. No per-ticket
# hand-launching; the manager stays gate-only.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
usage(){ echo "usage: fleet-droid.sh <opus|sonnet|haiku> [--wait <min>] [--retries <n>]"; exit 2; }
TIER=""; WAIT_MIN=0; RETRIES=6
while [ $# -gt 0 ]; do case "$1" in
  --wait)    WAIT_MIN="${2:?--wait needs minutes}"; shift 2;;
  --retries) RETRIES="${2:?--retries needs a count}"; shift 2;;
  opus|sonnet|haiku) TIER="$1"; shift;;
  *) usage;;
esac; done
[ -n "$TIER" ] || usage
MODEL="$TIER"
DROID="$TIER-$$"; current=""; empties=0
# Release the in-flight claim if the tab is Ctrl-C'd / killed (no stuck tickets).
cleanup(){ if [ -n "${current:-}" ] && [ ! -e "$FLEET/state/submitted/$current" ]; then
  bash "$FLEET/release.sh" "$current" >/dev/null 2>&1 || true; fi; }
trap 'cleanup; echo "[$DROID] stood down."; exit 130' INT TERM
trap cleanup EXIT
wmsg=""; [ "$WAIT_MIN" -gt 0 ] && wmsg=", wait=${WAIT_MIN}m retries=${RETRIES}"
echo "[$DROID] charon-fleet droid up (model=$MODEL$wmsg). Ctrl-C to stand down."
while true; do
  if ! res="$(bash "$FLEET/claim.sh" "$TIER" "$DROID")"; then
    if [ "$WAIT_MIN" -gt 0 ] && [ "$empties" -lt "$RETRIES" ]; then
      empties=$((empties+1))
      echo "[$DROID] no $TIER-eligible work — waiting ${WAIT_MIN}m (empty $empties/$RETRIES)…"
      sleep "$((WAIT_MIN*60))"; continue
    fi
    echo "[$DROID] no $TIER-eligible work left — standing down."; break
  fi
  empties=0
  read -r _tag id tfile <<<"$res"; current="$id"
  echo "[$DROID] claimed $id — launching session…"
  pfile="$(awk -F': ' '$1=="prompt"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  spec="$(cat "$tfile"; echo; echo '--- WORK SPEC ---'; cat "$pfile" 2>/dev/null || echo '(no prompt file)')"
  prompt="$(cat "$FLEET/JOIN-PROMPT.md")

=== YOUR ASSIGNED TICKET: $id ===
$spec"
  if claude -p --model "$MODEL" --dangerously-skip-permissions "$prompt"; then
    if bash "$FLEET/submit.sh" "$id"; then
      current=""; echo "[$DROID] $id submitted (PR open). Next…"
    else
      # submit refused: work committed but no real PR. Keep the claim + worktree (don't let
      # another droid redo it); submit flagged state/needs-push for the manager to land.
      current=""; echo "[$DROID] $id: work committed but NO PR opened — flagged needs-push; manager lands it. Next…"
    fi
  else
    bash "$FLEET/release.sh" "$id" || true; current=""
    echo "[$DROID] $id session exited non-zero — released for retry."
  fi
done
