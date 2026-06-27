#!/usr/bin/env bash
# THE ONE COMMAND PER TAB.  Usage:  fleet-droid.sh <opus|sonnet|haiku>
# Loops: claim a ticket for this tier -> run ONE ephemeral claude session on it
# (it makes a worktree, does the work, opens a DRAFT PR base=master, never merges)
# -> mark submitted -> claim the next.  Stops when no tier-eligible work remains.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIER="${1:?usage: fleet-droid.sh <opus|sonnet|haiku>}"
case "$TIER" in opus) MODEL=opus;; sonnet) MODEL=sonnet;; haiku) MODEL=haiku;;
  *) echo "tier must be opus|sonnet|haiku"; exit 2;; esac
DROID="$TIER-$$"; current=""
# Release the in-flight claim if the tab is Ctrl-C'd / killed (no stuck tickets).
cleanup(){ if [ -n "${current:-}" ] && [ ! -e "$FLEET/state/submitted/$current" ]; then
  bash "$FLEET/release.sh" "$current" >/dev/null 2>&1 || true; fi; }
trap 'cleanup; echo "[$DROID] stood down."; exit 130' INT TERM
trap cleanup EXIT
echo "[$DROID] charon-fleet droid up (model=$MODEL). Ctrl-C to stand down."
while true; do
  if ! res="$(bash "$FLEET/claim.sh" "$TIER" "$DROID")"; then
    echo "[$DROID] no $TIER-eligible work left — standing down."; break
  fi
  read -r _tag id tfile <<<"$res"; current="$id"
  echo "[$DROID] claimed $id — launching session…"
  pfile="$(awk -F': ' '$1=="prompt"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  spec="$(cat "$tfile"; echo; echo '--- WORK SPEC ---'; cat "$pfile" 2>/dev/null || echo '(no prompt file)')"
  prompt="$(cat "$FLEET/JOIN-PROMPT.md")

=== YOUR ASSIGNED TICKET: $id ===
$spec"
  if claude -p --model "$MODEL" --dangerously-skip-permissions "$prompt"; then
    bash "$FLEET/submit.sh" "$id" || true; current=""
    echo "[$DROID] $id submitted (PR open). Next…"
  else
    bash "$FLEET/release.sh" "$id" || true; current=""
    echo "[$DROID] $id session exited non-zero — released for retry."
  fi
done
