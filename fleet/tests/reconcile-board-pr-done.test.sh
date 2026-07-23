#!/usr/bin/env bash
# reconcile-board-pr-done.test.sh — FAIL-ON-REVERT tests for the board-PR-done reconciler.
# Tests (via RECONCILE_MERGED_SRC fixture; no gh / no network):
#   (a) merged PR with no ticket -> R-B RED
#   (b) open ticket whose branch: matches a merged PR -> R-A RED, then done-marker present -> GREEN
#   (c) N>1-owner overlap with no branch/title/sha match -> AMBIGUOUS (RED), not auto-closed
# Reverting the disambiguation ladder -> test (c) fails.
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }

d="$(mktemp -d)"
mkdir -p "$d/fleet/checks" "$d/fleet/board/archive" "$d/fleet/state/done" "$d/fleet/state/reviewed"
cp "$SRC/checks/reconcile-board-pr-done.sh" "$d/fleet/checks/"
CHECK="$d/fleet/checks/reconcile-board-pr-done.sh"

echo "=== (a) merged PR with no ticket -> R-B RED ==="
  printf 'tier: economy\nbranch: feat/tick-a\nowns: src/a.py\nwork_class: docs\n' > "$d/fleet/board/TICK-A.md"
  printf 'feat/orphan\tdeadbeef\tsrc/zzz.py\t101\n' > "$d/a.tsv"
  out_a="$(RECONCILE_MERGED_SRC="$d/a.tsv" bash "$CHECK" 2>&1)"; rc_a=$?
  echo "$out_a" | grep -q "R-B" && ok "a merged PR with no ticket -> R-B reported" \
                                  || bad "a merged PR with no ticket -> R-B reported (output: $out_a)"
  [ "$rc_a" != 0 ] && ok "a R-B exits non-zero" || bad "a R-B exits non-zero (rc=$rc_a)"

echo "=== (b) open ticket -> R-A RED, then done-marker -> GREEN ==="
  printf 'feat/tick-a\tdeadbeef\tsrc/a.py\t201\n' > "$d/b.tsv"
  out_b1="$(RECONCILE_MERGED_SRC="$d/b.tsv" bash "$CHECK" 2>&1)"; rc_b1=$?
  echo "$out_b1" | grep -q "R-A" && ok "b1 open ticket with merged PR -> R-A reported" \
                                    || bad "b1 open ticket with merged PR -> R-A reported"
  [ "$rc_b1" != 0 ] && ok "b1 R-A exits non-zero" || bad "b1 R-A exits non-zero (rc=$rc_b1)"

  # Create done marker for TICK-A (simulates reconcile-merged.sh or operator action)
  printf '%s\tmerged:%s\tbranch:feat/tick-a\n' "$(date -u +%FT%TZ)" "deadbeef" > "$d/fleet/state/done/TICK-A"
  out_b2="$(RECONCILE_MERGED_SRC="$d/b.tsv" bash "$CHECK" 2>&1)"; rc_b2=$?
  echo "$out_b2" | grep -q "R-A" && bad "b2 after done-marker, R-A NOT reported" \
                                    || ok "b2 after done-marker, R-A NOT reported"
  [ "$rc_b2" = 0 ] && ok "b2 done ticket -> GREEN (exit 0)" || bad "b2 done ticket -> GREEN (rc=$rc_b2)"
  rm -f "$d/fleet/state/done/TICK-A"

echo "=== (c) N>1-owner overlap with no branch/title/sha match -> AMBIGUOUS (RED) ==="
  printf 'tier: economy\nbranch: feat/shared-beta\nowns: src/shared.py\nwork_class: docs\n' > "$d/fleet/board/TICK-SH1.md"
  printf 'tier: economy\nbranch: feat/shared-gamma\nowns: src/shared.py\nwork_class: docs\n' > "$d/fleet/board/TICK-SH2.md"
  printf 'feat/DRIFTED-SHARED\tdeadbeef\tsrc/shared.py\t301\n' > "$d/c.tsv"
  out_c="$(RECONCILE_MERGED_SRC="$d/c.tsv" bash "$CHECK" 2>&1)"; rc_c=$?
  echo "$out_c" | grep -qi "AMBIGUOUS\|NEEDS-MANUAL" && ok "c N>1 overlap -> AMBIGUOUS reported" \
                                                       || bad "c N>1 overlap -> AMBIGUOUS reported (output: $out_c)"
  [ "$rc_c" != 0 ] && ok "c AMBIGUOUS exits non-zero" || bad "c AMBIGUOUS exits non-zero (rc=$rc_c)"
  echo "$out_c" | grep -q "R-A" && bad "c no R-A for either shared-owner ticket" \
                                  || ok "c no R-A for either shared-owner ticket"

echo "=== (d) clean/empty state: no merged PRs -> GREEN ==="
  printf '' > "$d/d.tsv"
  out_d="$(RECONCILE_MERGED_SRC="$d/d.tsv" bash "$CHECK" 2>&1)"; rc_d=$?
  [ "$rc_d" = 0 ] && ok "d empty merged PRs -> GREEN (exit 0)" || bad "d empty merged PRs -> GREEN (rc=$rc_d)"

rm -rf "$d"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL RECONCILE-BOARD-PR-DONE TESTS PASS"
