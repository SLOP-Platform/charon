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
# ROOT CAUSE (2026-07-23): loop-guard silently starved the priority ladder. When a droid
# claimed a ticket and produced ZERO commits due to an INFRA FAULT (pool exhaustion, RED
# board, gateway reset — anything not the ticket's fault), loop-guard quarantined it anyway.
# Those quarantined tickets were silently skipped by claim.sh → P0/P1 tabs dropped past them
# to un-quarantined economy work, with zero visible signal. The priority ladder was starved.
#
# CONTRACT: fleet-droid.sh calls `record <id> <droid>` on EVERY zero-commit release. After
# N (default 2) zero-commit releases of the SAME id within one droid run, the id is
# QUARANTINED via a durable `state/loop-guard/<id>` marker (which claim.sh skips) and an
# escalation is emitted on stderr. `record` exits 2 when it quarantines, 0 otherwise.
# The manager clears it with `clear <id>` once the underlying block is fixed.
#
# INFRA-FAULT EXEMPTION (2026-07-23): record accepts an optional `--reason <reason>` flag.
# When the reason is an INFRA classification (exhausted, pool-too-thin, red-board,
# gateway-reset, launcher-refused — anything the launcher/charon-run already attributes as
# provider/infra and NOT model-quality), the zero-commit release does NOT count toward the
# quarantine threshold. The release IS still tracked (separate infra counter, for
# observability), but it will NEVER quarantine — infra faults retry silently. No --reason
# (backward-compatible) OR --reason genuine counts toward quarantine as before.
#
# Per-run counts live under state/loop-guard/runs/<droid>/<id> (droid id carries the PID, so
# each run counts independently). fleet-droid.sh removes its run dir on exit.
# Infra-only counters live under state/loop-guard/infra/<id> (never cause quarantine).
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$FLEET/state"; LG="$STATE/loop-guard"
usage(){ echo "usage: loop-guard.sh {record <id> <droid> [threshold] [--reason <reason>] | clear <id> | list}" >&2; exit 2; }

# infra_reason <reason> -> 0 if the reason is an infra/provision failure, not ticket quality.
infra_reason(){
  local r="${1:-}"
  [ -z "$r" ] && return 1
  case "${r,,}" in
    infra|infra-fault|exhausted|all-exhausted|pool-exhausted|pool-too-thin|gateway-reset|\
    gateway-5xx|red-board|red-board-blocked-claim|launcher-refused|provider-exhausted|\
    leg-fault|provider-fault|provider-side|salvage-stash) return 0 ;;
    genuine|model-fault|ticket-fault) return 1 ;;
    *) return 1 ;;   # unknown -> safe default: treat as genuine (quarantine)
  esac
}

cmd="${1:-}"; shift 2>/dev/null || true
case "$cmd" in
  record)
    id="${1:?record needs <id>}"; droid="${2:?record needs <droid>}"; shift 2 2>/dev/null || true
    reason="" thresh="2"
    while [ $# -gt 0 ]; do
      case "$1" in
        --reason) reason="${2:-}"; shift 2 ;;
        --reason=*) reason="${1#*=}"; shift ;;
        ''|*[!0-9]*) : ;;
        *) thresh="$1"; shift ;;
      esac
    done
    if [ -n "$reason" ] && infra_reason "$reason"; then
      mkdir -p "$LG/infra"
      cf="$LG/infra/$id"
      n=0; [ -f "$cf" ] && n="$(cat "$cf" 2>/dev/null || echo 0)"
      n=$((n+1)); printf '%s' "$n" > "$cf"
      echo "loop-guard: '$id' zero-commit release #${n} — reason=$reason (INFRA: never quarantines, retry later)." >&2
      exit 0
    fi
    mkdir -p "$LG/runs/$droid"
    cf="$LG/runs/$droid/$id"
    n=0; [ -f "$cf" ] && n="$(cat "$cf" 2>/dev/null || echo 0)"
    n=$((n+1)); printf '%s' "$n" > "$cf"
    qreason="${reason:-repeated zero-commit re-claims (claim->no-op->release spin)}"
    if [ "$n" -ge "$thresh" ]; then
      printf 'droid=%s\ncount=%s\nthreshold=%s\nquarantined=%s\nreason=%s\n' \
        "$droid" "$n" "$thresh" "$(date -u +%FT%TZ)" "$qreason" > "$LG/$id"
      echo "LOOP-GUARD ESCALATION: '$id' claimed+released with ZERO commits ${n}x by $droid — QUARANTINED (claim.sh will skip it). Manager: fix the block (park/dep), then run 'fleet/loop-guard.sh clear $id'." >&2
      exit 2
    fi
    echo "loop-guard: '$id' zero-commit release ${n}/${thresh} (droid $droid, reason=$qreason) — one more triggers quarantine." >&2
    exit 0
    ;;
  clear)
    id="${1:?clear needs <id>}"
    rm -f "$LG/$id" "$LG/infra/$id"
    echo "loop-guard: cleared quarantine for '$id' (re-claimable)."
    ;;
  list)
    qc=0 ic=0
    for f in "$LG"/*; do
      [ -f "$f" ] || continue
      qc=$((qc+1))
      echo "QUARANTINED $(basename "$f"): $(head -1 "$f" 2>/dev/null)"
    done
    for f in "$LG/infra"/*; do
      [ -e "$f" ] || continue
      [ -f "$f" ] || continue
      ic=$((ic+1))
      n="$(cat "$f" 2>/dev/null || echo 0)"
      echo "INFRA-RETRY $(basename "$f"): ${n}x infra-fault zero-commit (never quarantined)"
    done
    echo "loop-guard: $qc quarantined, $ic infra-tracked."
    ;;
  *) usage;;
esac
