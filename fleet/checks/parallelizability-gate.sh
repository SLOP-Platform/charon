#!/usr/bin/env bash
# parallelizability-gate.sh — F46 PARALLELIZABILITY-GATE (build-rig only).
# Mechanizes the operator's wall-clock rule (MANAGER-OPERATING-RULES.md sec.4: "Big efforts
# MUST be DECOMPOSED into multiple PARALLEL agents ... A serial multi-slice build whose
# slices are independent is a wall-clock DEFECT to be caught and fixed"). THE MOTIVATING
# MISS this class catches: a big, multi-surface effort quietly run as ONE long serial job
# (e.g. preflight.sh's historic serial inner loop over independent per-item checks) when it
# could have fanned out across worktrees/tabs and finished in a fraction of the wall-clock.
#
# A ticket is SPLITTABLE when BOTH:
#   - size >= M:            difficulty >= DIFF_MIN (default 3; difficulty is the board's
#                            existing 1-5 ordinal — see validate_board.sh's difficulty check)
#   - >1 independent surface: its `owns:` list (same comma-list convention wci-contention.sh
#                            and validate_board.sh already parse) names >1 distinct,
#                            non-prose path — i.e. it COULD be decomposed into disjoint,
#                            parallel sub-tickets (fleet/decompose.sh does exactly this split).
# REUSES the board's owns/difficulty conventions rather than reinventing a collision map.
#
# A SPLITTABLE ticket PASSES the gate only if:
#   (a) it has already been DECOMPOSED — >= DECOMPOSE_MIN (default 2) OTHER live board
#       tickets carry `parent: <this-id>` (the exact field fleet/decompose.sh emits), or
#   (b) it is JUSTIFIED — a `--serial-justified=<reason>` CLI arg (per-run override) OR a
#       `serial_justified: <reason>` field on the ticket itself (persistent, board-visible).
# Anything else: FAIL. This is advisory-OVERRIDABLE (justification always available), never
# a hard blanket block — see fleet/fleet-droid.sh (launch-time HARD gate, per claimed ticket)
# and fleet/validate_board.sh (board-wide ADVISORY surfacing via `scan`).
#
# Usage:
#   parallelizability-gate.sh check <ticket-id> [--serial-justified=<reason>]
#       Exit 0 = PASS (not splittable, already decomposed, or justified).
#       Exit 1 = FAIL (splittable + serial + unjustified) — names the ticket, why it's
#                splittable, and the two ways to pass. Exit 2 = usage/unknown-ticket error.
#   parallelizability-gate.sh scan
#       ADVISORY board-wide scan of all LIVE tickets. Prints one SPLITTABLE-SERIAL line per
#       offender. ALWAYS exits 0 (advisory; consumed by validate_board.sh, never fails it).
#
# Env overrides (isolated self-test seams; defaults are the real fleet):
#   PARALLEL_GATE_BOARD        board dir (default <fleet>/board)
#   PARALLEL_GATE_DONE_DIR      done-marker dir (default <fleet>/state/done)
#   PARALLEL_GATE_DIFF_MIN       size>=M threshold (default 3)
#   PARALLEL_GATE_DECOMPOSE_MIN  #children required to count as "decomposed" (default 2)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # fleet/ (script lives in fleet/checks/)
BOARD="${PARALLEL_GATE_BOARD:-$HERE/board}"
DONE_DIR="${PARALLEL_GATE_DONE_DIR:-$HERE/state/done}"
DIFF_MIN="${PARALLEL_GATE_DIFF_MIN:-3}"
DECOMPOSE_MIN="${PARALLEL_GATE_DECOMPOSE_MIN:-2}"

# --- field: first "<key>: <value>" line's value, whitespace-trimmed on both sides. -------
field(){
  local raw; raw="$(grep -m1 -E "^[[:space:]]*$2:" "$1" 2>/dev/null || true)"
  printf '%s' "$raw" | sed -E "s/^[[:space:]]*$2:[[:space:]]*//; s/[[:space:]]+\$//"
}
lc(){ printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# --- owns -> distinct non-prose surfaces (same skip rule as validate_board.sh #4b: an
# entry containing whitespace or starting with '(' is prose/descriptive, not a real path). --
surfaces_of(){
  local f="$1" line parts=() p t out=()
  line="$(field "$f" owns)"
  IFS=',' read -ra parts <<< "$line"
  for p in "${parts[@]:-}"; do
    t="$(printf '%s' "$p" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    [ -n "$t" ] || continue
    case "$t" in *' '*|*$'\t'*|'('*) continue ;; esac
    out+=("$t")
  done
  printf '%s\n' "${out[@]:-}" | grep -v '^$' | sort -u
}

is_splittable(){
  local f="$1" diff surf_n
  diff="$(field "$f" difficulty | grep -oE '^[0-9]+' | head -1 || true)"
  [ -n "$diff" ] || diff=0
  surf_n="$(surfaces_of "$f" | grep -c .)"
  [ "$diff" -ge "$DIFF_MIN" ] && [ "$surf_n" -gt 1 ]
}

# decomposed: >= DECOMPOSE_MIN OTHER board tickets carry `parent: <id>` (case-insensitive) —
# the exact field fleet/decompose.sh's emit step writes onto each sub-ticket.
is_decomposed(){
  local id="$1" idl count=0 pf par
  idl="$(lc "$id")"
  shopt -s nullglob
  for pf in "$BOARD"/*.md; do
    [ -f "$pf" ] || continue
    par="$(field "$pf" parent)"
    [ -n "$par" ] || continue
    [ "$(lc "$par")" = "$idl" ] && count=$((count+1))
  done
  [ "$count" -ge "$DECOMPOSE_MIN" ]
}

# justified: a CLI --serial-justified=<reason> (arg $2, may be empty) OR the ticket's own
# `serial_justified:` field holding a non-empty, non-false value.
is_justified(){
  local f="$1" cli="$2" sj
  [ -n "$cli" ] && return 0
  sj="$(field "$f" serial_justified)"
  case "$(lc "$sj")" in ""|false|no|0) return 1 ;; esac
  return 0
}
justification_text(){
  local f="$1" cli="$2"
  if [ -n "$cli" ]; then printf '%s' "$cli"; else field "$f" serial_justified; fi
}

is_parked(){
  local f="$1" pf note
  pf="$(lc "$(field "$f" parked)")"
  case "$pf" in true|yes|1) return 0 ;; esac
  note="$(field "$f" note)"
  printf '%s' "$note" | grep -qi PARKED && return 0
  return 1
}

usage(){
  echo "usage: parallelizability-gate.sh check <ticket-id> [--serial-justified=<reason>]" >&2
  echo "       parallelizability-gate.sh scan" >&2
  exit 2
}

cmd_check(){
  local id="${1:-}"; [ -n "$id" ] || usage
  shift || true
  local reason=""
  for a in "$@"; do case "$a" in --serial-justified=*) reason="${a#*=}" ;; esac; done
  local tf="$BOARD/$id.md"
  [ -f "$tf" ] || { echo "parallelizability-gate: no such board ticket: $id ($tf)" >&2; exit 2; }

  if ! is_splittable "$tf"; then
    echo "parallelizability-gate: OK — $id is not splittable (difficulty<$DIFF_MIN or <=1 owned surface)."
    exit 0
  fi
  if is_decomposed "$id"; then
    echo "parallelizability-gate: OK — $id is splittable but already DECOMPOSED (>= $DECOMPOSE_MIN sub-ticket(s) carry 'parent: $id')."
    exit 0
  fi
  if is_justified "$tf" "$reason"; then
    local src="ticket serial_justified: field"; [ -n "$reason" ] && src="CLI --serial-justified"
    echo "parallelizability-gate: OK — $id is splittable but the SERIAL run is JUSTIFIED ($src): $(justification_text "$tf" "$reason")"
    exit 0
  fi

  local diff surf_n surf_list
  diff="$(field "$tf" difficulty | grep -oE '^[0-9]+' | head -1 || true)"
  surf_list="$(surfaces_of "$tf" | paste -sd, -)"
  surf_n="$(surfaces_of "$tf" | grep -c .)"
  {
    echo "parallelizability-gate: FAIL — $id is SPLITTABLE (difficulty=$diff >= $DIFF_MIN AND $surf_n independent owned surfaces: $surf_list)"
    echo "  and is about to run as a SINGLE SERIAL job — the wall-clock DEFECT this gate catches"
    echo "  (MANAGER-OPERATING-RULES.md sec.4: never run a large effort as one long serial job"
    echo "  when it splits into independent, collision-free chunks)."
    echo "  Fix ONE of:"
    echo "    1) DECOMPOSE it into >= $DECOMPOSE_MIN disjoint sub-tickets: fleet/decompose.sh $id"
    echo "    2) JUSTIFY the serial run: pass --serial-justified=\"<reason>\" at launch, or add"
    echo "       'serial_justified: <reason>' to $tf"
  } >&2
  exit 1
}

cmd_scan(){
  local hits=0 tf id
  shopt -s nullglob
  for tf in "$BOARD"/*.md; do
    [ -f "$tf" ] || continue
    id="$(basename "$tf" .md)"
    is_parked "$tf" && continue
    [ -e "$DONE_DIR/$id" ] && continue
    is_splittable "$tf" || continue
    is_decomposed "$id" && continue
    is_justified "$tf" "" && continue
    hits=$((hits+1))
    local diff surf_n
    diff="$(field "$tf" difficulty | grep -oE '^[0-9]+' | head -1 || true)"
    surf_n="$(surfaces_of "$tf" | grep -c .)"
    echo "  SPLITTABLE-SERIAL: $id (difficulty=$diff, $surf_n owned surfaces) — decompose (fleet/decompose.sh $id) or justify ('serial_justified: <reason>')"
  done
  if [ "$hits" -eq 0 ]; then
    echo "parallelizability-gate scan: OK — no live splittable ticket is unjustified-serial."
  else
    echo "parallelizability-gate scan: $hits splittable-serial ticket(s) — advisory (fleet/checks/parallelizability-gate.sh)."
  fi
  return 0   # ALWAYS advisory — never fails the board on its own (fleet-droid.sh is the hard gate)
}

case "${1:-scan}" in
  check) shift; cmd_check "$@" ;;
  scan)  shift || true; cmd_scan "$@" ;;
  *) usage ;;
esac
