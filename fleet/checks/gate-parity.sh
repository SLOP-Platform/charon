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
# EXIT CODES (matching AUTH-302-SILENT-FAILURE / EVAL-REGISTRY-DERIVE / CRON-REGISTRY-VISIBLE):
#   0  GREEN — all checks passed.
#   1  RED   — a genuine violation (parity gap, FAIL).
#   2  ERROR — internal/unexpected failure (fail-closed; treat as RED).
#   8  UNKNOWN — could not complete (timeout, crash, resource). Only UNKNOWN is budget-exceeded
#       or unavailability; this is DISTINCT from RED (a determined finding) and from GREEN
#       (a determined pass). An UNKNOWN that reads as RED trains operators to ignore REDs;
#       an UNKNOWN that reads as GREEN hides real findings.
#       Refs: #356, AUTH-302-SILENT-FAILURE, EVAL-REGISTRY-DERIVE, CRON-REGISTRY-VISIBLE.
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
#       Exit 8 = UNKNOWN (could not run — timeout or resource exhaustion).
#   gate-parity.sh scan
#       Board-wide scan of all LIVE tickets. Runs every predicate on every ticket.
#       Inlines the predicate logic (single-pass, ~5s for full board) rather than spawning
#       one bash subprocess per ticket (~31s for same board, the class fixed by #375).
#       Prints one FAIL line per predicate per offending ticket.
#       Exit 0 = no ticket would be refused (parity holds).
#       Exit 1 = >=1 ticket would be refused (parity gap — RED).
#       Exit 2 = internal error.
#       Exit 8 = UNKNOWN (timed out or could not complete).
#
# Env overrides (isolated self-test seams; defaults are the real fleet):
#   GATE_PARITY_BOARD          board dir (default <fleet>/board)
#   GATE_PARITY_DONE_DIR       done-marker dir (default <fleet>/state/done)
#   GATE_PARITY_PARGATE        path to parallelizability-gate.sh
#   GATE_PARITY_TIMEOUT        scan timeout in seconds (default 120). 0 = no timeout.
#   GATE_PARITY_DIFF_MIN        difficulty threshold for splittable (default 3)
#   GATE_PARITY_DECOMPOSE_MIN   children required for decomposed (default 2)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # fleet/
BOARD="${GATE_PARITY_BOARD:-$HERE/board}"
DONE_DIR="${GATE_PARITY_DONE_DIR:-$HERE/state/done}"
PARGATE="${GATE_PARITY_PARGATE:-$HERE/checks/parallelizability-gate.sh}"
GATE_PARITY_TIMEOUT="${GATE_PARITY_TIMEOUT:-120}"
DIFF_MIN="${GATE_PARITY_DIFF_MIN:-3}"
DECOMPOSE_MIN="${GATE_PARITY_DECOMPOSE_MIN:-2}"

if ! [[ "$GATE_PARITY_TIMEOUT" =~ ^[0-9]+$ ]]; then
  echo "gate-parity: GATE_PARITY_TIMEOUT must be a non-negative integer, got '$GATE_PARITY_TIMEOUT'" >&2
  exit 2
fi

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

# _surfaces_of <ticket-file> — count of distinct non-test owned surfaces.
# Mirrors parallelizability-gate.sh:surfaces_of to keep verdict parity.
_surfaces_of(){
  local f="$1" line parts=() p t b
  line="$(field "$f" owns)"
  IFS=',' read -ra parts <<< "$line"
  local count=0 seen=""
  for p in "${parts[@]:-}"; do
    t="$(printf '%s' "$p" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    [ -n "$t" ] || continue
    case "$t" in *' '*|*$'\t'*|'('*) continue ;; esac
    b="${t##*/}"
    case "$t" in tests/*|*/tests/*) continue ;; esac
    case "$b" in test_*|*_test.*|*_test|conftest.py) continue ;; esac
    case "$seen" in *"|$t|"*) continue ;; esac
    seen="$seen|$t|"
    count=$((count + 1))
  done
  printf '%s' "$count"
}

# _is_justified <ticket-file> — 0 if serial_justified field is non-empty, non-false.
_is_justified(){
  local sj; sj="$(lc "$(field "$1" serial_justified)")"
  case "$sj" in ""|false|no|0) return 1 ;; esac
  return 0
}

# --- predicate definitions --------------------------------------------------------------
# Each predicate is a function named pred_<name> that receives a ticket id and prints
# "<name>: <message>" to stdout on FAIL; returns 0=PASS, 1=FAIL, 2=ERROR.
# GATE_PREDICATES is a newline-separated list of "pred_<funcname>" entries — explicit and
# extensible: add a pred_* function and append its name here.
#
# NOTE: pred_parallelizability delegates to parallelizability-gate.sh for the `check`
# subcommand (single-ticket, subprocess OK). The `scan` subcommand uses the inline fast path
# to avoid N subprocess spawns (the O(n²) class fixed by GATE-PARITY-TIMEOUT-FLAKE #375).

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

  local any_fail=0 any_err=0 _start=$SECONDS
  for pred_fn in "${GATE_PREDICATES[@]}"; do
    if [ "$GATE_PARITY_TIMEOUT" -gt 0 ] && [ $(( SECONDS - _start )) -ge "$GATE_PARITY_TIMEOUT" ]; then
      echo "gate-parity: UNKNOWN — check $id timed out after ${GATE_PARITY_TIMEOUT}s (budget exceeded)" >&2
      exit 8
    fi
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

# cmd_scan — fast inline path.
# Reads the board in TWO passes:
#   Pass 1: build parent->children count map from ALL board files (O(n)).
#   Pass 2: walk live tickets; check splittable/decomposed/justified using the pre-built
#           map. No subprocess per ticket. ~5s for full board (down from ~31s).
# A GATE_PARITY_TIMEOUT budget is checked per-ticket iteration; if exceeded, exits 8.
cmd_scan(){
  local _start=$SECONDS
  shopt -s nullglob

  # --- Pass 1: build parent->child-count map -------------------------------------------
  declare -A parent_map
  local tf pid _scanned=0
  for tf in "$BOARD"/*.md; do
    [ -f "$tf" ] || continue
    if [ "$GATE_PARITY_TIMEOUT" -gt 0 ] && [ $(( SECONDS - _start )) -ge "$GATE_PARITY_TIMEOUT" ]; then
      echo "gate-parity scan: UNKNOWN — timed out after ${GATE_PARITY_TIMEOUT}s (budget exceeded during pass 1; $_scanned board files scanned)" >&2
      exit 8
    fi
    _scanned=$((_scanned + 1))
    pid="$(lc "$(field "$tf" parent)")"
    [ -n "$pid" ] && parent_map["$pid"]=$(( ${parent_map["$pid"]:-0} + 1 ))
  done

  # --- Pass 2: scan live tickets -------------------------------------------------------
  local hits=0 tf id
  for tf in "$BOARD"/*.md; do
    [ -f "$tf" ] || continue
    id="$(basename "$tf" .md)"
    is_parked "$tf" && continue
    [ -e "$DONE_DIR/$id" ] && continue

    if [ "$GATE_PARITY_TIMEOUT" -gt 0 ] && [ $(( SECONDS - _start )) -ge "$GATE_PARITY_TIMEOUT" ]; then
      echo "gate-parity scan: UNKNOWN — timed out after ${GATE_PARITY_TIMEOUT}s (budget exceeded after scanning $_scanned board files)" >&2
      exit 8
    fi

    local diff surf_n idl
    diff="$(field "$tf" difficulty | grep -oE '^[0-9]+' | head -1 || true)"
    [ -n "$diff" ] || diff=0
    [ "$diff" -ge "$DIFF_MIN" ] || continue

    surf_n="$(_surfaces_of "$tf")"
    [ "$surf_n" -gt 1 ] || continue

    idl="$(lc "$id")"
    [ "${parent_map["$idl"]:-0}" -ge "$DECOMPOSE_MIN" ] && continue

    _is_justified "$tf" && continue

    hits=$((hits + 1))
    echo "  GATE-PARITY: $id would be refused at launch — SPLITTABLE (difficulty=$diff, $surf_n owned surfaces) without justification or decomposition"
  done

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
