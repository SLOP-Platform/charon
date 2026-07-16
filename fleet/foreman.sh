#!/usr/bin/env bash
# foreman.sh — the fleet FOREMAN: claimability + composition monitor.
#
# The manager feeds work to the board; the foreman CONFIRMS it is actually claimable and being
# claimed, and when a tier starves OR a ticket that should be claimable isn't, it diagnoses WHY
# and reports LOUDLY. It composes the existing gates (claim.sh, validate_board owns-collision,
# parallelizability decomposition scan, wci-contention) rather than reinventing them.
#
# DISCIPLINE (operator: be super-smart, blast-radius-aware, CONFIRM don't act blindly):
#   * DEFAULT = REPORT + PROPOSE only. It changes NOTHING. Every proposed remedy prints its
#     BLAST RADIUS (what it touches / what it unblocks) so the manager confirms before acting.
#   * --fix acts ONLY on PROVABLY-SAFE, reversible items and PRINTS the blast radius of each:
#       - a loop-guard quarantine whose ticket now PASSES the decomposition gate (else it just
#         re-quarantines) -> clear;
#       - a dep whose PR is MERGED but unmarked -> done-mark (unblocks its dependents).
#     It NEVER auto-unparks (parked = a human decision) and NEVER clears a still-splittable
#     quarantine (that needs decompose/serial_justify first). Those are REPORTED for the human.
#
# Usage:  foreman.sh [--fix]
#         FOREMAN_FLEET=<dir> overrides the fleet root (isolated e2e test seam).
set -uo pipefail
if [ -n "${FOREMAN_FLEET:-}" ]; then FLEET="$FOREMAN_FLEET"
else FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; fi
BOARD="$FLEET/board"; STATE="$FLEET/state"
# is_parked / parked_value — THE canonical parked predicate (see _lib.sh). Sourced rather than
# re-implemented: foreman decides whether a quarantine is a human hold, and a private copy of the
# rule is exactly how this drifted from claim.sh in the first place.
[ -f "$FLEET/_lib.sh" ] && source "$FLEET/_lib.sh"
# batched merged-PR lookups (ONE gh call per repo, cached) instead of a gh call per blocked ticket
[ -f "$FLEET/gh-cache.sh" ] && source "$FLEET/gh-cache.sh"
FIX=0; [ "${1:-}" = "--fix" ] && FIX=1
meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2" 2>/dev/null; }
say(){ printf '%s\n' "$*"; }

# --- 1. tier claimable depth (LOUD on starve) --------------------------------------------------
say "== FOREMAN: tier claimable depth =="
starving=""
for t in frontier strong economy; do
  # DISTINCT count: hold each probe-claim through the loop (so the next iteration claims a
  # DIFFERENT ticket), then release them all — else we'd re-claim the same one repeatedly.
  ids=""
  for i in 1 2 3 4 5; do
    out="$(bash "$FLEET/claim.sh" "$t" foreman-probe own-only 2>/dev/null)"
    id="$(printf '%s' "$out" | awk '/^CLAIMED/{print $2}')"
    [ -z "$id" ] && break
    ids="$ids $id"
  done
  for id in $ids; do rm -f "$STATE/claims/$id"; done
  n=$(printf '%s' "$ids" | wc -w)
  # graduated depth: 0 = STARVE (down now), 1..LOW_WATER = LOW (almost empty, feed proactively),
  # above = ok. LOW_WATER default 2 (tune via FOREMAN_LOW_WATER).
  low_water="${FOREMAN_LOW_WATER:-2}"
  if [ "$n" -eq 0 ]; then say "  [STARVE] $t: 0 claimable -- feed it NOW"; starving="$starving $t"
  elif [ "$n" -le "$low_water" ]; then say "  [LOW]    $t: $n claimable ->$ids -- almost empty, feed proactively"; low="${low:-} $t"
  else say "  [ok]     $t: $n claimable ->$ids"; fi
done
[ -n "${low:-}" ] && say "  (LOW-WATER tiers:${low} -- top up before they starve)"

# --- 2. diagnose non-claimable tickets + collect provably-safe remedies ------------------------
say "== FOREMAN: non-claimable tickets (reason + blast radius) =="
safe_lg=""; keep_lg=""; safe_dep=""
for f in "$BOARD"/*.md; do
  [ -e "$f" ] || continue; id="$(basename "$f" .md)"
  [ -e "$STATE/claims/$id" ] && continue
  [ -e "$STATE/submitted/$id" ] && continue
  [ -e "$STATE/done/$id" ] && continue
  reason=""
  # Was `in true|yes|1)`, which missed PROSE park reasons -> foreman did not see them as a human
  # hold and could recommend clearing their quarantine, making an operator-parked ticket claimable.
  is_parked "$f" && reason="PARKED (human hold) -- NOT auto-cleared; confirm still intended"
  [ -z "$reason" ] && case "$(meta note "$f")" in *PARKED*) reason="PARKED-via-note -- confirm still intended";; esac
  if [ -z "$reason" ] && [ -e "$STATE/loop-guard/$id" ]; then
    if bash "$FLEET/checks/parallelizability-gate.sh" check "$id" >/dev/null 2>&1; then
      reason="QUARANTINED but now PASSES decomposition gate -> SAFE to clear (blast: becomes claimable; owns=$(meta owns "$f"))"; safe_lg="$safe_lg $id"
    else
      reason="QUARANTINED + still SPLITTABLE-unjustified -> KEEP (decompose fleet/decompose.sh $id, or serial_justify)"; keep_lg="$keep_lg $id"
    fi
  fi
  if [ -z "$reason" ]; then
    dep="$(meta depends_on "$f" | sed 's/#.*//')"
    for d in $(printf '%s' "$dep" | tr ',' ' '); do
      d="$(printf '%s' "$d" | xargs)"; [ -z "$d" ] && continue
      [ -e "$STATE/done/$d" ] && continue
      dbr="$(meta branch "$BOARD/$d.md")"; [ -z "$dbr" ] && dbr="$(meta branch "$BOARD/archive/$d.md")"
      merged=""
      if [ -n "$dbr" ] && command -v branch_merged_pr >/dev/null 2>&1; then
        merged="$(branch_merged_pr Nnyan/charon-private "$dbr")"
        [ -z "$merged" ] && merged="$(branch_merged_pr SLOP-Platform/charon "$dbr")"
      fi
      if [ -n "$merged" ]; then reason="BLOCKED on $d, whose PR #$merged is MERGED (unmarked) -> SAFE to done-mark (blast: unblocks $id)"; safe_dep="$safe_dep $d"
      else reason="blocked on $d (real prereq -- build it)"; fi
      break
    done
  fi
  [ -n "$reason" ] && printf "  %-30s %s\n" "$id" "$reason"
done

# --- 3. composition health: collisions + decomposition (compose existing gates) ----------------
say "== FOREMAN: composition health (collisions / decomposition) =="
coll="$(bash "$FLEET/validate_board.sh" "$FLEET" 2>&1 | grep -iE 'owns-collision LIVE')"
if [ -n "$coll" ]; then say "  [COLLISION] two writers, unsequenced -- DO NOT feed as-is (sequence or dedupe):"; printf '%s\n' "$coll" | sed 's/^/    /'
else say "  [ok] no live owns-collisions"; fi
undec="$(bash "$FLEET/checks/parallelizability-gate.sh" scan 2>/dev/null | grep -iE 'SPLITTABLE-SERIAL' | head -12)"
[ -n "$undec" ] && { say "  [DECOMP] splittable+serial+unjustified -- decompose or serial_justify before feeding:"; printf '%s\n' "$undec" | sed 's/^/    /'; }

# --- 4. remedies: PROPOSE (default) or act-if-safe (--fix), always showing blast radius ---------
say "== FOREMAN: remedies (provably-safe only) =="
if [ -z "$safe_lg$safe_dep" ]; then say "  (no provably-safe auto-remedies)"; fi
for id in $safe_lg; do
  if [ "$FIX" = 1 ]; then bash "$FLEET/loop-guard.sh" clear "$id" >/dev/null 2>&1 && say "  DID: cleared quarantine $id (now claimable)"
  else say "  PROPOSE: clear quarantine $id (SAFE: passes decomposition gate; blast: becomes claimable)"; fi
done
for d in $(printf '%s' "$safe_dep" | tr ' ' '\n' | sort -u); do
  [ -z "$d" ] && continue
  if [ "$FIX" = 1 ]; then AUTONOMOUS=1 bash "$FLEET/done.sh" "$d" >/dev/null 2>&1 && say "  DID: done-marked merged dep $d (unblocks its dependents)"
  else say "  PROPOSE: done-mark merged dep $d (blast: unblocks its dependents)"; fi
done
[ -n "$keep_lg" ] && say "  HUMAN NEEDED (not auto-fixed): decompose/justify ->$keep_lg"

# --- 5. verdict (loud) -------------------------------------------------------------------------
rc=0
[ -n "$coll" ]     && { say "== FOREMAN VERDICT: [FAIL] COLLISIONS present -- sequence/dedupe before feeding =="; rc=1; }
[ -n "$starving" ] && { say "== FOREMAN VERDICT: [FAIL] STARVING TIERS:$starving =="; rc=1; }
[ "$rc" = 0 ] && say "== FOREMAN VERDICT: [OK] all tiers fed, no collisions, decomposition clean =="
exit "$rc"
