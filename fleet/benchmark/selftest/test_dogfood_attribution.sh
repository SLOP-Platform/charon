#!/usr/bin/env bash
# selftest/test_dogfood_attribution.sh — fail-on-revert guard for
# lib/dogfood-attribution.sh (dogfood-eval.sh's failure-attribution classifier).
#
# Confirmed real bug (2026-07-13 Path C ranking audit): the OLD inline classifier
# checked "ALL MODELS EXHAUSTED" as a catch-all and stamped `provider-throttled`
# for it — that banner fires for ANY nonzero exit on a single-model invocation
# (which is all dogfood-eval ever does), so it silently mislabeled:
#   - a LOCAL sqlite "database is locked" error (minimax-m2.7 / PROVIDER-URL-HELPER)
#   - an opaque gateway "UnknownError" (phi-4, all 4 runs, both tickets)
#   - a TRAILING provider limit-hit AFTER the real diff already gate+test PASSED
#     (deepseek-v4-flash / kimi-k2.6 on TOOL-REPAIR-MUTATING)
# Fixture log excerpts below are copied verbatim from the real captured
# fleet/state/dogfood-eval/results/*.charon-run.log files for those runs — this
# is a characterization test pinned to REAL data, not synthetic guesses. If the
# ordering in lib/dogfood-attribution.sh is ever reverted (local/opaque checks
# moved back after the ALL-EXHAUSTED catch-all, or the trailing-success
# reclassification removed), these assertions FAIL.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_DIR="$(cd "$HERE/.." && pwd)"
# shellcheck source=../lib/dogfood-attribution.sh
source "$BENCH_DIR/lib/dogfood-attribution.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
check() {
  local desc="$1" got="$2" want_substr="$3" forbid_substr="${4:-}"
  case "$got" in
    *"$want_substr"*) ;;
    *) echo "FAIL: $desc — expected to contain '$want_substr', got: $got"; fail=1; return ;;
  esac
  if [ -n "$forbid_substr" ]; then
    case "$got" in
      *"$forbid_substr"*) echo "FAIL: $desc — must NOT contain '$forbid_substr', got: $got"; fail=1; return ;;
    esac
  fi
  echo "ok: $desc -> $got"
}

# ---- case 1: real rc=0 success ----
got="$(classify_attribution 0 /dev/null)"
check "rc=0 -> ran-to-completion" "$got" "ran-to-completion"

# ---- case 2: minimax-m2.7 / PROVIDER-URL-HELPER real db-lock log (verbatim excerpt) ----
cat > "$TMP/dblock.log" <<'EOF'
===== [charon-run] attempt: charon/minimax-m2.7 @ charon-fleet-dogfood-PROVIDER-URL-HELPER-minimax-m2.7-20260714T002000Z =====
Error: Unexpected error

database is locked
[charon-run] model 'minimax-m2.7' exited nonzero (rc=1, not a limit) -> failing over
[charon-run] ALL MODELS EXHAUSTED: minimax-m2.7
CHARON_RUN_RESULT=EXHAUSTED
EOF
got="$(classify_attribution 1 "$TMP/dblock.log")"
check "db-lock (rc=1) -> local-error, NEVER provider-throttled" "$got" "local-error" "provider-throttled"

# ---- case 3: phi-4 real opaque UnknownError log (verbatim excerpt, all 4 runs matched this) ----
cat > "$TMP/unknownerror.log" <<'EOF'
===== [charon-run] attempt: charon/phi-4 @ charon-fleet-dogfood-TOOL-REPAIR-MUTATING-phi-4-20260714T015426Z =====
Error: {
  "name": "UnknownError",
  "data": {
    "message": "Unexpected server error. Check server logs for details.",
    "ref": "err_1e15c68e"
  }
}
[charon-run] model 'phi-4' exited nonzero (rc=1, not a limit) -> failing over
[charon-run] ALL MODELS EXHAUSTED: phi-4
CHARON_RUN_RESULT=EXHAUSTED
EOF
got="$(classify_attribution 1 "$TMP/unknownerror.log")"
check "opaque UnknownError (rc=1) -> local-error, NEVER provider-throttled" "$got" "local-error" "provider-throttled"

# ---- case 4: a genuine all-exhausted case with NO local/opaque signature must still
# classify as a real provider symptom (the fix must not over-correct) ----
cat > "$TMP/genuine-exhausted.log" <<'EOF'
[charon-run] model 'some-model' exited nonzero (rc=1, not a limit) -> failing over
[charon-run] ALL MODELS EXHAUSTED: some-model
CHARON_RUN_RESULT=EXHAUSTED
EOF
got="$(classify_attribution 1 "$TMP/genuine-exhausted.log")"
check "genuine all-exhausted, no local signature -> still provider-throttled" "$got" "provider-throttled->try-another(all-exhausted)"

# ---- case 5: a genuine limit-hit BEFORE any real work (no gate/test pass) stays a
# real provider symptom, is NOT reclassified ----
got="$(classify_attribution 1 "$TMP/genuine-exhausted.log")"
got="$(reclassify_trailing_success "provider-throttled->try-another(limit-hit)" 1 0 "skipped" "not-given")"
check "limit-hit with n_changed=0 (no real work) -> NOT reclassified as success" "$got" "provider-throttled->try-another(limit-hit)"

# ---- case 6: deepseek-v4-flash/kimi-k2.6 real case — trailing limit-hit AFTER the
# real diff already graded clean (gate pass + ticket-test pass) must reclassify to a
# review-ready-eligible attribution, NOT a disqualifying provider-throttled ----
base_attr="provider-throttled->try-another(limit-hit)"
got="$(reclassify_trailing_success "$base_attr" 1 2 "pass" "pass")"
check "trailing limit-hit AFTER gate+test pass -> reclassified (ran-to-completion)" "$got" "ran-to-completion(trailing-provider-call-after-success" "FAIL"

# same, but ticket-test not given (only gate matters) — still must reclassify
got="$(reclassify_trailing_success "$base_attr" 1 2 "pass" "not-given")"
check "trailing limit-hit, gate pass + test not-given -> still reclassified" "$got" "ran-to-completion(trailing-provider-call-after-success"

# ---- case 7: a trailing hiccup where the gate actually FAILED must NOT be
# reclassified — a real gate failure still disqualifies regardless of attribution ----
got="$(reclassify_trailing_success "$base_attr" 1 2 "fail" "pass")"
check "trailing limit-hit but gate FAILED -> NOT reclassified" "$got" "$base_attr"

if [ "$fail" -ne 0 ]; then
  echo
  echo "DOGFOOD ATTRIBUTION SELFTEST: FAILED — see FAIL lines above."
  exit 1
fi
echo
echo "ALL DOGFOOD ATTRIBUTION SELFTESTS PASS: local/opaque errors and trailing-success"
echo "provider hiccups are never mislabeled as a disqualifying provider-throttled fail."
