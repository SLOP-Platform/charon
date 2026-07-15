#!/usr/bin/env bash
# reviewer-dogfood.test.sh — FAIL-ON-REVERT tests for
# fleet/benchmark/reviewer-dogfood.sh + fleet/state/REDS-CORPUS.md.
#
# Exercises the REAL grading/parsing functions in the actual harness (offline entry
# points --corpus-selfcheck / --grade), never a re-implementation of the logic in this
# test file. No live gateway/model call — those two entry points are pure git/text
# processing, so this test is fast and deterministic.
#
# What proves this FAILS ON REVERT:
#   1. corpus-selfcheck on a corpus with one DELIBERATELY CORRUPTED ref must go RED and
#      NAME the broken case — if reviewer-dogfood.sh's git-diff-based integrity check
#      were reverted to a no-op/always-pass stub, this assertion fails.
#   2. grade_recall on a MISSED fixture (mentions the file but not the defect concept)
#      must print MISSED/rc!=0 — if the recall grader were reverted to a naive
#      "file mentioned = caught" stub (no keyword check), this assertion fails.
#   3. grade_precision on a FALSE-POSITIVE fixture (flags a nonexistent bug on the clean
#      diff) must print FALSE-POSITIVE/rc!=0 — if the precision grader were reverted to
#      always emit CLEAN, this assertion fails.
#   4. corpus-selfcheck on ZERO parsed cases must FAIL (NON-VACUOUS: an empty corpus is
#      never a silent pass).
#
# Run:  bash fleet/tests/reviewer-dogfood.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$SRC/benchmark/reviewer-dogfood.sh"
[ -x "$TOOL" ] || { echo "FAIL: $TOOL missing or not executable"; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# ---- test 1: the REAL, committed corpus must self-check clean and NON-VACUOUS -------
REAL_CORPUS="$SRC/state/REDS-CORPUS.md"
if [ -f "$REAL_CORPUS" ]; then
  out="$("$TOOL" --corpus-selfcheck "$REAL_CORPUS" 2>&1)"; rc=$?
  [ "$rc" -eq 0 ] && ok "real REDS-CORPUS.md self-checks clean (every ref resolves to a real, non-empty diff)" \
                  || { bad "real REDS-CORPUS.md self-check FAILED (rc=$rc)"; echo "$out"; }
  case "$out" in
    *CASE1*CASE2*CASE3*CASE4*CLEAN0* | *"CASE1"*) ;;
  esac
  printf '%s\n' "$out" | grep -q "CASE1" && printf '%s\n' "$out" | grep -q "CASE2" \
    && printf '%s\n' "$out" | grep -q "CASE3" && printf '%s\n' "$out" | grep -q "CASE4" \
    && printf '%s\n' "$out" | grep -q "CLEAN0" \
    && ok "all 4 seeded red cases + CLEAN0 present in the real corpus" \
    || bad "real corpus is missing an expected case id"
else
  bad "REDS-CORPUS.md not found at $REAL_CORPUS"
fi

# ---- test 2: a CORRUPTED corpus (bogus bad_ref) must FAIL and NAME the broken case ---
CORRUPT="$TMP/CORRUPT-CORPUS.md"
sed 's/^CASE2\t.*/CASE2\tproduct\t0000000\t0000000\tsrc\/charon\/proxy.py\tsilent-misclassification\tlist|array/' \
  "$REAL_CORPUS" > "$CORRUPT" 2>/dev/null || cp "$REAL_CORPUS" "$CORRUPT"
out="$("$TOOL" --corpus-selfcheck "$CORRUPT" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "corpus with a corrupted ref (CASE2 -> bogus SHAs) goes RED" \
                || bad "corrupted corpus WRONGLY passed self-check (integrity check is broken/reverted)"
printf '%s\n' "$out" | grep -q "FAIL: CASE2" \
  && ok "corrupted-corpus failure NAMES the broken case (CASE2)" \
  || bad "corrupted-corpus failure did not name CASE2 (see: $out)"

# ---- test 3: an EMPTY corpus (no cases, no clean block) must FAIL (non-vacuous) ------
EMPTY="$TMP/EMPTY-CORPUS.md"
printf '# empty corpus, no cases\n' > "$EMPTY"
out="$("$TOOL" --corpus-selfcheck "$EMPTY" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "a corpus with ZERO cases fails self-check (non-vacuous — never a silent pass)" \
                || bad "an EMPTY corpus WRONGLY passed self-check (vacuous-pass bug)"

# ---- test 4: grade_recall discriminates CAUGHT vs MISSED on real ground truth --------
CAUGHT_FIXTURE="$TMP/case1-caught.txt"
MISSED_FIXTURE="$TMP/case1-missed.txt"
printf 'This diff touches balance.py. There is a real concurrency race in _save_parked: two threads can race on the same tmp file. REJECT.\n' > "$CAUGHT_FIXTURE"
printf 'Looks like a reasonable refactor of the retry/backoff logic here. APPROVE.\n' > "$MISSED_FIXTURE"

out="$("$TOOL" --grade CASE1 "$CAUGHT_FIXTURE" "$REAL_CORPUS" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && [ "$out" = "CAUGHT" ] && ok "grade_recall: a review naming the file + race/lock language -> CAUGHT" \
  || bad "grade_recall did not return CAUGHT for a genuine catch (got '$out' rc=$rc)"

out="$("$TOOL" --grade CASE1 "$MISSED_FIXTURE" "$REAL_CORPUS" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && [ "$out" = "MISSED" ] && ok "grade_recall: a generic/off-target review -> MISSED (proves the grader is not a naive always-pass stub)" \
  || bad "grade_recall WRONGLY returned CAUGHT for an off-target review (got '$out' rc=$rc) — recall grader may be reverted/gamed"

# file mentioned but WITHOUT any defect-concept keyword -> must still be MISSED
FILE_ONLY="$TMP/case1-file-only.txt"
printf 'I reviewed balance.py briefly and it seems fine overall. APPROVE.\n' > "$FILE_ONLY"
out="$("$TOOL" --grade CASE1 "$FILE_ONLY" "$REAL_CORPUS" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && [ "$out" = "MISSED" ] && ok "grade_recall: mentioning the file alone (no defect keywords) still -> MISSED (not a filename substring stub)" \
  || bad "grade_recall WRONGLY caught on filename-only mention (got '$out' rc=$rc)"

# ---- test 5: grade_precision discriminates CLEAN vs FALSE-POSITIVE ------------------
CLEAN_FIXTURE="$TMP/clean-ok.txt"
FP_FIXTURE="$TMP/clean-fp.txt"
printf 'This is a pure docstring addition with no logic change. No issues found. APPROVE.\n' > "$CLEAN_FIXTURE"
printf 'This introduces a subtle security vulnerability in human_bytes. REJECT, this is broken.\n' > "$FP_FIXTURE"

out="$("$TOOL" --grade CLEAN0 "$CLEAN_FIXTURE" "$REAL_CORPUS" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && [ "$out" = "CLEAN" ] && ok "grade_precision: a correct 'no issue' review on the clean diff -> CLEAN" \
  || bad "grade_precision did not return CLEAN for a genuinely clean review (got '$out' rc=$rc)"

out="$("$TOOL" --grade CLEAN0 "$FP_FIXTURE" "$REAL_CORPUS" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && [ "$out" = "FALSE-POSITIVE" ] && ok "grade_precision: hallucinating a defect on the clean diff -> FALSE-POSITIVE (proves the precision grader is not a stub that always says CLEAN)" \
  || bad "grade_precision WRONGLY returned CLEAN for a hallucinated defect (got '$out' rc=$rc) — precision grader may be reverted/gamed"

echo
echo "SELFTEST SUMMARY: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
