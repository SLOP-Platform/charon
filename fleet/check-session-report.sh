#!/usr/bin/env bash
# check-session-report.sh — validate a SESSION REPORT v1 block has every required field.
# Usage: check-session-report.sh <file>   (or pipe the report on stdin)
# Exit 0 = complete, 1 = missing fields. FAIL-LOUD: names every missing field.
set -euo pipefail
src="${1:-/dev/stdin}"
[ -r "$src" ] || { echo "check-session-report: cannot read '$src'" >&2; exit 2; }
body="$(cat "$src")"
# NON-VACUOUS: an empty or block-less input is a FAILURE, never a silent pass.
grep -q '=== SESSION REPORT v1 ===' <<<"$body" || {
  echo "check-session-report: no 'SESSION REPORT v1' block found — a missing report is a RED, not a pass" >&2; exit 1; }
missing=()
for f in TICKET SESSION STATUS COMMIT FILES OWNS-OK GATE TESTS RED-PROOF OBSERVABLE RAN READ BRIEF-ERRORS BLOCKED-BY NEXT; do
  grep -qE "^${f}:" <<<"$body" || missing+=("$f")
done
if [ ${#missing[@]} -gt 0 ]; then
  printf 'check-session-report: MISSING FIELD: %s\n' "${missing[@]}" >&2
  exit 1
fi
echo "check-session-report: OK — all 15 fields present"
