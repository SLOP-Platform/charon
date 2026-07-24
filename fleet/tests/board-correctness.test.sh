#!/usr/bin/env bash
# board-correctness.test.sh — FAIL-ON-REVERT tests for validate_board.sh's dependency +
# owns CORRECTNESS checks (audit item #15). Runs entirely OFFLINE in an isolated temp fleet;
# NEVER touches the live fleet/state or the product repo. CHARON_REPO is pointed at the temp
# dir (a non-git path) so the uncommitted-work check (#6) is a deterministic no-op.
#
# Covers:
#   (i)  a BROKEN board (dangling depends_on + a 2-node cycle + a self-dep) MUST fail RED,
#        and the output must name bad-dep, dep-cycle, and self-dep — so reverting any one of
#        the new checks drops its string and fails this test.
#   (ii) a VALID board MUST pass GREEN (exit 0) — guards against a false-positive that would
#        block every preflight (board_gate runs this each preflight).
#
# Run:  bash fleet/tests/board-correctness.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }
no(){  printf '%s' "$1" | grep -q -- "$2" && bad "$3 (unexpected '$2')" || ok "$3"; }

mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/validate_board.sh" "$d/"
  cp -r "$SRC/capability" "$d/capability"
  # validate_board.sh now invokes checks/gate-parity.sh (and siblings) by relative path — the
  # hermetic fixture MUST carry the checks/ dir or gate-parity fails "No such file" -> false RED
  # that silently reds the whole rig CI queue (2026-07-24 fixture-drift fix).
  cp -r "$SRC/checks" "$d/checks"
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/claims" "$d/state/submitted" "$d/prompts"
  echo "$d"
}
# Write a fully-valid ticket + its D&S prompt. Args: dir id branch [depends_on] [dep-kind-build?]
mk_ticket(){
  local d="$1" id="$2" branch="$3" deps="${4:-}" build="${5:-}"
  {
    echo "tier: economy"
    echo "difficulty: 1"
    echo "work_class: docs"
    echo "branch: $branch"
    echo "depends_on: $deps"
    [ -n "$build" ] && echo "dep-kind: build"
    echo "owns: docs/${id}.md"
    echo "prompt: $d/prompts/${id}.md"
  } > "$d/board/${id}.md"
  printf '# %s\n\n## Dependencies & sequence\nwave 1; concurrency-safe; depends_on: %s\n' \
    "$id" "$deps" > "$d/prompts/${id}.md"
}

# ---- (ii) VALID board: TICK-B is a justified (dep-kind: build) dependent of TICK-A ----
d="$(mk_fleet)"
mk_ticket "$d" TICK-A feat/tick-a ""       ""
mk_ticket "$d" TICK-B feat/tick-b "TICK-A" "build"
out="$(CHARON_REPO="$d" bash "$d/validate_board.sh" 2>&1)"; rc=$?
[ "$rc" = "0" ] && ok "valid board exits 0" || bad "valid board exits 0 (got $rc)"
has "$out" "GREEN" "valid board reports GREEN"
no  "$out" "  RED " "valid board has no RED lines"
rm -rf "$d"

# ---- (i) BROKEN board: dangling dep + cycle + self-dep ----
d="$(mk_fleet)"
mk_ticket "$d" TICK-A feat/tick-a ""            ""       # clean anchor
mk_ticket "$d" TICK-B feat/tick-b "GHOST-NONE"  "build"  # dangling depends_on -> bad-dep
mk_ticket "$d" TICK-C feat/tick-c "TICK-D"      "build"  # \
mk_ticket "$d" TICK-D feat/tick-d "TICK-C"      "build"  #  > 2-node cycle -> dep-cycle
mk_ticket "$d" TICK-E feat/tick-e "TICK-E"      "build"  # self-dep -> self-dep
out="$(CHARON_REPO="$d" bash "$d/validate_board.sh" 2>&1)"; rc=$?
[ "$rc" != "0" ] && ok "broken board exits non-zero" || bad "broken board exits non-zero (got 0)"
has "$out" "bad-dep"   "broken board names the dangling dep (bad-dep)"
has "$out" "dep-cycle" "broken board names the cycle (dep-cycle)"
has "$out" "self-dep"  "broken board names the self-dependency (self-dep)"
rm -rf "$d"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL BOARD-CORRECTNESS TESTS PASS"
