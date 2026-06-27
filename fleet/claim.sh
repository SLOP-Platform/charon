#!/usr/bin/env bash
# Atomically claim the next board ticket for a droid of <tier>.
# Prints "CLAIMED <id> <board-file>" and exits 0, or "NONE" and exits 1.
# Tier rule: a droid may claim a ticket at-or-below its tier; prefers its OWN tier
# first, then drops to lower tiers (so a freed Opus droid helps drain Sonnet/Haiku).
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"; STATE="$FLEET/state"; LOCK="$STATE/lock"
mkdir -p "$STATE/claims" "$STATE/submitted" "$STATE/done"; : >>"$LOCK"
TIER="${1:?usage: claim.sh <tier> <droid> [both|own-only]}"; DROID="${2:?usage: claim.sh <tier> <droid> [both|own-only]}"
MODE="${3:-both}"
case "$MODE" in both|own-only) ;; *) echo "usage: claim.sh <tier> <droid> [both|own-only]" >&2; exit 2;; esac
source "$FLEET/_lib.sh"
rank(){ case "$1" in opus) echo 3;; sonnet) echo 2;; haiku) echo 1;; *) echo 0;; esac; }
meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2"; }
drank=$(rank "$TIER")
exec 9>"$LOCK"; flock 9
passes="own lower"; [ "$MODE" = own-only ] && passes="own"
for pass in $passes; do
  for f in "$BOARD"/*.md; do
    [ -e "$f" ] || continue
    id="$(basename "$f" .md)"
    [ -e "$STATE/claims/$id" ] && continue
    [ -e "$STATE/submitted/$id" ] && continue
    [ -e "$STATE/done/$id" ] && continue
    ttier="$(meta tier "$f")"; trank=$(rank "$ttier")
    [ "$trank" -le "$drank" ] || continue
    if [ "$pass" = own ]; then [ "$ttier" = "$TIER" ] || continue
    else [ "$ttier" = "$TIER" ] && continue; fi
    dep="$(meta depends_on "$f")"
    deps_done "$dep" || continue
    printf '%s %s\n' "$DROID" "$(date -u +%FT%TZ)" > "$STATE/claims/$id"
    echo "CLAIMED $id $f"; exit 0
  done
done
echo "NONE"; exit 1
