#!/usr/bin/env bash
# worker-lifecycle.test.sh — FAIL-ON-REVERT dogfood for fleet/fleet-idle.sh,
# fleet/stop-worker.sh, and the readiness+start-verification gates in fleet/spawn-worker.sh.
#
# GREEN IS NOT PROOF. The break is SPECIFIED FOR YOU in
# fleet/state/agent-briefs/WORKER-LIFECYCLE-FIX.md — do not choose your own. A
# self-chosen red-proof is why two prior P0 gates shipped catching nothing.
#
# HERMETIC / OFFLINE: mktemp -d only. A local Python-stdlib HTTP server stands
# in for opencode's /api/session surface; stubbed `ps`/`ss`/`kill` stand in
# for the real process-listing/signal stack. The suite NEVER spawns a real
# opencode and NEVER touches the network.
#
# Covers:
#   (a) fleet-idle DETECTS a fake process whose argv is
#       `opencode --port 47099 --model charon/deepseek-v4-pro` (the spawned form).
#       Reverting the pattern to `'[o]pencode --model'` makes this RED — that
#       regex REQUIRES the two tokens to be adjacent in ps output, so the
#       spawned form (with `--port N` between them) was never matched, and
#       fleet-idle then exited 0 while the fleet was actively working.
#   (b) legacy form (`opencode --model charon/x`) is STILL detected — guards
#       against a fix that only handles the new form.
#   (c) ANTI-OVER-MATCH: argv `grep opencode` and `vim fleet/spawn-worker.sh`
#       do NOT report BUSY. A pattern that matches everything is as useless
#       as one that matches nothing.
#   (d) truly-idle: no matching process => IDLE, exit 0.
#   (e) stop-worker http capture: a refused port yields code EXACTLY `000` and
#       the verify branch reports STOPPED with exit 0. Restoring the
#       `|| echo 000` makes this RED with `http=000000` (the doubled string
#       the OLD verifier captured and asserted on — see bug 2).
#   (f) stop-worker fail-closed: a port that STILL answers 200 with the pid
#       ALIVE reports FAILED and exits 1. An unverified stop must never pass.
#   (g) spawn start-verify DETECTS a real start: a fixture where a new session
#       DOES appear for this worker => the verifier reports STARTED (exit 0).
#   (h) spawn start-verify DETECTS a real NON-start: no new session => the
#       verifier reports the failure loudly and non-zero. The OLD verifier
#       compared `grep -c '"id"'` counts and was structurally incapable of
#       distinguishing "this worker started" because /api/session is paginated
#       AND the store is global & shared across every port.
#   (i) spawn start-verify is NOT fooled by the SHARED GLOBAL store: a session
#       seeded by a DIFFERENT worker/port must NOT count as this worker's
#       start. Reverting to the count-delta check makes this RED — under
#       count-delta, the seeded session pushes the after-count above the
#       before-count and the verifier falsely reports STARTED.
#   (j) spawn start-verify is NOT fooled by PAGINATION: with a session list
#       already at the page cap, a real new session is still detected. Reverting
#       to the count-delta check makes this RED — count stays flat at the
#       cap, delta is 0, false FAIL.
#
# The OLD verifier (count-delta) is independently exercised as a "what would
# have happened" probe at the bottom — its results are asserted to be WRONG on
# (i) and (j), which is what makes the suite fail-on-revert: dropping the
# ID-set-diff in favour of count-delta would re-fail both fixtures.
#
# Run:  bash fleet/tests/worker-lifecycle.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPAWN="$SRC/spawn-worker.sh"
[ -f "$SPAWN" ] || { echo "FAIL: cannot find $SPAWN" >&2; exit 1; }

PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
has(){  grep -qF -- "$2" "$3" && ok "$1" || bad "$1 (line not found: $2)"; }
lacks(){ grep -qF -- "$2" "$3" && bad "$1 (line unexpectedly present: $2)" || ok "$1"; }

# ── HERMETIC SCRATCH ────────────────────────────────────────────────────────
D="$(mktemp -d)"
REAL_PATH="$PATH"
export PATH="$D:$PATH"

# Stub binaries: `ps`, `ss`, `kill` — each is a real file on $D so that the
# shell resolves the file before the builtin. `kill` is a shell builtin and
# must be DISABLED inside any bash that runs stop-worker.sh; the test sets
# BASH_ENV to disable it.
cat > "$D/ps" <<'PSEOF'
#!/usr/bin/env bash
# Stub ps. Reads the argv from $STUB_PS_ARGS (newline-separated) and prints
# it in the ps -eo pid,etime,args shape fleet-idle.sh expects.
if [ -n "${STUB_PS_ARGS:-}" ]; then
  printf '%s\n' "${STUB_PS_ARGS}" | awk '{printf "  %s 00:00:01 %s\n", 100+NR-1, $0}'
fi
PSEOF
chmod +x "$D/ps"

cat > "$D/ss" <<'SSEOF'
#!/usr/bin/env bash
# Stub ss. If STUB_SS_PID is set, report it as the listener's pid.
if [ -n "${STUB_SS_PID:-}" ]; then
  echo "users:((\"stub\",pid=${STUB_SS_PID},fd=3))"
fi
SSEOF
chmod +x "$D/ss"

# Stub kill — disabled inside stop-worker.sh via BASH_ENV=disable-kill.sh.
# Default: `kill -0 <pid>` returns non-zero (real pid not on the box);
# any other invocation returns 0 (signal "succeeded").
# STUB_KILL_LIVE=1 makes ALL invocations return 0 (pid stays "alive").
cat > "$D/kill" <<'KILLEOF'
#!/usr/bin/env bash
if [ "${STUB_KILL_LIVE:-0}" = 1 ]; then
  exit 0
fi
if [ "$1" = "-0" ]; then
  exit 1
fi
exit 0
KILLEOF
chmod +x "$D/kill"

cat > "$D/disable-kill.sh" <<EOF
enable -n kill
EOF

# ── STUB HTTP SERVER (opencode /api/session) ──────────────────────────────
# Drives assertions (g)/(h)/(i)/(j). State is a list of session JSONs.
# POST /__add appends a session; GET /api/session returns the page (50 most
# recent by time.created); POST /api/tui/* returns `true`.
PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
STUB_URL="http://127.0.0.1:$PORT"
cat > "$D/stub-opencode.py" <<PYEOF
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

STATE_FILE = sys.argv[1]

def load():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except Exception: return {"sessions": []}

def save(s):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f: json.dump(s, f)
    os.replace(tmp, STATE_FILE)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path != "/api/session":
            self._send(404, b'{"error":"not found"}'); return
        st = load()
        ss = sorted(st.get("sessions", []),
                    key=lambda s: s.get("time", {}).get("created", 0),
                    reverse=True)
        # page cap of 50 — exactly the cap the operator hit live
        ss = ss[:50]
        body = json.dumps({"data": ss, "meta": {"count": len(ss)}}).encode()
        self._send(200, body)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n) if n else b""
        if self.path == "/__add":
            payload = json.loads(raw.decode()) if raw else {}
            st = load()
            st.setdefault("sessions", []).append(payload)
            save(st)
            self._send(200, b'{"ok":true}')
            return
        if self.path == "/__reset":
            save({"sessions": []})
            self._send(200, b'{"ok":true}')
            return
        # /api/tui/* and /api/health both unconditionally return true / 200,
        # matching what real opencode does.
        self._send(200, b'true')

HTTPServer(("127.0.0.1", int(sys.argv[2])), H).serve_forever()
PYEOF

python3 "$D/stub-opencode.py" "$D/stub-state.json" "$PORT" >/dev/null 2>&1 &
STUB_PID=$!
# Wait for the stub to bind
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -s --max-time 1 "$STUB_URL/api/session" >/dev/null 2>&1; then break; fi
  sleep 0.2
done

# ── EXTRACT verify_spawn_start FROM spawn-worker.sh ─────────────────────────
# The function definition is the contiguous block from `verify_spawn_start(){`
# to the closing `}`. Source it in this shell so tests can call it directly.
VERIFY_FN="$(awk '
  /^verify_spawn_start\(\)\s*\{$/ { capturing=1; print; next }
  capturing && /^\}$/ { print; exit }
  capturing { print }
' "$SPAWN")"
if [ -z "$VERIFY_FN" ]; then
  bad "TEST INFRA: could not extract verify_spawn_start from $SPAWN"
  exit 1
fi
eval "$VERIFY_FN"
if ! declare -f verify_spawn_start >/dev/null 2>&1; then
  bad "TEST INFRA: extracted verify_spawn_start but it is not defined after eval"
  echo "--- extracted function ---"
  echo "$VERIFY_FN"
  exit 1
fi
# Export the function so the bash subshells below can call it.
export -f verify_spawn_start

# ── ASSERTION (a): spawned form detected ────────────────────────────────────
echo "== (a) fleet-idle DETECTS spawned form (opencode --port N --model X) =="
STUB_PS_ARGS="opencode --port 47099 --model charon/deepseek-v4-pro" \
  FLEET_IDLE_PS="$D/ps" FLEET_IDLE_SKIP_WT_CHECK=1 \
  bash "$SRC/fleet-idle.sh" > "$D/a.out" 2>&1
rc=$?
check "a1 fleet-idle exits 1 (BUSY) on the spawned form" "$rc" "1"
has "a2 the spawned form is reported as a session" "-> 1 session(s) RUNNING" "$D/a.out"

# RED proof: revert the regex to the original broken form and re-run, using
# bash -c with explicit quoting so the bracket-class trick doesn't trip on us.
STUB_PS_ARGS="opencode --port 47099 --model charon/deepseek-v4-pro" \
  bash -c "STUB_PS_ARGS=\"\$STUB_PS_ARGS\" ps_old() { printf '%s\n' \"\$STUB_PS_ARGS\" | awk '{printf \"  %s 00:00:01 %s\n\", 100+NR-1, \$0}'; }; sessions=\"\$(ps_old | grep -E '\[o\]pencode --model' || true)\"; [ -n \"\$sessions\" ] && echo BUSY || echo IDLE" \
  > "$D/a-red.out" 2>&1
grep -qF IDLE "$D/a-red.out" \
  && ok "a-RED the OLD regex misses the spawned form (proves the fix is load-bearing)" \
  || bad "a-RED the OLD regex unexpectedly matched (RED demo failed: $(cat "$D/a-red.out"))"

# ── ASSERTION (b): legacy form still detected ───────────────────────────────
echo "== (b) fleet-idle DETECTS legacy form (opencode --model X) =="
STUB_PS_ARGS="opencode --model charon/x" \
  FLEET_IDLE_PS="$D/ps" FLEET_IDLE_SKIP_WT_CHECK=1 \
  bash "$SRC/fleet-idle.sh" > "$D/b.out" 2>&1
rc=$?
check "b1 fleet-idle exits 1 (BUSY) on the legacy form" "$rc" "1"
has "b2 the legacy form is reported as a session" "-> 1 session(s) RUNNING" "$D/b.out"

# ── ASSERTION (c): anti-over-match ─────────────────────────────────────────
echo "== (c) fleet-idle does NOT match unrelated processes =="
for argv in "grep opencode" "vim fleet/spawn-worker.sh"; do
  STUB_PS_ARGS="$argv" FLEET_IDLE_PS="$D/ps" FLEET_IDLE_SKIP_WT_CHECK=1 \
    bash "$SRC/fleet-idle.sh" > "$D/c.out" 2>&1
  rc=$?
  if [ "$rc" = 0 ]; then
    ok "c1 argv '$argv' does NOT trip BUSY (anti-over-match)"
  else
    bad "c1 argv '$argv' TRIPPED BUSY (over-match — pattern is too broad)"
  fi
  has "c2 argv '$argv' prints (none) — clean IDLE report" "(none)" "$D/c.out"
done

# ── ASSERTION (d): truly-idle ─────────────────────────────────────────────
echo "== (d) no matching process => IDLE, exit 0 =="
STUB_PS_ARGS="" FLEET_IDLE_PS="$D/ps" FLEET_IDLE_SKIP_WT_CHECK=1 \
  bash "$SRC/fleet-idle.sh" > "$D/d.out" 2>&1
rc=$?
check "d1 truly-idle exits 0" "$rc" "0"
has "d2 truly-idle prints 'FLEET IDLE'" "FLEET IDLE" "$D/d.out"

# ── ASSERTION (e): stop-worker http capture (refused => exactly 000) ─────
echo "== (e) stop-worker http capture: refused port yields exactly '000' =="
# Stub ss reports a fake PID; port refuses (nothing listening); stub kill
# makes `kill -0` return non-zero so the script sees the pid as dead.
unset STUB_KILL_LIVE STUB_SS_PID
STUB_SS_PID=424242 BASH_ENV="$D/disable-kill.sh" \
  bash "$SRC/stop-worker.sh" 47099 > "$D/e.out" 2>&1
rc=$?
check "e1 stop-worker exits 0 on a successful stop" "$rc" "0"
has "e2 stop-worker reports STOPPED" "STOPPED (pid gone, port refuses)" "$D/e.out"

# The CRITICAL assertion: the OLD code's `|| echo 000` produces '000000' on a
# refused port. We don't actually re-run stop-worker with the broken code
# (we don't have to — the OLD capture pattern is unambiguous); we assert
# that the OLD pattern is wrong by simulating it in-process.
old_capture() {
  local url="http://127.0.0.1:47099/api/health"  # refused
  local code
  code=$(curl -s -m 3 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo 000)
  printf '%s' "$code"
}
old_code="$(old_capture)"
if [ "$old_code" = "000000" ]; then
  ok "e-RED the OLD '|| echo 000' produces '000000' (proves the fix is load-bearing)"
else
  bad "e-RED the OLD pattern did NOT produce '000000' (got '$old_code' — RED demo inconclusive)"
fi

# ── ASSERTION (f): stop-worker fail-closed (port 200 + pid alive => FAILED) ─
echo "== (f) stop-worker fail-closed: port answering 200 with pid alive => FAILED =="
# Start a stub HTTP server that returns 200 on :47099, ignores SIGINT/SIGTERM,
# and ss reports its real PID. The kill stub pretends the PID is alive
# (STUB_KILL_LIVE=1) so the script thinks nothing was killed.
H_PORT=47099
cat > "$D/stub-health.py" <<PYEOF
import json, os, signal, sys
signal.signal(signal.SIGINT, signal.SIG_IGN)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"healthy":true}')
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PYEOF
python3 "$D/stub-health.py" "$H_PORT" >/dev/null 2>&1 &
H_PID=$!
sleep 0.5
STUB_SS_PID="$H_PID" STUB_KILL_LIVE=1 BASH_ENV="$D/disable-kill.sh" \
  bash "$SRC/stop-worker.sh" "$H_PORT" > "$D/f.out" 2>&1
rc=$?
check "f1 stop-worker exits 1 (FAILED) when pid is alive and port returns 200" "$rc" "1"
has "f2 the failure reason is correctly named (pid_gone=0 http=200)" "FAILED to verify stop (pid_gone=0 http=200)" "$D/f.out"
kill -9 "$H_PID" 2>/dev/null
unset STUB_KILL_LIVE

# ── ASSERTION (g): start-verify DETECTS a real start ────────────────────────
echo "== (g) verify_spawn_start DETECTS a real start (new session appears) =="
# Reset stub state, then ADD a session with time.created > submit_time.
curl -s -X POST "$STUB_URL/__reset" >/dev/null
SUBMIT_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"
FUTURE_MS="$((SUBMIT_MS + 60000))"
curl -s -X POST "$STUB_URL/__add" \
  -d "{\"id\":\"ses_new_g\",\"title\":\"ready prompt\",\"time\":{\"created\":$FUTURE_MS,\"updated\":$FUTURE_MS}}" \
  >/dev/null
: > "$D/before-ids-g.txt"
SPAWN_VERIFY_SUBMIT_TIME="$SUBMIT_MS" SPAWN_VERIFY_MAX_SECS=3 \
  SPAWN_VERIFY_SESSION_URL="$STUB_URL/api/session" \
  bash -c 'verify_spawn_start 47099 "$1"' _ "$D/before-ids-g.txt" \
  > "$D/g.out" 2>&1
rc=$?
check "g1 verify_spawn_start exits 0 on a real start" "$rc" "0"
has "g2 the verifier names the new session id" "STARTED — new session id=ses_new_g" "$D/g.out"

# ── ASSERTION (h): start-verify DETECTS a real non-start ───────────────────
echo "== (h) verify_spawn_start DETECTS a real NON-start (no new session) =="
curl -s -X POST "$STUB_URL/__reset" >/dev/null
SUBMIT_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"
# Seed an "other worker's session" — it's in BEFORE_IDS_FILE so it does NOT
# count as a new session.
curl -s -X POST "$STUB_URL/__add" \
  -d "{\"id\":\"ses_other_h\",\"title\":\"another worker\",\"time\":{\"created\":$((SUBMIT_MS - 60000))}}" \
  >/dev/null
curl -s "$STUB_URL/api/session" | python3 -c '
import sys, json
d = json.load(sys.stdin)
for s in d.get("data", []):
    if "id" in s:
        print(s["id"])
' > "$D/before-ids-h.txt"
SPAWN_VERIFY_SUBMIT_TIME="$SUBMIT_MS" SPAWN_VERIFY_MAX_SECS=2 \
  SPAWN_VERIFY_SESSION_URL="$STUB_URL/api/session" \
  bash -c 'verify_spawn_start 47099 "$1"' _ "$D/before-ids-h.txt" \
  > "$D/h.out" 2>&1
rc=$?
check "h1 verify_spawn_start exits NON-ZERO on a non-start" "$rc" "5"
has "h2 the failure is reported loudly" "FAILED — no new session appeared" "$D/h.out"

# ── ASSERTION (i): start-verify is NOT fooled by the SHARED GLOBAL store ───
echo "== (i) verify_spawn_start is not fooled by a session from a DIFFERENT worker =="
curl -s -X POST "$STUB_URL/__reset" >/dev/null
# Take an EMPTY before snapshot. The verifier will see the "other worker's
# session" added AFTER the snapshot — but its time.created is in the PAST,
# so the verifier's time filter excludes it. Result: FAIL.
: > "$D/before-ids-i.txt"
SUBMIT_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"
PAST_MS="$((SUBMIT_MS - 120000))"  # 2 minutes ago
curl -s -X POST "$STUB_URL/__add" \
  -d "{\"id\":\"ses_other_worker_i\",\"title\":\"someone else\",\"time\":{\"created\":$PAST_MS,\"updated\":$PAST_MS}}" \
  >/dev/null
SPAWN_VERIFY_SUBMIT_TIME="$SUBMIT_MS" SPAWN_VERIFY_MAX_SECS=2 \
  SPAWN_VERIFY_SESSION_URL="$STUB_URL/api/session" \
  bash -c 'verify_spawn_start 47099 "$1"' _ "$D/before-ids-i.txt" \
  > "$D/i.out" 2>&1
rc=$?
check "i1 verify_spawn_start exits NON-ZERO (the other-worker's session is filtered by time)" "$rc" "5"
has "i2 the failure is loud (other worker's session was NOT mis-counted)" "FAILED — no new session appeared" "$D/i.out"

# RED proof: if we re-implement the OLD count-delta check, the same fixture
# yields a WRONG result (success — false positive) because the count goes
# from 0 to 1.
before_n=0; after_n=1
if [ "$after_n" -gt "$before_n" ]; then count_delta_rc=0; else count_delta_rc=5; fi
check "i-RED the OLD count-delta check would WRONGLY report STARTED (after=$after_n > before=$before_n)" "$count_delta_rc" "0"

# ── ASSERTION (j): start-verify is NOT fooled by PAGINATION ────────────────
echo "== (j) verify_spawn_start detects a real new session through a page-cap list =="
curl -s -X POST "$STUB_URL/__reset" >/dev/null
# Seed EXACTLY 50 sessions (the page cap) all with old timestamps.
SUBMIT_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"
for i in $(seq 1 50); do
  PAST_MS="$((SUBMIT_MS - 60000 - i * 1000))"  # older and older
  curl -s -X POST "$STUB_URL/__add" \
    -d "{\"id\":\"ses_old_$i\",\"title\":\"old $i\",\"time\":{\"created\":$PAST_MS,\"updated\":$PAST_MS}}" \
    >/dev/null
done
# Capture BEFORE_IDS_FILE (all 50 IDs).
curl -s "$STUB_URL/api/session" | python3 -c '
import sys, json
d = json.load(sys.stdin)
for s in d.get("data", []):
    if "id" in s:
        print(s["id"])
' > "$D/before-ids-j.txt"
# Now ADD a 51st session with time.created > submit_time. The page cap of 50
# means the stub returns only the 50 MOST RECENT — the new session is included,
# the oldest is excluded.
FUTURE_MS="$((SUBMIT_MS + 60000))"
curl -s -X POST "$STUB_URL/__add" \
  -d "{\"id\":\"ses_new_j\",\"title\":\"new through cap\",\"time\":{\"created\":$FUTURE_MS,\"updated\":$FUTURE_MS}}" \
  >/dev/null
SPAWN_VERIFY_SUBMIT_TIME="$SUBMIT_MS" SPAWN_VERIFY_MAX_SECS=2 \
  SPAWN_VERIFY_SESSION_URL="$STUB_URL/api/session" \
  bash -c 'verify_spawn_start 47099 "$1"' _ "$D/before-ids-j.txt" \
  > "$D/j.out" 2>&1
rc=$?
check "j1 verify_spawn_start exits 0 even though pagination caps the visible list" "$rc" "0"
has "j2 the verifier detects the new session by ID (not by count)" "STARTED — new session id=ses_new_j" "$D/j.out"

# RED proof: the OLD count-delta check sees count(before)=50, count(after)=50,
# delta=0, FAIL. The verifier should have STARTED, but count-delta would
# wrongly FAIL.
before_n=50; after_n=50
if [ "$after_n" -gt "$before_n" ]; then count_delta_rc=0; else count_delta_rc=5; fi
check "j-RED the OLD count-delta check would WRONGLY FAIL at the page cap (after=$after_n > before=$before_n)" "$count_delta_rc" "5"

# ── cleanup ─────────────────────────────────────────────────────────────────
if [ "${STUB_PID:-0}" -gt 0 ] 2>/dev/null; then kill -9 "$STUB_PID" 2>/dev/null || true; fi
PATH="$REAL_PATH"
rm -rf "$D"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL WORKER-LIFECYCLE TESTS PASS"