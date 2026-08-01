#!/usr/bin/env bash
# ledger-no-evidence-no-verdict.test.sh — FAIL-ON-REVERT tests for the 2026-08-01 fix to
# charon-run.sh's is_infra_fault().
#
# THE DEFECT. is_infra_fault() decides whether a failed run is charged to the MODEL (a BLOCK row
# in fleet/model-scorecard.tsv that permanently drags that model's grade) or to the local box.
# Every branch asked "is there a recognised infra signature in the tail?", so a run that produced
# NO OUTPUT AT ALL fell through to `return 1` and was booked as a model-QUALITY failure on the
# strength of an EMPTY string. Fail-OPEN, in the one path that must fail closed.
#
# MEASURED: two models sat at -100 in the live ledger from rows whose entire basis was
# `opencode exited rc=1 (non-limit, non-infra failure)`. The client had failed before ever
# reaching the model — their ids were undeclared to opencode (OPENCODE-MODEL-SYNC). A grade is an
# accusation; an accusation with no evidence is not a finding.
#
# The fix is deliberately NARROW: empty/whitespace-only tail => infra. A tail with real content
# and no infra signature is STILL charged to the model, because a false INFRA is exactly as
# corrosive as a false BLOCK — just in the other direction. Tests (3) and (4) pin that down, so a
# later "simplification" to blanket rc=1 => infra fails here.
#
# Run:  bash fleet/tests/ledger-no-evidence-no-verdict.test.sh   (exit 0 = pass, 1 = failure)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$SRC/charon-run.sh"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

[ -r "$RUN" ] || { echo "FAIL: cannot read $RUN"; exit 1; }

# Extract the REAL is_infra_fault() out of charon-run.sh and source it in isolation. Extracting
# rather than re-implementing is what makes this fail-on-revert: the test runs shipped code.
FN="$(awk '/^is_infra_fault\(\) \{/{f=1} f{print} f&&/^\}$/{exit}' "$RUN")"
[ -n "$FN" ] || { echo "FAIL: could not extract is_infra_fault() from charon-run.sh"; exit 1; }
HARNESS="$(mktemp)"; printf '%s\n' "$FN" > "$HARNESS"
# shellcheck disable=SC1090
. "$HARNESS"

verdict(){ if is_infra_fault "$1" "$2"; then echo INFRA; else echo MODEL; fi; }

echo "== (1) THE REGRESSION: rc=1 with NO evidence must never be a model verdict =="
check "1a empty tail            -> INFRA" "$(verdict 1 '')"        "INFRA"
check "1b whitespace-only tail  -> INFRA" "$(verdict 1 '   ')"     "INFRA"
check "1c newlines-only tail    -> INFRA" "$(verdict 1 '
	 ')" "INFRA"

echo "== (2) the real-world shape that poisoned the ledger =="
# opencode's client-side failure when the model id is not declared to it. The model is never
# reached, so this can never be a quality signal.
UNKNOWN='Error: {
  "name": "UnknownError",
  "data": { "message": "Unexpected server error. Check server logs for details." }
}'
check "2a opencode UnknownError -> INFRA" "$(verdict 1 "$UNKNOWN")" "INFRA"

echo "== (3) ANTI-OVER-CLAIM: a real model failure is STILL charged to the model =="
# If this ever flips to INFRA the guard has been over-widened and every genuine model failure
# silently stops counting — the failure mode the original rc=1 comment warns about.
check "3a rc=1 + substantive non-infra tail -> MODEL" \
  "$(verdict 1 'assistant produced an incomplete patch and exited')" "MODEL"
check "3b rc=1 + plain refusal text         -> MODEL" \
  "$(verdict 1 'I cannot complete this task.')" "MODEL"

echo "== (4) pre-existing classifications are unchanged =="
check "4a rc=127 command-not-found -> INFRA" "$(verdict 127 'x')" "INFRA"
check "4b rc=2   bad arguments     -> INFRA" "$(verdict 2   'x')" "INFRA"
check "4c rc=134 SIGABRT           -> INFRA" "$(verdict 134 'x')" "INFRA"
check "4d rc=3   opaque            -> INFRA" "$(verdict 3   'x')" "INFRA"
check "4e rc=1 + 401 unauthorized  -> INFRA" "$(verdict 1 'HTTP 401 unauthorized')" "INFRA"
check "4f rc=1 + connection reset  -> INFRA" "$(verdict 1 'connection reset by peer')" "INFRA"

rm -f "$HARNESS"
echo
echo "== ledger-no-evidence-no-verdict: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ] || exit 1
