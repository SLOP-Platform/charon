#!/usr/bin/env bash
# landing-plane-canary-registration.test.sh — FAIL-ON-REVERT reconciliation-coverage
# for the "landing" plane's row in fleet/plane-canary-registry.tsv.
#
# RECONCILIATION-COVERAGE: the landing/merge-gate plane
# (fleet/checks/substrate-first-gate.sh + fleet/checks/gate-parity.sh) is the gate
# that refuses a bad land. If substrate-first-gate.sh or its dogfood test is ever
# renamed/moved without updating the registry row, the landing plane silently loses
# its canary coverage — the gates still exist on disk but nobody proves they do.
#
# This test is the landing plane's OWN supplementary coverage, operating alongside
# the general plane-canary reconciliation (plane-canary.test.sh) as a targeted
# fail-on-revert pin for the landing row.
#
# FULLY HERMETIC: reads the real registry for the landing row, builds a throwaway
# fixture for the fail-on-revert variant. Never modifies the real filesystem.
#
# Run: bash fleet/tests/landing-plane-canary-registration.test.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
REGISTRY="$REPO/fleet/plane-canary-registry.tsv"

PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "  ok   $1"; }
bad(){  FAIL=$((FAIL+1)); echo "  FAIL $1"; }

# resolve_landing_row <registry> — checks landing row resolves to existing files
# Exits 0 if both canary_script and dogfood_test paths exist on disk.
resolve_landing_row(){
  local reg="$1" canary dogfood rc=0
  canary="$(awk -F'\t' '$1 == "landing" { print $2 }' "$reg")"
  dogfood="$(awk -F'\t' '$1 == "landing" { print $3 }' "$reg")"
  [ -z "$canary" ] && { echo "landing row: cannot read canary_script"; return 1; }
  [ -z "$dogfood" ] && { echo "landing row: cannot read dogfood_test"; return 1; }
  [ ! -f "$REPO/$canary" ] && { echo "landing row: canary_script not found: $canary"; rc=1; }
  [ ! -f "$REPO/$dogfood" ] && { echo "landing row: dogfood_test not found: $dogfood"; rc=1; }
  return "$rc"
}

echo "== landing-registration: path resolution =="

read -r CANARY_SCRIPT DOGFOOD_TEST WIRED_IN OWNER_TICKET <<< \
  "$(awk -F'\t' '$1 == "landing" { print $2, $3, $4, $5 }' "$REGISTRY")"

[ -n "$CANARY_SCRIPT" ] && ok "landing row: canary_script is not blank" \
  || bad "landing row: canary_script is blank"
[ -f "$REPO/$CANARY_SCRIPT" ] && ok "landing row: canary_script exists ($CANARY_SCRIPT)" \
  || bad "landing row: canary_script missing ($CANARY_SCRIPT)"
[ -n "$DOGFOOD_TEST" ] && ok "landing row: dogfood_test is not blank" \
  || bad "landing row: dogfood_test is blank"
[ -f "$REPO/$DOGFOOD_TEST" ] && ok "landing row: dogfood_test exists ($DOGFOOD_TEST)" \
  || bad "landing row: dogfood_test missing ($DOGFOOD_TEST)"
[ -n "$WIRED_IN" ] && ok "landing row: wired_in ($WIRED_IN)" \
  || bad "landing row: wired_in is blank"
[ "$OWNER_TICKET" = "LANDING-GATE-REGISTER" ] && \
  ok "landing row: owner_ticket is LANDING-GATE-REGISTER" || \
  bad "landing row: owner_ticket is '$OWNER_TICKET'"

echo "== landing-registration: dogfood assertion =="

if bash "$REPO/$DOGFOOD_TEST" >/dev/null 2>&1; then
  ok "dogfood test exits 0 (substrate-first-gate.test.sh passing)"
else
  bad "dogfood test did not exit 0"
fi

echo "== landing-registration: fail-on-revert =="

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

awk -F'\t' -v OFS='\t' '
  $1 == "landing" { print $1, "fleet/checks/nonexistent-gate.sh", $3, $4, $5 }
  $1 != "landing" { print }
' "$REGISTRY" > "$TMP/broken-registry.tsv"

if resolve_landing_row "$TMP/broken-registry.tsv" >/dev/null 2>&1; then
  bad "fail-on-revert: broken canary_script NOT detected (should RED)"
else
  ok "fail-on-revert: broken canary_script detected [RED]"
fi

if resolve_landing_row "$REGISTRY"; then
  ok "fail-on-revert (revert): restored landing row resolves [GREEN]"
else
  bad "fail-on-revert (revert): landing row still broken"
fi

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LANDING-PLANE-CANARY-REGISTRATION TESTS PASS"
