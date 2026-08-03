#!/usr/bin/env bash
# handoff-root-staleness.test.sh — FAIL-ON-REVERT self-test for the rig-root
# HANDOFF.md staleness check.  Verifies that a root handoff-style doc cannot
# claim live authority while stale, and must name at least one current source
# of truth.  Hermetic: operates on FIXTURE content (temp files), not the live
# HANDOFF.md.  Drive with content, not byte-assertions.
#
# REVERT CONTRACT: if someone strips the staleness-detection logic so a stale
# authoritative doc passes silently, this test MUST fail.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# ---------------------------------------------------------------------------
# Handoff staleness checker — operates on a FILE PATH.
# Scans the file for authority-claiming phrases and source-of-truth pointers.
# ---------------------------------------------------------------------------
check_handoff(){
  local f="$1"
  local err=0

  # (a) Authority claim detection: "You are the next Charon Manager" or
  #     "complete, self-contained handoff".
  local claim_phrase=""
  if grep -q "You are the next Charon Manager" "$f"; then
    claim_phrase="$claim_phrase|You are the next Charon Manager"
  fi
  if grep -q "complete, self-contained handoff" "$f"; then
    claim_phrase="$claim_phrase|complete, self-contained handoff"
  fi

  if [ -n "$claim_phrase" ]; then
    # Authority phrase present — require a date stamp in the file.
    if ! grep -qE "(ARCHIVED|archived|historical|This document is historical)" "$f"; then
      echo "  FAIL: authority claim without archive marker" >&2
      err=1
    fi
    if ! grep -qE "(202[0-9]-[0-9]{2}-[0-9]{2}|Archived content)" "$f"; then
      echo "  FAIL: authority claim without date stamp" >&2
      err=1
    fi
  fi

  # (b) Source-of-truth pointer: must reference fleet/state/ or SESSION-HANDOFF-
  if ! grep -qE "(fleet/state/|SESSION-HANDOFF-)" "$f"; then
    echo "  FAIL: no current source-of-truth pointer (fleet/state/ or SESSION-HANDOFF-)" >&2
    err=1
  fi

  return "$err"
}

echo "== (1) stale authoritative doc (claim + no date/archive) == RETURN FALSE =="
touch "$TMP/stale.md"
printf '# Charon — Manager Handoff\n\nYou are the next Charon Manager. This is a complete, self-contained handoff.\n' > "$TMP/stale.md"
check_handoff "$TMP/stale.md" && bad "a1 stale authoritative doc passed (should fail)" \
  || ok "a1 stale authoritative doc correctly fails"

echo "== (2) archived doc (claim + archive header + date) == RETURN TRUE =="
touch "$TMP/archived.md"
printf '# Charon — Manager Handoff (ARCHIVED)\n\nThis document is historical. Dated 2026-07-10.\n\nYou are the next Charon Manager. This is a complete, self-contained handoff.\n\nSee fleet/state/ for current state.\n' > "$TMP/archived.md"
check_handoff "$TMP/archived.md" && ok "a2 archived doc with date passes" \
  || bad "a2 archived doc with date failed (should pass)"

echo "== (3) pointer doc (no claim, names current sources) == RETURN TRUE =="
touch "$TMP/pointer.md"
printf 'See fleet/state/ and the newest SESSION-HANDOFF-*.md.' > "$TMP/pointer.md"
check_handoff "$TMP/pointer.md" && ok "b1 pointer doc passes" \
  || bad "b1 pointer doc failed (should pass)"

echo "== (4) dead-end doc (no pointer) == RETURN FALSE =="
touch "$TMP/deadend.md"
printf '# Handoff\n\nNothing useful here.' > "$TMP/deadend.md"
check_handoff "$TMP/deadend.md" && bad "b2 dead-end doc passed (should fail)" \
  || ok "b2 dead-end doc correctly fails"

echo "== (5) archived + pointer (claim + archive + date + sources) == RETURN TRUE =="
touch "$TMP/full.md"
printf '# Charon — Manager Handoff (ARCHIVED)\n\nThis document is historical. Dated 2026-07-10.\n\nYou are the next Charon Manager. This is a complete, self-contained handoff.\n\nSee fleet/state/ and SESSION-HANDOFF-*.md for current state.\n' > "$TMP/full.md"
check_handoff "$TMP/full.md" && ok "c1 full archived+pointer doc passes" \
  || bad "c1 full archived+pointer doc failed (should pass)"

# ---------------------------------------------------------------------------
# Fail-on-revert meta check: prove the checker is LOAD-BEARING by stripping
# the authority-claim detection and verifying a stale authoritative doc then
# slips through.
# ---------------------------------------------------------------------------
echo "== (6) fail-on-revert: stripped authority detection lets stale doc through =="
stripped_checker(){
  local f="$1"
  local err=0
  # Intentionally SKIP the authority-claim detection (simulating a revert).
  # Only check source-of-truth pointer:
  if ! grep -qE "(fleet/state/|SESSION-HANDOFF-)" "$f"; then
    err=1
  fi
  return "$err"
}

# A doc with authority claims + a pointer but NO archive/date marker.
# Full checker fails (authority claim stale). Stripped checker passes
# (only checks pointer, which exists).
touch "$TMP/stale-w-pointer2.md"
printf '# Charon — Manager Handoff\n\nYou are the next Charon Manager. This is a complete, self-contained handoff.\n\nSee fleet/state/ for current state.\n' > "$TMP/stale-w-pointer2.md"

check_handoff "$TMP/stale-w-pointer2.md" && bad "c0 full checker FAILED to catch stale authority claim (fixture problem)" \
  || ok "c0 full checker catches stale authority claim (fixture valid)"

stripped_checker "$TMP/stale-w-pointer2.md" && \
  ok "c2 stripped checker ACCEPTS stale+pointer doc (original authority check was load-bearing)" \
  || bad "c2 stripped checker STILL FAILS stale+pointer doc -> authority check is redundant"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL HANDOFF-ROOT-STALENESS TESTS PASS"
