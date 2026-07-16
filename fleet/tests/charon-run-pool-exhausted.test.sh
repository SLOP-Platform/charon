#!/usr/bin/env bash
# charon-run-pool-exhausted.test.sh — FAIL-ON-REVERT tests for
# SALVAGE-STASH-CHARON-RUN (the OPENCODE_LOG rc=124 disambiguation branch on
# fleet/charon-run.sh). See docs/review-log/SALVAGE-STASH-CHARON-RUN.md for
# the full design rationale; the short version:
#
#   When the `timeout` wrapper kills a charon-run attempt (rc=124), there are
#   THREE genuinely different causes that all look like "hung" from the
#   caller's POV:
#     (a) model streamed real output but didn't finish in time  -> too-slow,
#         model-attributable, BLOCK the model in the scorecard
#     (b) no output at all before the budget                   -> leg-fault,
#         infra/leg hang, NEVER model-attributable, do NOT BLOCK
#     (c) no output at all, BUT opencode's own log shows        -> gateway
#         repeated "all providers exhausted" during the          pool was
#         attempt window                                        drained and
#         opencode silently retried in a loop, PROVIDER-side, NEVER
#         model-attributable, do NOT BLOCK
#
#   Master only had (a) and (b) (EVAL-LATENCY-GATE, see
#   fleet/tests/dogfood-latency-gate.test.sh). Without (c), a pool-exhaustion
#   masquerade was getting charged to the model as a too-slow fault (or, in
#   the no-output variant, was indistinguishable from a true leg-fault hang).
#   This test pins (c) on top of master's intact (a)+(b) behaviour.
#
# Also re-pins the CHARON_RUN_TIMEOUT_S override contract for the timeout
# branch's marker text (master's contract; the stash just adds a third
# sub-case that lives in the same branch — must not regress the others).
#
# Fully hermetic: stub `opencode` on PATH, isolated COPY of charon-run.sh with
# no sibling capture/ (cap() hook safely no-ops), override
# CHARON_EXHAUST_LEDGER and CAPTURE_SPOOL_DIR to throwaway paths, fake
# OPENCODE_LOG pointing at a WORK-scoped file we control line-by-line. No
# live network, no real gateway/opencode call, no writes to any file outside
# $WORK. Real lib/dogfood-attribution.sh sourced as-is so a revert of either
# the charon-run.sh marker text OR the attribution grep flips this test RED.
#
# Run:  bash fleet/tests/charon-run-pool-exhausted.test.sh   (exit 0 = all pass)
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
grep_line(){ # grep_line <desc> <file> <ere>
  if grep -qE "$3" "$2" 2>/dev/null; then ok "$1"; else
    bad "$1 (no line in $2 matched /$3/)"; echo "----- file: $2 -----"; cat "$2" 2>/dev/null; echo "---------------------"
  fi
}
not_grep_line(){ # not_grep_line <desc> <file> <ere>
  if grep -qE "$3" "$2" 2>/dev/null; then
    bad "$1 (line in $2 matched /$3/, must NOT)"; echo "----- file: $2 -----"; cat "$2" 2>/dev/null; echo "---------------------"
  else
    ok "$1"
  fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── isolated charon-run.sh copy: no sibling capture/ dir, so its own cap()
# hook is structurally a no-op here (never touches real capture state) ──────
BIN="$WORK/bin"; mkdir -p "$BIN"
cp "$FLEET_DIR/charon-run.sh" "$BIN/charon-run.sh"
chmod +x "$BIN/charon-run.sh"

# ── hermetic overrides: never the real ledger, never the real bench-grader
# spool, never the real $HOME/.local/share/opencode/log path ────────────────
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

# ── shared fake opencode log. The awk filter inside charon-run.sh does a
# lexical `>=` against ATTEMPT_START_ISO (the timestamp the script captures
# immediately before launching `timeout`). So:
#   - "before" lines must have `ts < ATTEMPT_START_ISO` (use -10s from NOW)
#   - "in-window" lines must have `ts >= ATTEMPT_START_ISO` (use NOW, which
#     is captured fresh on each call right before the charon-run.sh launch)
#   - charon-run.sh itself reads `date -u +%FT%TZ` AFTER the test's NOW
#     capture, so NOW will always be `ts <= ATTEMPT_START_ISO` and the
#     lexical `>=` filter accepts the in-window lines.
# We do NOT test the "future-dated" direction: the awk filter is deliberately
# one-sided (only filters out before-window noise from prior loop iterations
# or prior runs sharing the same log). Future-dated lines don't happen in
# real opencode logs; if they did, counting them would be a false-positive
# that errs on the side of "provider-side, don't BLOCK the model" — safe.
# Timezone discipline: -d on GNU date expects "10 seconds ago" / "10 seconds".
# BSD/macOS date would need -v; this fleet lives on Linux (the droid host),
# so GNU syntax is the right portability bet. If a future test runner is BSD,
# swap to a python helper — see the comment in tools/.
stamp_line() { # stamp_line <file> <iso_ts>
  printf 'timestamp=%s level=ERROR modelID=fake-model other stuff "all providers exhausted"\n' "$2" >> "$1"
}
seed_log() { # seed_log <before_n> <during_n>
  # `during_n` lines are stamped at the moment this function runs, which
  # is the same moment we launch charon-run.sh on the next line — so they
  # land at or just before the script's own ATTEMPT_START_ISO capture.
  : > "$OPENCODE_LOG"
  local before_ts
  before_ts="$(date -u -d '10 seconds ago' +%FT%TZ 2>/dev/null || date -u +%FT%TZ)"
  # `i` is the seq loop counter; the body doesn't reference it, so shellcheck
  # would warn SC2034 if we declared it `local`. Leaving it undeclared in
  # the for-loop position is the idiom shellcheck accepts.
  for i in $(seq 1 "$1"); do stamp_line "$OPENCODE_LOG" "$before_ts"; done
  for i in $(seq 1 "$2"); do stamp_line "$OPENCODE_LOG" "$(date -u +%FT%TZ)"; done
}

OPENCODE_LOG="$WORK/opencode.log"
: > "$OPENCODE_LOG"
export OPENCODE_LOG

# ═════════════════════════════════════════════════════════════════════════
# STAGE 1 — baseline (master's existing behaviour, regression guard).
# A no-output rc=124 hang with NO opencode log entries at all must still
# route to "leg-fault" — the new pool-exhausted branch must NOT eat this case.
# ═════════════════════════════════════════════════════════════════════════
seed_log 0 0
CWD_LF="$WORK/cwd-legfault"; mkdir -p "$CWD_LF"
LOG_LF="$WORK/legfault.charon-run.log"
STUB_MODE=hang CHARON_RUN_TIMEOUT_S=2 "$BIN/charon-run.sh" "$CWD_LF" "$LOG_LF" "$BRIEF" fake-model
grep_line      "stage 1: leg-fault marker still emitted (regression guard)" "$LOG_LF" "TIMEOUT \(rc=124\).*leg-fault"
not_grep_line  "stage 1: leg-fault case is NOT misclassified as pool-exhausted" "$LOG_LF" "CAUSE: gateway pool exhausted"
not_grep_line  "stage 1: leg-fault case is NOT misclassified as too-slow"     "$LOG_LF" "too-slow FAIL"

# ═════════════════════════════════════════════════════════════════════════
# STAGE 2 — too-slow with no pool-exhausted log entries: still routes to
# the (master's) too-slow FAIL marker (model-attributable, BLOCK'd).
# Also re-pins the CHARON_RUN_TIMEOUT_S=2 override contract — without that,
# the marker would say `budget=1800s` and the regression test for the
# timeout-override contract in dogfood-latency-gate.test.sh would already
# catch it, but pinning it here too means a future regression in this file's
# own scope flips RED.
# ═════════════════════════════════════════════════════════════════════════
seed_log 0 0
CWD_TS="$WORK/cwd-tooslow"; mkdir -p "$CWD_TS"
LOG_TS="$WORK/tooslow.charon-run.log"
STUB_MODE=too-slow CHARON_RUN_TIMEOUT_S=2 "$BIN/charon-run.sh" "$CWD_TS" "$LOG_TS" "$BRIEF" fake-model
grep_line      "stage 2: too-slow marker still emitted (regression guard)"      "$LOG_TS" "TIMEOUT \(rc=124\) budget=2s too-slow FAIL"
not_grep_line  "stage 2: too-slow case is NOT misclassified as pool-exhausted"  "$LOG_TS" "CAUSE: gateway pool exhausted"
not_grep_line  "stage 2: too-slow case is NOT misclassified as leg-fault"       "$LOG_TS" "leg-fault"
grep_line      "stage 2: budget from CHARON_RUN_TIMEOUT_S appears in marker"    "$LOG_TS" "budget=2s too-slow FAIL"

# ═════════════════════════════════════════════════════════════════════════
# STAGE 3 — NEW FEATURE: rc=124 with a no-output hang AND in-window
# "all providers exhausted" log entries routes to the pool-exhausted marker.
# This is the marker lib/dogfood-attribution.sh's classify_attribution
# already greps for on its first non-zero line (`TIMEOUT (rc=124.*CAUSE:
# gateway pool exhausted`); round-trip the contract by sourcing the real
# attribution lib and asserting classify_attribution returns the
# provider-degraded bucket for this case.
# ═════════════════════════════════════════════════════════════════════════
seed_log 0 3
CWD_PE="$WORK/cwd-pool-exhausted"; mkdir -p "$CWD_PE"
LOG_PE="$WORK/pool-exhausted.charon-run.log"
STUB_MODE=hang CHARON_RUN_TIMEOUT_S=2 "$BIN/charon-run.sh" "$CWD_PE" "$LOG_PE" "$BRIEF" fake-model
grep_line     "stage 3: pool-exhausted marker emitted (NEW feature)"        "$LOG_PE" "TIMEOUT \(rc=124\) budget=2s — CAUSE: gateway pool exhausted"
grep_line     "stage 3: marker reports the actual in-window count (3 hits)" "$LOG_PE" "3x 'all providers exhausted'"
not_grep_line "stage 3: pool-exhausted case is NOT misclassified as too-slow"  "$LOG_PE" "too-slow FAIL"
not_grep_line "stage 3: pool-exhausted case is NOT misclassified as leg-fault"   "$LOG_PE" "leg-fault"
# AND: the ledger for THIS run (filtered by LABEL = OUT basename) only got
# the provider-side event, NOT a model-attributable one. Filtering by LABEL
# avoids cross-stage contamination: each stage's prior leg-fault/too-slow
# rows live in the same ledger file but on different LABEL rows.
PE_LINES="$(grep -E "$(printf '\tpool-exhausted.charon-run.log\t')" "$WORK/ledger.tsv" || true)"
grep_line     "stage 3: ledger (this run) records the pool-exhausted event"  <(printf '%s\n' "$PE_LINES") "pool-exhausted-timeout"
not_grep_line "stage 3: ledger (this run) does NOT record too-slow"          <(printf '%s\n' "$PE_LINES") "too-slow-failover"
not_grep_line "stage 3: ledger (this run) does NOT record leg-fault"         <(printf '%s\n' "$PE_LINES") "leg-fault-failover"

# Attribution round-trip: real lib/dogfood-attribution.sh must read the new
# marker and return its dedicated "pool-exhausted-on-timeout" bucket. This
# is the upstream signal that retires "provider-throttled->try-another"
# misclassification for genuine gateway-pool exhaustion during a hang.
# (The script's outer exit is 3 ALL-EXHAUSTED because the single candidate
# model failed — that's correct; we read the per-attempt rc=124 from the log
# body instead, which is what classify_attribution's contract uses.)
source "$FLEET_DIR/benchmark/lib/dogfood-attribution.sh"
ATTR_PE="$(classify_attribution 124 "$LOG_PE")"
has        "stage 3: classify_attribution routes the new marker to its bucket" "$ATTR_PE" "pool-exhausted-on-timeout"
not_has    "stage 3: classify_attribution does NOT call this too-slow"         "$ATTR_PE" "too-slow"
not_has    "stage 3: classify_attribution does NOT call this leg-fault"        "$ATTR_PE" "leg-fault"

# ═════════════════════════════════════════════════════════════════════════
# STAGE 4 — TIME-SCOPED COUNT GUARD: BEFORE-window "all providers exhausted"
# log lines from prior runs / prior loop iterations sharing the same log
# must NOT be counted (lexical `>=` against ATTEMPT_START_ISO). If a
# stale-before-window entry was counted, the test would falsely route the
# leg-fault case to pool-exhausted — stage 1 is the structural regression
# guard for that; this stage makes the count guard explicit (5 in / 0 out
# noise vs 0 noise should still be leg-fault).
# ═════════════════════════════════════════════════════════════════════════
seed_log 5 0
CWD_STALE="$WORK/cwd-stale-only"; mkdir -p "$CWD_STALE"
LOG_STALE="$WORK/stale-only.charon-run.log"
STUB_MODE=hang CHARON_RUN_TIMEOUT_S=2 "$BIN/charon-run.sh" "$CWD_STALE" "$LOG_STALE" "$BRIEF" fake-model
not_grep_line "stage 4: BEFORE-window log noise is NOT promoted to pool-exhausted" "$LOG_STALE" "CAUSE: gateway pool exhausted"
grep_line     "stage 4: BEFORE-window-only case still routes to leg-fault"          "$LOG_STALE" "TIMEOUT \(rc=124\).*leg-fault"

# ═════════════════════════════════════════════════════════════════════════
# STAGE 5 — opencode.log absent (the default $HOME/.local/share path does
# not exist on most test hosts). charon-run.sh must NOT crash; the OPENCODE_LOG
# peek must degrade to "0 hits" and the existing too-slow/leg-fault split
# must run unchanged. Override OPENCODE_LOG to a path that does NOT exist.
# ═════════════════════════════════════════════════════════════════════════
unset OPENCODE_LOG   # fall back to $HOME/.local/share/opencode/log/opencode.log
# Defensive: make sure neither default path exists in the test env.
rm -f "$HOME/.local/share/opencode/log/opencode.log" 2>/dev/null || true
CWD_NOLOG="$WORK/cwd-no-log"; mkdir -p "$CWD_NOLOG"
LOG_NOLOG="$WORK/no-log.charon-run.log"
STUB_MODE=hang CHARON_RUN_TIMEOUT_S=2 "$BIN/charon-run.sh" "$CWD_NOLOG" "$LOG_NOLOG" "$BRIEF" fake-model
grep_line     "stage 5: missing OPENCODE_LOG degrades cleanly to leg-fault" "$LOG_NOLOG" "TIMEOUT \(rc=124\).*leg-fault"
not_grep_line "stage 5: missing OPENCODE_LOG never causes a pool-exhausted misclassification" "$LOG_NOLOG" "CAUSE: gateway pool exhausted"

echo
echo "SELFTEST SUMMARY: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
  echo "CHARON-RUN POOL-EXHAUSTED SELFTEST: FAILED — see FAIL lines above."
  exit 1
fi
echo "ALL CHARON-RUN POOL-EXHAUSTED SELFTESTS PASS: rc=124 disambiguation now"
echo "  distinguishes too-slow (model-attributable) | leg-fault (infra hang) |"
echo "  pool-exhausted (provider-side, never a model verdict)."
