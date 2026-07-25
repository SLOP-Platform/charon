#!/usr/bin/env bash
# wci-strict.test.sh — FAIL-ON-REVERT tests for wci-contention.sh's --strict HARD gate
# (DEC-VALIDATE-STRICT). Runs entirely OFFLINE in an isolated temp fleet; NEVER touches
# the live fleet/board or the product repo. The script under test resolves its board via
# $HERE/board, so each fixture copies wci-contention.sh into a temp dir + writes a board/
# there — a self-contained fixture, no env override needed.
#
# Covers:
#   (i)   COLLISION board (2 LIVE tickets own the SAME file):
#           --strict            -> exits NON-ZERO and NAMES the colliding file.
#           default (no flag)   -> exits 0 (advisory behavior UNCHANGED even on collision).
#   (ii)  DISJOINT board (every file owned by exactly one ticket):
#           --strict            -> exits 0.
#
# FAIL-ON-REVERT: revert the --strict branch of wci-contention.sh and case (i) --strict
# stops exiting non-zero (an unknown/positional "--strict" arg is a no-op that keeps the
# old always-0 advisory path) -> this test goes RED.
#
# Run:  bash fleet/tests/wci-strict.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }

# Build an isolated fleet dir holding only wci-contention.sh + an empty board/.
mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/wci-contention.sh" "$d/"
  mkdir -p "$d/board"
  echo "$d"
}
# Write a live board ticket. Args: dir id owns-csv
mk_ticket(){
  local d="$1" id="$2" owns="$3"
  {
    echo "tier: economy"
    echo "difficulty: 1"
    echo "work_class: docs"
    echo "branch: feat/${id}"
    echo "depends_on:"
    echo "owns: ${owns}"
    echo "prompt: ${d}/prompts/${id}.md"
  } > "$d/board/${id}.md"
}

COLLIDE="src/shared/god_module.py"

# ---- (i) COLLISION board: two LIVE tickets own the SAME file ----------------
d="$(mk_fleet)"
mk_ticket "$d" TICK-A "$COLLIDE, src/a_only.py"
mk_ticket "$d" TICK-B "$COLLIDE, src/b_only.py"

# --strict MUST fail hard and name the colliding file.
out="$(bash "$d/wci-contention.sh" --strict 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "collision + --strict exits non-zero" || bad "collision + --strict exits non-zero (got $rc)"
has "$out" "$COLLIDE" "collision + --strict names the colliding file"
has "$out" "COLLISION" "collision + --strict labels it a COLLISION"

# default (no flag) MUST stay advisory (exit 0) even with the collision present.
out="$(bash "$d/wci-contention.sh" 2>&1)"; rc=$?
[ "$rc" = "0" ] && ok "collision + default exits 0 (advisory unchanged)" || bad "collision + default exits 0 (got $rc)"
rm -rf "$d"

# ---- (ii) DISJOINT board: every file owned by exactly one ticket ------------
d="$(mk_fleet)"
mk_ticket "$d" TICK-A "src/a_one.py, src/a_two.py"
mk_ticket "$d" TICK-B "src/b_one.py, src/b_two.py"
out="$(bash "$d/wci-contention.sh" --strict 2>&1)"; rc=$?
[ "$rc" = "0" ] && ok "disjoint + --strict exits 0" || bad "disjoint + --strict exits 0 (got $rc)"
rm -rf "$d"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL WCI-STRICT TESTS PASS"
