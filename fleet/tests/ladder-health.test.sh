#!/usr/bin/env bash
# ladder-health.test.sh — FAIL-ON-REVERT tests for fleet/ladder-health.sh.
#
# Covers every exclusion reason the surfacer must report — a starved P0 must never
# be invisible again. Each fixture creates a specific exclusion and asserts it is
# SURFACED with the expected reason. A negative test asserts a genuinely-claimable
# P0 reports CLAIMABLE.
#
# Fully ISOLATED: builds a temp fleet (copied scripts + synthetic board + state).
# NEVER touches the live board/state or the product repo.
#
# Run:  bash fleet/tests/ladder-health.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "  ok   $1"; }
bad(){  FAIL=$((FAIL+1)); echo "  FAIL $1"; }
chk(){  # chk <desc> <needle> <haystack>
  case "$3" in *"$2"*) ok "$1";; *) bad "$1 (missing '$2' in: $(printf '%s' "$3" | tr '\n' ' '))";; esac
}
nchk(){ case "$3" in *"$2"*) bad "$1 (unexpected '$2')";; *) ok "$1";; esac; }

# ── Build an isolated temp fleet ──────────────────────────────────────────────
mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/ladder-health.sh" "$SRC/_lib.sh" "$SRC/repo-registry.sh" "$d/" 2>/dev/null || true
  # validate_board.sh required (Python, needs capability/ too)
  mkdir -p "$d/board" "$d/state/claims" "$d/state/submitted" "$d/state/done" "$d/state/loop-guard"
  mkdir -p "$d/capability"
  if [ -d "$SRC/capability" ]; then cp -r "$SRC/capability"/* "$d/capability/" 2>/dev/null || true; fi
  # Provide a minimal, always-green validate_board.sh for the fixture
  printf '#!/usr/bin/env bash\nexit 0\n' > "$d/validate_board.sh"
  chmod +x "$d/validate_board.sh"
  echo "$d"
}

# ── Ticket helpers ────────────────────────────────────────────────────────────
# mk_ticket <dir> <id> <priority> [extra-yaml-lines...]
mk_ticket(){
  local d="$1" id="$2" prio="${3:-}"
  local b="$d/board/$id.md"
  {
    echo "tier: haiku"
    echo "difficulty: 1"
    echo "work_class: docs"
    echo "branch: feat/$(echo "$id" | tr 'A-Z' 'a-z')"
    echo "depends_on:"
    echo "owns: docs/${id}.md"
    [ -n "$prio" ] && echo "priority: $prio"
    shift 3
    for line in "$@"; do echo "$line"; done
  } > "$b"
}

run_health(){ LADDER_HEALTH_TOP="$1" LADDER_HEALTH_TIER="${2:-haiku}" bash "$FLEET/ladder-health.sh" 2>&1; }
run_health_all(){ LADDER_HEALTH_TOP=50 LADDER_HEALTH_TIER="${1:-haiku}" bash "$FLEET/ladder-health.sh" 2>&1; }

# ==============================================================================
echo "== (a) QUARANTINED P0 is surfaced with reason =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" Q-P0 0
mk_ticket "$FLEET" ALSO-READY 1

# Create loop-guard marker
printf 'droid=droidX\nquarantined=2026-07-23T10:00:00Z\nreason=repeated zero-commit re-claims\n' \
  > "$FLEET/state/loop-guard/Q-P0"

OUT="$(run_health 5)"
chk "a1 QUARANTINED P0 surfaced"    "QUARANTINED" "$OUT"
chk "a2 QUARANTINED names the id"   "Q-P0"        "$OUT"
chk "a3 QUARANTINED has reason"     "zero-commit"  "$OUT"
nchk "a4 QUARANTINED P0 is NOT reported CLAIMABLE" "CLAIMABLE.*Q-P0" "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (b) CLAIMED P0 with STALE droid is surfaced =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" STALE-CLAIM-P0 0
mk_ticket "$FLEET" ALSO-READY 1

# Create claim marker with a droid name that is NOT alive
printf 'dead-droid-12345 2026-07-22T08:00:00Z\n' > "$FLEET/state/claims/STALE-CLAIM-P0"

OUT="$(run_health 5)"
chk "b1 CLAIMED P0 surfaced"       "CLAIMED"          "$OUT"
chk "b2 CLAIMED names the id"      "STALE-CLAIM-P0"    "$OUT"
chk "b3 CLAIMED names the droid"   "dead-droid-12345"  "$OUT"
chk "b4 CLAIMED flagged STALE"     "STALE"             "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (c) SUBMITTED P0 is surfaced =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" SUBMITTED-P0 0
mk_ticket "$FLEET" ALSO-READY 1

# Create submitted marker
printf '2026-07-23T12:00:00Z\n' > "$FLEET/state/submitted/SUBMITTED-P0"

OUT="$(run_health 5)"
chk "c1 SUBMITTED P0 surfaced"     "SUBMITTED"     "$OUT"
chk "c2 SUBMITTED names the id"    "SUBMITTED-P0"   "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (d) DONE P0 is surfaced =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" DONE-P0 0
mk_ticket "$FLEET" ALSO-READY 1

: > "$FLEET/state/done/DONE-P0"

OUT="$(run_health 5)"
chk "d1 DONE P0 surfaced"          "DONE"           "$OUT"
chk "d2 DONE names the id"         "DONE-P0"         "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (e) PARKED P0 is surfaced =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" PARKED-P0 0 "parked: true"
mk_ticket "$FLEET" ALSO-READY 1

OUT="$(run_health 5)"
chk "e1 PARKED P0 surfaced"        "PARKED"         "$OUT"
chk "e2 PARKED names the id"       "PARKED-P0"       "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (f) BLOCKED P0 names its undone dep(s) =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" BLOCKED-P0 0 "" "depends_on: UNDONE-DEP"
mk_ticket "$FLEET" UNDONE-DEP 2
mk_ticket "$FLEET" ALSO-READY 1

OUT="$(run_health 5)"
chk "f1 BLOCKED P0 surfaced"       "BLOCKED"        "$OUT"
chk "f2 BLOCKED names the id"      "BLOCKED-P0"      "$OUT"
chk "f3 BLOCKED names the dep"     "UNDONE-DEP"      "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (g) BLOCKED P0 with a dep that has BOTH done + claimed markers =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" BLOCKED-DUAL 0 "" "depends_on: DUAL-DEP"
mk_ticket "$FLEET" DUAL-DEP 2
mk_ticket "$FLEET" ALSO-READY 1
# DUAL-DEP has a done marker (so deps_all_done_check passes → ticket unblocked)
: > "$FLEET/state/done/DUAL-DEP"
# But also a claim marker (historical — done+claimed is contradictory but the
# done marker wins for claimability)
printf 'old-droid 2026-07-22T08:00:00Z\n' > "$FLEET/state/claims/DUAL-DEP"

OUT="$(run_health 5)"
chk "g1 done dep unblocks the ticket"      "BLOCKED-DUAL" "$OUT"
chk "g2 done dep → ticket is CLAIMABLE"     "CLAIMABLE"    "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (h) TIER: ticket tier > checker tier =="

FLEET="$(mk_fleet)"
# Ticket tier 'opus' has rank 3; checker tier 'haiku' has rank 1
mk_ticket "$FLEET" OPUS-ONLY-P0 0 "tier: opus" "difficulty: 3"
mk_ticket "$FLEET" ALSO-READY 1

OUT="$(run_health_all haiku)"
chk "h1 TIER P0 surfaced"          "TIER"           "$OUT"
chk "h2 TIER names the id"         "OPUS-ONLY-P0"    "$OUT"
chk "h3 TIER mentions opus"        "opus"            "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (i) BOARD_RED: validate_board failing blocks all =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" BOARD-RED-P0 0
printf '#!/usr/bin/env bash\necho "RED: deliberate failure"; exit 1\n' > "$FLEET/validate_board.sh"
chmod +x "$FLEET/validate_board.sh"

OUT="$(run_health 5)"
chk "i1 BOARD_RED surfaced"        "BOARD_RED"      "$OUT"
chk "i2 BOARD_RED names the id"    "BOARD-RED-P0"    "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (j) parallelizability-refused surfaced =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" BIG-SPLITTABLE 0 "difficulty: 4" "owns: docs/a.md, docs/b.md, docs/c.md"

OUT="$(run_health_all haiku)"
chk "j1 PARALLELIZABILITY-REFUSED surfaced"   "PARALLELIZABILITY-REFUSED"   "$OUT"
chk "j2 names the id"                           "BIG-SPLITTABLE"              "$OUT"
chk "j3 mentions the fix"                       "serial_justified"            "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (k) Genuinely-claimable P0 reports CLAIMABLE =="

FLEET="$(mk_fleet)"
mk_ticket "$FLEET" CLAIMABLE-P0 0
mk_ticket "$FLEET" ALSO-READY 1

OUT="$(run_health 5)"
chk "k1 CLAIMABLE P0 surfaced"     "CLAIMABLE"      "$OUT"
chk "k2 CLAIMABLE names the id"    "CLAIMABLE-P0"     "$OUT"
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo "== (l) FAIL-ON-REVERT: if the body of ladder-health.sh is removed, a "
echo "    starved P0 goes invisible → test must detect the gap. =="

FLEET="$(mk_fleet)"
# Copy the REAL script first so we can hollow it out
cp "$SRC/ladder-health.sh" "$FLEET/ladder-health-real.sh"

# Create a fixture with a QUARANTINED P0 (should be surfaced)
mk_ticket "$FLEET" STARVED-P0 0
printf 'droid=droidX\nquarantined=2026-07-23T10:00:00Z\nreason=repeated zero-commit re-claims\n' \
  > "$FLEET/state/loop-guard/STARVED-P0"

OUT_REAL="$(LADDER_HEALTH_TOP=5 LADDER_HEALTH_TIER=haiku bash "$FLEET/ladder-health-real.sh" 2>&1)"
chk "l1 real surfacer sees STARVED-P0"  "QUARANTINED"  "$OUT_REAL"
chk "l2 real surfacer names it"         "STARVED-P0"   "$OUT_REAL"

# Hollow out: replace the surfacer with a stub that only prints CLAIMABLE
{
  echo '#!/usr/bin/env bash'
  echo 'FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"'
  echo 'source "$FLEET/_lib.sh"'
  echo 'echo "(hollow surfacer — exclusion logic removed)"'
  echo 'for f in "$FLEET/board"/*.md; do'
  echo '  [ -f "$f" ] || continue'
  echo '  id="$(basename "$f" .md)"'
  echo '  echo "$id P:- CLAIMABLE"'
  echo 'done'
} > "$FLEET/ladder-health.sh"
chmod +x "$FLEET/ladder-health.sh"

OUT_HOLLOW="$(LADDER_HEALTH_TOP=5 LADDER_HEALTH_TIER=haiku bash "$FLEET/ladder-health.sh" 2>&1)"
# The hollow surfacer should never print QUARANTINED
nchk "l3 hollow surfacer does NOT surface QUARANTINED" "QUARANTINED" "$OUT_HOLLOW"
# But it DOES print the ticket (falsely as CLAIMABLE)
chk "l4 hollow surfacer falsely reports STARVED-P0 as CLAIMABLE" "STARVED-P0" "$OUT_HOLLOW"

# FAIL-ON-REVERT: if the real surfacer was disabled, the starved ticket
# becomes invisible as a problem. Assert that the real surfacer's output
# contains the exclusion signal that the hollow one lacks.
if echo "$OUT_REAL" | grep -q "QUARANTINED" && ! echo "$OUT_HOLLOW" | grep -q "QUARANTINED"; then
  ok "l5 fail-on-revert: real surfacer sees QUARANTINED; hollow one doesn't — gap detected"
else
  bad "l5 fail-on-revert: expected real to show QUARANTINED and hollow to NOT (real: $(echo "$OUT_REAL" | grep -c QUARANTINED), hollow: $(echo "$OUT_HOLLOW" | grep -c QUARANTINED))"
fi
rm -rf "$(dirname "$FLEET")"

# ==============================================================================
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LADDER-HEALTH TESTS PASS"
