#!/usr/bin/env bash
# Canonical fleet gate: run fleet bash tests and shellcheck fleet scripts.
set -euo pipefail

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="${FLEET_TESTS_DIR:-$FLEET/tests}"
PASS=0
FAIL=0

if [ -d "$TESTS_DIR" ]; then
  shopt -s nullglob
  tests=("$TESTS_DIR"/*.test.sh)
  shopt -u nullglob
else
  tests=()
fi

for test_file in "${tests[@]}"; do
  test_name="$(basename "$test_file")"
  if test_out="$(bash "$test_file" 2>&1)"; then
    PASS=$((PASS+1))
    printf 'test: PASS %s\n' "$test_name"
  else
    rc=$?
    FAIL=$((FAIL+1))
    printf 'test: FAIL %s (exit %s)\n' "$test_name" "$rc"
    [ -n "$test_out" ] && printf '%s\n' "$test_out"
  fi
done

# ADVISORY ONLY. fleet/*.sh carry embedded-python heredocs and legacy style that trip shellcheck
# with false positives (SC1122/SC2148 on the sourced _lib.sh, plus SC2015/SC2086 style). Findings
# are SURFACED but do NOT gate the handoff — the behavioral fleet tests above are the pass/fail.
# Flipping shellcheck to gate-blocking is tracked separately (clean fleet/*.sh first).
if command -v shellcheck >/dev/null 2>&1; then
  shopt -s nullglob
  shell_scripts=("$FLEET"/*.sh)
  shopt -u nullglob
  if [ "${#shell_scripts[@]}" -eq 0 ]; then
    printf 'shellcheck: (no fleet/*.sh files)\n'
  elif shellcheck "${shell_scripts[@]}"; then
    printf 'shellcheck: clean\n'
  else
    printf 'shellcheck: ADVISORY — findings above are non-blocking (shellcheck-clean tracked separately)\n'
  fi
else
  printf 'shellcheck: skipped (not installed)\n'
fi

printf 'summary: %s passed, %s failed\n' "$PASS" "$FAIL"

if [ "$FAIL" -ne 0 ]; then
  exit 1
fi

exit 0
