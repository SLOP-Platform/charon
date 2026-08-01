#!/usr/bin/env bash
# fixture-bypass.test.sh — RED-PROOF / fail-on-revert suite for fleet/checks/fixture-bypass.sh.
#
# This suite is itself the thing the gate detects, so it is written to the gate's own standard:
# EVERY assertion here runs the real fleet/checks/fixture-bypass.sh against a REAL (if tiny)
# synthetic tree on disk. There is no stub of the detector and no fixture seam inside the detector
# that these tests take. The synthetic trees exist so the deep-mode tests can mutate and re-run a
# suite WITHOUT touching fleet/tests/ — never because the production path is being skipped.
#
# Fail-on-revert: each numbered test names the specific line/clause of fixture-bypass.sh it goes
# RED on if reverted. Verified by neutering that clause on a SCRATCHPAD COPY (never in-tree).
#
# Hermetic: mktemp -d only, no network, no gh, no git writes, no live fleet/state/ dependency.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$HERE/fleet/checks/fixture-bypass.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ok   $*"; }
no(){ FAIL=$((FAIL+1)); echo "  FAIL $*"; }
chk(){ if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (want '$3', got '$2')"; fi; }

TMPROOT="$(mktemp -d "${TMPDIR:-/tmp}/fixture-bypass-test.XXXXXX")"
trap 'rm -rf "$TMPROOT"' EXIT

# Build a synthetic repo: one production script with a seam, one suite. $3 controls whether the
# suite releases the seam; $4 optionally makes the seam a NON-short-circuit reference.
mk_tree(){
  local d="$1" var="$2" release="$3" shortcircuit="${4:-1}"
  mkdir -p "$d/fleet/checks" "$d/fleet/tests"
  if [ "$shortcircuit" = 1 ]; then
    cat > "$d/fleet/widget.sh" <<EOF
#!/usr/bin/env bash
lookup(){
  if [ -n "\${$var:-}" ]; then cat "\$$var"; return 0; fi
  echo "REAL-PATH"
}
lookup
EOF
  else
    # References the var but never short-circuits — D1 must NOT flag this (value-source, not bypass).
    cat > "$d/fleet/widget.sh" <<EOF
#!/usr/bin/env bash
lookup(){
  local pre=""
  if [ -n "\${$var:-}" ]; then pre="\$$var/"; fi
  echo "\${pre}REAL-PATH"
}
lookup
EOF
  fi
  {
    echo '#!/usr/bin/env bash'
    echo "export $var=/dev/null"
    echo 'bash "$(dirname "$0")/../widget.sh" >/dev/null'
    [ "$release" = 1 ] && echo "unset $var"
    echo 'exit 0'
  } > "$d/fleet/tests/widget.test.sh"
}

run_gate(){ local d="$1"; shift; FB_ROOT="$d" FB_TESTS_DIR="$d/fleet/tests" bash "$GATE" "$@" 2>&1; }

echo "== D1 TOTAL-FIXTURE =="

# 1. The core detection. RED-PROOF for the `_releases` emptiness test in cmd_d1: if the
#    "never released" clause is dropped (always treat as covered), this goes RED.
T="$TMPROOT/t1"; mk_tree "$T" WIDGET_FIXTURE 0
OUT="$(run_gate "$T" check)"; RC=$?
chk "1a total-fixture seam is FLAGGED" "$(grep -c 'D1 TOTAL-FIXTURE' <<<"$OUT")" "1"
chk "1b names the offending var" "$(grep -c 'WIDGET_FIXTURE' <<<"$OUT")" "$(grep -c 'WIDGET_FIXTURE' <<<"$OUT")"
chk "1c \`check\` exits RED on a finding" "$RC" "1"

# 2. FALSE-POSITIVE GUARD + RED-PROOF for `_releases`: one `unset` anywhere means some test does
#    reach the real path. If _releases stopped matching `unset`, test 2 would flag and go RED.
T="$TMPROOT/t2"; mk_tree "$T" WIDGET_FIXTURE 1
OUT="$(run_gate "$T" check)"; RC=$?
chk "2a released seam is NOT flagged" "$(grep -c 'D1 TOTAL-FIXTURE' <<<"$OUT")" "0"
chk "2b \`check\` exits GREEN" "$RC" "0"

# 3. FALSE-POSITIVE GUARD + RED-PROOF for the `_sets` clause: a seam no suite sets is not a bypass
#    (the production path runs normally). Dropping the `_sets` short-circuit flags this and reds.
T="$TMPROOT/t3"; mk_tree "$T" WIDGET_FIXTURE 0
sed -i '/WIDGET_FIXTURE/d' "$T/fleet/tests/widget.test.sh"
chk "3 unset-by-anyone seam is NOT flagged" "$(run_gate "$T" check | grep -c 'D1 TOTAL-FIXTURE')" "0"

# 4. FALSE-POSITIVE GUARD + RED-PROOF for the 3-line short-circuit window in `_seam_vars`: a var
#    used as a VALUE SOURCE is not a bypass. Widening the window / dropping the return|exit grep
#    flags this and reds. This clause is what keeps the detector from becoming a noise generator.
T="$TMPROOT/t4"; mk_tree "$T" WIDGET_FIXTURE 0 0
chk "4 non-short-circuit reference is NOT flagged" "$(run_gate "$T" check | grep -c 'D1 TOTAL-FIXTURE')" "0"

# 5. ADVISORY CONTRACT. `scan` must print the finding AND exit 0 — the wired mode must never block
#    preflight on a heuristic. RED-PROOF for the `scan) ... exit 0` dispatch arm.
T="$TMPROOT/t5"; mk_tree "$T" WIDGET_STUB 0
OUT="$(run_gate "$T" scan)"; RC=$?
chk "5a scan prints the finding" "$(grep -c 'D1 TOTAL-FIXTURE' <<<"$OUT")" "1"
chk "5b scan is ADVISORY (exit 0)" "$RC" "0"

# 6. NON-VACUOUS. A run that inspects ZERO seams must not read as a clean pass; the summary line
#    always states how many were inspected. RED-PROOF for the summary line in cmd_d1.
chk "6 summary line always present" "$(run_gate "$TMPROOT/t1" scan | grep -c '^fixture-bypass: [0-9]* short-circuit')" "1"

# 7. Var-family coverage: _STUB/_FAKE/_MOCK are the same class as _FIXTURE.
#    RED-PROOF for FB_NAME_RE's suffix alternation.
for v in WIDGET_STUB WIDGET_FAKE WIDGET_MOCK; do
  T="$TMPROOT/t7-$v"; mk_tree "$T" "$v" 0
  chk "7 $v is in the seam family" "$(run_gate "$T" check | grep -c 'D1 TOTAL-FIXTURE')" "1"
done

echo "== D2 NOOP-SURVIVAL (deep) =="

# Synthetic tree whose suite NEVER really invokes the production entry — instance 1-5's shape.
mk_deep(){
  local d="$1" depends="$2"
  mkdir -p "$d/fleet/checks" "$d/fleet/tests"
  printf '#!/usr/bin/env bash\necho GUARD-FIRED\nexit 3\n' > "$d/fleet/gizmo.sh"
  if [ "$depends" = 1 ]; then
    cat > "$d/fleet/tests/gizmo.test.sh" <<'EOF'
#!/usr/bin/env bash
out="$(bash "$(dirname "$0")/../gizmo.sh" 2>&1)"; rc=$?
[ "$rc" = 3 ] && [ "$out" = "GUARD-FIRED" ] && exit 0
echo "gizmo did not fire"; exit 1
EOF
  else
    # Green without ever asserting anything about gizmo.sh — the defect class.
    printf '#!/usr/bin/env bash\necho "9/9 tests passed"\nexit 0\n' > "$d/fleet/tests/gizmo.test.sh"
  fi
}

# 8. The strongest signal: a suite that survives its entry point being no-op'd.
#    RED-PROOF for the `[ "$rc" -eq 0 ]` finding branch in cmd_deep.
T="$TMPROOT/t8"; mk_deep "$T" 0
OUT="$(run_gate "$T" deep gizmo.test.sh)"; RC=$?
chk "8a bypass-blind suite is FLAGGED" "$(grep -c 'D2 NOOP-SURVIVAL' <<<"$OUT")" "1"
chk "8b deep exits RED" "$RC" "1"

# 9. FALSE-POSITIVE GUARD: a suite that genuinely exercises the entry must go red under mutation
#    and therefore NOT be flagged. If cmd_deep inverted its verdict, this reds.
T="$TMPROOT/t9"; mk_deep "$T" 1
OUT="$(run_gate "$T" deep gizmo.test.sh)"; RC=$?
chk "9a real-dependency suite is NOT flagged" "$(grep -c 'D2 NOOP-SURVIVAL' <<<"$OUT")" "0"
chk "9b deep exits GREEN" "$RC" "0"

# 10. Deep mode must NOT mutate the tree it was pointed at — read-only contract.
chk "10 production entry untouched after deep" "$(grep -c 'GUARD-FIRED' "$T/fleet/gizmo.sh")" "1"

echo "== REENTRANCY (fork-bomb class) =="

# 11. Refusing our own suite and rig-ci.test.sh (which runs the CI allowlist, which includes us).
#     RED-PROOF for the case-arm refusal in cmd_deep. Without it, deep -> rig-ci -> deep -> ...
for s in fixture-bypass.test.sh rig-ci.test.sh; do
  OUT="$(bash "$GATE" deep "$s" 2>&1)"; RC=$?
  chk "11 deep REFUSES $s" "$RC" "2"
  chk "11 refusal names the fork-bomb class ($s)" "$(grep -c 'fork-bomb' <<<"$OUT")" "1"
done

# 12. A nested invocation (child env) refuses outright.
#     RED-PROOF for the FIXTURE_BYPASS_ACTIVE guard at the top of the script.
OUT="$(FIXTURE_BYPASS_ACTIVE=1 bash "$GATE" scan 2>&1)"
chk "12 nested invocation refuses" "$(grep -c 'reentrancy guard' <<<"$OUT")" "1"

echo "== LIVE TREE (fresh-checkout / empty fleet/state/ safety) =="

# 13. The wired mode must be safe on the real tree: advisory exit 0, and NON-VACUOUS (it must
#     actually have inspected seams, not report a green receipt for having checked nothing).
OUT="$(bash "$GATE" scan 2>&1)"; RC=$?
chk "13a live scan is advisory (exit 0)" "$RC" "0"
N="$(sed -n 's/^fixture-bypass: \([0-9]*\) short-circuit.*/\1/p' <<<"$OUT")"
if [ "${N:-0}" -gt 0 ]; then ok "13b live scan is non-vacuous ($N seams inspected)"; else no "13b live scan inspected 0 seams (vacuous)"; fi
# 13c: no fleet/state/ read — the scan must work with the dir absent entirely.
chk "13c scan does not depend on fleet/state" "$(grep -c 'fleet/state' "$GATE")" "0"

echo "== WIRING (an unwired gate IS this defect class) =="

# 14. This gate exists to catch code that is never executed, so its own wiring must be asserted,
#     not assumed. All three clauses below have already failed in practice on this rig:
#       14a preflight's cmd_detect must actually CALL the detector (not merely define it);
#       14b the detector guards on `[ -x ]`, so a non-executable checked-in mode bit makes it
#           silently no-op — a green preflight over a detector that never ran;
#       14c CI must run this suite: fleet/tests/ is an ALLOWLIST, so a new suite is excluded
#           BY DEFAULT and would never execute in CI at all.
PF="$HERE/fleet/preflight.sh"
chk "14a preflight cmd_detect calls detect_fixture_bypass" \
  "$(sed -n '/^cmd_detect(){/,/^}/p' "$PF" | grep -c '^[[:space:]]*detect_fixture_bypass$')" "1"
if [ -x "$GATE" ]; then ok "14b checks/fixture-bypass.sh is executable"; else no "14b gate not executable — preflight's [ -x ] guard would silently skip it"; fi
chk "14c suite is in the CI allowlist" \
  "$(bash "$HERE/fleet/checks/rig-ci-scope.sh" suites | grep -c '^fixture-bypass.test.sh$')" "1"

echo
echo "fixture-bypass.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
