#!/usr/bin/env bash
# gate-parity-timeout.test.sh — TIMEOUT/UNKNOWN classification red-proof for GATE-PARITY
# (fleet/checks/gate-parity.sh, ticket GATE-PARITY-TIMEOUT-FLAKE).
#
# RED-PROOFS the timeout->UNKNOWN classification so "could not check" is NEVER read as
# "check failed" (RED) or "check passed" (GREEN). The exit code 8 shape matches
# AUTH-302-SILENT-FAILURE / EVAL-REGISTRY-DERIVE / CRON-REGISTRY-VISIBLE.
#
# FULLY HERMETIC: isolated board/state/done dirs, no network, no live board interaction.
# The REAL fleet/checks/gate-parity.sh is run UNMODIFIED via env overrides.
#
# Covers:
#   (T1) timeout -> UNKNOWN (exit 8), output says UNKNOWN, not RED/GREEN terminology
#   (T2) scan with generous budget -> real verdict (exit 0 or 1, never 8)
#   (T3) ANTIRED: splittable-unjustified -> RED (exit 1) even with generous timeout
#   (T4) ANTIRED: clean board -> GREEN (exit 0) with generous timeout
#   (T5) board with mixed live/parked/done -> UNKNOWN on timeout, never a false GREEN
#   (T6) error -> RED (exit 2) — missing board dir, fail-closed
#   (T7) timeout=0 (disabled) completes normally
#
# Run:  bash fleet/tests/gate-parity-timeout.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$SRC/checks/gate-parity.sh"
[ -f "$GATE" ] || { echo "FAIL: cannot find $GATE" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }
no(){  printf '%s' "$1" | grep -q -- "$2" && bad "$3 (unexpected '$2')" || ok "$3"; }

mk_board(){
  local d; d="$(mktemp -d)"
  mkdir -p "$d/board" "$d/state/done"
  echo "$d"
}

write_ticket(){
  local d="$1" id="$2" diff="$3" owns="$4"; shift 4 || true
  {
    echo "tier: strong"
    echo "difficulty: $diff"
    echo "work_class: ci-infra"
    echo "branch: feat/${id,,}"
    echo "owns: $owns"
    for extra in "$@"; do echo "$extra"; done
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

# ========================================================================
# (T1) timeout -> UNKNOWN (exit 8). Bulk board of difficulty-1 tickets so scan
# budget is exceeded before completion. Each file forces a field() subprocess
# (grep+sed); pass 1 walks them all to build the parent map, then pass 2
# starts and the per-iteration timeout check fires.
D="$(mk_board)"
N_FILES=500
for i in $(seq 1 "$N_FILES"); do
  printf 'tier: economy\ndifficulty: 1\nwork_class: ci-infra\nbranch: feat/t%d\nowns: src/t%d.py\n' "$i" "$i" > "$D/board/T-$i.md"
done

export GATE_PARITY_BOARD="$D/board" GATE_PARITY_DONE_DIR="$D/state/done"
out="$(GATE_PARITY_TIMEOUT=1 bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 8 ] && ok "(T1) timeout (1s, $N_FILES files) -> UNKNOWN (exit $rc)" \
                || bad "(T1) timeout -> UNKNOWN (got exit $rc, expected 8)"
has "$out" "UNKNOWN"  "(T1) output contains UNKNOWN classification"
no  "$out" "PARITY GAP" "(T1) output does NOT say PARITY GAP (would read as RED)"
no  "$out" "parity holds" "(T1) output does NOT say parity holds (would read as GREEN)"
rm -rf "$D"

# ========================================================================
# (T2) scan with generous budget -> real verdict (0 or 1), never 8.
D="$(mk_board)"
export GATE_PARITY_BOARD="$D/board" GATE_PARITY_DONE_DIR="$D/state/done"

# empty board -> should be GREEN
out="$(GATE_PARITY_TIMEOUT=120 bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(T2) empty board + generous timeout -> GREEN (exit $rc)" \
                || bad "(T2) empty board + generous timeout -> rc=$rc (expected 0)"
has "$out" "parity holds" "(T2) verdict confirms parity holds"
no  "$out" "UNKNOWN" "(T2) no spurious UNKNOWN on a completed scan"
rm -rf "$D"

# ========================================================================
# (T3) ANTIRED: splittable-unjustified -> RED (exit 1) with generous timeout.
# A fix that turns real findings into UNKNOWN is worse than the flake.
D="$(mk_board)"
export GATE_PARITY_BOARD="$D/board" GATE_PARITY_DONE_DIR="$D/state/done"

write_ticket "$D" SPLIT-FLAKE 4 "src/a.py, src/b.py"

out="$(GATE_PARITY_TIMEOUT=120 bash "$GATE" check SPLIT-FLAKE 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(T3) ANTIRED: splittable-unjustified -> RED (exit $rc, expected non-zero)" \
                || bad "(T3) ANTIRED BROKEN: splittable-unjustified -> rc=$rc (GREEN — took finding away)"
has "$out" "would be refused at launch" "(T3) message names the parity gap"
has "$out" "SPLIT-FLAKE" "(T3) message names the offending ticket"
no  "$out" "UNKNOWN" "(T3) real finding is RED, not UNKNOWN"

out="$(GATE_PARITY_TIMEOUT=120 bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 1 ] && ok "(T3a) scan with violation -> RED (exit 1)" \
                || bad "(T3a) scan with violation -> rc=$rc (expected 1)"
has "$out" "PARITY GAP" "(T3a) scan output names PARITY GAP"
no  "$out" "UNKNOWN" "(T3a) scan: real finding is RED, not UNKNOWN"
rm -rf "$D"

# ========================================================================
# (T4) ANTIRED: clean board -> GREEN (exit 0) with generous timeout.
D="$(mk_board)"
export GATE_PARITY_BOARD="$D/board" GATE_PARITY_DONE_DIR="$D/state/done"

write_ticket "$D" CLEAN-OK 4 "src/a.py, src/b.py" "serial_justified: single operator call"
write_ticket "$D" LOW 1 "src/one.py"

out="$(GATE_PARITY_TIMEOUT=120 bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(T4) justified + low-difficulty board -> GREEN (exit 0)" \
                || bad "(T4) justified board -> rc=$rc (expected 0)"
has "$out" "parity holds" "(T4) verdict confirms parity holds"
no  "$out" "UNKNOWN" "(T4) completed scan is GREEN, not UNKNOWN"
rm -rf "$D"

# ========================================================================
# (T5) Board with parked + done tickets does not inflate scan budget; timeout
# on a large parked/done board still produces UNKNOWN, never GREEN.
D="$(mk_board)"
export GATE_PARITY_BOARD="$D/board" GATE_PARITY_DONE_DIR="$D/state/done"

# parked ticket
{
  echo "tier: strong"
  echo "difficulty: 4"
  echo "work_class: ci-infra"
  echo "branch: feat/parked-one"
  echo "owns: src/a.py, src/b.py"
  echo "parked: true"
} > "$D/board/PARKED.md"

# done marker
touch "$D/state/done/DONE"

{
  echo "tier: strong"
  echo "difficulty: 4"
  echo "work_class: ci-infra"
  echo "branch: feat/done-one"
  echo "owns: src/c.py, src/d.py"
} > "$D/board/DONE.md"

out="$(GATE_PARITY_TIMEOUT=120 bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(T5) parked+d-only (no live splittable) -> GREEN (exit 0)" \
                || bad "(T5) parked+d-only -> rc=$rc (expected 0)"
has "$out" "parity holds" "(T5) parked+d-only verdict confirms parity holds"

# large bulk parked board + timeout -> UNKNOWN
for i in $(seq 1 500); do
  printf 'tier: economy\ndifficulty: 1\nwork_class: ci-infra\nbranch: feat/p%d\nowns: src/p%d.py\nparked: true\n' "$i" "$i" > "$D/board/P-$i.md"
done

out="$(GATE_PARITY_TIMEOUT=1 bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 8 ] && ok "(T5a) large parked board + 1s timeout -> UNKNOWN (exit 8)" \
                || bad "(T5a) large parked board + 1s timeout -> rc=$rc (expected 8)"
has "$out" "UNKNOWN" "(T5a) output contains UNKNOWN (parked don't count but bulk scan still times out)"
rm -rf "$D"

# ========================================================================
# (T6) error -> fail-closed: check mode on non-existent ticket file (exit 2).
# scan on an empty board correctly returns 0 — no tickets = no violations.
# check on a missing ticket is the unambiguous error case.
D="$(mk_board)"
export GATE_PARITY_BOARD="$D/board" GATE_PARITY_DONE_DIR="$D/state/done"

out="$(GATE_PARITY_TIMEOUT=120 bash "$GATE" check NOSUCH 2>&1)"; rc=$?
[ "$rc" -eq 2 ] && ok "(T6) check non-existent ticket -> ERROR (exit 2, fail-closed)" \
                || bad "(T6) check non-existent ticket -> rc=$rc (expected 2)"
has "$out" "no such board ticket" "(T6) message says no such board ticket"

# Also verify empty board scan is GREEN (vacuous: no tickets = no violations)
out="$(GATE_PARITY_TIMEOUT=120 bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(T6a) empty board scan -> GREEN (exit 0, vacuous pass)" \
                || bad "(T6a) empty board scan -> rc=$rc (expected 0)"
rm -rf "$D"

# ========================================================================
# (T7) timeout=0 (disabled) completes normally — zero does NOT trigger timeout.
D="$(mk_board)"
export GATE_PARITY_BOARD="$D/board" GATE_PARITY_DONE_DIR="$D/state/done"

write_ticket "$D" NO-TO 1 "src/one.py"

out="$(GATE_PARITY_TIMEOUT=0 bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(T7) timeout=0 (disabled) -> GREEN (exit 0, scan completed)" \
                || bad "(T7) timeout=0 disabled -> rc=$rc (expected 0)"
has "$out" "parity holds" "(T7) disabled timeout: parity holds"
no  "$out" "UNKNOWN" "(T7) timeout=0 does NOT produce UNKNOWN"

# timeout=0 also works for check
out="$(GATE_PARITY_TIMEOUT=0 bash "$GATE" check NO-TO 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(T7a) timeout=0 check -> GREEN (exit 0)" \
                || bad "(T7a) timeout=0 check -> rc=$rc (expected 0)"
rm -rf "$D"

# ========================================================================
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL GATE-PARITY TIMEOUT/UNKNOWN CLASSIFICATION TESTS PASS"
