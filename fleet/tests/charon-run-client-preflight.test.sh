#!/usr/bin/env bash
# charon-run-client-preflight.test.sh — FAIL-ON-REVERT tests for
# DROID-CLIENT-PREFLIGHT (fleet/charon-run.sh + fleet/fleet-droid.sh).
#
# THE BUG THIS PINS (real incident, 2026-07-25T05:14Z — see
# fleet/state/reviews/DROID-SESSION-FAILURE-agen-kolar.md):
#
#   `opencode` lives in ~/.local/bin, which is put on PATH ONLY by ~/.bashrc
#   and ~/.profile — interactive/login shells only. A fleet-droid.sh tab
#   launched from a non-login, non-interactive shell ran `timeout … opencode`
#   with no `opencode` on PATH. `timeout` exited 127 for EVERY model in the
#   chain, in under one second, and charon-run.sh reported:
#       [charon-run] ALL MODELS EXHAUSTED: <4 models>
#       CHARON_RUN_RESULT=EXHAUSTED            (exit 3)
#   …i.e. a MISSING LOCAL BINARY was reported as PROVIDER POOL EXHAUSTION.
#
#   Worse: rc=127 was absent from is_infra_fault(), so each leg took the
#   generic `elif RC -ne 0` branch and enqueued a scorecard BLOCK — 24 false
#   BLOCK enqueues against 4 innocent models, into the very ledger routing
#   ranks on.
#
# TWO independent regressions are pinned here, because either alone is a
# silent mis-route:
#   A. PREFLIGHT — a missing client fails with a DISTINCT exit code (4) and a
#      loud message, and NEVER emits exhaustion language or an ALL-EXHAUSTED
#      ledger row.
#   B. ATTRIBUTION — an rc=127/126 leg (client vanishing MID-CHAIN, past the
#      preflight) is classified INFRA, so no scorecard BLOCK is enqueued.
#
# NON-VACUOUS BY CONSTRUCTION: the capture hook is stubbed with a RECORDER
# (not the usual "no sibling capture/ dir so cap() no-ops" trick), and a
# control case with a plain rc=1 leg PROVES the recorder does capture a real
# BLOCK. So "no BLOCK for rc=127" cannot pass because the recorder was dead.
#
# Fully hermetic: isolated COPY of charon-run.sh, fake $HOME, stubbed client,
# stubbed capture recorder, throwaway ledger. No network, no gateway, no real
# bench-grader spool, no writes outside $WORK.
#
# Run:  bash fleet/tests/charon-run-client-preflight.test.sh   (exit 0 = pass)
set -uo pipefail

FLEET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ # has <desc> <haystack> <needle>
  case "$2" in
    *"$3"*) ok "$1" ;;
    *) bad "$1 (expected to find '$3')"; echo "----- haystack -----"; printf '%s\n' "$2"; echo "--------------------" ;;
  esac
}
not_has(){ # not_has <desc> <haystack> <needle>
  case "$2" in
    *"$3"*) bad "$1 (must NOT contain '$3')"; echo "----- haystack -----"; printf '%s\n' "$2"; echo "--------------------" ;;
    *) ok "$1" ;;
  esac
}
eq(){ # eq <desc> <actual> <expected>
  if [ "$2" = "$3" ]; then ok "$1 (=$3)"; else bad "$1 (got '$2', expected '$3')"; fi
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── isolated charon-run.sh copy ──────────────────────────────────────────────
BIN="$WORK/bin"; mkdir -p "$BIN"
cp "$FLEET_DIR/charon-run.sh" "$BIN/charon-run.sh"
chmod +x "$BIN/charon-run.sh"

# ── capture RECORDER: charon-run.sh's cap() calls $SCRIPT_DIR/capture/
# enqueue-capture.sh when it is executable. Standing it up here (instead of
# omitting it) is what makes the "no BLOCK was enqueued" assertions REAL. ────
mkdir -p "$BIN/capture"
CAP_LOG="$WORK/capture-calls.log"
cat > "$BIN/capture/enqueue-capture.sh" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$CAP_LOG"
exit 0
EOF
chmod +x "$BIN/capture/enqueue-capture.sh"

# ── hermetic env: never the real ledger, never the real spool, and a FAKE
# \$HOME so the script's "~/.local/bin fallback" has nothing real to find. ────
export CHARON_EXHAUST_LEDGER="$WORK/ledger.tsv"
export CAPTURE_SPOOL_DIR="$WORK/spool/req"; mkdir -p "$CAPTURE_SPOOL_DIR"
export HOME="$WORK/fakehome"; mkdir -p "$HOME"
export CHARON_RUN_TIMEOUT_S=20

BRIEF="$WORK/brief.md"; echo "hermetic preflight test brief" > "$BRIEF"
CWD="$WORK/cwd"; mkdir -p "$CWD"

# ── stub client. STUB_MODE selects behaviour; never touches the network. ─────
STUBBIN="$WORK/stubbin"; mkdir -p "$STUBBIN"
cat > "$STUBBIN/opencode" <<'EOF'
#!/usr/bin/env bash
case "${STUB_MODE:-clean}" in
  clean)     echo "stub: did the ticket work"; exit 0 ;;
  notfound)  echo "stub: simulating exec failure" >&2; exit 127 ;;
  noexec)    echo "stub: simulating not-executable" >&2; exit 126 ;;
  plainfail) echo "stub: model produced a genuine bad result"; exit 1 ;;
esac
EOF
chmod +x "$STUBBIN/opencode"

# A minimal PATH that HAS coreutils (so `timeout` resolves) but NOT the client.
# This is the exact shape of the real incident's environment.
SANITIZED_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

run_charon(){ # run_charon <outlog> <path> [models...] -> echoes rc; sets RUN_OUT
  local out="$1" path="$2"; shift 2
  RUN_STDERR="$WORK/stderr.txt"
  PATH="$path" "$BIN/charon-run.sh" "$CWD" "$out" "$BRIEF" "$@" 2>"$RUN_STDERR"
  local rc=$?
  RUN_OUT="$(cat "$out" 2>/dev/null)"
  RUN_ERR="$(cat "$RUN_STDERR" 2>/dev/null)"
  return $rc
}

MODELS=(model-a model-b model-c model-d)

echo "=== A. PREFLIGHT: client missing from PATH ==="
: > "$CAP_LOG"
: > "$CHARON_EXHAUST_LEDGER"
OUT_A="$WORK/a.txt"
run_charon "$OUT_A" "$SANITIZED_PATH" "${MODELS[@]}"; RC_A=$?
echo "--- sanitized-PATH exit code: $RC_A"
eq       "A1 preflight exits with the DISTINCT prereq code (not 3=exhausted, not 0)" "$RC_A" "4"
has      "A2 log names the missing binary"                "$RUN_OUT" "required binary not found: opencode"
has      "A3 log states the PATH it searched"             "$RUN_OUT" "PATH searched:"
has      "A4 log says LOCAL ENVIRONMENT fault"            "$RUN_OUT" "LOCAL ENVIRONMENT fault"
has      "A5 machine-readable result line"                "$RUN_OUT" "CHARON_RUN_RESULT=PREREQ-MISSING"
has      "A6 FATAL also reaches stderr (operator sees it)" "$RUN_ERR" "required binary not found"
# THE CORE OF THE DEFECT: a missing binary must never be laundered as pool exhaustion.
not_has  "A7 does NOT claim ALL MODELS EXHAUSTED"         "$RUN_OUT" "ALL MODELS EXHAUSTED"
not_has  "A8 does NOT emit CHARON_RUN_RESULT=EXHAUSTED"   "$RUN_OUT" "CHARON_RUN_RESULT=EXHAUSTED"
not_has  "A9 does NOT announce a model attempt"           "$RUN_OUT" "attempt: charon/model-a"
not_has  "A10 does NOT announce STARTED on a model"       "$RUN_OUT" "STARTED on charon/"
LEDGER_A="$(cat "$CHARON_EXHAUST_LEDGER")"
not_has  "A11 ledger gets NO ALL-EXHAUSTED row"           "$LEDGER_A" "ALL-EXHAUSTED"
has      "A12 ledger records the prereq-missing fault"    "$LEDGER_A" "prereq-missing"
CAP_A="$(cat "$CAP_LOG")"
eq       "A13 ZERO scorecard captures enqueued"           "$(wc -l < "$CAP_LOG" | tr -d ' ')" "0"
not_has  "A14 no BLOCK verdict enqueued"                  "$CAP_A" "BLOCK"

echo
echo "=== B. RESTORED PATH: same invocation now succeeds ==="
: > "$CAP_LOG"
: > "$CHARON_EXHAUST_LEDGER"
OUT_B="$WORK/b.txt"
STUB_MODE=clean run_charon "$OUT_B" "$STUBBIN:$SANITIZED_PATH" "${MODELS[@]}"; RC_B=$?
echo "--- restored-PATH exit code: $RC_B"
eq       "B1 restored PATH exits 0 (red-proof: A's failure was the missing client)" "$RC_B" "0"
has      "B2 reports SUCCESS on the primary model"        "$RUN_OUT" "CHARON_RUN_RESULT=SUCCESS model=model-a"
not_has  "B3 no FATAL on the healthy path"                "$RUN_OUT" "FATAL"

echo
echo "=== C. \$HOME/.local/bin fallback resolves the client without .bashrc ==="
# Reproduces the FIX: a non-login shell has no ~/.local/bin on PATH, but the
# script appends it itself. Put the stub in the fake HOME's ~/.local/bin ONLY.
: > "$CAP_LOG"; : > "$CHARON_EXHAUST_LEDGER"
mkdir -p "$HOME/.local/bin"
cp "$STUBBIN/opencode" "$HOME/.local/bin/opencode"
OUT_C="$WORK/c.txt"
STUB_MODE=clean run_charon "$OUT_C" "$SANITIZED_PATH" "${MODELS[@]}"; RC_C=$?
eq       "C1 client found via the ~/.local/bin fallback (exit 0)" "$RC_C" "0"
has      "C2 succeeded on the primary model"              "$RUN_OUT" "CHARON_RUN_RESULT=SUCCESS model=model-a"

echo
echo "=== D. PATH fallback is APPEND-only: an explicit stub still wins ==="
# If ~/.local/bin were PREPENDED it would shadow a caller's deliberate stub /
# operator override — and would break every hermetic test in this suite.
: > "$CAP_LOG"; : > "$CHARON_EXHAUST_LEDGER"
cat > "$HOME/.local/bin/opencode" <<'EOF'
#!/usr/bin/env bash
echo "HOME-LOCAL-BIN-CLIENT-RAN"
exit 0
EOF
chmod +x "$HOME/.local/bin/opencode"
cat > "$STUBBIN/opencode" <<'EOF'
#!/usr/bin/env bash
echo "EXPLICIT-PATH-CLIENT-RAN"
case "${STUB_MODE:-clean}" in
  clean)     exit 0 ;;
  notfound)  exit 127 ;;
  noexec)    exit 126 ;;
  plainfail) exit 1 ;;
esac
EOF
chmod +x "$STUBBIN/opencode"
OUT_D="$WORK/d.txt"
STUB_MODE=clean run_charon "$OUT_D" "$STUBBIN:$SANITIZED_PATH" "${MODELS[@]}"; RC_D=$?
eq       "D1 exit 0"                                      "$RC_D" "0"
has      "D2 the EXPLICIT PATH client ran"                "$RUN_OUT" "EXPLICIT-PATH-CLIENT-RAN"
not_has  "D3 the ~/.local/bin client did NOT shadow it"   "$RUN_OUT" "HOME-LOCAL-BIN-CLIENT-RAN"
rm -f "$HOME/.local/bin/opencode"

echo
echo "=== E. CONTROL: a genuine rc=1 leg DOES enqueue a BLOCK ==="
# Non-vacuity anchor for F/G below: proves the capture recorder is live and
# that model-attributable failures are still charged to the model.
: > "$CAP_LOG"; : > "$CHARON_EXHAUST_LEDGER"
OUT_E="$WORK/e.txt"
STUB_MODE=plainfail run_charon "$OUT_E" "$STUBBIN:$SANITIZED_PATH" "${MODELS[@]}"; RC_E=$?
CAP_E="$(cat "$CAP_LOG")"
eq       "E1 chain genuinely exhausts (exit 3)"           "$RC_E" "3"
has      "E2 recorder IS live — rc=1 enqueues a BLOCK"    "$CAP_E" "BLOCK"
has      "E3 rc=1 classified model-attributable"          "$RUN_OUT" "not a limit, not an infra fault"
eq       "E4 one BLOCK per model in the chain"            "$(grep -c -- '--actual-verdict BLOCK' "$CAP_LOG" | tr -d ' ')" "4"

echo
echo "=== F. rc=127 MID-CHAIN is INFRA, never a model BLOCK ==="
: > "$CAP_LOG"; : > "$CHARON_EXHAUST_LEDGER"
OUT_F="$WORK/f.txt"
STUB_MODE=notfound run_charon "$OUT_F" "$STUBBIN:$SANITIZED_PATH" "${MODELS[@]}"; RC_F=$?
CAP_F="$(cat "$CAP_LOG")"; LEDGER_F="$(cat "$CHARON_EXHAUST_LEDGER")"
eq       "F1 chain still exhausts (exit 3)"               "$RC_F" "3"
has      "F2 rc=127 classified as infra fault"            "$RUN_OUT" "provider/local/infra FAULT (rc=127"
not_has  "F3 rc=127 NOT called model-attributable"        "$RUN_OUT" "not a limit, not an infra fault"
not_has  "F4 NO scorecard BLOCK enqueued for rc=127"      "$CAP_F" "BLOCK"
eq       "F5 ZERO captures at all for an rc=127 chain"    "$(wc -l < "$CAP_LOG" | tr -d ' ')" "0"
has      "F6 ledger row is infra-fault-failover"          "$LEDGER_F" "infra-fault-failover"
not_has  "F7 ledger does NOT record error-failover"       "$LEDGER_F" "error-failover"

echo
echo "=== F/2. THE WHOLE INFRA EXIT-CODE CLASS, not just rc=127 ==="
# An audit of the live ledger found 42 of 46 lifetime BLOCK enqueues were provably INFRA,
# because is_infra_fault() was a hand-extended list of magic numbers. One false BLOCK is
# already merged (model-scorecard.tsv:36, kimi-k2.6, rc=134 SIGABRT) and is at 33% routing
# block. Every code below must be classified infra and enqueue NOTHING.
#   2   client rejected OUR argv (argparse) — a launcher bug, never a model verdict
#   125 `timeout` itself failed internally
#   126 found but not executable   127 not found
#   128+N signal death: 130 SIGINT, 134 SIGABRT, 137 SIGKILL/OOM, 139 SIGSEGV, 143 SIGTERM
for code in 2 125 126 127 130 134 137 139 143; do
  : > "$CAP_LOG"; : > "$CHARON_EXHAUST_LEDGER"
  cat > "$STUBBIN/opencode" <<EOF
#!/usr/bin/env bash
exit $code
EOF
  chmod +x "$STUBBIN/opencode"
  OUT_CLS="$WORK/cls-$code.txt"
  run_charon "$OUT_CLS" "$STUBBIN:$SANITIZED_PATH" "${MODELS[@]}" >/dev/null 2>&1 || true
  CAP_CLS="$(cat "$CAP_LOG")"
  not_has "F2/$code classified INFRA — no scorecard BLOCK enqueued" "$CAP_CLS" "BLOCK"
done

echo
echo "=== F/3. rc=1 STAYS AMBIGUOUS: text-discriminated, never blanket-infra ==="
# A false INFRA is as damaging as a false BLOCK. rc=1 is BOTH "the model run failed"
# (a real verdict) and "auth rejected / cd into a reaped worktree" (infra), so it must be
# decided on this attempt's own output — never on the code alone.
rc1_case(){ # rc1_case <label> <stub-stderr-text> <expect BLOCK|NOBLOCK>
  : > "$CAP_LOG"; : > "$CHARON_EXHAUST_LEDGER"
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" %q >&2\nexit 1\n' "$2" > "$STUBBIN/opencode"
  chmod +x "$STUBBIN/opencode"
  run_charon "$WORK/rc1.txt" "$STUBBIN:$SANITIZED_PATH" "${MODELS[@]}" >/dev/null 2>&1 || true
  local cap; cap="$(cat "$CAP_LOG")"
  if [ "$3" = BLOCK ]; then has "$1" "$cap" "BLOCK"; else not_has "$1" "$cap" "BLOCK"; fi
}
# CONTROL (non-vacuity): a bare rc=1 with nothing infra in the tail is STILL the model's.
rc1_case "F3a bare rc=1 is still charged to the model (ambiguity not swallowed)" \
         "assertion failed: expected 1 got 2" BLOCK
rc1_case "F3b rc=1 + 401 is infra (auth), not a model verdict"      "HTTP 401 unauthorized" NOBLOCK
rc1_case "F3c rc=1 + 403 is infra (auth), not a model verdict"      "403 forbidden: invalid api key" NOBLOCK
rc1_case "F3d rc=1 + reaped-worktree cd is infra, not a model verdict" \
         "cd: /tmp/gone-worktree: No such file or directory" NOBLOCK


# F/2 and F/3 replaced the shared stub; restore the STUB_MODE one the later sections use.
cat > "$STUBBIN/opencode" <<'EOF'
#!/usr/bin/env bash
echo "EXPLICIT-PATH-CLIENT-RAN"
case "${STUB_MODE:-clean}" in
  clean)     exit 0 ;;
  notfound)  exit 127 ;;
  noexec)    exit 126 ;;
  plainfail) exit 1 ;;
esac
EOF
chmod +x "$STUBBIN/opencode"

echo
echo "=== G. rc=126 (found but not executable) is the same class ==="
: > "$CAP_LOG"; : > "$CHARON_EXHAUST_LEDGER"
OUT_G="$WORK/g.txt"
STUB_MODE=noexec run_charon "$OUT_G" "$STUBBIN:$SANITIZED_PATH" "${MODELS[@]}"; RC_G=$?
CAP_G="$(cat "$CAP_LOG")"
eq       "G1 chain exhausts (exit 3)"                     "$RC_G" "3"
has      "G2 rc=126 classified as infra fault"            "$RUN_OUT" "provider/local/infra FAULT (rc=126"
not_has  "G3 NO scorecard BLOCK enqueued for rc=126"      "$CAP_G" "BLOCK"

echo
echo "=== H. OPENCODE_BIN override is honoured (client is not hardwired) ==="
: > "$CAP_LOG"; : > "$CHARON_EXHAUST_LEDGER"
ALT="$WORK/alt-client"
cat > "$ALT" <<'EOF'
#!/usr/bin/env bash
echo "ALT-CLIENT-RAN"
exit 0
EOF
chmod +x "$ALT"
OUT_H="$WORK/h.txt"
OPENCODE_BIN="$ALT" run_charon "$OUT_H" "$SANITIZED_PATH" "${MODELS[@]}"; RC_H=$?
eq       "H1 absolute-path override passes preflight and runs (exit 0)" "$RC_H" "0"
has      "H2 the override client actually ran"            "$RUN_OUT" "ALT-CLIENT-RAN"
# …and a BOGUS override must fail preflight, not masquerade as exhaustion.
OUT_H2="$WORK/h2.txt"
OPENCODE_BIN="definitely-not-a-real-binary-xyz" run_charon "$OUT_H2" "$SANITIZED_PATH" "${MODELS[@]}"; RC_H2=$?
eq       "H3 bogus override exits 4, not 3"               "$RC_H2" "4"
has      "H4 bogus override names the binary it wanted"   "$RUN_OUT" "definitely-not-a-real-binary-xyz"
not_has  "H5 bogus override does not claim exhaustion"    "$RUN_OUT" "ALL MODELS EXHAUSTED"

echo
echo "=== I. fleet-droid.sh preflights its OWN externals (git/gh/python3) ==="
# The launcher shells out to git and gh; gh ALSO lives in ~/.local/bin, so the
# identical non-login-shell fault silently breaks PR publication.
DROID_OUT="$(PATH="/usr/bin:/bin" HOME="$WORK/emptyhome" \
  bash "$FLEET_DIR/fleet-droid.sh" strong --wait 0 2>&1)"
DROID_RC=$?
has      "I1 launcher preflight names a missing binary"   "$DROID_OUT" "required binary not found"
has      "I2 launcher preflight names gh"                 "$DROID_OUT" "gh"
has      "I3 launcher says LOCAL ENVIRONMENT fault"       "$DROID_OUT" "LOCAL ENVIRONMENT fault"
eq       "I4 launcher exits with the distinct prereq code" "$DROID_RC" "4"

echo
echo "=== J/K/L. GATEWAY + TOKEN PREFLIGHT (pre-claim) ==="
# INSTANCE 2 of the same class: the launcher trusted the ambient shell for the gateway
# bearer token. A PowerShell-invoked non-interactive bash inherited none, so
# capability/availability.py's unauthenticated GET /charon/status came back 302 with a
# ZERO-BYTE body -> json.loads("") -> "Expecting value: line 1 column 1 (char 0)". The
# capped-filter then failed closed and DETAINED the ticket — correct in itself, but it
# fired PER TICKET and quarantined FIVE tickets before the operator killed the tab.
#
# ISOLATION: these legs run fleet-droid.sh against a full COPY of fleet/ with an EMPTY
# board and EMPTY claim state, so a run that gets past the preflight claims nothing and
# stands down. "Zero tickets claimed" is then a MEASURED fact (state/claims stays empty),
# not an assumption — and no real board/claim/quarantine state is ever touched.
FLEETCOPY="$WORK/fleetcopy"
cp -a "$FLEET_DIR" "$FLEETCOPY"
rm -rf "$FLEETCOPY/board" "$FLEETCOPY/state/claims" "$FLEETCOPY/state/loop-guard"
mkdir -p "$FLEETCOPY/board" "$FLEETCOPY/state/claims"

# opencode.json the token is DERIVED from (env-registry.sh:bearer_token reads this).
GOOD_TOK="derived-token-from-opencode-json"
CFG="$WORK/opencode.json"
cat > "$CFG" <<EOF
{"provider": {"charon": {"options": {"apiKey": "$GOOD_TOK"}}}}
EOF

# Fake gateway. MODE_FILE switches behaviour per request; AUTH_FILE records the exact
# Authorization header seen, which is how we PROVE which token was actually sent.
MODE_FILE="$WORK/gw-mode"; AUTH_FILE="$WORK/gw-auth"; PORT_FILE="$WORK/gw-port"
cat > "$WORK/fakegw.py" <<'PY'
import http.server, json, sys
MODE_FILE, AUTH_FILE, PORT_FILE = sys.argv[1], sys.argv[2], sys.argv[3]
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        with open(AUTH_FILE, "w") as f:
            f.write(self.headers.get("Authorization", "") + "\n")
        mode = open(MODE_FILE).read().strip()
        if mode == "redirect-empty":
            # EXACT real-world signature: 302, zero-byte body, no Location followed.
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps({"pools": {}, "providers": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
with open(PORT_FILE, "w") as f:
    f.write(str(srv.server_port))
srv.serve_forever()
PY
echo "redirect-empty" > "$MODE_FILE"
python3 "$WORK/fakegw.py" "$MODE_FILE" "$AUTH_FILE" "$PORT_FILE" &
GW_PID=$!
trap 'kill "$GW_PID" 2>/dev/null; rm -rf "$WORK"' EXIT
for _ in $(seq 1 50); do [ -s "$PORT_FILE" ] && break; sleep 0.1; done
GW_PORT="$(cat "$PORT_FILE" 2>/dev/null)"
if [ -z "$GW_PORT" ]; then bad "J0 fake gateway failed to start — cannot red-proof"; else
ok "J0 fake gateway up on 127.0.0.1:$GW_PORT"

run_droid(){ # run_droid <gateway-url> <token-env> <cfg> -> echoes rc; sets DR_OUT
  local url="$1" tokenv="$2" cfg="$3"
  DR_OUT="$(CHARON_GATEWAY_URL="$url" CHARON_GATEWAY_TOKEN="$tokenv" \
            CHARON_OPENCODE_CONFIG="$cfg" \
            bash "$FLEETCOPY/fleet-droid.sh" strong --wait 0 2>&1)"
  return $?
}
claims_count(){ find "$FLEETCOPY/state/claims" -type f 2>/dev/null | wc -l | tr -d ' '; }

echo "--- J. gateway answers 302 with a 0-byte body (the real signature) ---"
echo "redirect-empty" > "$MODE_FILE"
run_droid "http://127.0.0.1:$GW_PORT" "" "$CFG"; RC_J=$?
echo "--- 302/empty-body exit code: $RC_J"
eq       "J1 stands down with the DISTINCT gateway code (not 0, not 4)" "$RC_J" "5"
has      "J2 FATAL names /charon/status as unreadable"    "$DR_OUT" "gateway /charon/status is NOT READABLE"
has      "J3 FATAL states ZERO tickets were claimed"      "$DR_OUT" "ZERO tickets were claimed"
has      "J4 FATAL explains the 302/0-byte signature"     "$DR_OUT" "0-byte body"
has      "J5 FATAL gives the remedy (opencode.json path)" "$DR_OUT" "opencode.json"
# THE EXPENSIVE HALF OF THE BUG: it must not claim -> detain -> re-claim -> quarantine.
not_has  "J6 never reached the claim loop (no droid-up banner)" "$DR_OUT" "charon-fleet droid up"
not_has  "J7 no per-ticket detain fired"                  "$DR_OUT" "CAPPED-FILTER-UNAVAILABLE"
eq       "J8 MEASURED: zero tickets claimed"              "$(claims_count)" "0"

echo "--- K. unreachable gateway (nothing listening) ---"
run_droid "http://127.0.0.1:1" "" "$CFG"; RC_K=$?
eq       "K1 unreachable gateway also exits 5"            "$RC_K" "5"
eq       "K2 MEASURED: still zero tickets claimed"        "$(claims_count)" "0"

echo "--- L. readable gateway: preflight passes and the loop is reached ---"
echo "ok" > "$MODE_FILE"
: > "$AUTH_FILE"
run_droid "http://127.0.0.1:$GW_PORT" "" "$CFG"; RC_L=$?
echo "--- readable-gateway exit code: $RC_L"
if [ "$RC_L" -eq 5 ]; then bad "L1 readable gateway must NOT exit 5 (red-proof broken)"; else ok "L1 readable gateway does not trip the preflight (rc=$RC_L)"; fi
not_has  "L2 no gateway FATAL on the healthy path"        "$DR_OUT" "NOT READABLE"
has      "L3 reached the claim loop (droid-up banner)"    "$DR_OUT" "charon-fleet droid up"
has      "L4 token was DERIVED from opencode.json, not the empty env" \
         "$(cat "$AUTH_FILE")" "Bearer $GOOD_TOK"

echo "--- M. shell token is STALE: derived value wins, drift reported ---"
: > "$AUTH_FILE"
run_droid "http://127.0.0.1:$GW_PORT" "stale-shell-token-do-not-use" "$CFG"; RC_M=$?
has      "M1 drift is reported loudly"                    "$DR_OUT" "gateway-token-drift"
has      "M2 says it prefers the derived token"           "$DR_OUT" "PREFERRING THE DERIVED TOKEN"
has      "M3 the DERIVED token is what actually went out" "$(cat "$AUTH_FILE")" "Bearer $GOOD_TOK"
not_has  "M4 the stale shell token never reached the gateway" "$(cat "$AUTH_FILE")" "stale-shell-token-do-not-use"

echo "--- M/2. a STALE shell token gets the SAME 302 as no token (must still trip) ---"
# Dogfooded fact: no token -> 302/0-byte; STALE token -> 302/0-byte; correct token -> 200 JSON.
# So the preflight must key on "is the body parseable JSON", NEVER on a status code — a check
# written as `== 401` misses this entirely, and a check that DEFERS to the shell var (rather than
# overwriting it) leaves the bug fully intact. Both are pinned here.
echo "redirect-empty" > "$MODE_FILE"
run_droid "http://127.0.0.1:$GW_PORT" "stale-shell-token-do-not-use" "$CFG"; RC_M2=$?
eq       "M5 stale shell token + 302/0-byte still exits 5" "$RC_M2" "5"
not_has  "M6 preflight never claims this was a 401"       "$DR_OUT" "401"
eq       "M7 MEASURED: zero tickets claimed"              "$(claims_count)" "0"

echo "--- N. no token derivable anywhere -> fail loud, claim nothing ---"
echo '{"provider": {}}' > "$WORK/empty-opencode.json"
echo "redirect-empty" > "$MODE_FILE"
run_droid "http://127.0.0.1:$GW_PORT" "" "$WORK/empty-opencode.json"; RC_N=$?
eq       "N1 exits 5"                                     "$RC_N" "5"
has      "N2 says no token could be derived"              "$DR_OUT" "no token could be derived"
eq       "N3 MEASURED: zero tickets claimed"              "$(claims_count)" "0"
fi

echo "--- O. source pins: the two shapes that silently re-break this ---"
# O1/O2 are TEXT pins, deliberately. The remediation string is only emitted from a mid-run
# CAPPED-FILTER-UNAVAILABLE path that would cost a full claim+detain cycle to trigger, and the
# regression it guards is the WORDING itself: the old text advised "Export a gateway token",
# which is the action that CAUSED the outage (availability.py PREFERS the env var, and a stale
# value yields the identical 302/0-byte answer as no value at all).
DROID_SRC="$(cat "$FLEET_DIR/fleet-droid.sh")"
not_has  "O1 remediation no longer advises exporting a token" "$DROID_SRC" "Export a gateway token"
has      "O2 remediation points at re-deriving from opencode config" "$DROID_SRC" "RE-DERIVE it from"
# O3: the export must OVERWRITE the (documented-stale) shell value, never defer to it. A
# `${CHARON_GATEWAY_TOKEN:-$_derived_tok}` shape would make the whole fix a no-op.
has      "O3 token export is an unconditional overwrite"  "$DROID_SRC" 'export CHARON_GATEWAY_TOKEN="$_derived_tok"'
not_has  "O4 no defer-to-stale-var shape"                 "$DROID_SRC" 'CHARON_GATEWAY_TOKEN:-$_derived_tok'

echo
echo "=========================================="
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
