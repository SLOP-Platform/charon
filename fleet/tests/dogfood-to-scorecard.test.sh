#!/usr/bin/env bash
# dogfood-to-scorecard.test.sh — FAIL-ON-REVERT tests for
# fleet/benchmark/dogfood-to-scorecard.sh. Uses a tiny fixture SUMMARY.md with
# one MERGE row, one BLOCK row (gate fail), one too-slow row (BLOCK — latency
# is a failure class), and one provider-fault row (must be SKIPPED, never
# appended). Never touches the real model-scorecard.tsv or tier-models.tsv —
# only exercises the GENERATED append-script's contents, then deletes it.
#
# Run:  bash fleet/tests/dogfood-to-scorecard.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$SRC/benchmark/dogfood-to-scorecard.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ grep -q -- "$2" "$1" && ok "$3" || bad "$3 (missing '$2' in $1)"; }
no(){  grep -q -- "$2" "$1" && bad "$3 (unexpected '$2' in $1)" || ok "$3"; }

TMP="$(mktemp -d)"
GENERATED=""
cleanup() { [ -n "$GENERATED" ] && rm -f "$GENERATED"; rm -rf "$TMP"; }
trap cleanup EXIT

FIXTURE="$TMP/FIX-TICKET-20260713T000000Z-SUMMARY.md"
cat > "$FIXTURE" <<'EOF'
# Path C dogfood-eval — FIX-TICKET (20260713T000000Z)

| model | verdict | attribution | wall_s | budget_s | gate | ticket-test | diff | scope | card |
|---|---|---|---|---|---|---|---|---|---|
| alpha-model | REVIEW-READY(candidate-for-merge; human must still read the diff) | ran-to-completion | 120 | 600 | pass | pass | real-diff(files=3) | in-scope(matches owns:) | alpha.card.md |
| beta-model | FIXES-NEEDED | ran-to-completion | 90 | 600 | fail | pass | real-diff(files=2) | in-scope(matches owns:) | beta.card.md |
| gamma-model | DETAIN(latency) | too-slow(latency-budget-exceeded) | 650 | 600 | skipped | not-given | early-ditch-no-diff(quality-fail) | not-checked(no DOGFOOD_EXPECT_FILES given) | gamma.card.md |
| delta-model | RETRY(provider-symptom-not-model-fault) | provider-throttled->try-another(all-exhausted) | 45 | 600 | skipped | not-given | early-ditch-no-diff(quality-fail) | not-checked(no DOGFOOD_EXPECT_FILES given) | delta.card.md |
EOF

OUTPUT="$("$TOOL" "$FIXTURE" --ticket FIX-TICKET --work-class ci-infra 2>&1)"
RC=$?
[ "$RC" -eq 0 ] && ok "tool exits 0 on a valid fixture" || bad "tool exited $RC"

GENERATED="$(printf '%s\n' "$OUTPUT" | sed -n 's/^generated: \([^ ]*\).*/\1/p' | head -1)"
if [ -n "$GENERATED" ] && [ -f "$GENERATED" ]; then
  ok "generated append-script exists: $GENERATED"
else
  bad "could not find generated append-script path in tool output"
  echo "$OUTPUT"
  echo "SELFTEST SUMMARY: $PASS passed, $FAIL failed"
  [ "$FAIL" -eq 0 ] && exit 0 || exit 1
fi

# --- stage: every emitted row must ride on CHARON_SCORECARD_STAGE=provisional ---
has "$GENERATED" 'CHARON_SCORECARD_STAGE=provisional' "sets stage=provisional"

# --- MERGE row: alpha-model, ran-to-completion + gate=pass + test=pass + real-diff ---
has "$GENERATED" 'append 20[0-9-]* live FIX-TICKET ci-infra - alpha-model MERGE pass' "alpha-model appended as MERGE"

# --- FIXES row: beta-model ran-to-completion, produced a REAL diff but gate=fail (a fixable miss, NOT a detention BLOCK) ---
has "$GENERATED" 'append 20[0-9-]* live FIX-TICKET ci-infra - beta-model FIXES fail' "beta-model appended as FIXES (real diff, gate fail — not a detention BLOCK)"

# --- BLOCK row: gamma-model, too-slow attribution (latency is a failure class) ---
has "$GENERATED" 'append 20[0-9-]* live FIX-TICKET ci-infra - gamma-model BLOCK' "gamma-model appended as BLOCK (too-slow)"
has "$GENERATED" 'gamma-model.*attribution=too-slow' "gamma-model note carries too-slow attribution"

# --- SKIP row: delta-model, provider-fault — must NOT be appended ---
no "$GENERATED" 'append 20[0-9-]* live FIX-TICKET ci-infra - delta-model' "delta-model is NOT appended (provider-fault)"
has "$GENERATED" '# SKIPPED (provider-fault' "delta-model recorded as a SKIPPED comment"
has "$GENERATED" 'delta-model attribution=provider-throttled' "SKIPPED comment names delta-model + its attribution"

# --- exactly one MERGE and no accidental double-emit ---
n_merge="$(grep -c 'append .* MERGE ' "$GENERATED")"
[ "$n_merge" -eq 1 ] && ok "exactly one MERGE row emitted" || bad "expected 1 MERGE row, got $n_merge"
n_block="$(grep -c 'append .* BLOCK ' "$GENERATED")"
[ "$n_block" -eq 1 ] && ok "exactly one BLOCK row emitted (gamma too-slow)" || bad "expected 1 BLOCK row, got $n_block"
n_fixes="$(grep -c 'append .* FIXES ' "$GENERATED")"
[ "$n_fixes" -eq 1 ] && ok "exactly one FIXES row emitted (beta real-diff gate-fail)" || bad "expected 1 FIXES row, got $n_fixes"
n_appends="$(grep -c '^bash "\$S" append' "$GENERATED")"
[ "$n_appends" -eq 3 ] && ok "exactly 3 append lines total (delta excluded)" || bad "expected 3 append lines, got $n_appends"

# --- tool itself never touches the real ledger or tier file ---
no "$GENERATED" 'model-scorecard\.tsv' "generated script does not reference model-scorecard.tsv directly (goes through model-scorecard.sh)"
no "$GENERATED" 'tier-models\.tsv' "generated script never touches tier-models.tsv"

echo "SELFTEST SUMMARY: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
