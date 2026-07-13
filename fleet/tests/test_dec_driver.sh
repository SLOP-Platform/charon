#!/usr/bin/env bash
# test_dec_driver.sh — FAIL-ON-REVERT tests for fleet/decompose.sh (DEC-DRIVER).
#
# The product decomposer engine (change_surface + plan_decomposition) needs a live strong
# model, so calling it live here is impractical + non-deterministic. We therefore MOCK the
# engine via decompose.sh's DEC_PLAN_CMD seam (the REAL path always calls the product
# engine; only the plan SOURCE is swapped). What is exercised for real is the part this
# ticket owns: the driver's step-3 VALIDATE guard (intake.assert_disjoint_waves + strict
# all-pairs disjoint-owns) and step-4 EMIT (board *.md with parent / disjoint owns /
# depends_on chain).
#
# Cases:
#   (i)   GREEN split — mock returns 2 DISJOINT units (beta depends_on alpha). The driver
#         emits >=2 board sub-tickets, each with `parent:` set, disjoint `owns:`, and the
#         depends_on chain preserved. Emitted into the REAL board + validate_board.sh is
#         asserted to stay at its baseline exit (proves the emitted tickets are board-VALID),
#         then cleaned up.
#   (ii)  FAIL-ON-REVERT — mock returns 2 OVERLAPPING units (identical owns). The driver
#         MUST refuse: non-zero exit and ZERO board files written. Reverting decompose.sh's
#         validate step makes these overlapping tickets get emitted -> this assertion flips
#         RED. (Same for the zero-units plan.)
#
# Run:  bash fleet/tests/test_dec_driver.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"      # the fleet/ dir
DRIVER="$SRC/decompose.sh"
REAL_BOARD="$SRC/board"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }

TMP="$(mktemp -d)"
# Any children the GREEN case emits into the REAL board are named decdrv-fixture-* and are
# removed here no matter how the test exits (never leave fixtures on the live board).
cleanup(){ rm -f "$REAL_BOARD"/decdrv-fixture-*.md; rm -rf "$TMP"; }
trap cleanup EXIT

FIX_A="src/charon/_decdrv_fixture_alpha.py"
FIX_B="src/charon/_decdrv_fixture_beta.py"

# The broad parent ticket (lives ONLY in $TMP, passed via TICKET_FILE, so it never touches
# the real board). Inherited fields (work_class/difficulty/repo) flow into the children.
cat > "$TMP/parent.md" <<EOF
tier: frontier
difficulty: 4
work_class: greenfield-feature
branch: feat/decdrv-fixture-parent
repo: charon
depends_on:
owns: $FIX_A, $FIX_B
accept: |
  A deliberately broad fixture ticket that crosses two modules.
note: decompose fixture parent
EOF

# ---- (i) GREEN split: 2 disjoint units, beta depends_on alpha ----------------
cat > "$TMP/plan_ok.json" <<EOF
{"units":[
  {"id":"decdrv-fixture-alpha","goal":"own alpha module","accept":["revert alpha -> RED"],"owns":["$FIX_A"],"depends_on":[],"tier":"med"},
  {"id":"decdrv-fixture-beta","goal":"own beta module","accept":["revert beta -> RED"],"owns":["$FIX_B"],"depends_on":["decdrv-fixture-alpha"],"tier":"med"}
]}
EOF

# baseline validate_board exit BEFORE emitting anything into the real board
CHARON_REPO=/home/stack/code/charon bash "$SRC/validate_board.sh" >/dev/null 2>&1; base_rc=$?

out="$(TICKET_FILE="$TMP/parent.md" BOARD_DIR="$REAL_BOARD" \
       DEC_PLAN_CMD="cat '$TMP/plan_ok.json'" \
       bash "$DRIVER" DECDRV-FIXTURE-PARENT 2>&1)"; rc=$?
[ "$rc" = "0" ] && ok "GREEN split: driver exits 0" || bad "GREEN split: driver exits 0 (got $rc: $out)"

n=$(ls "$REAL_BOARD"/decdrv-fixture-*.md 2>/dev/null | wc -l)
[ "$n" -ge 2 ] && ok "GREEN split: emitted >=2 board sub-tickets (got $n)" || bad "GREEN split: emitted >=2 board sub-tickets (got $n)"

A_FILE="$REAL_BOARD/decdrv-fixture-alpha.md"
B_FILE="$REAL_BOARD/decdrv-fixture-beta.md"
if [ -f "$A_FILE" ] && [ -f "$B_FILE" ]; then
  has "$(cat "$A_FILE")" "parent: DECDRV-FIXTURE-PARENT" "alpha sub-ticket has parent set"
  has "$(cat "$B_FILE")" "parent: DECDRV-FIXTURE-PARENT" "beta sub-ticket has parent set"
  has "$(cat "$A_FILE")" "owns: $FIX_A"                  "alpha owns only its own file"
  has "$(cat "$B_FILE")" "owns: $FIX_B"                  "beta owns only its own file"
  has "$(cat "$B_FILE")" "depends_on: decdrv-fixture-alpha" "depends_on chain preserved (beta->alpha)"
  # disjoint owns: alpha's file must NOT appear in beta's ticket and vice-versa
  grep -q -- "$FIX_A" "$B_FILE" && bad "owns are disjoint (alpha leaked into beta)" || ok "owns are disjoint (alpha not in beta)"
else
  bad "expected both alpha + beta sub-ticket files to exist"
fi

# The emitted sub-tickets must be BOARD-VALID: validate_board must not regress from baseline.
CHARON_REPO=/home/stack/code/charon bash "$SRC/validate_board.sh" >/dev/null 2>&1; after_rc=$?
[ "$after_rc" = "$base_rc" ] && ok "emitted sub-tickets keep validate_board at baseline (rc=$after_rc)" \
  || bad "emitted sub-tickets regressed validate_board (baseline=$base_rc, after=$after_rc)"

rm -f "$REAL_BOARD"/decdrv-fixture-*.md

# ---- (ii) FAIL-ON-REVERT: overlapping owns MUST be refused, ZERO emitted ------
# Isolated temp board so a (wrongly) emitted ticket cannot reach the live board.
mkdir -p "$TMP/board2"
cat > "$TMP/plan_overlap.json" <<EOF
{"units":[
  {"id":"decdrv-fixture-alpha","goal":"own shared","accept":["x"],"owns":["$FIX_A"],"depends_on":[],"tier":"med"},
  {"id":"decdrv-fixture-beta","goal":"own shared too","accept":["y"],"owns":["$FIX_A"],"depends_on":[],"tier":"med"}
]}
EOF
out="$(TICKET_FILE="$TMP/parent.md" BOARD_DIR="$TMP/board2" \
       DEC_PLAN_CMD="cat '$TMP/plan_overlap.json'" \
       bash "$DRIVER" DECDRV-FIXTURE-PARENT 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "overlap plan: driver REFUSES (non-zero exit)" || bad "overlap plan: driver REFUSES (got rc=0 — validate step reverted?)"
n=$(ls "$TMP/board2"/*.md 2>/dev/null | wc -l)
[ "$n" = "0" ] && ok "overlap plan: emitted ZERO sub-tickets" || bad "overlap plan: emitted ZERO sub-tickets (got $n — overlapping owns leaked to board)"

# ---- (iii) zero-units plan MUST also be refused ------------------------------
mkdir -p "$TMP/board3"
echo '{"units":[]}' > "$TMP/plan_empty.json"
out="$(TICKET_FILE="$TMP/parent.md" BOARD_DIR="$TMP/board3" \
       DEC_PLAN_CMD="cat '$TMP/plan_empty.json'" \
       bash "$DRIVER" DECDRV-FIXTURE-PARENT 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "empty plan: driver REFUSES (non-zero exit)" || bad "empty plan: driver REFUSES (got rc=0)"
n=$(ls "$TMP/board3"/*.md 2>/dev/null | wc -l)
[ "$n" = "0" ] && ok "empty plan: emitted ZERO sub-tickets" || bad "empty plan: emitted ZERO sub-tickets (got $n)"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL DEC-DRIVER TESTS PASS"
