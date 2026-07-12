#!/usr/bin/env bash
# cg-drift.sh — tally of CG-attributed PROCESS-DISCIPLINE failures + the "wake
# trigger" for the DEFERRED gateway contract-injection (PROPOSAL §5 step-3).
#
# WHY: we deferred runtime behavioral steering of CG sessions (gateway inject) on
# blast-radius grounds, betting the STATIC-doc doctrine would steer well enough.
# This gate proves/disproves that bet with evidence: every time CI or the
# land-push gate rejects CG-produced work for a discipline reason (false-green,
# missing review, collision), log it here. When >= THRESHOLD land within WINDOW
# days, the static doctrine is demonstrably NOT steering CG -> `check` FAILS
# LOUDLY and points at the deferred fix. See memory
# [charon-gateway-contract-inject-deferred] + board GATEWAY-CONTRACT-INJECT.
#
#   cg-drift.sh log <ticket> <discipline>   # append one drift event (date auto)
#   cg-drift.sh check                        # exit 2 + LOUD if >=THRESHOLD in WINDOW; else 0
#   cg-drift.sh list                         # show events currently in window
#
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TALLY="$HERE/state/cg-drift.tsv"
THRESHOLD=2          # operator-set 2026-07-11
WINDOW_DAYS=30
PROPOSAL="fleet/PROPOSAL-SESSION-GUARDRAILS.md"
mkdir -p "$(dirname "$TALLY")"; touch "$TALLY"

_cutoff(){ date -d "-${WINDOW_DAYS} days" +%Y-%m-%d 2>/dev/null || echo "0000-00-00"; }
# dates are YYYY-MM-DD (lexicographically sortable) -> string compare is date compare
_in_window(){ awk -F'\t' -v c="$(_cutoff)" 'NF>=2 && $1 >= c' "$TALLY" 2>/dev/null; }

cmd_log(){
  local ticket="${1:?usage: cg-drift.sh log <ticket> <discipline>}" disc="${2:?need discipline (scan|review|false-green|collision|docs-over-code)}"
  printf '%s\t%s\t%s\n' "$(date +%Y-%m-%d)" "$ticket" "$disc" >> "$TALLY"
  echo "cg-drift logged: $(date +%Y-%m-%d)  $ticket  $disc"
}

cmd_list(){ echo "cg-drift events in last ${WINDOW_DAYS}d:"; _in_window | sed 's/^/  /'; }

cmd_check(){
  local n; n="$(_in_window | grep -c . || true)"
  if [ "${n:-0}" -ge "$THRESHOLD" ]; then
    echo "DETECTED: cg-drift — ${n} CG discipline-failure(s) in ${WINDOW_DAYS}d (threshold ${THRESHOLD})."
    echo "    Static-doc doctrine is NOT steering CG. The DEFERRED gateway contract-injection"
    echo "    ($PROPOSAL step-3) is now WARRANTED — build it HARDENED: flag-guarded, try/except"
    echo "    fail-open, byte-identical-off. Un-park board/GATEWAY-CONTRACT-INJECT."
    _in_window | sed 's/^/      /'
    return 2
  fi
  echo "clean: cg-drift (${n:-0}/${THRESHOLD} in ${WINDOW_DAYS}d — deferred gateway inject not yet warranted)"
  return 0
}

case "${1:-check}" in
  log)   shift; cmd_log "$@";;
  list)  cmd_list;;
  check) cmd_check;;
  *) echo "usage: cg-drift.sh {log <ticket> <discipline>|check|list}" >&2; exit 3;;
esac
