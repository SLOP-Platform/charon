#!/usr/bin/env bash
# needs-push-gate.test.sh — FAIL-ON-REVERT tests for the #3 needs-push preflight gate AND the
# Wave-A HIGH #1 fix (fleet/preflight.sh detect_needs_push must STOP trusting the done marker).
# SOURCES a COPY of preflight.sh (+ _lib.sh + verify-merged.sh) in an isolated temp fleet and
# drives detect_needs_push + cmd_scan directly. NEVER touches the live reds.tsv or product repo
# (verify_merged is driven entirely by VERIFY_MERGED_FIXTURE — fully offline).
#
# Covers:
#   (a) a live needs-push marker AUTO-REGISTERS an open red 'needs-push-<id>'.
#   (b) that red is STILL-RED -> cmd_scan (the preflight gate) exits non-zero (BLOCKS).
#   (c) once the marker is gone (landed), the red AUTO-CLOSES and the gate goes green.
#   (d) done + MERGE-VERIFIED -> stale marker cleared (the ONLY safe clear).
#   (e) HIGH #1: done + needs-push + NOT-verified -> marker KEPT + red stays OPEN (contradiction).
# Reverting detect_needs_push's ensure-red leaves (a)/(b) failing; reverting the HIGH #1 verify_merged
# guard (back to "done marker exists -> rm -f") clears the marker in (e) and fails it.
#
# Run:  bash fleet/tests/needs-push-gate.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

D="$(mktemp -d)"
cp "$SRC/preflight.sh" "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$D/"
printf '# reds registry (test fixture)\n# id\topened\tsev\tarea\tdesc\tcheck\tstatus\tclosed_by\n' > "$D/reds.tsv"
mkdir -p "$D/state/needs-push" "$D/state/done" "$D/board/archive"
# fixture: ONLY TICK-Y is merge-verified. TICK-Z is deliberately absent (not verified).
printf 'TICK-Y\n' > "$D/verified.txt"
export VERIFY_MERGED_FIXTURE="$D/verified.txt"

red_status(){ awk -F'\t' -v id="$1" '$1==id{print $7; exit}' "$D/reds.tsv"; }

# shellcheck source=/dev/null
source "$D/preflight.sh"   # exposes detect_needs_push, cmd_scan, verify_merged (dispatch guarded)

echo "== (a) live marker auto-registers an open red =="
: > "$D/state/needs-push/TICK-X"
detect_needs_push >/dev/null 2>&1
check "a1 red 'needs-push-tick-x' is open" "$(red_status needs-push-tick-x)" "open"

echo "== (b) the gate BLOCKS while the marker is live =="
rc=0; cmd_scan >/dev/null 2>&1 || rc=$?
check "b1 cmd_scan (preflight gate) exits non-zero" "$rc" "1"

echo "== (c) landing the push auto-closes the red and the gate goes green =="
rm -f "$D/state/needs-push/TICK-X"
detect_needs_push >/dev/null 2>&1
check "c1 red auto-closed" "$(red_status needs-push-tick-x)" "closed"
rc=0; cmd_scan >/dev/null 2>&1 || rc=$?
check "c2 gate now green (cmd_scan exits 0)" "$rc" "0"

echo "== (d) done + MERGE-VERIFIED -> stale marker cleared =="
: > "$D/state/needs-push/TICK-Y"
: > "$D/state/done/TICK-Y"
detect_needs_push >/dev/null 2>&1
[ -e "$D/state/needs-push/TICK-Y" ] && bad "d1 verified stale marker cleared" || ok "d1 verified stale marker cleared"
case "$(red_status needs-push-tick-y)" in ""|closed) ok "d2 no live red for a verified-done ticket";;
  *) bad "d2 no live red for a verified-done ticket (got '$(red_status needs-push-tick-y)')";; esac

echo "== (e) HIGH #1: done + needs-push + NOT-verified -> marker KEPT, red OPEN =="
: > "$D/state/needs-push/TICK-Z"
: > "$D/state/done/TICK-Z"       # a done marker that is NOT merge-verified (not in fixture)
detect_needs_push >/dev/null 2>&1
[ -e "$D/state/needs-push/TICK-Z" ] && ok "e1 guard KEPT (marker not silently deleted)" \
                                    || bad "e1 guard KEPT (marker not silently deleted)"
check "e2 blocking red stays open" "$(red_status needs-push-tick-z)" "open"
rc=0; cmd_scan >/dev/null 2>&1 || rc=$?
check "e3 gate BLOCKS on the unverified contradiction" "$rc" "1"

rm -rf "$D"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL NEEDS-PUSH-GATE TESTS PASS"
