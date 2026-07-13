#!/usr/bin/env bash
# Canonical fleet gate: run fleet bash tests and shellcheck fleet scripts.
#
# GATE-PERF (2026-07-13): each *.test.sh isolates itself in its own `mktemp -d`
# (verified — no shared fixture/state path across files), so they carry no
# cross-test dependency and are safe to run CONCURRENTLY. shellcheck is a pure
# read-only advisory pass over fleet/*.sh with no dependency on the test
# results either, so it now runs IN PARALLEL with the tests instead of after
# them. Output is still printed in the original deterministic file order (and
# the lint block stays last) so this is a pure speed change — same tests,
# same lint findings, same PASS/FAIL/exit semantics as before.
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

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Launch every test file concurrently (each is fixture-isolated via mktemp -d).
# Exit code + combined output are captured per-test so the reporting loop below
# can print results in the SAME order as the old sequential loop.
pids=()
for test_file in "${tests[@]}"; do
  test_name="$(basename "$test_file")"
  ( rc=0; bash "$test_file" >"$WORK/$test_name.out" 2>&1 || rc=$?
    echo "$rc" >"$WORK/$test_name.rc" ) &
  pids+=("$!")
done

# The lint pass runs concurrently with the tests too — it's advisory-only and
# reads fleet/*.sh, touching nothing the tests write.
SHELLCHECK_PID=""
if command -v shellcheck >/dev/null 2>&1; then
  shopt -s nullglob
  shell_scripts=("$FLEET"/*.sh)
  shopt -u nullglob
  if [ "${#shell_scripts[@]}" -eq 0 ]; then
    printf '(no fleet/*.sh files)\n' > "$WORK/shellcheck.out"
    echo 0 > "$WORK/shellcheck.rc"
  else
    ( rc=0; shellcheck "${shell_scripts[@]}" >"$WORK/shellcheck.out" 2>&1 || rc=$?
      echo "$rc" >"$WORK/shellcheck.rc" ) &
    SHELLCHECK_PID="$!"
  fi
else
  printf 'shellcheck: skipped (not installed)\n'
fi

for pid in "${pids[@]}"; do wait "$pid" || true; done

for test_file in "${tests[@]}"; do
  test_name="$(basename "$test_file")"
  rc="$(cat "$WORK/$test_name.rc")"
  test_out="$(cat "$WORK/$test_name.out")"
  if [ "$rc" -eq 0 ]; then
    PASS=$((PASS+1))
    printf 'test: PASS %s\n' "$test_name"
  else
    FAIL=$((FAIL+1))
    printf 'test: FAIL %s (exit %s)\n' "$test_name" "$rc"
    [ -n "$test_out" ] && printf '%s\n' "$test_out"
  fi
done

# ADVISORY ONLY. fleet/*.sh carry embedded-python heredocs and legacy style that trip shellcheck
# with false positives (SC1122/SC2148 on the sourced _lib.sh, plus SC2015/SC2086 style). Findings
# are SURFACED but do NOT gate the handoff — the behavioral fleet tests above are the pass/fail.
# Flipping shellcheck to gate-blocking is tracked separately (clean fleet/*.sh first).
if [ -n "$SHELLCHECK_PID" ]; then
  wait "$SHELLCHECK_PID" || true
  sc_rc="$(cat "$WORK/shellcheck.rc")"
  sc_out="$(cat "$WORK/shellcheck.out")"
  [ -n "$sc_out" ] && printf '%s\n' "$sc_out"
  if [ "$sc_rc" -eq 0 ]; then
    printf 'shellcheck: clean\n'
  else
    printf 'shellcheck: ADVISORY — findings above are non-blocking (shellcheck-clean tracked separately)\n'
  fi
elif [ -f "$WORK/shellcheck.out" ]; then
  cat "$WORK/shellcheck.out"
fi

printf 'summary: %s passed, %s failed\n' "$PASS" "$FAIL"

if [ "$FAIL" -ne 0 ]; then
  exit 1
fi

exit 0
