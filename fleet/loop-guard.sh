#!/usr/bin/env bash
# loop-guard.sh — break the claim -> no-commit -> release -> re-claim SPIN.
#
# ROOT CAUSE (2026-07-09): a PARKED/blocked ticket kept being re-offered by claim.sh; a
# droid claimed it, the build session correctly refused with ZERO commits, release cleared
# the claim, and the fleet-droid loop RE-CLAIMED THE SAME id — an infinite no-commit loop
# that also STARVED the next ready ticket. claim.sh now skips parked tickets, but a ticket
# can go zero-commit for other reasons (a hard block, a bad prompt); this guard is the
# backstop that stops ANY such spin.
#
# CONTRACT: fleet-droid.sh calls `record <id> <droid>` on EVERY zero-commit release. After
# N (default 2) zero-commit releases of the SAME id within one droid run, the id is
# QUARANTINED via a durable `state/loop-guard/<id>` marker (which claim.sh skips) and an
# escalation is emitted on stderr. `record` exits 2 when it quarantines, 0 otherwise.
# The manager clears it with `clear <id>` once the underlying block is fixed.
#
# Per-run counts live under state/loop-guard/runs/<droid>/<id> (droid id carries the PID, so
# each run counts independently). fleet-droid.sh removes its run dir on exit.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$FLEET/state"; LG="$STATE/loop-guard"
usage(){ echo "usage: loop-guard.sh {record <id> <droid> [threshold] | clear <id> | list}" >&2; exit 2; }

cmd="${1:-}"; shift 2>/dev/null || true
case "$cmd" in
  record)
    id="${1:?record needs <id>}"; droid="${2:?record needs <droid>}"; thresh="${3:-2}"
    mkdir -p "$LG/runs/$droid"
    cf="$LG/runs/$droid/$id"
    n=0; [ -f "$cf" ] && n="$(cat "$cf" 2>/dev/null || echo 0)"
    n=$((n+1)); printf '%s' "$n" > "$cf"
    if [ "$n" -ge "$thresh" ]; then
      printf 'droid=%s\ncount=%s\nthreshold=%s\nquarantined=%s\nreason=repeated zero-commit re-claims (claim->no-op->release spin)\n' \
        "$droid" "$n" "$thresh" "$(date -u +%FT%TZ)" > "$LG/$id"
      echo "LOOP-GUARD ESCALATION: '$id' claimed+released with ZERO commits ${n}x by $droid — QUARANTINED (claim.sh will skip it). Manager: fix the block (park/dep), then run 'fleet/loop-guard.sh clear $id'." >&2
      exit 2
    fi
    echo "loop-guard: '$id' zero-commit release ${n}/${thresh} (droid $droid) — one more triggers quarantine." >&2
    exit 0
    ;;
  clear)
    id="${1:?clear needs <id>}"
    rm -f "$LG/$id"
    echo "loop-guard: cleared quarantine for '$id' (re-claimable)."
    ;;
  list)
    for f in "$LG"/*; do
      [ -f "$f" ] || continue   # skips the runs/ dir
      echo "$(basename "$f"): $(head -1 "$f" 2>/dev/null)"
    done
    ;;
  *) usage;;
esac
