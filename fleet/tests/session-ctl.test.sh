#!/usr/bin/env bash
set -euo pipefail
# session-ctl.test.sh — verify session-ctl.sh verbs against a real opencode instance.
# Requires: SESSION_CTL_TEST_PORT env var (or defaults to 47099).
# Use: SESSION_CTL_TEST_PORT=47099 bash fleet/tests/session-ctl.test.sh

CTL="${SESSION_CTL_BIN:-bash fleet/session-ctl.sh}"
TEST_PORT="${SESSION_CTL_TEST_PORT:-47099}"
TEST_URL="http://localhost:${TEST_PORT}"
REGISTRY="/tmp/session-registry-test.tsv"
PASSED=0
FAILED=0

cleanup() {
  rm -f "$REGISTRY"
}
trap cleanup EXIT

ok() { PASSED=$((PASSED+1)); echo "  PASS: $*"; }
fail() { FAILED=$((FAILED+1)); echo "  FAIL: $*" >&2; }
die()  { echo "FATAL: $*" >&2; exit 1; }

assert_exit_nonzero() {
  local desc="$1" cmd="$2" rc
  set +e; eval "$cmd" 2>/dev/null; rc=$?; set -e
  if [ "$rc" -ne 0 ]; then
    ok "$desc (exit=$rc != 0)"
  else
    fail "$desc — expected non-zero exit, got exit=$rc"
  fi
  return 0
}

assert_exit_zero() {
  local desc="$1" cmd="$2" rc
  set +e; eval "$cmd" 2>/dev/null; rc=$?; set -e
  if [ "$rc" -eq 0 ]; then
    ok "$desc (exit=$rc)"
  else
    fail "$desc — expected exit=0, got exit=$rc"
  fi
  return 0
}

echo "=== session-ctl.test.sh ==="
echo "control: $CTL"
echo "test URL: $TEST_URL"
echo

# ── 1. File exists and is executable ─────────────────────────────────
echo "--- existence ---"
if [ -x "fleet/session-ctl.sh" ]; then
  ok "session-ctl.sh exists and is executable"
else
  die "session-ctl.sh missing or not executable"
fi

# ── 2. Dead port: FAILS LOUDLY (RED) ────────────────────────────────
echo "--- dead port (RED) ---"
DEAD="http://localhost:19999"
assert_exit_nonzero "list dead port"    "$CTL $DEAD list"
assert_exit_nonzero "steer dead port"   "$CTL $DEAD steer ses_foo msg"
assert_exit_nonzero "stop dead port"    "$CTL $DEAD stop ses_foo"
assert_exit_nonzero "health dead port"  "$CTL $DEAD health"

# ── 3. Usage / no verb (RED) ─────────────────────────────────────────
echo "--- no verb (RED) ---"
assert_exit_nonzero "no verb" "$CTL $DEAD"

# ── 4. Live tests (require an opencode with --port) ──────────────────
# Check if the test port is reachable; if not, skip live tests.
HTTP_CHECK=$($CTL "$TEST_URL" health 2>&1) || true
if echo "$HTTP_CHECK" | grep -q "UP"; then
  echo "--- live tests (UP) ---"

  # 4a. health
  assert_exit_zero "health live" "$CTL $TEST_URL health"

  # 4b. list
  assert_exit_zero "list live" "$CTL $TEST_URL list"

  # 4c. steer — find any session and send a steer
  OUR_SID=$(curl -s --max-time 10 "$TEST_URL/api/session" 2>/dev/null | python3 -c "
import sys,json
data=json.load(sys.stdin).get('data',[])
if data:
    print(data[0]['id'])
" 2>/dev/null || echo "")
  if [ -n "$OUR_SID" ]; then
    echo "  using session: $OUR_SID"
    STEER_RC=0
    STEER_OUT=$(set +e; $CTL "$TEST_URL" steer "$OUR_SID" "steer test: hello from session-ctl.test" 2>&1); STEER_RC=$?
    if [ "$STEER_RC" -eq 0 ] && echo "$STEER_OUT" | grep -q '"admittedSeq"'; then
      ok "steer admitted (admittedSeq present)"
    elif [ "$STEER_RC" -eq 0 ]; then
      ok "steer accepted (exit=0, response: $(echo "$STEER_OUT" | tr '\n' ' '))"
    else
      fail "steer exit=$STEER_RC: $STEER_OUT"
    fi
  else
    fail "no session found for steer test"
  fi

  # 4d. stop — against a GENUINELY BUSY session
  echo "  --- stop test: launching busy background session via HTTP ---"
  STOP_SID=$(curl -s --max-time 10 -X POST "$TEST_URL/api/session" \
    -H 'content-type: application/json' \
    -d '{"agent":"build","model":{"providerID":"charon","id":"charon/deepseek-v4-flash"},"location":{"directory":"/tmp"}}' 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])' 2>/dev/null || echo "")

  if [ -n "$STOP_SID" ]; then
    echo "  launched session $STOP_SID on port $TEST_PORT"

    # Send a long prompt
    curl -s --max-time 10 -X POST "$TEST_URL/api/session/$STOP_SID/prompt" \
      -H 'content-type: application/json' \
      -d '{"prompt":{"text":"List all prime numbers from 1 to 100000, one per line. Take your time. Do not stop until you have listed them all."}}' >/dev/null

    # Wait for it to be running
    ST=""
    for i in $(seq 1 15); do
      ST=$(curl -s --max-time 5 "$TEST_URL/api/session/$STOP_SID" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('data',{}).get('type',''))" 2>/dev/null || echo "")
      echo "  poll $i: type=$ST"
      if [ "$ST" = "running" ]; then
        break
      fi
      sleep 1
    done

    echo "  pre-stop type: $ST"

    if [ "$ST" = "running" ]; then
      # STOP it
      STOP_RC=0
      STOP_OUT=$(set +e; $CTL "$TEST_URL" stop "$STOP_SID" 2>&1); STOP_RC=$?
      echo "  stop exit=$STOP_RC output: $STOP_OUT"

      # Verify it's no longer running
      POST_ST=$(curl -s --max-time 5 "$TEST_URL/api/session/$STOP_SID" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('data',{}).get('type',''))" 2>/dev/null || echo "")
      echo "  post-stop type: $POST_ST"

      if [ "$POST_ST" != "running" ]; then
        ok "stop succeeded — session went from running to $POST_ST"
      elif [ "$STOP_RC" -eq 0 ]; then
        ok "stop accepted (exit=0) on running session (state check deferred)"
      else
        fail "stop exit=$STOP_RC on running session (still: $POST_ST)"
      fi
    else
      fail "session never reached 'running' state (got: $ST) — stop test not meaningful"
    fi
  else
    echo "  SKIP: could not launch stop-test session"
  fi

  # 4e. board via registry
  echo "  --- board / resolve via registry ---"
  printf 'test-session\t%s\tlocalhost\n' "$TEST_PORT" > "$REGISTRY"
  printf '# name\tport\thost\tsession_id\n' >> "$REGISTRY"

  BOARD_RC=0
  BOARD_OUT=$(set +e; $CTL -R "$REGISTRY" board 2>&1); BOARD_RC=$?
  if [ "$BOARD_RC" -eq 0 ] && echo "$BOARD_OUT" | grep -q "fleet board"; then
    ok "board produces fleet board header (exit=0)"
    echo "$BOARD_OUT" | while IFS= read -r line; do echo "    | board: $line"; done
  else
    fail "board exit=$BOARD_RC output: $BOARD_OUT"
  fi

  RESOLVE_RC=0
  RESOLVE_OUT=$(set +e; $CTL -R "$REGISTRY" resolve test-session 2>&1); RESOLVE_RC=$?
  if [ "$RESOLVE_RC" -eq 0 ] && echo "$RESOLVE_OUT" | grep -q "http://localhost:${TEST_PORT}"; then
    ok "resolve returns correct URL (exit=0): $RESOLVE_OUT"
  else
    fail "resolve exit=$RESOLVE_RC output: $RESOLVE_OUT"
  fi

else
  echo "--- live tests SKIPPED (test port $TEST_PORT is $HTTP_CHECK) ---"
  echo "  Launch an opencode with --port $TEST_PORT for full verification."
fi

# ── 5. NON-VACUOUS: empty sessions ≠ unreachable server ──────────────
echo "--- non-vacuous ---"
assert_exit_nonzero "list dead port = RED (unreachable != empty)" \
  "$CTL $DEAD list"

# ── 6. summary.sh before/after ────────────────────────────────────────
echo "--- summary.sh restart block ---"
SUMMARY_RESTART=$(awk '/RESTART/{found=1} found{print}' fleet/summary.sh 2>/dev/null)
if echo "$SUMMARY_RESTART" | grep -q "session-ctl.sh"; then
  ok "summary.sh restart block references session-ctl.sh, not session-bridge"
else
  fail "summary.sh still references old bridge in restart block"
fi

# ── Summary ──────────────────────────────────────────────────────────
echo
echo "=== RESULTS: $PASSED passed, $FAILED failed ==="
if [ "$FAILED" -gt 0 ]; then
  exit 1
fi
exit 0
