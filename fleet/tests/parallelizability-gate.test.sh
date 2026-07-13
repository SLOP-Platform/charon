#!/usr/bin/env bash
# parallelizability-gate.test.sh — FAIL-ON-REVERT tests for the F46 PARALLELIZABILITY-GATE
# (fleet/checks/parallelizability-gate.sh), which mechanizes the operator's wall-clock rule:
# a SPLITTABLE ticket (difficulty>=M AND >1 independent owned surface) must not silently run
# as one SERIAL job — it must be decomposed or carry an explicit justification.
#
# Operates entirely in a TEMP isolated board (PARALLEL_GATE_BOARD/PARALLEL_GATE_DONE_DIR env
# overrides) — never touches the live fleet/board or fleet/state.
#
# Covers:
#   (a) SPLITTABLE + serial + no decomposition + no justification -> `check` FAILS (exit 1)
#       and the message names the ticket, WHY it's splittable, and BOTH ways to pass
#       (decompose / --serial-justified). THIS IS THE CORE, LOAD-BEARING ASSERTION: if the
#       splittable+serial+unjustified detection in parallelizability-gate.sh is ever reverted
#       (e.g. the FAIL branch is dropped, or is_splittable/is_decomposed/is_justified always
#       return true), this case wrongly exits 0 and (a) below fails RED — proving the gate is
#       load-bearing, not decorative.
#   (b) the SAME splittable ticket, DECOMPOSED (>=2 other board tickets carry
#       'parent: <id>') -> `check` PASSES (exit 0).
#   (c) the SAME splittable ticket with a 'serial_justified: <reason>' FIELD -> PASSES.
#   (d) the SAME splittable ticket with NO field, launched with a CLI
#       --serial-justified=<reason> arg -> PASSES.
#   (e) NOT splittable (difficulty below M, or only 1 owned surface) -> PASSES either way.
#   (f) `scan` mode: an unjustified splittable ticket shows up as SPLITTABLE-SERIAL and scan
#       ALWAYS exits 0 (advisory, never fails the board on its own).
#
# Run:  bash fleet/tests/parallelizability-gate.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$SRC/checks/parallelizability-gate.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }

mk_board(){
  local d; d="$(mktemp -d)"
  mkdir -p "$d/board" "$d/state/done"
  echo "$d"
}
write_ticket(){
  # write_ticket <dir> <id> <difficulty> <owns-csv> [extra-field-line]
  local d="$1" id="$2" diff="$3" owns="$4" extra="${5:-}"
  {
    echo "tier: strong"
    echo "difficulty: $diff"
    echo "work_class: ci-infra"
    echo "branch: feat/${id,,}"
    echo "owns: $owns"
    [ -n "$extra" ] && echo "$extra"
  } > "$d/board/$id.md"
}
write_child(){
  local d="$1" id="$2" parent="$3" owns="$4"
  {
    echo "tier: strong"
    echo "difficulty: 2"
    echo "work_class: ci-infra"
    echo "branch: feat/${id,,}"
    echo "parent: $parent"
    echo "owns: $owns"
  } > "$d/board/$id.md"
}

D="$(mk_board)"
export PARALLEL_GATE_BOARD="$D/board" PARALLEL_GATE_DONE_DIR="$D/state/done"

# ---- (a) splittable + serial + unjustified -> FAIL, message names ticket + both remedies ----
write_ticket "$D" SPLIT-1 4 "a/one.py, b/two.py"
out="$(bash "$GATE" check SPLIT-1 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(a) unjustified splittable ticket FAILS (core, load-bearing check)" \
                || bad "(a) unjustified splittable ticket FAILS (core, load-bearing check) (got exit 0 — GATE REVERTED)"
has "$out" "SPLIT-1"              "(a) message names the ticket"
has "$out" "SPLITTABLE"           "(a) message states why (splittable)"
has "$out" "decompose.sh SPLIT-1" "(a) message gives remedy 1 (decompose)"
has "$out" "serial-justified"     "(a) message gives remedy 2 (--serial-justified)"

# ---- (b) decomposed -> PASS ----
write_child "$D" CHILD-1 SPLIT-1 "a/one.py"
write_child "$D" CHILD-2 SPLIT-1 "b/two.py"
out="$(bash "$GATE" check SPLIT-1 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(b) decomposed splittable ticket PASSES" || bad "(b) decomposed splittable ticket PASSES (got exit $rc)"
has "$out" "DECOMPOSED" "(b) message confirms decomposed reason"
rm -f "$D/board/CHILD-1.md" "$D/board/CHILD-2.md"

# ---- (c) ticket-field justified -> PASS ----
write_ticket "$D" SPLIT-2 4 "a/one.py, b/two.py" "serial_justified: single session cheaper than 2 PRs"
out="$(bash "$GATE" check SPLIT-2 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(c) serial_justified field PASSES" || bad "(c) serial_justified field PASSES (got exit $rc)"
has "$out" "JUSTIFIED" "(c) message confirms justified reason"

# ---- (d) CLI --serial-justified -> PASS (ticket has NO field) ----
out="$(bash "$GATE" check SPLIT-1 --serial-justified=ops-call 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(d) CLI --serial-justified PASSES" || bad "(d) CLI --serial-justified PASSES (got exit $rc)"
has "$out" "ops-call" "(d) message echoes the CLI reason"

# ---- (e) not splittable: difficulty below M ----
write_ticket "$D" LOWDIFF 2 "a/one.py, b/two.py"
bash "$GATE" check LOWDIFF >/dev/null 2>&1
[ $? -eq 0 ] && ok "(e1) below-M difficulty is not splittable -> PASSES" || bad "(e1) below-M difficulty is not splittable -> PASSES"

# ---- (e) not splittable: single owned surface ----
write_ticket "$D" ONESURF 4 "a/one.py"
bash "$GATE" check ONESURF >/dev/null 2>&1
[ $? -eq 0 ] && ok "(e2) single owned surface is not splittable -> PASSES" || bad "(e2) single owned surface is not splittable -> PASSES"

# ---- (f) scan: unjustified splittable ticket is surfaced; scan always exits 0 ----
out="$(bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(f) scan mode always exits 0 (advisory)" || bad "(f) scan mode always exits 0 (advisory) (got $rc)"
has "$out" "SPLITTABLE-SERIAL: SPLIT-1" "(f) scan surfaces the unjustified splittable ticket"

rm -rf "$D"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL PARALLELIZABILITY-GATE TESTS PASS"
