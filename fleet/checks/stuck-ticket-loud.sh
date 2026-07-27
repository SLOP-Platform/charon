#!/usr/bin/env bash
# stuck-ticket-loud.sh — STUCK / UNCLAIMABLE TICKET DETECTOR.
#
# WHY THIS EXISTS (2026-07-23 deadlock RCA)
#   A P0 keystone ticket was loop-guard-quarantined ("repeated zero-commit re-claims") and
#   NOTHING was loud about it — the pool just went dry and the rig deadlocked. Quarantined
#   tickets were a SILENT state marker (no status.sh / report.sh / preflight emitted them),
#   so a structural wedge looked exactly like "pool drained, nothing to do." A ticket that
#   is NOT claimable for ANY reason must NEVER be silently parked or quarantined.
#
#   [[stuck-tickets-loud-never-silent]] [[sg-never-deadlocks]]
#
# THE FOUR CATEGORIES (each was a real silent kill on this rig)
#   1 quarantined       loop-guard marker exists — the droid re-claimed+released with zero
#                       commits. Was SILENT before this check; now LOUD until cleared.
#   2 parked            explicit operator hold (parked: field). Already visible in status.sh
#                       but surfaced here so the full unclaimable set is in ONE place.
#   3 dep-dissolved     depends_on references a ticket that has NO board file AND NO archive
#                       file. The dep was deleted/renamed — this ticket can NEVER unblock.
#   4 orphan-marker     a state marker (claims/, submitted/, needs-push/) exists for an id
#                       that has NO corresponding board ticket. Residue from a deleted ticket
#                       that is holding slots / blocking waves silently.
#
# QUARANTINE NARROWING (the other half of the anti-deadlock guarantee)
#   loop-guard.sh may quarantine ONLY for genuine repeated MODEL-ATTRIBUTABLE failure
#   (claim -> no-commit -> release -> re-claim spin). A lands-but-unlaunchable ticket must
#   be caught at LAND by gate-parity, NEVER quarantined. A structurally-wedged ticket
#   (dep-dissolved, owner-mismatch, prompt-path-missing) surfaces as STUCK here, not as a
#   silent loop-guard marker. When a quarantine IS found, this check surfaces it LOUDLY
#   regardless of cause — the narrowing is about PREVENTING mis-quarantines, not about
#   hiding quarantined tickets.
#
# CONTRACT
#   Read-only. Never deletes, prunes, clears, or mutates anything. Exit non-zero when ANY
#   stuck ticket exists — this is a HARD signal, not an advisory. Every status.sh / report.sh
#   / preflight run should invoke this check so a stuck pool can never go silent again.
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]
#   This script must NEVER invoke preflight.sh, validate_board.sh, claim.sh, loop-guard.sh,
#   land*.sh, or any gate that could re-invoke it. STUCK_TICKET_LOUD_ACTIVE short-circuits
#   accidental nesting.
#
# Usage: fleet/checks/stuck-ticket-loud.sh [--quiet]
# Exit:  0  clean — no stuck tickets found
#        1  STUCK TICKETS FOUND (LOUD — must be actioned)
#        2  usage error
# Env:
#   STL_FLEET_DIR    fleet dir holding board/ + state/ (default: auto-detected from script location)
#   STL_QUIET=1      suppress header/footer lines (findings still print)
#   STL_LIMIT        max detail lines per category (default 10; 0 = print all)
set -uo pipefail

[ -n "${STUCK_TICKET_LOUD_ACTIVE:-}" ] && { echo "stuck-ticket-loud: already running (reentrancy guard) — skipping"; exit 0; }
export STUCK_TICKET_LOUD_ACTIVE=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET="${STL_FLEET_DIR:-$(cd "$HERE/.." && pwd)}"
BOARD="$FLEET/board"
ARCHIVE="$BOARD/archive"
STATE="$FLEET/state"
LG="$STATE/loop-guard"
QUIET="${STL_QUIET:-0}"
LIMIT="${STL_LIMIT:-10}"

case "${1:-}" in
  --quiet) QUIET=1 ;;
  "") ;;
  *) echo "usage: stuck-ticket-loud.sh [--quiet]" >&2; exit 2 ;;
esac

say(){ [ "$QUIET" -eq 1 ] || echo "$*"; }

FOUND=0
declare -A CAT_N=()

finding(){
  FOUND=$((FOUND+1))
  local cat="$1" msg="$2"
  local n=$(( ${CAT_N[$cat]:-0} + 1 )); CAT_N[$cat]=$n
  if [ "$LIMIT" -eq 0 ] || [ "$n" -le "$LIMIT" ]; then
    echo "STUCK[${cat}] $msg"
  elif [ "$n" -eq $((LIMIT+1)) ]; then
    echo "STUCK[${cat}] ... more of this category suppressed (STL_LIMIT=0 for the full list)"
  fi
}

# ── helpers ────────────────────────────────────────────────────────────────────────────────
# _frontmatter <key> <file> -> value ("" if absent). Same parse as _vm_meta in _lib.sh and
# field() in validate_board.sh: literal "<key>:" prefix, strip surrounding whitespace.
# Skips empty-value lines (e.g. "depends_on:\n" with no actual deps) and keeps scanning —
# YAML frontmatter may repeat keys and the first non-empty wins.
_frontmatter(){
  awk -v k="$1" 'index($0,k ":")==1{sub("^" k ":[[:space:]]*","");sub(/[[:space:]]+$/,""); if ($0!=""){print;exit}}' "$2" 2>/dev/null
}

# _ticket_exists <id> -> 0 if board/<id>.md or board/archive/<id>.md exists.
_ticket_exists(){
  local id="$1"
  [ -f "$BOARD/$id.md" ] && return 0
  [ -f "$ARCHIVE/$id.md" ] && return 0
  return 1
}

# _is_parked_file <file> -> 0 if the board ticket is parked, 1 otherwise.
# Mirrors is_parked_value/is_parked from _lib.sh: parked: present, non-empty, not explicit false.
_is_parked_file(){
  local pv; pv="$(_frontmatter parked "$1")"
  case "${pv:-}" in ""|false|no|0) return 1;; *) return 0;; esac
}

# _is_done <id> -> 0 if state/done/<id> exists.
_is_done(){ [ -e "$STATE/done/$1" ]; }
# _is_submitted <id> -> 0 if state/submitted/<id> exists.
_is_submitted(){ [ -e "$STATE/submitted/$1" ]; }
# _is_claimed <id> -> 0 if state/claims/<id> exists.
_is_claimed(){ [ -e "$STATE/claims/$1" ]; }
# _is_quarantine_marker <file> -> 0 if the file looks like a loop-guard quarantine marker
# (contains "droid=" as written by loop-guard.sh::record). Other state files may live in
# the loop-guard directory (GRACEFUL-DEGRADE, ROUTER-LEDGER-DECAY, etc.) — only files
# with the quarantine format are real quarantines.
_is_quarantine_marker(){ grep -q '^droid=' "$1" 2>/dev/null; }

# ── category 1: QUARANTINED ──────────────────────────────────────────────────────────────────
# A board ticket with a loop-guard marker. These were SILENT before this check — the core fix.
scan_quarantined(){
  local f id
  for f in "$LG"/*; do
    [ -f "$f" ] || continue
    id="$(basename "$f")"
    _is_quarantine_marker "$f" || continue
    # Only report quarantined tickets that still have a board file and are not already done/submitted.
    _ticket_exists "$id" || continue
    _is_done "$id" && continue
    _is_submitted "$id" && continue
    local reason; reason="$(head -1 "$f" 2>/dev/null)"
    finding quarantined "$id — LOOP-GUARD QUARANTINED (${reason:-no reason recorded}). Manager: fix the block, then 'fleet/loop-guard.sh clear $id'"
  done
}

# ── category 2: PARKED ───────────────────────────────────────────────────────────────────────
# Explicit operator hold. Visible in status.sh but surfaced here for a unified STUCK dashboard.
scan_parked(){
  local f id
  for f in "$BOARD"/*.md; do
    [ -f "$f" ] || continue
    id="$(basename "$f" .md)"
    _is_parked_file "$f" || continue
    _is_done "$id" && continue
    _is_submitted "$id" && continue
    local pv; pv="$(_frontmatter parked "$f")"
    local reason="${pv:0:60}"; [ -z "$reason" ] && reason="no reason recorded"
    finding parked "$id — operator-held (${reason}). Unpark: edit board/$id.md"
  done
}

# ── category 3: DEP-DISSOLVED ────────────────────────────────────────────────────────────────
# A board ticket whose depends_on references a ticket with NO board/archive file. This ticket
# can NEVER unblock — its dep was deleted or renamed out from under it.
scan_dep_dissolved(){
  local f id deps_raw d
  for f in "$BOARD"/*.md; do
    [ -f "$f" ] || continue
    id="$(basename "$f" .md)"
    _is_done "$id" && continue
    _is_submitted "$id" && continue
    _is_claimed "$id" && continue
    deps_raw="$(_frontmatter depends_on "$f")"
    [ -n "$deps_raw" ] || continue
    for d in $(printf '%s' "$deps_raw" | tr ',' ' '); do
      [ -n "$d" ] || continue
      d="$(printf '%s' "$d" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      [ -n "$d" ] || continue
      _ticket_exists "$d" && continue
      # Check if the dep is already done (state/done/<id> might exist even without board file — rare)
      _is_done "$d" && continue
      finding dep-dissolved "$id — depends_on '$d' which has NO board file + NO archive file + NO done marker. This ticket can NEVER unblock."
      break  # one dissolved dep per ticket is enough
    done
  done
}

# ── category 4: ORPHAN-MARKER ────────────────────────────────────────────────────────────────
# A state marker (claims/, submitted/, needs-push/) whose id has no board file. Residue from a
# deleted ticket — holds claim slots / blocks waves SILENTLY.
scan_orphan_markers(){
  local bucket dir id
  for bucket in claims submitted needs-push; do
    dir="$STATE/$bucket"
    [ -d "$dir" ] || continue
    for f in "$dir"/*; do
      [ -f "$f" ] || continue
      id="$(basename "$f")"
      _ticket_exists "$id" && continue
      finding orphan-marker "state/$bucket/$id — marker exists but board/$id.md (and archive) NOT FOUND. Orphaned residue from a deleted ticket."
    done
  done
}

# ── main ─────────────────────────────────────────────────────────────────────────────────────
[ "$QUIET" -eq 0 ] && echo "--- stuck-ticket-loud: unclaimable ticket detector ---"

scan_quarantined
scan_parked
scan_dep_dissolved
scan_orphan_markers

if [ "$FOUND" -gt 0 ]; then
  [ "$QUIET" -eq 0 ] && echo ""
  local_cat=""; local_n=""
  for local_cat in quarantined parked dep-dissolved orphan-marker; do
    local_n="${CAT_N[$local_cat]:-0}"
    [ "$local_n" -gt 0 ] || continue
    echo "stuck-ticket-loud: $local_n x STUCK[$local_cat]"
  done
  echo "stuck-ticket-loud: $FOUND unclaimable ticket(s) — STUCK TICKETS EXIST (action required)"
  exit 1
fi

[ "$QUIET" -eq 0 ] && echo "clean: stuck-ticket-loud (0 unclaimable tickets — pool fully claimable)"
exit 0
