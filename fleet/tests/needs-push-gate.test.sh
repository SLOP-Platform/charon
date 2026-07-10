#!/usr/bin/env bash
# needs-push-gate.test.sh — FAIL-ON-REVERT tests for the #3 needs-push preflight gate
# (fleet/preflight.sh detect_needs_push). SOURCES a COPY of preflight.sh in an isolated temp
# fleet (the copy resolves HERE/TSV to the temp dir; the dispatch is guarded so sourcing has NO
# side effects) and drives detect_needs_push + cmd_scan directly. NEVER touches the live reds.tsv.
#
# Covers:
#   (a) a live needs-push marker AUTO-REGISTERS an open red 'needs-push-<id>'.
#   (b) that red is STILL-RED -> cmd_scan (the preflight gate) exits non-zero (BLOCKS).
#   (c) once the marker is gone (landed), the red AUTO-CLOSES and the gate goes green.
#   (d) a marker whose ticket is already state/done is stale -> cleared, no red.
# Reverting detect_needs_push leaves no red -> (a)/(b) fail.
#
# Run:  bash fleet/tests/needs-push-gate.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# isolated temp fleet: a copy of preflight.sh + a minimal reds.tsv + empty state dirs.
D="$(mktemp -d)"
cp "$SRC/preflight.sh" "$D/preflight.sh"
printf '# reds registry (test fixture)\n# id\topened\tsev\tarea\tdesc\tcheck\tstatus\tclosed_by\n' > "$D/reds.tsv"
mkdir -p "$D/state/needs-push" "$D/state/done"

# red status by id (blank if absent), reading the temp reds.tsv.
red_status(){ awk -F'\t' -v id="$1" '$1==id{print $7; exit}' "$D/reds.tsv"; }

# shellcheck source=/dev/null
source "$D/preflight.sh"   # exposes detect_needs_push, cmd_scan, etc. (dispatch guarded)

echo "== (a) live marker auto-registers an open red =="
: > "$D/state/needs-push/TICK-X"
detect_needs_push >/dev/null 2>&1
check "a1 red 'needs-push-tick-x' is open" "$(red_status needs-push-tick-x)" "open"

echo "== (b) the gate BLOCKS while the marker is live =="
rc=0; cmd_scan >/dev/null 2>&1 || rc=$?
check "b1 cmd_scan (preflight gate) exits non-zero" "$rc" "1"

echo "== (c) landing the push auto-closes the red and the gate goes green =="
rm -f "$D/state/needs-push/TICK-X"        # simulate the push landing (submit.sh clears the marker)
detect_needs_push >/dev/null 2>&1
check "c1 red auto-closed" "$(red_status needs-push-tick-x)" "closed"
rc=0; cmd_scan >/dev/null 2>&1 || rc=$?
check "c2 gate now green (cmd_scan exits 0)" "$rc" "0"

echo "== (d) a marker whose ticket is already done is stale -> cleared, no red =="
: > "$D/state/needs-push/TICK-Y"
: > "$D/state/done/TICK-Y"
detect_needs_push >/dev/null 2>&1
[ -e "$D/state/needs-push/TICK-Y" ] && bad "d1 stale marker cleared" || ok "d1 stale marker cleared"
case "$(red_status needs-push-tick-y)" in ""|closed) ok "d2 no live red for a done ticket";;
  *) bad "d2 no live red for a done ticket (got '$(red_status needs-push-tick-y)')";; esac

rm -rf "$D"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL NEEDS-PUSH-GATE TESTS PASS"
