#!/usr/bin/env bash
# reviewer-cron-trigger.sh — DEFERRED-DECISION TRIGGER for the reviewer cron.
#
# Evaluates five conditions in fleet/review-pool.sh and fleet/checks/rig-ci-scope.sh.
# While ANY condition is unmet, exits 0 and stays quiet — a nagging check gets muted,
# and a muted check is a dead check. When ALL five are met, exits NON-ZERO, prints
# "REVIEWER-CRON-TRIGGER - FIRED", and escalates via fleet/pending.sh so the OPERATOR
# is asked to re-decide C1. It never enables anything itself — the decision returns to
# the human who deferred it.
#
# Fail-closed: unknown counts as NOT met. Every condition is evaluated locally from
# source files with no network, no live `gh`, no live gateway call.
#
# Cron wrapper: writes a heartbeat on EVERY invocation (including failures), so
# "registered but not executing" is distinguishable from "removed". Uses state-change
# hashing so escalation fires once on transition, not on every poll.
#
# Usage: fleet/checks/reviewer-cron-trigger.sh [--verbose]
# Exit:  0 no fire (at least one condition unmet — this is NORMAL and quiet)
#        2 ALL FIVE MET — FIRED (the deferred decision must be re-opened)
# Env:
#   RCT_FLEET         override fleet dir (tests)
#   RCT_STATE         override state dir (tests)
#   RCT_REVIEW_POOL   path to review-pool.sh under test (tests inject fixture)
#   RCT_RIG_CI_SCOPE  path to rig-ci-scope.sh under test
#   RCT_NO_PENDING=1  do not call pending.sh (tests)
#   RCT_VERBOSE=1     show which conditions are unmet
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET="${RCT_FLEET:-$(cd "$HERE/.." && pwd)}"
STATE="${RCT_STATE:-$FLEET/state}"
REVIEW_POOL="${RCT_REVIEW_POOL:-$FLEET/review-pool.sh}"
RIG_CI_SCOPE="${RCT_RIG_CI_SCOPE:-$FLEET/checks/rig-ci-scope.sh}"
HB="$STATE/.reviewer-cron-trigger.heartbeat"
HASHF="$STATE/.reviewer-cron-trigger.hash"
PENDING="$FLEET/pending.sh"
VERBOSE="${RCT_VERBOSE:-0}"
PEND_KEY="REVIEWER-CRON TRIGGER:"
mkdir -p "$STATE" 2>/dev/null

heartbeat(){ printf '%s rc=%s %s\n' "$(date -Is)" "${1:-?}" "${2:-}" > "$HB"; }
announce(){
  [ -n "${RCT_NO_PENDING:-}" ] && return 0
  bash "$PENDING" add --key "$PEND_KEY" "$PEND_KEY$1" >/dev/null 2>&1 || true
}
vmsg(){ [ "$VERBOSE" -eq 1 ] && echo "reviewer-cron-trigger: $*" >&2 || true; }

# ── THE FIVE CONDITIONS ───────────────────────────────────────────────────────────
# Each returns 0 if the CONDITION IS MET (defect closed). Fail-closed: unknown = 1.

check_1(){
  local pool="$1"
  [ -f "$pool" ] || return 1
  # DEFECT: dispatch `main_loop "$CMD"` silently drops --wait and --retries.
  #     Fix: dispatch passes all remaining args or parses --wait/--retries before
  #     calling main_loop, so `review-pool.sh economy --wait 5` works end to end.
  #     Proven by a test suite that goes RED when the fix is reverted.
  # CHECK: the literal bug pattern "main_loop \"$CMD\"" is absent, AND a test suite
  #     file exists at fleet/tests/review-pool.test.sh with wait/retries assertions.
  local testsuite="${pool%/*}/tests/review-pool.test.sh"
  if grep -qE 'main_loop[[:space:]]+"\$CMD"' "$pool" 2>/dev/null; then
    vmsg "  C1: UNMET — main_loop \"\$CMD\" still drops --wait/--retries"
    return 1
  fi
  if [ ! -f "$testsuite" ]; then
    vmsg "  C1: UNMET — no review-pool.test.sh found at $testsuite"
    return 1
  fi
  if ! grep -qE '\-\-wait|\-\-retries' "$testsuite" 2>/dev/null; then
    vmsg "  C1: UNMET — review-pool.test.sh has no --wait/--retries assertions"
    return 1
  fi
  vmsg "  C1: MET"
}

check_2(){
  local rig="$1"
  [ -f "$rig" ] || return 1
  # DEFECT: a suite outside the CI_SUITES allowlist has never executed in CI.
  #     Fix: review-pool.test.sh is listed literally in CI_SUITES=(...) in rig-ci-scope.sh.
  # CHECK: the literal filename appears in the CI_SUITES array.
  if grep -q 'review-pool.test.sh' "$rig" 2>/dev/null; then
    vmsg "  C2: MET"
    return 0
  fi
  vmsg "  C2: UNMET — review-pool.test.sh not in CI_SUITES allowlist"
  return 1
}

check_3(){
  local pool="$1"
  [ -f "$pool" ] || return 1
  # DEFECT: _write_verdict writes to $DONE_DIR unconditionally, and do_review calls it
  #     on EVERY failure path (diff fetch failure, CG failure, verdict parse failure,
  #     invalid verdict type). An infra fault permanently retires a PR — 16 PRs hit
  #     this on 2026-08-02.
  #     Fix: infra-failure paths (CG failure, diff fetch failure, verdict parse failure)
  #     do NOT call _write_verdict and do NOT write to $DONE_DIR/$key. Only a genuine
  #     model-returned verdict writes a done marker.
  # CHECK: _write_verdict is NOT called within 8 lines after "CG review failed" or
  #     "failed to fetch diff" or "verdict parse failure" — those are the infra paths
  #     that must not retire a PR.
  if grep -A8 'CG review failed' "$pool" 2>/dev/null | grep -q '_write_verdict'; then
    vmsg "  C3: UNMET — CG failure still writes a done marker (permanently retires PR)"
    return 1
  fi
  if grep -A8 'failed to fetch diff' "$pool" 2>/dev/null | grep -q '_write_verdict'; then
    vmsg "  C3: UNMET — diff fetch failure still writes a done marker"
    return 1
  fi
  if grep -A8 'verdict parse failure' "$pool" 2>/dev/null | grep -q '_write_verdict'; then
    vmsg "  C3: UNMET — verdict parse failure still writes a done marker"
    return 1
  fi
  vmsg "  C3: MET"
}

check_4(){
  local pool="$1"
  [ -f "$pool" ] || return 1
  # DEFECT: queue_gen is not idempotent (regenerates from scratch on every call) and
  #     is not locked — two concurrent callers race.
  #     Fix (option a): cut over to fleet/pr-queue.sh (landed PR #392, REST + ETag,
  #     zero-quota steady state).
  #     Fix (option b): queue_gen is under explicit flock.
  # CHECK: either "pr-queue.sh" is referenced in review-pool.sh, or queue_gen is
  #     guarded by a lock.
  if grep -q 'pr-queue.sh' "$pool" 2>/dev/null; then
    vmsg "  C4: MET — cut over to pr-queue.sh"
    return 0
  fi
  if grep -qE 'flock.*queue_gen|lock.*queue_gen' "$pool" 2>/dev/null; then
    vmsg "  C4: MET — queue_gen is locked"
    return 0
  fi
  vmsg "  C4: UNMET — queue_gen not locked and pr-queue.sh not referenced"
  return 1
}

check_5(){
  local pool="$1"
  [ -f "$pool" ] || return 1
  # DEFECT: CHARON_REVIEW_MODELS defaults to the hardcoded list "deepseek-v3,deepseek-r1"
  #     which rots as the catalog changes.
  #     Fix: the model chain is sourced from live data (e.g. the tier-models.tsv
  #     catalog) rather than a pinned literal string.
  # CHECK: the default value for CHARON_REVIEW_MODELS is NOT the hardcoded string
  #     "deepseek-v3,deepseek-r1" — the literal is absent OR the default is a
  #     dynamic lookup.
  if grep -qE 'CHARON_REVIEW_MODELS[[:space:]]*:[[:space:]]*-[[:space:]]*deepseek-v3,deepseek-r1' "$pool" 2>/dev/null; then
    vmsg "  C5: UNMET — model chain is the pinned literal 'deepseek-v3,deepseek-r1'"
    return 1
  fi
  vmsg "  C5: MET"
}

# ── MAIN ──────────────────────────────────────────────────────────────────────────

case "${1:-}" in
  --verbose) VERBOSE=1 ;;
  "") ;;
  *) echo "usage: reviewer-cron-trigger.sh [--verbose]" >&2; exit 2 ;;
esac

C1_OUT="$(check_1 "$REVIEW_POOL" 2>&1)"; c1=$?
C2_OUT="$(check_2 "$RIG_CI_SCOPE" 2>&1)"; c2=$?
C3_OUT="$(check_3 "$REVIEW_POOL" 2>&1)"; c3=$?
C4_OUT="$(check_4 "$REVIEW_POOL" 2>&1)"; c4=$?
C5_OUT="$(check_5 "$REVIEW_POOL" 2>&1)"; c5=$?

[ "$VERBOSE" -eq 1 ] && { printf '%s\n' "$C1_OUT" "$C2_OUT" "$C3_OUT" "$C4_OUT" "$C5_OUT" | grep -v '^$' >&2 || true; }
ALL=$(( (c1==0) + (c2==0) + (c3==0) + (c4==0) + (c5==0) ))
SPAN_KEY="c1=$c1 c2=$c2 c3=$c3 c4=$c4 c5=$c5"
FIRE_KEY="fired:$SPAN_KEY"
PREV="$(cat "$HASHF" 2>/dev/null || true)"

heartbeat "$ALL" "all=$ALL"

if [ "$ALL" -eq 5 ]; then
  if [ "$FIRE_KEY" != "$PREV" ]; then
    printf '%s\n' "$FIRE_KEY" > "$HASHF"
    cat << 'TRIGGERMSG'
REVIEWER-CRON-TRIGGER - FIRED — all five review-pool.sh defects are closed

The five conditions that kept the reviewer cron deferred are now satisfied.
The OPERATOR is asked to re-decide C1 (2026-08-02): enable the reviewer half
of the PR-draft triage cadence on the same cron schedule.

See: fleet/checks/reviewer-cron-trigger.sh for the five conditions.
     fleet/state/REVIEWER-CRON-REVISIT.md for the deferral rationale.
TRIGGERMSG
    announce " FIRED — all five review-pool.sh defects are closed. Condition details: $SPAN_KEY."
    exit 2
  fi
  # Already escalated — fire again without re-announcing
  echo "REVIEWER-CRON-TRIGGER - FIRED — all five conditions remain met ($SPAN_KEY)"
  exit 2
fi

exit 0
