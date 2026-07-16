#!/usr/bin/env bash
# test_foreman_wire.sh — FAIL-ON-REVERT: preflight.sh scan runs foreman.sh
# (report-only, never --fix) and surfaces its STARVE/COLLISION/[OK] verdict
# prominently in the operator-actions output.
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Source preflight.sh to define functions (foreman_advisory, show_operator_actions, etc.)
source "$SRC/preflight.sh"

PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -qiF -- "$2" && ok "$3" || bad "$3 (missing: $2)"; }
no(){  printf '%s' "$1" | grep -qiF -- "$2" && bad "$3 (unexpected: $2)" || ok "$3"; }

T="$(mktemp -d)"
cleanup(){ rm -rf "$T"; }
trap cleanup EXIT

# --- hermetic fixture fleet (foreman.sh callees symlinked from real fleet) ---
FIX="$T/fix"
mkdir -p "$FIX"
for x in claim.sh _lib.sh repo-registry.sh loop-guard.sh validate_board.sh \
         model-detention.sh leak-guard.sh tier-models.tsv wci-contention.sh \
         done.sh; do
  [ -e "$SRC/$x" ] && ln -s "$SRC/$x" "$FIX/$x"
done
ln -s "$SRC/checks" "$FIX/checks"
mkdir -p "$FIX/board" "$FIX/state/done" "$FIX/state/loop-guard" \
         "$FIX/state/claims" "$FIX/state/submitted"

# --- (a) starving board (empty) -> foreman_advisory surfaces [STARVE] ---
D_A="$T/a"
mkdir -p "$D_A"
cp -r "$FIX"/* "$D_A/" 2>/dev/null

FOREMAN_FLEET="$D_A" foreman_advisory > "$T/out_a.txt" 2>&1 || true
no  "$(cat "$T/out_a.txt")" "foreman\.sh.*--fix" "(a1) foreman NEVER runs --fix"
has "$(cat "$T/out_a.txt")" "STARVE"              "(a2) starve surfaces on empty board"

FOREMAN_FLEET="$D_A" show_operator_actions > "$T/surface_a.txt" 2>&1 || true
has "$(cat "$T/surface_a.txt")" "STARVING" "(a3) starve verdict in operator actions"
has "$(cat "$T/surface_a.txt")" "!!"       "(a4) starve verdict LOUD (wrapped in !!)"

# --- (b) fully fed board -> [OK], no false alarm ---
D_B="$T/b"
mkdir -p "$D_B"
cp -r "$FIX"/* "$D_B/" 2>/dev/null
for t in frontier strong economy; do
  {
    echo "repo: charon-private"
    echo "tier: $t"
    echo "difficulty: 2"
    echo "work_class: rig-meta"
    echo "branch: feat/fed-${t}"
    echo "owns: fleet/${t}.sh"
    echo "depends_on:"
  } > "$D_B/board/FED-$t.md"
done

FOREMAN_FLEET="$D_B" foreman_advisory > "$T/out_b.txt" 2>&1 || true
has "$(cat "$T/out_b.txt")" "OK"     "(b1) fed board surfaces OK"
no  "$(cat "$T/out_b.txt")" "STARVE" "(b2) no false STARVE on fully fed board"

FOREMAN_FLEET="$D_B" show_operator_actions > "$T/surface_b.txt" 2>&1 || true
has "$(cat "$T/surface_b.txt")" "OK" "(b3) OK verdict in operator actions"

echo; echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] && echo "ALL FOREMAN-WIRE TESTS PASS" || exit 1
