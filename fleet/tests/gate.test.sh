#!/usr/bin/env bash
# gate.test.sh — hermetic tests for fleet/gate.sh.
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0

ok(){ PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

mk_test_dir(){
  local d
  d="$(mktemp -d)"
  mkdir -p "$d/tests"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$d/tests/alpha.test.sh"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$d/tests/bravo.test.sh"
  chmod +x "$d/tests/alpha.test.sh" "$d/tests/bravo.test.sh"
  printf '%s\n' "$d"
}

mk_shellcheck_stub(){
  local d
  d="$(mktemp -d)"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$d/shellcheck"
  chmod +x "$d/shellcheck"
  printf '%s\n' "$d"
}

echo "== gate.sh =="

d="$(mk_test_dir)"
stub="$(mk_shellcheck_stub)"
out="$({ PATH="$stub:$PATH" FLEET_TESTS_DIR="$d/tests" bash "$SRC/gate.sh"; } 2>&1)"
rc=$?
check "g-pass exit 0 with two passing tests" "$rc" "0"
printf '%s\n' "$out" | grep -q 'test: PASS alpha.test.sh' && ok "g-pass names alpha pass" || bad "g-pass names alpha pass"
printf '%s\n' "$out" | grep -q 'test: PASS bravo.test.sh' && ok "g-pass names bravo pass" || bad "g-pass names bravo pass"
printf '%s\n' "$out" | grep -q 'summary: 2 passed, 0 failed' && ok "g-pass summary counts" || bad "g-pass summary counts"
rm -rf "$d"
rm -rf "$stub"

d="$(mk_test_dir)"
printf '#!/usr/bin/env bash\nexit 1\n' > "$d/tests/charlie.test.sh"
chmod +x "$d/tests/charlie.test.sh"
stub="$(mk_shellcheck_stub)"
out="$({ PATH="$stub:$PATH" FLEET_TESTS_DIR="$d/tests" bash "$SRC/gate.sh"; } 2>&1)"
rc=$?
[ "$rc" -ne 0 ] && ok "g-fail exits non-zero when a test fails" || bad "g-fail exits non-zero when a test fails"
printf '%s\n' "$out" | grep -q 'test: FAIL charlie.test.sh' && ok "g-fail names the failing test" || bad "g-fail names the failing test"
printf '%s\n' "$out" | grep -q 'summary: 2 passed, 1 failed' && ok "g-fail summary counts" || bad "g-fail summary counts"
rm -rf "$d"
rm -rf "$stub"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL GATE TESTS PASS"
