#!/usr/bin/env bash
# launcher-gate-sete-kill.test.sh — FAIL-ON-REVERT tests for the 2026-08-01 launcher gate fix.
#
# THE DEFECT (measured, not theorised). fleet-droid.sh runs `set -euo pipefail`. Its launcher
# gate block had TWO ways to kill the WHOLE TAB rather than record a FAIL and move on:
#
#   1. ORDERING — the redirect `( ... ) > "$FLEET/state/gate-results/..."` ran BEFORE the
#      `mkdir -p` of that directory. bash opens the target while setting up the redirection,
#      so a missing dir fails the command outright and `set -e` exits the tab.
#   2. RED GATE — a failing gate is a non-zero compound command in plain statement position,
#      so `set -e` exits the tab there too. `GATE_EXIT=$?` on the next line was therefore
#      UNREACHABLE on failure, making the `GATE_EXIT=1` FAIL default and the 125 sentinel
#      dead code for exactly the path they exist to describe.
#
# Consequence: pools drained below their floor and tickets fell back to READY still holding a
# claim — the tab died mid-ticket. A failing gate must be DATA (an exit code we record), never
# a fault that unwinds the loop.
#
# These tests extract the REAL block out of fleet-droid.sh (they do not re-implement it) and
# run it under the same `set -euo pipefail`, so restoring either defect fails them.
#
# Run:  bash fleet/tests/launcher-gate-sete-kill.test.sh   (exit 0 = all pass, 1 = a failure)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the real fleet/ dir
LAUNCHER="$SRC/fleet-droid.sh"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

[ -r "$LAUNCHER" ] || { echo "FAIL: cannot read $LAUNCHER"; exit 1; }

# Extract the launcher's gate block verbatim: from the "running the gate" echo through the
# `fi` that closes the skip-marker if/else. Extracting rather than copying is what makes this
# fail-on-revert — the test executes the shipped code, not a paraphrase of it.
extract_gate_block(){
  # The block starts INSIDE the skip-marker if/else, so stop BEFORE the `fi` that closes
  # that outer conditional — printing it would leave the harness with an unbalanced `fi`.
  # The failure-tail block's own `fi` is indented deeper and is not the terminator.
  awk '
    /launcher running the gate \(one-shot verification\)/ { inb=1 }
    inb && /^    fi$/ { exit }
    inb { print }
  ' "$LAUNCHER"
}

BLOCK="$(extract_gate_block)"
if [ -z "$BLOCK" ]; then
  echo "FAIL: could not extract the gate block from fleet-droid.sh (markers moved?)"
  exit 1
fi

# Run the extracted block under the launcher's own shell options, with the surrounding
# variables stubbed. $RR_GATE is the gate command under test; $wt is the worktree it cds into.
run_block(){
  local fleetdir="$1" gate_cmd="$2" premake="$3" harness
  harness="$(mktemp)"
  {
    echo 'set -euo pipefail'
    echo "FLEET=$(printf '%q' "$fleetdir")"
    echo 'DROID=testdroid'
    echo 'id=TEST-TICKET'
    echo "wt=$(printf '%q' "$fleetdir")"
    echo "RR_GATE=$(printf '%q' "$gate_cmd")"
    echo 'GATE_EXIT=1'
    echo "$BLOCK"
    # Only reached if the block did NOT kill the shell. This is the whole assertion.
    echo 'echo "SURVIVED GATE_EXIT=$GATE_EXIT"'
  } > "$harness"
  [ "$premake" = "premake" ] && mkdir -p "$fleetdir/state/gate-results"
  bash "$harness" 2>/dev/null
  rm -f "$harness"
}

echo "== (1) a MISSING gate-results dir must not kill the tab (ordering defect) =="
d="$(mktemp -d)"
out="$(run_block "$d" "true" no-premake)"
check "1a survives a missing gate-results dir" "$(echo "$out" | grep -c '^SURVIVED')" "1"
check "1b records the passing exit code"       "$(echo "$out" | sed -n 's/^SURVIVED GATE_EXIT=//p')" "0"
check "1c creates gate-results before writing" "$([ -d "$d/state/gate-results" ] && echo yes || echo no)" "yes"
rm -rf "$d"

echo "== (2) a RED gate must be DATA, not a fault that unwinds the tab (set -e defect) =="
d="$(mktemp -d)"
out="$(run_block "$d" "exit 7" premake)"
check "2a survives a failing gate"             "$(echo "$out" | grep -c '^SURVIVED')" "1"
check "2b GATE_EXIT carries the real code (7)" "$(echo "$out" | sed -n 's/^SURVIVED GATE_EXIT=//p')" "7"
rm -rf "$d"

echo "== (3) both defects at once: RED gate AND missing dir =="
d="$(mktemp -d)"
out="$(run_block "$d" "exit 3" no-premake)"
check "3a survives red gate + missing dir"     "$(echo "$out" | grep -c '^SURVIVED')" "1"
check "3b GATE_EXIT carries the real code (3)" "$(echo "$out" | sed -n 's/^SURVIVED GATE_EXIT=//p')" "3"
rm -rf "$d"

echo "== (4) a RED gate must SURFACE its log tail (gate-results had no reader) =="
# Before the fix, $FLEET/state/gate-results/* was written and never read by anything in the
# rig (grep -rn gate-results = the two write lines only), so a RED gate discarded its own
# diagnosis and the skipped publish downstream looked causeless.
d="$(mktemp -d)"
harness="$(mktemp)"
{
  echo 'set -euo pipefail'
  echo "FLEET=$(printf '%q' "$d")"
  echo 'DROID=testdroid'; echo 'id=TEST-TICKET'; echo "wt=$(printf '%q' "$d")"
  echo "RR_GATE=$(printf '%q' 'echo UNIQUE-GATE-DIAGNOSTIC-LINE; exit 9')"
  echo 'GATE_EXIT=1'
  echo "$BLOCK"
} > "$harness"
err="$(bash "$harness" 2>&1 >/dev/null)"
check "4a failing gate's output reaches stderr" "$(echo "$err" | grep -c 'UNIQUE-GATE-DIAGNOSTIC-LINE')" "1"
check "4b failure names the gate log path"      "$(echo "$err" | grep -c 'gate-results')" "1"
rm -f "$harness"; rm -rf "$d"

echo "== (5) the gate log is still written where the report expects it =="
d="$(mktemp -d)"
run_block "$d" "echo hello-from-gate" no-premake >/dev/null
check "5a gate log written to gate-results/<droid>-<id>.txt" \
  "$([ -f "$d/state/gate-results/testdroid-TEST-TICKET.txt" ] && echo yes || echo no)" "yes"
check "5b gate log captured the gate's stdout" \
  "$(grep -c 'hello-from-gate' "$d/state/gate-results/testdroid-TEST-TICKET.txt" 2>/dev/null)" "1"
rm -rf "$d"

echo "== (6) an UNCREATABLE gate-results dir is recorded as FAIL, not a tab kill =="
# Raised by adversarial review of PR #356: `mkdir -p ... || true` would swallow the failure and
# then the redirect would fail anyway, moving the tab-kill one line down instead of removing it.
# Also guards `set -u`: that branch leaves $gate_log UNSET, and a bare reference would abort here.
d="$(mktemp -d)"
: > "$d/state"          # a FILE where the code needs a directory -> mkdir -p cannot succeed
out="$(run_block "$d" "true" no-premake)"
check "6a survives an uncreatable gate-results dir" "$(echo "$out" | grep -c '^SURVIVED')" "1"
check "6b records the 126 sentinel"                 "$(echo "$out" | sed -n 's/^SURVIVED GATE_EXIT=//p')" "126"
rm -rf "$d"

echo "== (7) the block must NOT mutate global shell options =="
# The first version toggled `set +e` / `set -e` around the gate call, which re-enables errexit
# UNCONDITIONALLY — correct only by coincidence (fleet-droid.sh happens to set it at :17) and
# silently wrong the moment that changes. The `|| GATE_EXIT=$?` form needs no toggling at all.
d="$(mktemp -d)"; harness="$(mktemp)"
{
  echo 'set -uo pipefail'          # deliberately NOT errexit — the caller-without-set-e case
  echo "FLEET=$(printf '%q' "$d")"
  echo 'DROID=testdroid'; echo 'id=TEST-TICKET'; echo "wt=$(printf '%q' "$d")"
  echo "RR_GATE=$(printf '%q' 'exit 5')"
  echo 'GATE_EXIT=1'
  echo "$BLOCK"
  # If the block turned errexit ON behind our back, this reports 'on'.
  echo 'case "$-" in *e*) echo "ERREXIT=on";; *) echo "ERREXIT=off";; esac'
  echo 'echo "SURVIVED GATE_EXIT=$GATE_EXIT"'
} > "$harness"
out="$(bash "$harness" 2>/dev/null)"
check "7a errexit left OFF when the caller had it off" "$(echo "$out" | sed -n 's/^ERREXIT=//p')" "off"
check "7b still captures the real gate exit code (5)"  "$(echo "$out" | sed -n 's/^SURVIVED GATE_EXIT=//p')" "5"
rm -f "$harness"; rm -rf "$d"

echo
echo "== launcher-gate-sete-kill: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ] || exit 1
