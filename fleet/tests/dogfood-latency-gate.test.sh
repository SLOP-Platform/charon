#!/usr/bin/env bash
# dogfood-latency-gate.test.sh — FAIL-ON-REVERT tests for EVAL-LATENCY-GATE
# (restoring latency-is-a-failure-class; see fleet/board/EVAL-LATENCY-GATE.md
# and fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md F1 + F4 + F-attr-2).
#
# BUG THIS RESTORES: charon-run.sh never emitted the TIMEOUT strings
# dogfood-attribution.sh's classify_attribution greps for (F1) — every rc=124
# hang was mislabeled `provider-throttled->try-another(all-exhausted)` and
# RETRIED, never disqualified. Independently, dogfood-eval.sh computed
# elapsed>=LATENCY_BUDGET_S but never gated on it (F4) — glm-5.2 RFL-3 ran
# 499s > 480s budget and still landed REVIEW-READY -> eligible live MERGE.
#
# Fully hermetic: a stub `opencode` binary on PATH (controlled by STUB_MODE),
# an isolated COPY of charon-run.sh with no sibling capture/ dir (so its cap()
# hook safely no-ops instead of touching real capture state), an override
# CHARON_EXHAUST_LEDGER (never the real ledger), an override CAPTURE_SPOOL_DIR
# (never the real bench-grader spool), and a throwaway git repo as the
# DOGFOOD_PRODUCT_REPO. No live network, no real gateway/opencode call, no
# writes to any file outside $WORK. dogfood-eval.sh and the real
# lib/dogfood-attribution.sh are exercised AS-IS (not reimplemented) so a
# revert of either the charon-run.sh marker text OR the attribution grep OR
# the dogfood-eval.sh gate logic flips this test RED.
#
# Run:  bash fleet/tests/dogfood-latency-gate.test.sh   (exit 0 = all pass)
set -uo pipefail

FLEET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ # has <desc> <haystack> <needle>
  case "$2" in
    *"$3"*) ok "$1" ;;
    *) bad "$1 (expected to find '$3')"; echo "----- haystack -----"; printf '%s\n' "$2"; echo "---------------------" ;;
  esac
}
not_has(){ # not_has <desc> <haystack> <needle>
  case "$2" in
    *"$3"*) bad "$1 (must NOT contain '$3')"; echo "----- haystack -----"; printf '%s\n' "$2"; echo "---------------------" ;;
    *) ok "$1" ;;
  esac
}
# grep_line: exact-anchored check via grep -E against a file (stronger than a
# plain substring match — distinguishes e.g. "DETAIN(latency)" from
# "DETAIN(latency-wallclock)" which contains it as a substring).
grep_line(){ # grep_line <desc> <file> <ere>
  if grep -qE "$3" "$2" 2>/dev/null; then ok "$1"; else
    bad "$1 (no line in $2 matched /$3/)"; echo "----- file: $2 -----"; cat "$2" 2>/dev/null; echo "---------------------"
  fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── isolated charon-run.sh copy: no sibling capture/ dir, so its own cap()
# hook is structurally a no-op here (never touches real capture state) ──────
BIN="$WORK/bin"; mkdir -p "$BIN"
cp "$FLEET_DIR/charon-run.sh" "$BIN/charon-run.sh"
chmod +x "$BIN/charon-run.sh"

# ── hermetic overrides: never the real ledger, never the real bench-grader spool ──
export CHARON_EXHAUST_LEDGER="$WORK/ledger.tsv"
export CAPTURE_SPOOL_DIR="$WORK/spool/req"
mkdir -p "$CAPTURE_SPOOL_DIR"

# ── stub `opencode` on PATH — mocks `opencode run --model charon/<M> <PROMPT>`.
# STUB_MODE selects the behavior; the stub never touches the network. ────────
STUBBIN="$WORK/stubbin"; mkdir -p "$STUBBIN"
cat > "$STUBBIN/opencode" <<'EOF'
#!/usr/bin/env bash
case "${STUB_MODE:-clean}" in
  clean)
    # exits fast, well inside any budget; edits an EXISTING tracked file (git
    # diff ignores untracked new files, so this must modify README.md, not
    # create a new file) so the caller's git-diff-based did-real-work check
    # sees a real, nonzero diff.
    echo "stub: did the ticket work"
    echo "stub change $$" >> README.md
    exit 0
    ;;
  too-slow)
    # streams real output FIRST (leg is healthy), then hangs well past any
    # small test budget so the `timeout` wrapper kills it (rc=124).
    echo "stub: model is streaming real tokens before the budget kills it"
    sleep 5
    ;;
  hang)
    # NO output at all before the `timeout` wrapper kills it (rc=124) — a
    # dead/hung leg, nothing model-attributable to see.
    sleep 5
    ;;
esac
EOF
chmod +x "$STUBBIN/opencode"
export PATH="$STUBBIN:$PATH"

BRIEF="$WORK/brief.md"
echo "hermetic test ticket brief" > "$BRIEF"

# ═════════════════════════════════════════════════════════════════════════
# STAGE 1 — charon-run.sh marker <-> dogfood-attribution.sh grep round-trip.
# "Assert the charon-run marker string is exactly what the attribution grep
# matches (revert either side -> the dead-code bug returns -> test fails)."
# ═════════════════════════════════════════════════════════════════════════
source "$FLEET_DIR/benchmark/lib/dogfood-attribution.sh"

CWD_TS="$WORK/cwd-too-slow"; mkdir -p "$CWD_TS"
LOG_TS="$WORK/too-slow.charon-run.log"
STUB_MODE=too-slow CHARON_RUN_TIMEOUT_S=2 "$BIN/charon-run.sh" "$CWD_TS" "$LOG_TS" "$BRIEF" fake-model
RC_TS=$?
grep_line "charon-run.sh emits the too-slow TIMEOUT marker (leg healthy: real output observed)" \
  "$LOG_TS" "TIMEOUT \(rc=124\) budget=2s too-slow FAIL"
ATTR_TS="$(classify_attribution "$RC_TS" "$LOG_TS")"
has "round-trip: classify_attribution reads the real too-slow marker -> too-slow bucket" "$ATTR_TS" "too-slow"

CWD_HANG="$WORK/cwd-hang"; mkdir -p "$CWD_HANG"
LOG_HANG="$WORK/hang.charon-run.log"
STUB_MODE=hang CHARON_RUN_TIMEOUT_S=2 "$BIN/charon-run.sh" "$CWD_HANG" "$LOG_HANG" "$BRIEF" fake-model
RC_HANG=$?
grep_line "charon-run.sh emits the leg-fault TIMEOUT marker (no output before budget)" \
  "$LOG_HANG" "TIMEOUT \(rc=124\) leg-fault"
ATTR_HANG="$(classify_attribution "$RC_HANG" "$LOG_HANG")"
has "round-trip: classify_attribution reads the real leg-fault marker -> leg-fault bucket" "$ATTR_HANG" "leg-fault"
not_has "a no-output hang is NEVER classified too-slow" "$ATTR_HANG" "too-slow"

# ═════════════════════════════════════════════════════════════════════════
# STAGE 2 — dogfood-eval.sh end-to-end overall-verdict gate (F4). Real
# dogfood-eval.sh, real lib/dogfood-attribution.sh, hermetic product repo.
# ═════════════════════════════════════════════════════════════════════════
PRODUCT_REPO="$WORK/product"
mkdir -p "$PRODUCT_REPO"
git -C "$PRODUCT_REPO" init -q -b master
git -C "$PRODUCT_REPO" config user.email "test@hermetic.local"
git -C "$PRODUCT_REPO" config user.name "hermetic-test"
echo "seed" > "$PRODUCT_REPO/README.md"
git -C "$PRODUCT_REPO" add README.md
git -C "$PRODUCT_REPO" commit -q -m seed

DOGFOOD_EVAL="$FLEET_DIR/benchmark/dogfood-eval.sh"

run_scenario() { # run_scenario <scenario-name> <stub-mode> <budget-s> <model>
  local scn="$1" stub_mode="$2" budget="$3" model="$4"
  local results_dir="$WORK/results-$scn"
  mkdir -p "$results_dir"
  STUB_MODE="$stub_mode" \
    DOGFOOD_PRODUCT_REPO="$PRODUCT_REPO" \
    DOGFOOD_BASE_REF="master" \
    DOGFOOD_WORKTREE_PARENT="$WORK" \
    DOGFOOD_RESULTS_DIR="$results_dir" \
    DOGFOOD_GATE_CMD="true" \
    DOGFOOD_TEST_CMD="true" \
    DOGFOOD_LATENCY_BUDGET_S="$budget" \
    DOGFOOD_CHARON_RUN="$BIN/charon-run.sh" \
    DOGFOOD_KEEP_WORKTREE=0 \
    "$DOGFOOD_EVAL" "$scn" "$BRIEF" "$model" \
    >"$WORK/$scn.stdout.log" 2>"$WORK/$scn.stderr.log"
}

card_for() { find "$WORK/results-$1" -maxdepth 1 -name '*.card.md' | head -1; }

# ---- scenario A: streams past budget (leg healthy) -> rc=124 too-slow ->
# DETAIN(latency)/BLOCK, NOT REVIEW-READY. This is the F1 (marker<->grep)
# path: revert the charon-run.sh marker text OR the dogfood-attribution.sh
# grep and this goes RED. NOTE: this does NOT independently guard the F4
# wall-clock branch — a too-slow attribution is caught by the too-slow branch
# ABOVE the F4 elif, so F4 is exercised in isolation only by scenario D. ----
run_scenario "TEST-TOO-SLOW" "too-slow" 2 "stub-model-a"
CARD_A="$(card_for TEST-TOO-SLOW)"
if [ -n "$CARD_A" ] && [ -f "$CARD_A" ]; then
  ok "scenario A (too-slow): result card produced"
  grep_line "scenario A: overall verdict is exactly DETAIN(latency), NOT REVIEW-READY" \
    "$CARD_A" '^overall verdict: \*\*DETAIN\(latency\)\*\*'
  grep_line "scenario A: card attribution names too-slow" "$CARD_A" 'attribution: too-slow'
else
  bad "scenario A (too-slow): no result card produced at all"
fi

# ---- scenario B: no-output rc=124 hang -> leg-fault, NEVER a model BLOCK ----
run_scenario "TEST-HANG" "hang" 2 "stub-model-b"
CARD_B="$(card_for TEST-HANG)"
if [ -n "$CARD_B" ] && [ -f "$CARD_B" ]; then
  ok "scenario B (hang): result card produced"
  grep_line "scenario B: overall verdict is RETRY(leg-fault-*), never DETAIN/BLOCK" \
    "$CARD_B" '^overall verdict: \*\*RETRY\(leg-fault'
  not_has "scenario B: overall verdict never contains DETAIN" "$(cat "$CARD_B")" "DETAIN"
  grep_line "scenario B: card attribution names leg-fault" "$CARD_B" 'attribution: leg-fault'
else
  bad "scenario B (hang): no result card produced at all"
fi

# ---- scenario C: clean run, well within budget -> REVIEW-READY unchanged ----
run_scenario "TEST-CLEAN" "clean" 30 "stub-model-c"
CARD_C="$(card_for TEST-CLEAN)"
if [ -n "$CARD_C" ] && [ -f "$CARD_C" ]; then
  ok "scenario C (clean/within-budget): result card produced"
  grep_line "scenario C: overall verdict is REVIEW-READY (unaffected by the latency gate)" \
    "$CARD_C" '^overall verdict: \*\*REVIEW-READY\(candidate-for-merge'
  grep_line "scenario C: latency_verdict is within-budget" "$CARD_C" 'latency_verdict: within-budget'
else
  bad "scenario C (clean/within-budget): no result card produced at all"
fi

# ═════════════════════════════════════════════════════════════════════════
# STAGE 3 — scenario D: the ISOLATED F4 wall-clock guard (glm-5.2 RFL-3 case).
# A clean rc=0 run that ran OVER the wall-clock budget with NO rc=124 marker
# and NO too-slow/leg-fault attribution — attribution=ran-to-completion. The
# ONLY thing that can catch it is the F4 elapsed>=LATENCY_BUDGET_S branch in
# dogfood-eval.sh; the too-slow/leg-fault/early-ditch branches all miss it.
# Revert ONLY the F4 branch -> this run falls through to REVIEW-READY -> RED.
#
# F4 is attribution-string-independent by design (belt-and-suspenders), so we
# drive it with a dedicated stub charon-run that decouples the model's own
# runtime from the timeout: it does REAL work (edits a tracked file), overruns
# the budget on the wall clock, and exits 0 WITHOUT ever being killed by the
# `timeout` wrapper (no rc=124). This reproduces the historical glm-5.2 case
# (wall=499s > budget=480s, exit 0, REVIEW-READY) that F4 exists to catch.
# ═════════════════════════════════════════════════════════════════════════
STUB_CRUN="$WORK/stub-charon-run.sh"
cat > "$STUB_CRUN" <<'EOF'
#!/usr/bin/env bash
# stub charon-run.sh — mimics the SUCCESS contract (rc=0 + a real worktree
# diff + the CHARON_RUN_RESULT=SUCCESS marker) but overruns the wall-clock
# budget without ever hitting rc=124. Decoupled from the `timeout` wrapper on
# purpose: this is what a model that finishes cleanly but SLOWLY looks like.
CWD="$1"; OUT="$2"; shift 3
M="$1"
: > "$OUT"
echo "===== [stub-charon-run] attempt: charon/$M =====" >> "$OUT"
( cd "$CWD" && printf 'wallclock-overrun change %s\n' "$$" >> README.md )
echo "[stub-charon-run] SUCCESS on model '$M' (rc=0)" >> "$OUT"
echo "CHARON_RUN_RESULT=SUCCESS model=$M" >> "$OUT"
sleep 2   # budget below is 1s -> measured elapsed (>=2) exceeds it; still rc=0
exit 0
EOF
chmod +x "$STUB_CRUN"

RESULTS_D="$WORK/results-TEST-WALLCLOCK"
mkdir -p "$RESULTS_D"
DOGFOOD_PRODUCT_REPO="$PRODUCT_REPO" \
  DOGFOOD_BASE_REF="master" \
  DOGFOOD_WORKTREE_PARENT="$WORK" \
  DOGFOOD_RESULTS_DIR="$RESULTS_D" \
  DOGFOOD_GATE_CMD="true" \
  DOGFOOD_TEST_CMD="true" \
  DOGFOOD_LATENCY_BUDGET_S=1 \
  DOGFOOD_CHARON_RUN="$STUB_CRUN" \
  DOGFOOD_KEEP_WORKTREE=0 \
  "$DOGFOOD_EVAL" "TEST-WALLCLOCK" "$BRIEF" "stub-model-d" \
  >"$WORK/TEST-WALLCLOCK.stdout.log" 2>"$WORK/TEST-WALLCLOCK.stderr.log"
CARD_D="$(card_for TEST-WALLCLOCK)"
if [ -n "$CARD_D" ] && [ -f "$CARD_D" ]; then
  ok "scenario D (clean rc=0, over wall-clock budget): result card produced"
  # The isolated F4 assertion: exactly DETAIN(latency-wallclock), NOT REVIEW-READY.
  grep_line "scenario D: F4 wall-clock gate fires -> DETAIN(latency-wallclock)" \
    "$CARD_D" '^overall verdict: \*\*DETAIN\(latency-wallclock\)\*\*'
  not_has "scenario D: over-budget clean run is NEVER REVIEW-READY" "$(cat "$CARD_D")" "REVIEW-READY"
  # Prove the trigger was the wall clock, not an rc=124/too-slow attribution:
  # attribution must be ran-to-completion (no rc=124 marker involved at all).
  grep_line "scenario D: attribution is ran-to-completion (rc=0; no rc=124/too-slow)" \
    "$CARD_D" 'attribution: ran-to-completion'
  not_has "scenario D: attribution is NOT too-slow (proves F4, not the F1 path, caught it)" \
    "$(grep '^- failure attribution:' "$CARD_D")" "too-slow"
else
  bad "scenario D (clean rc=0, over wall-clock budget): no result card produced at all"
fi

echo
echo "SELFTEST SUMMARY: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "DOGFOOD LATENCY GATE SELFTEST: FAILED — see FAIL lines above."
  exit 1
fi
echo "ALL DOGFOOD LATENCY GATE SELFTESTS PASS: latency-is-a-failure-class is enforced" \
     "(too-slow -> DETAIN/BLOCK, leg-fault -> RETRY not BLOCK, within-budget -> REVIEW-READY)."
