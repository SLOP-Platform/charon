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
# Load tier ranks ONCE, BEFORE flock, from `charon tier ranks` (canonical+aliases,
# alias-folded). Pure data; never spawn Python under the lock. Legacy fallback when
# `charon` is absent/old or tiers.json is unset → unchanged opus/sonnet/haiku ranks.
declare -A RANK; nrank=0
if out="$(charon tier ranks 2>/dev/null)"; then        # "low 1\nmed 2\nhigh 3\nopus 3 ..."
  while read -r n r; do [ -n "$n" ] && { RANK["$n"]=$r; nrank=$((nrank+1)); }; done <<<"$out"
fi
[ "$nrank" -gt 0 ] || RANK=([opus]=3 [sonnet]=2 [haiku]=1)   # legacy, unchanged
rank(){ echo "${RANK[$1]:-0}"; }
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
    # PARK: a ticket explicitly parked in its board file is STAGED, not claimable (gated on
    # an operator/manager decision). Recognize the clean field `parked: true` and, as a
    # fallback, a `note:` whose text contains PARKED. Data-only under the flock (meta = awk;
    # no Python spawned), matching the existing style. This is the fix for the claim-loop:
    # BENCH-OOB-GRADING carried `note: PARKED` but no marker, so it was offered forever.
    case "$(meta parked "$f" | tr 'A-Z' 'a-z')" in true|yes|1) continue;; esac
    case "$(meta note "$f")" in *PARKED*) continue;; esac
    # LOOP-GUARD quarantine: fleet-droid.sh parks an id here after repeated zero-commit
    # re-claims (the claim -> refuse/no-op -> release -> re-claim spin). Manager clears it
    # via fleet/loop-guard.sh clear <id>. (release.sh does NOT remove this marker.)
    [ -e "$STATE/loop-guard/$id" ] && continue
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
