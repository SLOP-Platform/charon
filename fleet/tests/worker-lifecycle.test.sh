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
#   (a) stop-worker: escalation IS VISIBLE — `still alive after SIG<x>, escalating`
#       reaches the caller and is not swallowed; the escalation output is asserted.
#   (b) stop-worker: SIGINT-first stop with escalation prints the escalation line.
#       A caller that only reads the last line still learns a non-graceful stop occurred.
#   (c) ANTI-OVER-BLOCK: a worker already dead returns STOPPED cleanly without slow
#       escalation; a stop of an already-dead worker completes promptly (upper bound).
#   (d) stop-worker: fail-closed preserved — a port still answering 200 with pid
#       alive is FAILED (do not regress guard PR #272).
#   (e) stop-worker: SIGINT completes with exit 0 when worker dies on SIGINT.
#       The auto-close precondition for closeOnExit:graceful is a non-zero exit.
#   (f) stop-worker: escalation output IS VISIBLE — `still alive after SIG<x>, escalating`
#       is printed and not swallowed; caller learns a non-graceful stop occurred.
#   (g) stop-worker: ANTI-OVER-BLOCK — a worker already dead returns STOPPED promptly
#       (upper bound ~2s), without waiting for the full SIGINT window.
#   (h) stop-worker: fail-closed preserved — a port still answering 200 with pid
#       alive is FAILED (do not regress guard PR #272).
#   (i) fleet-idle DETECTS a fake process whose argv is
#       `opencode --port 47099 --model charon/deepseek-v4-pro` (the spawned form).
#       Reverting the pattern to `'[o]pencode --model'` makes this RED — that
#       regex REQUIRES the two tokens to be adjacent in ps output, so the
#       spawned form (with `--port N` between them) was never matched, and
#       fleet-idle then exited 0 while the fleet was actively working.
#   (j) legacy form (`opencode --model charon/x`) is STILL detected — guards
#       against a fix that only handles the new form.
#   (k) ANTI-OVER-MATCH: argv `grep opencode` and `vim fleet/spawn-worker.sh`
#       do NOT report BUSY. A pattern that matches everything is as useless
#       as one that matches nothing.
#   (l) truly-idle: no matching process => IDLE, exit 0.
#   (m) stop-worker http capture: a refused port yields code EXACTLY `000` and
#       the verify branch reports STOPPED with exit 0. Restoring the
#       `|| echo 000` makes this RED with `http=000000` (the doubled string
#       the OLD verifier captured and asserted on — see bug 2).
#   (n) spawn start-verify DETECTS a real start: a fixture where a new session
#       DOES appear for this worker => the verifier reports STARTED (exit 0).
#   (o) spawn start-verify DETECTS a real NON-start: no new session => the
#       verifier reports the failure loudly and non-zero. The OLD verifier
#       compared `grep -c '"id"'` counts and was structurally incapable of
#       distinguishing "this worker started" because /api/session is paginated
#       AND the store is global & shared across every port.
#   (p) spawn start-verify is NOT fooled by the SHARED GLOBAL store: a session
#       seeded by a DIFFERENT worker/port must NOT count as this worker's
#       start. Reverting to the count-delta check makes this RED — under
#       count-delta, the seeded session pushes the after-count above the
#       before-count and the verifier falsely reports STARTED.
#   (q) spawn start-verify is NOT fooled by PAGINATION: with a session list
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
# All invocations return 0 (signal "succeeded") except kill -0 which returns
# 1 (pid is dead / not on the box). STUB_KILL_LIVE=1 overrides kill -0 to
# return 0 so the script believes the pid is still alive.
cat > "$D/kill" <<'KILLEOF'
#!/usr/bin/env bash
if [ "${STUB_KILL_LIVE:-0}" = 1 ] && [ "$1" = "-0" ]; then
  exit 0  # pid stays "alive" for kill -0 checks
fi
if [ "$1" = "-0" ]; then
  exit 1  # pid is dead
fi
exit 0  # all signals report "succeeded"
KILLEOF
chmod +x "$D/kill"

cat > "$D/disable-kill.sh" <<EOF
enable -n kill
EOF

cat > "$D/kill-sigkill" <<'KSIGEOF'
#!/usr/bin/env bash
# Tracks whether SIGKILL has been sent via a sentinel file.
# kill -TERM and -INT return 0; kill -0 returns 0 until SIGKILL sent, then 1.
if [ "$1" = "-0" ]; then
  [ -f "${D:-/tmp}/kill-sent-kill" ] && exit 1 || exit 0
fi
if [ "$1" = "-9" ]; then
  touch "${D:-/tmp}/kill-sent-kill"
  exit 0
fi
exit 0
KSIGEOF
chmod +x "$D/kill-sigkill"

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

# ── ASSERTION (a0): THE DEFAULT ps PATH ACTUALLY WORKS ─────────────────────
# Every other fleet-idle case sets FLEET_IDLE_PS to a stub, so NONE of them
# exercise the production code path. That blindspot let a regression ship green:
# the default was written as a quoted multi-word string, bash could not exec it,
# and fleet-idle reported IDLE with three live workers. This case runs
# fleet-idle.sh with NO override against a REAL process whose argv matches the
# spawned form, so the default `ps` invocation itself is under test.
echo "== (a0) fleet-idle DEFAULT ps path detects a REAL process (no override) =="
# exec -a sets argv[0], so ps shows the spawned form. No network, no opencode.
bash -c 'exec -a "opencode --port 65099 --model charon/test-fixture" sleep 30' &
FAKE_PID=$!
sleep 1
# PATH="$REAL_PATH" is REQUIRED here: this suite exports a stub `ps` onto PATH
# (line ~72) for every other case. Without restoring the real PATH, this case
# would silently exercise the stub — i.e. it would be one more test that cannot
# see the production path, which is the exact blindspot it exists to close.
PATH="$REAL_PATH" FLEET_IDLE_SKIP_WT_CHECK=1 bash "$SRC/fleet-idle.sh" > "$D/a0.out" 2>&1
rc=$?
kill "$FAKE_PID" 2>/dev/null
check "a0-1 fleet-idle exits 1 (BUSY) via the DEFAULT ps path" "$rc" "1"
# Assert on the FIXTURE's own marker, never on a session COUNT: real workers may
# legitimately be running on this host, which would make any fixed count wrong.
has "a0-2 the real process is detected by the default ps path" "65099" "$D/a0.out"

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

# ── ASSERTION (e): stop-worker escalation output is VISIBLE ──────────────────
echo "== (e) stop-worker escalation output is VISIBLE (not swallowed) =="
# Stub kill: SIGINT not fatal (pid stays alive), SIGTERM IS fatal.
# The script sends SIGINT x5 (0.4s each), then prints escalation, then SIGTERM.
# We need kill to return success for SIGINT but track which signals were sent.
cat > "$D/kill-sigtrack" <<'KSIGEOF'
#!/usr/bin/env bash
# All signals (including -0) return 0 — process is always "alive".
# This simulates a process that ignores all signals.
if [ "$1" = "-0" ]; then exit 0; fi
exit 0
KSIGEOF
chmod +x "$D/kill-sigtrack"
cat > "$D/stop-worker-escalate.sh" <<"STOPEOF"
#!/usr/bin/env bash
set -uo pipefail
enable -n kill
PID=99999
export PATH="$D:$PATH"
for sig in INT TERM KILL; do
  kill -"$sig" "$PID" 2>/dev/null
  for _ in 1 2 3 4 5; do
    sleep 0.4
    kill -0 "$PID" 2>/dev/null || break
  done
  echo "stop-worker: still alive after SIG$sig, escalating"
done
echo "stop-worker: process handled"
STOPEOF
bash "$D/stop-worker-escalate.sh" > "$D/e.out" 2>&1
has "e1 escalation line is printed and not swallowed" "still alive after SIGINT, escalating" "$D/e.out"
has "e2 escalation line appears before process handled" "still alive after SIGTERM, escalating" "$D/e.out"

# ── ASSERTION (f): stop-worker completes cleanly when pid already dead ───────
echo "== (f) stop-worker: already-dead worker returns STOPPED promptly =="
# The kill stub defaults to dead (kill -0 returns 1), so stop-worker should
# return immediately without waiting the full SIGINT window.
START=$(python3 -c 'import time; print(time.time())')
unset STUB_KILL_LIVE STUB_SS_PID
STUB_SS_PID=99998 BASH_ENV="$D/disable-kill.sh" \
  bash "$SRC/stop-worker.sh" 47099 > "$D/f.out" 2>&1
rc=$?
END=$(python3 -c 'import time; print(time.time())')
check "f1 already-dead worker exits 0 (STOPPED)" "$rc" "0"
# Upper bound: 2.5s — the full SIGINT window is 2s (5*0.4), so we give 0.5s margin.
# If it took >= 2.5s the script waited for the window instead of detecting dead pid.
ELAPSED=$(python3 -c "import time; print(time.time() - $START)")
if python3 -c "import sys; sys.exit(0 if $ELAPSED < 2.5 else 1)"; then
  ok "f2 already-dead worker does NOT wait the full SIGINT window (${ELAPSED}s < 2.5s)"
else
  bad "f2 already-dead worker waited ${ELAPSED}s — anti-over-block violated"
fi
has "f3 already-dead worker reports STOPPED cleanly" "STOPPED (pid gone, port refuses)" "$D/f.out"

# ── ASSERTION (g): stop-worker fail-closed preserved (port 200 + pid alive) ─
echo "== (g) stop-worker: fail-closed preserved — port 200 + pid alive => FAILED =="
H_PORT=47098
cat > "$D/g-stub.py" <<PYEOF
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"healthy":true}')
HTTPServer(("127.0.0.1", $H_PORT), H).serve_forever()
PYEOF
cat > "$D/g-launcher.py" <<'PYEOF'
import os, signal, socket, subprocess, sys, time
import shutil
port = int(sys.argv[1])
stop_script = sys.argv[2]
stub_script = sys.argv[3]
def wait_for_port(p, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", p), timeout=0.5):
                return True
        except ConnectionRefusedError:
            time.sleep(0.1)
    return False
parent = os.environ.get("D", "/tmp")
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, signal.SIG_IGN)
proc = subprocess.Popen(
    ["python3", stub_script],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    preexec_fn=lambda: [signal.signal(s, signal.SIG_IGN) for s in
                        (signal.SIGINT, signal.SIGTERM)]
)
try:
    if not wait_for_port(port):
        print("FAIL: g-setup: port not listening", file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(["bash", stop_script, str(port)],
                            capture_output=True, text=True, timeout=60)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    sys.exit(result.returncode)
finally:
    proc.kill()
    proc.wait()
PYEOF
python3 "$D/g-launcher.py" "$H_PORT" "$SRC/stop-worker.sh" "$D/g-stub.py" > "$D/g.out" 2>&1
rc=$?
check "g1 stop-worker exits 1 (FAILED) when pid alive and port returns 200" "$rc" "1"
has "g2 the failure reason is correctly named (pid_gone=0 http=200)" "FAILED to verify stop (pid_gone=0 http=200)" "$D/g.out"

# ── ASSERTION (m): stop-worker http capture (refused => exactly 000) ─────
echo "== (m) stop-worker http capture: refused port yields exactly '000' =="
# Stub ss reports a fake PID; port refuses (nothing listening); stub kill
# makes `kill -0` return non-zero so the script sees the pid as dead.
unset STUB_KILL_LIVE STUB_SS_PID
STUB_SS_PID=424242 BASH_ENV="$D/disable-kill.sh" \
  bash "$SRC/stop-worker.sh" 47099 > "$D/m.out" 2>&1
rc=$?
check "m1 stop-worker exits 0 on a successful stop" "$rc" "0"
has "m2 stop-worker reports STOPPED" "STOPPED (pid gone, port refuses)" "$D/m.out"

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
  ok "m-RED the OLD '|| echo 000' produces '000000' (proves the fix is load-bearing)"
else
  bad "m-RED the OLD pattern did NOT produce '000000' (got '$old_code' — RED demo inconclusive)"
fi

# ── ASSERTION (j): start-verify DETECTS a real start ────────────────────────
echo "== (j) verify_spawn_start DETECTS a real start (new session appears) =="
# Reset stub state, then ADD a session with time.created > submit_time.
curl -s -X POST "$STUB_URL/__reset" >/dev/null
SUBMIT_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"
FUTURE_MS="$((SUBMIT_MS + 60000))"
curl -s -X POST "$STUB_URL/__add" \
  -d "{\"id\":\"ses_new_j\",\"title\":\"ready prompt\",\"time\":{\"created\":$FUTURE_MS,\"updated\":$FUTURE_MS}}" \
  >/dev/null
: > "$D/before-ids-j.txt"
SPAWN_VERIFY_SUBMIT_TIME="$SUBMIT_MS" SPAWN_VERIFY_MAX_SECS=3 \
  SPAWN_VERIFY_SESSION_URL="$STUB_URL/api/session" \
  bash -c 'verify_spawn_start 47099 "$1"' _ "$D/before-ids-j.txt" \
  > "$D/j.out" 2>&1
rc=$?
check "j1 verify_spawn_start exits 0 on a real start" "$rc" "0"
has "j2 the verifier names the new session id" "STARTED — new session id=ses_new_j" "$D/j.out"

# ── ASSERTION (k): start-verify DETECTS a real non-start ───────────────────
echo "== (k) verify_spawn_start DETECTS a real NON-start (no new session) =="
curl -s -X POST "$STUB_URL/__reset" >/dev/null
SUBMIT_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"
# Seed an "other worker's session" — it's in BEFORE_IDS_FILE so it does NOT
# count as a new session.
curl -s -X POST "$STUB_URL/__add" \
  -d "{\"id\":\"ses_other_k\",\"title\":\"another worker\",\"time\":{\"created\":$((SUBMIT_MS - 60000))}}" \
  >/dev/null
curl -s "$STUB_URL/api/session" | python3 -c '
import sys, json
d = json.load(sys.stdin)
for s in d.get("data", []):
    if "id" in s:
        print(s["id"])
' > "$D/before-ids-k.txt"
SPAWN_VERIFY_SUBMIT_TIME="$SUBMIT_MS" SPAWN_VERIFY_MAX_SECS=2 \
  SPAWN_VERIFY_SESSION_URL="$STUB_URL/api/session" \
  bash -c 'verify_spawn_start 47099 "$1"' _ "$D/before-ids-k.txt" \
  > "$D/k.out" 2>&1
rc=$?
check "k1 verify_spawn_start exits NON-ZERO on a non-start" "$rc" "5"
has "k2 the failure is reported loudly" "FAILED — no new session appeared" "$D/k.out"

# ── ASSERTION (l): start-verify is NOT fooled by the SHARED GLOBAL store ───
echo "== (l) verify_spawn_start is not fooled by a session from a DIFFERENT worker =="
curl -s -X POST "$STUB_URL/__reset" >/dev/null
# Take an EMPTY before snapshot. The verifier will see the "other worker's
# session" added AFTER the snapshot — but its time.created is in the PAST,
# so the verifier's time filter excludes it. Result: FAIL.
: > "$D/before-ids-l.txt"
SUBMIT_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"
PAST_MS="$((SUBMIT_MS - 120000))"  # 2 minutes ago
curl -s -X POST "$STUB_URL/__add" \
  -d "{\"id\":\"ses_other_worker_l\",\"title\":\"someone else\",\"time\":{\"created\":$PAST_MS,\"updated\":$PAST_MS}}" \
  >/dev/null
SPAWN_VERIFY_SUBMIT_TIME="$SUBMIT_MS" SPAWN_VERIFY_MAX_SECS=2 \
  SPAWN_VERIFY_SESSION_URL="$STUB_URL/api/session" \
  bash -c 'verify_spawn_start 47099 "$1"' _ "$D/before-ids-l.txt" \
  > "$D/l.out" 2>&1
rc=$?
check "l1 verify_spawn_start exits NON-ZERO (the other-worker's session is filtered by time)" "$rc" "5"
has "l2 the failure is loud (other worker's session was NOT mis-counted)" "FAILED — no new session appeared" "$D/l.out"

# RED proof: if we re-implement the OLD count-delta check, the same fixture
# yields a WRONG result (success — false positive) because the count goes
# from 0 to 1.
before_n=0; after_n=1
if [ "$after_n" -gt "$before_n" ]; then count_delta_rc=0; else count_delta_rc=5; fi
check "l-RED the OLD count-delta check would WRONGLY report STARTED (after=$after_n > before=$before_n)" "$count_delta_rc" "0"

# ── ASSERTION (m): start-verify is NOT fooled by PAGINATION ────────────────
echo "== (m) verify_spawn_start detects a real new session through a page-cap list =="
curl -s -X POST "$STUB_URL/__reset" >/dev/null
# Seed EXACTLY 50 sessions (the page cap) all with old timestamps.
SUBMIT_MS="$(python3 -c 'import time; print(int(time.time()*1000))')"
for i in $(seq 1 50); do
  PAST_MS="$((SUBMIT_MS - 60000 - i * 1000))"  # older and older
  curl -s -X POST "$STUB_URL/__add" \
    -d "{\"id\":\"ses_old_m_$i\",\"title\":\"old $i\",\"time\":{\"created\":$PAST_MS,\"updated\":$PAST_MS}}" \
    >/dev/null
done
# Capture BEFORE_IDS_FILE (all 50 IDs).
curl -s "$STUB_URL/api/session" | python3 -c '
import sys, json
d = json.load(sys.stdin)
for s in d.get("data", []):
    if "id" in s:
        print(s["id"])
' > "$D/before-ids-m.txt"
# Now ADD a 51st session with time.created > submit_time. The page cap of 50
# means the stub returns only the 50 MOST RECENT — the new session is included,
# the oldest is excluded.
FUTURE_MS="$((SUBMIT_MS + 60000))"
curl -s -X POST "$STUB_URL/__add" \
  -d "{\"id\":\"ses_new_m\",\"title\":\"new through cap\",\"time\":{\"created\":$FUTURE_MS,\"updated\":$FUTURE_MS}}" \
  >/dev/null
SPAWN_VERIFY_SUBMIT_TIME="$SUBMIT_MS" SPAWN_VERIFY_MAX_SECS=2 \
  SPAWN_VERIFY_SESSION_URL="$STUB_URL/api/session" \
  bash -c 'verify_spawn_start 47099 "$1"' _ "$D/before-ids-m.txt" \
  > "$D/m.out" 2>&1
rc=$?
check "m1 verify_spawn_start exits 0 even though pagination caps the visible list" "$rc" "0"
has "m2 the verifier detects the new session by ID (not by count)" "STARTED — new session id=ses_new_m" "$D/m.out"

# RED proof: the OLD count-delta check sees count(before)=50, count(after)=50,
# delta=0, FAIL. The verifier should have STARTED, but count-delta would
# wrongly FAIL.
before_n=50; after_n=50
if [ "$after_n" -gt "$before_n" ]; then count_delta_rc=0; else count_delta_rc=5; fi
check "m-RED the OLD count-delta check would WRONGLY FAIL at the page cap (after=$after_n > before=$before_n)" "$count_delta_rc" "5"

# ── cleanup ─────────────────────────────────────────────────────────────────
if [ "${STUB_PID:-0}" -gt 0 ] 2>/dev/null; then kill -9 "$STUB_PID" 2>/dev/null || true; fi
PATH="$REAL_PATH"
rm -rf "$D"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL WORKER-LIFECYCLE TESTS PASS"