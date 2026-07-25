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

# REENTRANCY GUARD (2026-07-15 fork-bomb incident): gate.sh runs the fleet test
# suite; one test (handoff-mechanize.test.sh) invokes handoff.sh, which itself
# runs gate.sh — an exponential, concurrent handoff->gate->test->handoff->gate...
# recursion that saturated the box (18k procs). This marker lets handoff.sh (and
# any other gate-invoking script) detect it is already nested and skip re-running
# the gate. Any test spawned below inherits it via the exported env.
export CHARON_GATE_ACTIVE=1

if [ -d "$TESTS_DIR" ]; then
  shopt -s nullglob
  tests=("$TESTS_DIR"/*.test.sh)
  shopt -u nullglob
else
  tests=()
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# BOUNDED CONCURRENCY (RIG-REDS 2026-07-24). This loop used to launch ALL of the
# fleet's test files at once — 77 of them on a 16-core box, each of which forks
# git/python/mktemp subprocesses of its own. That unbounded fan-out was itself a
# defect, not just a slow choice:
#   * `fork: retry: Resource temporarily unavailable` was observed inside
#     selfcheck-cycle.test.sh under the gate (that test lowers RLIMIT_NPROC to 256
#     as a fork-bomb backstop — a PER-USER limit, so an overloaded box starves it).
#   * reconcile-merged.test.sh's 5000ms wall-clock budget measured the BOX'S LOAD
#     rather than the code: 2.4-2.7s standalone vs 6.7-7.7s under the fan-out.
#   * rule-coverage.test.sh passed 3/3 standalone and failed under the fan-out.
# All three read as product reds and burned sub-sessions chasing phantom defects.
# Cap in-flight tests at the core count (override with CHARON_GATE_JOBS). Ordering,
# per-test capture and PASS/FAIL semantics below are unchanged — this only limits
# how many run at once.
JOBS="${CHARON_GATE_JOBS:-$(nproc 2>/dev/null || echo 4)}"
case "$JOBS" in ''|*[!0-9]*|0) JOBS=4 ;; esac
pids=()
for test_file in "${tests[@]}"; do
  # Block until a slot frees up. `wait -n` returns when ANY child exits; the child
  # bodies below never fail (rc is captured, not propagated), so `|| true` here is
  # not masking a test failure — it only absorbs `wait -n`'s "no children" rc.
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n || true; done
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
  # FAIL-LOUD (RIG-REDS 2026-07-24): a child that was killed outright (OOM, RLIMIT)
  # never writes its .rc, and under `set -e` the bare `cat` aborted the whole gate
  # mid-report — a partial listing with a nonzero exit that read like a crash rather
  # than naming the test. Missing .rc is now an explicit RED for that test.
  if [ -f "$WORK/$test_name.rc" ]; then
    rc="$(cat "$WORK/$test_name.rc")"
  else
    rc="killed (no exit status recorded — child died before writing .rc)"
  fi
  test_out="$(cat "$WORK/$test_name.out" 2>/dev/null || true)"
  case "$rc" in ''|*[!0-9]*) FAIL=$((FAIL+1)); printf 'test: FAIL %s (%s)\n' "$test_name" "$rc"
    [ -n "$test_out" ] && printf '%s\n' "$test_out"; continue ;; esac
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
