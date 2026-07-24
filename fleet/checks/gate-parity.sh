#!/usr/bin/env bash
# gate-parity.sh — LAND-LAUNCH PARITY GATE (build-rig only).
# Closes the root-cause gap that let the strong pool deadlock on 2026-07-23: the LAND gate
# (validate_board.sh:385-399) treated the parallelizability gate as ADVISORY (WCI, non-blocking),
# while the LAUNCH path (launch-plan.sh:168, fleet-droid.sh:316-336) enforced the SAME gate
# HARD (refuses launch). So a ticket could pass land, be refused at claim/launch, spin
# zero-commit, and get loop-guard-quarantined — wedging it and re-REDing the board.
#
# ROOT PRINCIPLE: land-gate MUST be >= launch-gate — nothing lands that the launcher would
# refuse. This check re-runs EVERY launch-refusal predicate the launcher applies and FAILS
# HARD (RED, exit non-zero) at LAND time if a board ticket would be refused at launch.
# A ticket that passes gate-parity.sh CAN be launched. Fail-CLOSED: an unrunnable predicate
# (missing binary, timeout, parse error) => RED — never silently pass through.
#
# PREDICATE SET (explicit + extensible — add new predicates to GATE_PREDICATES array):
#   P1) parallelizability-gate — delegates to fleet/checks/parallelizability-gate.sh check
#       <tid>. If exit != 0 and exit != 2 (usage error), the ticket is SPLITTABLE-UNDECOMPOSED
#       and would be refused by BOTH launch-plan.sh and fleet-droid.sh at claim time.
#
# Usage:
#   gate-parity.sh check <ticket-id>
#       Exit 0 = PASS (ticket would NOT be refused at launch).
#       Exit 1 = FAIL (ticket WOULD be refused — parity gap).
#       Exit 2 = usage/internal error.
#   gate-parity.sh scan
#       Board-wide scan of all LIVE tickets. Runs every predicate on every ticket.
#       Prints one FAIL line per predicate per offending ticket.
#       Exit 0 = no ticket would be refused (parity holds).
#       Exit 1 = >=1 ticket would be refused (parity gap — RED).
#       Exit 2 = internal error.
#
# Env overrides (isolated self-test seams; defaults are the real fleet):
#   GATE_PARITY_BOARD          board dir (default <fleet>/board)
#   GATE_PARITY_DONE_DIR       done-marker dir (default <fleet>/state/done)
#   GATE_PARITY_PARGATE        path to parallelizability-gate.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # fleet/
BOARD="${GATE_PARITY_BOARD:-$HERE/board}"
DONE_DIR="${GATE_PARITY_DONE_DIR:-$HERE/state/done}"
PARGATE="${GATE_PARITY_PARGATE:-$HERE/checks/parallelizability-gate.sh}"

# --- helpers (self-contained; no dependency on _lib.sh) ----------------------------------
field(){
  local raw; raw="$(grep -m1 -E "^[[:space:]]*$2:" "$1" 2>/dev/null || true)"
  printf '%s' "$raw" | sed -E "s/^[[:space:]]*$2:[[:space:]]*//; s/[[:space:]]+\$//"
}
lc(){ printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

is_parked(){
  local f="$1" pf note
  pf="$(lc "$(field "$f" parked)")"
  case "$pf" in true|yes|1) return 0 ;; esac
  note="$(field "$f" note)"
  printf '%s' "$note" | grep -qi PARKED && return 0
  return 1
}

# --- predicate definitions --------------------------------------------------------------
# Each predicate is a function named pred_<name> that receives a ticket id and prints
# "<name>: <message>" to stdout on FAIL; returns 0=PASS, 1=FAIL, 2=ERROR.
# GATE_PREDICATES is a newline-separated list of "pred_<funcname>" entries — explicit and
# extensible: add a pred_* function and append its name here.

pred_parallelizability(){
  local id="$1"
  local out rc
  out="$(PARALLEL_GATE_BOARD="$BOARD" PARALLEL_GATE_DONE_DIR="$DONE_DIR" \
         bash "$PARGATE" check "$id" 2>&1)"; rc=$?
  if [ "$rc" -eq 2 ]; then
    echo "parallelizability: ERROR running parallelizability-gate.sh check $id (exit 2) — $out"
    return 2
  elif [ "$rc" -ne 0 ]; then
    echo "parallelizability: $id would be refused at launch — $out"
    return 1
  fi
  return 0
}

# GATE_PREDICATES — the explicit, extensible list of launch-refusal predicate functions.
# Each function is called as: pred_<name> <ticket-id>; exit 0=PASS, 1=FAIL, 2=ERROR.
# Add new predicates by appending to this list.
GATE_PREDICATES=(
  pred_parallelizability
)

# --- check / scan -----------------------------------------------------------------------
cmd_usage(){
  echo "usage: gate-parity.sh check <ticket-id>" >&2
  echo "       gate-parity.sh scan" >&2
  exit 2
}

cmd_check(){
  local id="${1:-}"; [ -n "$id" ] || cmd_usage
  local tf="$BOARD/$id.md"
  [ -f "$tf" ] || { echo "gate-parity: no such board ticket: $id ($tf)" >&2; exit 2; }

  local any_fail=0 any_err=0
  for pred_fn in "${GATE_PREDICATES[@]}"; do
    local out rc
    out="$("$pred_fn" "$id" 2>&1)"; rc=$?
    if [ "$rc" -eq 2 ]; then
      echo "$out" >&2
      any_err=1
    elif [ "$rc" -ne 0 ]; then
      echo "$out" >&2
      any_fail=1
    fi
  done

  if [ "$any_err" -ne 0 ]; then
    echo "gate-parity: ERROR running one or more predicates on $id — fail-closed (RED)" >&2
    exit 2
  fi
  if [ "$any_fail" -ne 0 ]; then
    echo "gate-parity: FAIL — $id would be refused at launch (parity gap)" >&2
    exit 1
  fi
  echo "gate-parity: OK — $id passes all launch-refusal predicates"
  exit 0
}

cmd_scan(){
  local hits=0 errored=0 tf id
  shopt -s nullglob
  for tf in "$BOARD"/*.md; do
    [ -f "$tf" ] || continue
    id="$(basename "$tf" .md)"
    is_parked "$tf" && continue
    [ -e "$DONE_DIR/$id" ] && continue

    local ticket_fails=0
    for pred_fn in "${GATE_PREDICATES[@]}"; do
      local out rc
      out="$("$pred_fn" "$id" 2>&1)"; rc=$?
      if [ "$rc" -eq 2 ]; then
        echo "  GATE-PARITY: $id — $out" >&2
        errored=1
      elif [ "$rc" -ne 0 ]; then
        echo "  GATE-PARITY: $out"
        ticket_fails=1
      fi
    done
    if [ "$ticket_fails" -ne 0 ]; then
      hits=$((hits+1))
    fi
  done

  if [ "$errored" -ne 0 ]; then
    echo "gate-parity scan: >=1 predicate ERROR (fail-closed) — RED" >&2
    exit 2
  fi
  if [ "$hits" -eq 0 ]; then
    echo "gate-parity scan: OK — no live ticket would be refused at launch (parity holds)."
    exit 0
  else
    echo "gate-parity scan: $hits ticket(s) would be refused at launch — land-launch PARITY GAP (RED)."
    exit 1
  fi
}

case "${1:-}" in
  check) shift; cmd_check "$@" ;;
  scan)  shift || true; cmd_scan "$@" ;;
  *) cmd_usage ;;
esac
