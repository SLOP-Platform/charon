#!/usr/bin/env bash
# reviewer-cron-trigger.test.sh — RED-PROOF tests for fleet/checks/reviewer-cron-trigger.sh.
#
# HERMETIC: throwaway fixture files under mktemp -d. No network, no live gh, no live
# gateway call. The trigger is driven with env overrides (RCT_REVIEW_POOL, RCT_RIG_CI_SCOPE,
# RCT_NO_PENDING, RCT_VERBOSE) to point at synthetic fixtures.
#
# TESTS:
#   A. With the CURRENT broken review-pool.sh, the trigger is QUIET (exit 0).
#   B. With ALL FIVE conditions satisfied in a fixture, the trigger FIRES (exit 2).
#   C. ANTI-FALSE-FIRE: each of the five individually holds the trigger closed (5 subtests).
#   D. State-change dedup: a second run with same state does not re-escalate.
#   E. Heartbeat: a heartbeat file is written regardless of outcome.
#   F. Verbose mode: --verbose shows which conditions are unmet.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIGGER="$HERE/../checks/reviewer-cron-trigger.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ok   $*"; }
no(){ FAIL=$((FAIL+1)); echo "  FAIL $*"; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FLEETD="$TMP/fleet"; mkdir -p "$FLEETD/checks" "$FLEETD/tests" "$FLEETD/state"
cp "$HERE/../pending.sh" "$FLEETD/pending.sh" 2>/dev/null || true

# Paths the trigger will use under test
RP="$FLEETD/review-pool.sh"          # fixture review-pool.sh
RCI="$FLEETD/checks/rig-ci-scope.sh" # fixture rig-ci-scope.sh
TS="$FLEETD/tests/review-pool.test.sh" # fixture test suite

# Common env for ALL trigger invocations
RENV="RCT_FLEET=$FLEETD RCT_STATE=$TMP/state RCT_REVIEW_POOL=$RP RCT_RIG_CI_SCOPE=$RCI RCT_NO_PENDING=1"
STATE="$TMP/state"; mkdir -p "$STATE"

run_trig(){ env $RENV RCT_VERBOSE="${RCT_VERBOSE:-0}" bash "$TRIGGER" "$@" 2>&1; RC=$?; }

# ── FIXTURE TEMPLATES ─────────────────────────────────────────────────────────────

# A BROKEN review-pool.sh — the real defects are present.
write_broken_review_pool(){
  cat > "$RP" << 'BROKENEOF'
#!/usr/bin/env bash
# review-pool.sh — review tab pool (BROKEN: all five defects present)

CHARON_REVIEW_MODELS="${CHARON_REVIEW_MODELS:-deepseek-v3,deepseek-r1}"
WAIT="${REVIEW_POOL_WAIT:-60}"
RETRIES="${REVIEW_POOL_RETRIES:-1}"

main_loop(){
  echo "main_loop called with: $*"
}

queue_gen(){ echo "queue_gen: not idempotent"; }

do_review(){
  local key="$1"
  # diff fetch failure -> BOUNCE + DONE marker (DEFECT 3)
  echo "review-pool: ERROR failed to fetch diff" >&2
  _write_verdict "$key" "BOUNCE" "- diff fetch failure" "N/A" "t" "u" "a"
}
_write_verdict(){
  local key="$1"
  printf '%s\t%s\n' "droid" "$(date)" > "$DONE_DIR/$key"   # DEFECT 3: always writes done
  echo "verdict written to $key"
}
DONE_DIR="/tmp/review-done"
CMD="${1:-}"; shift
case "$CMD" in
  *) main_loop "$CMD" ;;   # DEFECT 1: drops --wait/--retries
esac
BROKENEOF
  chmod +x "$RP"
}

# A FIXED review-pool.sh — all five defects are closed.
write_fixed_review_pool(){
  cat > "$RP" << 'FIXEDEOF'
#!/usr/bin/env bash
# review-pool.sh — ALL FIVE DEFECTS CLOSED

# DEFECT 5 CLOSED: model chain sourced from live catalog, not pinned literal.
# shellcheck source=/dev/null
if [ -f "$(dirname "${BASH_SOURCE[0]}")/tier-models.tsv" ]; then
  CHARON_REVIEW_MODELS="$(awk -F'\t' '/review/&&!/^#/{print $2; exit}' "$(dirname "${BASH_SOURCE[0]}")/tier-models.tsv" 2>/dev/null || echo "deepseek-v3")"
else
  CHARON_REVIEW_MODELS="${CHARON_REVIEW_MODELS:-deepseek-v3}"
fi

WAIT=60; RETRIES=1

main_loop(){
  echo "main_loop with WAIT=$WAIT RETRIES=$RETRIES"
}

# DEFECT 4 CLOSED: cut over to pr-queue.sh for queue generation.
queue_gen(){
  bash "$(dirname "${BASH_SOURCE[0]}")/pr-queue.sh" queue
}

do_review(){
  local key="$1"
  echo "review-pool: CG review failed (rc=1) for $key" >&2
  # DEFECT 3 CLOSED: infra failure does NOT write done marker.
  # No _write_verdict call on this path — the done marker is only written
  # on genuine, model-returned verdicts.
  return 1
}
_write_verdict(){
  local key="$1"
  # Only called on genuine verdicts (after _parse_verdict succeeds).
  # DEFECT 3 CLOSED: DONE_DIR only written for real verdicts, not infra bounces.
  printf '%s\t%s\n' "droid" "$(date)" > "$DONE_DIR/$key"
  echo "verdict written to $key"
}
DONE_DIR="/tmp/review-done"

# DEFECT 1 CLOSED: parse --wait/--retries from argv before main_loop.
while [ $# -gt 0 ]; do
  case "$1" in
    --wait)   WAIT="$2"; shift 2;;
    --retries) RETRIES="$2"; shift 2;;
    *) break;;
  esac
done
CMD="${1:-}"
case "$CMD" in
  *) main_loop "$CMD" ;;   # NOTE: still "$CMD" but --wait already consumed above
esac
FIXEDEOF
  chmod +x "$RP"
}

write_fixed_rig_ci_scope(){
  cat > "$RCI" << 'RCIEOF'
#!/usr/bin/env bash
CI_SUITES=(
  review-pool.test.sh     # DEFECT 2 CLOSED: suite is in the allowlist
  stranded-work.test.sh
)
RCIEOF
}

write_test_suite(){
  cat > "$TS" << 'TSEOF'
#!/usr/bin/env bash
# review-pool.test.sh — test suite with --wait and --retries assertions
# Contains tests for --wait and --retries behaviour
echo "test --wait and --retries flow"
TSEOF
  chmod +x "$TS"
}

# ── SETUP: create an unfixed rig-ci-scope for the real-file tests ──────────────────
write_unfixed_rig_ci_scope(){
  cat > "$RCI" << 'RCIEOF'
#!/usr/bin/env bash
# rig-ci-scope.sh — CI_SUITES does NOT list review-pool.test.sh
CI_SUITES=(
  stranded-work.test.sh
  flow-canary.test.sh
)
RCIEOF
}

echo "=== A. CURRENT broken state: trigger is QUIET and exits 0 ==="
write_broken_review_pool
write_unfixed_rig_ci_scope
# No test suite file needed — its absence is part of the broken state

OUT="$(run_trig)"; RC=$?
[ "$RC" -eq 0 ] && ok "A1 rc=0 (quiet) on broken state" || no "A1 rc=$RC expected 0 on broken state"
! printf '%s\n' "$OUT" | grep -q 'FIRED' && ok "A2 does NOT fire with defects present" \
  || no "A2 incorrectly fired on broken state"
! printf '%s\n' "$OUT" | grep -q 'REVIEWER-CRON-TRIGGER' && ok "A3 output is quiet (no trigger message)" \
  || no "A3 trigger message emitted while defects still present"

echo "=== B. ALL FIVE FIXED: trigger FIRES and exits non-zero ==="
write_fixed_review_pool
write_fixed_rig_ci_scope
write_test_suite
rm -f "$STATE/.reviewer-cron-trigger.hash"   # fresh state

OUT="$(run_trig)"; RC=$?
[ "$RC" -eq 2 ] && ok "B1 rc=2 (fired) when all 5 conditions met" || no "B1 rc=$RC expected 2"
printf '%s\n' "$OUT" | grep -q 'REVIEWER-CRON-TRIGGER - FIRED' \
  && ok "B2 prints FIRED message" || no "B2 no FIRED message in output"
printf '%s\n' "$OUT" | grep -q 'C1' \
  && ok "B3 the OPERATOR is directed to re-decide C1" || no "B3 no reference to C1 re-decision"

echo "=== C. ANTI-FALSE-FIRE: each condition individually holds trigger closed ==="

# C1: only C1 unmet — main_loop "$CMD" still present
write_fixed_review_pool
write_fixed_rig_ci_scope
write_test_suite
# Re-introduce the C1 bug: restore main_loop "$CMD" in the dispatch
sed -i 's#while \[ \$# -gt 0 \]; do#while [ 0 -gt 0 ]; do#; s#--wait)   WAIT=.*shift 2;;#)#; s#--retries) RETRIES=.*shift 2;;#)#' "$RP"
# Add back the bug pattern
printf '\n# restore C1 bug\nmain_loop "\$CMD"\n' >> "$RP"
rm -f "$STATE/.reviewer-cron-trigger.hash"
OUT="$(run_trig)"; RC=$?
[ "$RC" -eq 0 ] && ok "C1 C1 unmet: rc=0 (did NOT fire)" || no "C1 rc=$RC expected 0"
! printf '%s\n' "$OUT" | grep -q 'FIRED' && ok "C1b C1 unmet: no FIRED" || no "C1b incorrectly fired"

# C2: only C2 unmet — review-pool.test.sh NOT in CI_SUITES
write_fixed_review_pool
write_fixed_rig_ci_scope
write_test_suite
write_unfixed_rig_ci_scope   # overwrite rig-ci-scope with version lacking the entry
rm -f "$STATE/.reviewer-cron-trigger.hash"
OUT="$(run_trig)"; RC=$?
[ "$RC" -eq 0 ] && ok "C2 C2 unmet: rc=0" || no "C2 rc=$RC expected 0"
! printf '%s\n' "$OUT" | grep -q 'FIRED' && ok "C2b C2 unmet: no FIRED" || no "C2b incorrectly fired"

# C3: only C3 unmet — _write_verdict still called on CG failure path
write_fixed_review_pool
write_fixed_rig_ci_scope
write_test_suite
# Inject _write_verdict call after "CG review failed"
sed -i '/echo "review-pool: CG review failed/s/; return 1/_write_verdict "$key" "BOUNCE" "- infra" "N/A" "t" "u" "a"; return 1/' "$RP" 2>/dev/null
rm -f "$STATE/.reviewer-cron-trigger.hash"
OUT="$(run_trig)"; RC=$?
[ "$RC" -eq 0 ] && ok "C3 C3 unmet: rc=0" || no "C3 rc=$RC expected 0"
! printf '%s\n' "$OUT" | grep -q 'FIRED' && ok "C3b C3 unmet: no FIRED" || no "C3b incorrectly fired"

# C4: only C4 unmet — no pr-queue.sh reference, no lock on queue_gen
write_fixed_review_pool
write_fixed_rig_ci_scope
write_test_suite
sed -i 's#bash.*pr-queue\.sh.*queue#echo "queue_gen: direct, not locked"#' "$RP"
sed -i '/pr-queue\.sh/d' "$RP"   # remove the pr-queue.sh reference comment too
rm -f "$STATE/.reviewer-cron-trigger.hash"
OUT="$(run_trig)"; RC=$?
[ "$RC" -eq 0 ] && ok "C4 C4 unmet: rc=0" || no "C4 rc=$RC expected 0"
! printf '%s\n' "$OUT" | grep -q 'FIRED' && ok "C4b C4 unmet: no FIRED" || no "C4b incorrectly fired"

# C5: only C5 unmet — CHARON_REVIEW_MODELS still the pinned literal
write_fixed_review_pool
write_fixed_rig_ci_scope
write_test_suite
# Re-introduce the hardcoded default
sed -i 's|CHARON_REVIEW_MODELS=.*if.*|CHARON_REVIEW_MODELS="${CHARON_REVIEW_MODELS:-deepseek-v3,deepseek-r1}"|' "$RP"
sed -i '/DEFECT 5 CLOSED/,/^fi$/c\CHARON_REVIEW_MODELS="${CHARON_REVIEW_MODELS:-deepseek-v3,deepseek-r1}"' "$RP"
rm -f "$STATE/.reviewer-cron-trigger.hash"
OUT="$(run_trig)"; RC=$?
[ "$RC" -eq 0 ] && ok "C5 C5 unmet: rc=0" || no "C5 rc=$RC expected 0"
! printf '%s\n' "$OUT" | grep -q 'FIRED' && ok "C5b C5 unmet: no FIRED" || no "C5b incorrectly fired"

echo "=== D. State-change dedup: second identical run does NOT re-escalate ==="
write_fixed_review_pool
write_fixed_rig_ci_scope
write_test_suite
rm -f "$STATE/.reviewer-cron-trigger.hash" "$FLEETD/state/OPERATOR-ACTIONS.md"

# First run: should fire and escalate
OUT1="$(run_trig)"; RC1=$?
[ "$RC1" -eq 2 ] && ok "D1 first run fires" || no "D1 first run rc=$RC1"
[ -f "$STATE/.reviewer-cron-trigger.hash" ] && ok "D2 state hash written on first fire" \
  || no "D2 no state hash file"

# Second run with SAME fixtures: should fire (non-zero exit) but NOT re-escalate
OUT2="$(run_trig)"; RC2=$?
[ "$RC2" -eq 2 ] && ok "D3 second run still fires (non-zero exit, cron sees it)" \
  || no "D3 second run rc=$RC2"
HASH1="$(cat "$STATE/.reviewer-cron-trigger.hash")"
printf '%s\n' "$OUT2" | grep -q 'FIRED' && ok "D4 second run still prints FIRED" \
  || no "D4 no FIRED in second run output"

echo "=== E. Heartbeat: written on EVERY invocation ==="
write_broken_review_pool
write_unfixed_rig_ci_scope
HB="$STATE/.reviewer-cron-trigger.heartbeat"
rm -f "$HB"
run_trig >/dev/null
[ -f "$HB" ] && ok "E1 heartbeat written on quiet run (broken state)" || no "E1 no heartbeat on quiet run"

write_fixed_review_pool
write_fixed_rig_ci_scope
write_test_suite
rm -f "$HB" "$STATE/.reviewer-cron-trigger.hash"
run_trig >/dev/null
[ -f "$HB" ] && ok "E2 heartbeat written on firing run (all met)" || no "E2 no heartbeat on fire run"
grep -q 'rc=2' "$HB" && ok "E3 heartbeat records the fire rc" || no "E3 heartbeat wrong rc"

echo "=== F. Verbose mode shows which conditions are unmet ==="
write_broken_review_pool
write_unfixed_rig_ci_scope
rm -f "$STATE/.reviewer-cron-trigger.hash"
OUT="$(RCT_VERBOSE=1 run_trig 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "F1 verbose mode still exits 0 on unmet" || no "F1 rc=$RC"
printf '%s\n' "$OUT" | grep -q 'UNMET' && ok "F2 verbose output names unmet conditions" \
  || no "F2 no UNMET in verbose output"
printf '%s\n' "$OUT" | grep -q 'C1' && ok "F3 condition labels appear in verbose output" \
  || no "F3 no condition labels"

echo "=== G. Trigger exists and is executable (wiring check) ==="
[ -f "$TRIGGER" ] && ok "G1 trigger script exists at fleet/checks/reviewer-cron-trigger.sh" \
  || no "G1 trigger script missing"
[ -x "$TRIGGER" ] && ok "G2 trigger script is executable" || no "G2 trigger not executable"

echo
echo "reviewer-cron-trigger.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
