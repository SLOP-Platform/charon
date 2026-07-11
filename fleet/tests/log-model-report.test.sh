#!/usr/bin/env bash
# log-model-report.test.sh — FAIL-ON-REVERT tests for fleet/log-model-report.sh.
# Fully hermetic (temp dirs, isolated log + sidecar). No live files touched.
# Run: bash fleet/tests/log-model-report.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

D="$(mktemp -d)"
LOG="$D/MODEL-SELF-REPORT-RELIABILITY.md"
SCRIPT="$SRC/log-model-report.sh"

last_row(){
  grep -v '^|---' "$LOG" | tail -n1
}
count_rows(){
  grep -cE '^\|' "$LOG"
}

# ------------------------------------------------------------------
# (a) missing args -> exit 1
# ------------------------------------------------------------------
echo "== (a) missing required args =="
rc=0; bash "$SCRIPT" --job J --model M --incident I 2>/dev/null || rc=$?
check "a1 missing evidence exits 1" "$rc" "1"

rc=0; bash "$SCRIPT" --model M 2>/dev/null || rc=$?
[ "$rc" -ne 0 ] && ok "a2 missing multiple args exits non-zero" || bad "a2 missing multiple args exits non-zero"

# ------------------------------------------------------------------
# (b) dry-run prints correctly without writing
# ------------------------------------------------------------------
echo "== (b) dry-run =="
out="$(bash "$SCRIPT" --job TEST --model mdl-1 \
          --incident "Claimed done" --evidence "Empty" --log "$LOG" --dry-run)"
[ ! -e "$LOG" ] && ok "b1 dry-run does not create log" || bad "b1 dry-run does not create log"
printf '%s\n' "$out" | grep -q '\[mdl-1\]' \
  && bad "b2 dry-run row lacks brackets (Markdown, not bracketed)" \
  || ok   "b2 dry-run row lacks brackets"

# ------------------------------------------------------------------
# (c) first append seeds header + row
# ------------------------------------------------------------------
echo "== (c) first append seeds header =="
MODEL_LIE_LOG="$LOG" bash "$SCRIPT" --date 2026-07-11 --job "ACTUALS-LEDGER" \
  --model "deepseek-v4-flash" \
  --incident "Reported SUCCESS with zero commits on branch" \
  --evidence "git log master..HEAD empty; files leaked to main repo" >/dev/null
[ -f "$LOG" ] && ok "c1 log file created" || bad "c1 log file created"
grep -q '^# Model self-report reliability log' "$LOG" && ok "c2 header present" || bad "c2 header present"
grep -q '| date | job | model | incident | evidence |' "$LOG" && ok "c3 table header present" || bad "c3 table header present"
check "c4 row count after first entry" "$(count_rows)" "3"
row="$(last_row)"
[ -n "$row" ] && ok "c5 row not empty" || bad "c5 row not empty"
printf '%s' "$row" | grep -q 'deepseek-v4-flash' && ok "c6 model in row" || bad "c6 model in row"

# ------------------------------------------------------------------
# (d) second distinct append adds another row
# ------------------------------------------------------------------
echo "== (d) second distinct append =="
MODEL_LIE_LOG="$LOG" bash "$SCRIPT" --date 2026-07-11 --job "GRADER-SECFIX" \
  --model "kimi-k2.6" \
  --incident "Claimed tests pass; pytest actually FAILED with 59 collection errors" \
  --evidence "pytest log shows '59 errors during collection'" >/dev/null
check "d1 row count after second entry" "$(count_rows)" "4"

# ------------------------------------------------------------------
# (e) identical append is idempotent (no duplicate row)
# ------------------------------------------------------------------
echo "== (e) idempotent duplicate =="
MODEL_LIE_LOG="$LOG" bash "$SCRIPT" --date 2026-07-11 --job "ACTUALS-LEDGER" \
  --model "deepseek-v4-flash" \
  --incident "Reported SUCCESS with zero commits on branch" \
  --evidence "git log master..HEAD empty; files leaked to main repo" >/dev/null
check "e1 no duplicate after repeat" "$(count_rows)" "4"

# ------------------------------------------------------------------
# (f) pipe characters in incident are escaped, not broken
# ------------------------------------------------------------------
echo "== (f) pipe escaping =="
MODEL_LIE_LOG="$LOG" bash "$SCRIPT" --date 2026-07-11 --job "PIPE-TEST" \
  --model "gpt-5" \
  --incident "A | B | C" \
  --evidence "D | E" >/dev/null
row="$(last_row)"
printf '%s' "$row" | grep -qF 'A \| B \| C' && ok "f1 pipes escaped in incident" \
  || bad "f1 pipes escaped in incident"
nf="$(printf '%s' "$row" | awk -F'|' '{print NF}')"
[ "${nf:-0}" -ge 5 ] && ok "f2 row can be parsed as >=5 pipes" || bad "f2 row pipe count"

# ------------------------------------------------------------------
# (g) newline collapsing
# ------------------------------------------------------------------
echo "== (g) newline collapsing =="
MODEL_LIE_LOG="$LOG" bash "$SCRIPT" --date 2026-07-11 --job "MULTI-LINE" \
  --model "llama-4" \
  --incident $'Line one\nLine two' \
  --evidence "ok" >/dev/null
row="$(last_row)"
printf '%s' "$row" | grep -q 'Line one Line two' && ok "g1 newlines collapsed to spaces" \
  || bad "g1 newlines collapsed to spaces"

# ------------------------------------------------------------------
# (h) sidecar file records hash
# ------------------------------------------------------------------
echo "== (h) sidecar created and populated =="
SIDECAR="${LOG%.md}.ids"
[ -f "$SIDECAR" ] && ok "h1 sidecar exists" || bad "h1 sidecar exists"
# Should have exactly 4 unique hashes (c + d + f + g)
count_s="$(sort -u "$SIDECAR" | wc -l)"
check "h2 sidecar unique hashes match rows" "$count_s" "4"

rm -rf "$D"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LOG-MODEL-REPORT TESTS PASS"
