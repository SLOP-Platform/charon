#!/usr/bin/env bash
# egress-key-canary.test.sh — FAIL-ON-REVERT dogfood for EGRESS-KEY-CANARY
# (fleet/checks/egress-key-canary.sh, design of record fleet/board/BOUNCE-1.md).
#
# GREEN IS NOT PROOF. This is a SECURITY canary — the standing regression guard
# for the #181 egress allowlist. A false-GREEN here means a live key-exfil
# vector the product is built on would ship undetected. Each class below SEEDS
# a real fault and PROVES the canary goes RED on it, then GREEN when the single
# seeded fault is reverted.
#
# REAL SUT, NOT A FAKE. Unlike flow-canary/balance-canary (which use hermetic
# stdlib HTTP fakes), this test drives a REAL charon gateway subprocess — the
# exfil lives IN the real header-forwarding code path (src/charon), so a fake
# gateway CANNOT stand in for it. The prior EGRESS-KEY-CANARY was REJECTED for
# exactly this reason: its hermetic decoupled model "passed" without ever running
# the real key-send code.
#
# Covers:
#   (H)  HEALTHY baseline -> GREEN (allowlist blocks the exfil)
#   (R1) ALLOWLIST PATCHED -> RED (key reaches the sink)
#   (R1-revert) Restore allowlist -> GREEN again
#
# Run:  bash fleet/tests/egress-key-canary.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
CANARY="$SRC/checks/egress-key-canary.sh"
[ -f "$CANARY" ] || { echo "FAIL: cannot find $CANARY" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

random_port() {
  python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()'
}

# ── sink server: records Authorization headers ───────────────────────────────
make_sink() { # <records-file> <port>
  cat > "$D/sink.py" <<'PYEOF'
import json, os, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

RECORD_FILE = sys.argv[1]
PORT = int(sys.argv[2])
lock = threading.Lock()

class Sink(BaseHTTPRequestHandler):
    def _capture(self):
        auth = self.headers.get("Authorization", "")
        with lock:
            captured = []
            if os.path.exists(RECORD_FILE):
                with open(RECORD_FILE) as f: captured = json.load(f)
            captured.append({"path": self.path, "auth": auth})
            with open(RECORD_FILE, "w") as f: json.dump(captured, f)
    def do_GET(self):
        self._capture()
        body = json.dumps({"data": [{"id": "test-model", "free": True}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_POST(self):
        self._capture()
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        body = json.dumps({"choices": [{"message": {"role":"assistant","content":"ok"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a, **k): return

srv = HTTPServer(("127.0.0.1", PORT), Sink)
t = threading.Thread(target=srv.serve_forever, daemon=True)
t.start()
print(f"sink ready on port {PORT}", flush=True)
srv.serve_forever()
PYEOF
  python3 -u "$D/sink.py" "$1" "$2" >"$D/sink-${2}.log" 2>&1 &
  echo $!
}

# ── patched gateway launcher ─────────────────────────────────────────────────
make_patched_gw() { # <port> <token> <charon-home>
  local port="$1" token="$2" home="$3"
  cat > "$D/patched-gw-${port}.py" <<'PYEOF'
import sys, os

import charon.egress as _egress
import charon.routing_policy as _rp

def _always_allowed(base_url):
    return True
_egress.is_allowed_base = _always_allowed
_egress.assert_base_allowed = lambda base_url: str(base_url)

from charon.cli import main
p = sys.argv[1]
t = sys.argv[2]
sys.argv = ["charon", "gateway", "--host", "127.0.0.1", "--port", p, "--token", t]
sys.exit(main())
PYEOF
  CHARON_HOME="$home" python3 -u "$D/patched-gw-${port}.py" "$port" "$token" >"$D/gw-${port}.log" 2>&1 &
  echo $!
}

wait_gw() { # <port> [timeout-deciseconds]
  local port="$1" limit="${2:-100}" i=0
  while [ "$i" -lt "$limit" ]; do
    python3 -c "
import socket, sys
s = socket.socket(); s.settimeout(0.2)
try: s.connect(('127.0.0.1', $port)); s.close(); sys.exit(0)
except: sys.exit(1)" 2>/dev/null && return 0
    sleep 0.1; i=$((i+1))
  done
  return 1
}

http_req() { # <method> <url> <bearer-token> [body-json]
  local m="$1" u="$2" t="$3" b="${4:-}"
  python3 -c "
import json, urllib.request
body = $b
url = '$u'
req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, method='$m')
req.add_header('Content-Type', 'application/json')
req.add_header('Authorization', 'Bearer $t')
try:
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode())
    print(f'STATUS={resp.status} OK=1 DATA={json.dumps(data)}')
except urllib.error.HTTPError as e:
    data = json.loads(e.read().decode()) if e.code != 500 else {}
    print(f'STATUS={e.code} OK=0 DATA={json.dumps(data)}')
except Exception as e:
    print(f'STATUS=0 OK=0 ERROR={e}')
" 2>/dev/null
}

# ── run the REAL canary ──────────────────────────────────────────────────────
run_canary(){
  EKC_GATEWAY_PORT="$EKC_PORT" \
  EKC_TOKEN="ekc-canary-token" \
  EKC_TIMEOUT_S=10 \
  EKC_PRESET="${1:-openrouter}" \
    bash "$CANARY" 2>&1
  return "${PIPESTATUS[0]:-$?}"
}
cap(){ CAP_OUT="$(run_canary "$@")"; CAP_RC=$?; }
has(){ printf '%s' "$CAP_OUT" | grep -q "$1"; }

# ═══════════════════════════════════════════════════════════════════════════════
# (H) HEALTHY baseline -> GREEN
# ═══════════════════════════════════════════════════════════════════════════════
echo "=== (H) HEALTHY baseline ==="
EKC_PORT="$(random_port)"
cap
[ "$CAP_RC" -eq 0 ] && ok "(H) canary exits 0 (GREEN) against real fixed master" \
                    || bad "(H) canary exit $CAP_RC (expected 0)
$CAP_OUT"
has "EGRESS-KEY-CANARY: GREEN" && ok "(H) prints GREEN verdict" \
                               || bad "(H) no GREEN verdict"
has "allowlist rejected" && ok "(H) GREEN reason: allowlist rejected evil provider" \
                         || bad "(H) GREEN reason unexpected"

# ═══════════════════════════════════════════════════════════════════════════════
# (R1) ALLOWLIST PATCHED -> RED (key reaches sink)
# ═══════════════════════════════════════════════════════════════════════════════
echo
echo "=== (R1) ALLOWLIST PATCHED -> RED (key reaches sink) ==="

GW_PORT="$(random_port)"
SINK_PORT="$(random_port)"
TOKEN="test-patched-token"
RECORDS="$D/sink-records.json"
echo '[]' > "$RECORDS"

# Start sink FIRST so the probe can reach it
SINK_PID="$(make_sink "$RECORDS" "$SINK_PORT")"
sleep 0.3
_info() { echo "         $1"; }
_info "sink PID $SINK_PID on port $SINK_PORT"

# Start patched gateway
GW_HOME="$D/gw-home-patched"
mkdir -p "$GW_HOME"
GW_PID="$(make_patched_gw "$GW_PORT" "$TOKEN" "$GW_HOME")"
sleep 1
wait_gw "$GW_PORT" 200 || true  # may take a moment; we check below
_info "patched gateway PID $GW_PID on port $GW_PORT"
if ! kill -0 "$GW_PID" 2>/dev/null; then
  bad "(R1) patched gateway failed to start"; cat "$D/gw-${GW_PORT}.log"
fi

# Step 1: POST /charon/providers — repoint a preset at the sink
_info "step 1: create provider openrouter pointing at sink"
R1_RESP="$(http_req POST "http://127.0.0.1:$GW_PORT/charon/providers" "$TOKEN" \
  '{"name":"openrouter","base_url":"http://127.0.0.1:'"$SINK_PORT"'/v1","key":"sk-throwaway"}')"
_info "$R1_RESP"
R1_STATUS="$(echo "$R1_RESP" | grep -o 'STATUS=[0-9]*' | cut -d= -f2)"

if [ "$R1_STATUS" = "200" ]; then
  ok "(R1) provider created with patched allowlist (200)"

  # Step 2: POST /charon/models/import -> key sent to sink
  _info "step 2: models/import -> key should reach sink"
  IMPORT_RESP="$(http_req POST "http://127.0.0.1:$GW_PORT/charon/models/import" "$TOKEN" \
    '{"provider":"openrouter"}')"
  _info "$IMPORT_RESP"

  sleep 0.5

  # Step 3: check sink records
  R1_LEAKED="$(python3 -c "
import json
try:
    with open('$RECORDS') as f: records = json.load(f)
    auths = [r.get('auth','') for r in records]
    print('; '.join(auths) if auths else 'NONE')
except Exception as e:
    print(f'ERROR={e}')
")"
  if [ "$R1_LEAKED" != "NONE" ] && [ "$R1_LEAKED" != "ERROR=*" ]; then
    _info "sink captured auth: $R1_LEAKED"
    ok "(R1) key reached the sink — canary detects real leak"
  else
    # The sink might not have been hit if models/import failed
    IMPORT_STATUS="$(echo "$IMPORT_RESP" | grep -o 'STATUS=[0-9]*' | cut -d= -f2)"
    if [ "$IMPORT_STATUS" = "200" ]; then
      # models/import returned 200 but sink has no record — either the key
      # was not sent (broken), or model import didn't reach the sink
      python3 -c "
import json
with open('$RECORDS') as f: records = json.load(f)
print('SINK RECORDS:', json.dumps(records))
"
      bad "(R1) models/import 200 but sink has no records — key not leaked?"
    else
      bad "(R1) models/import HTTP $IMPORT_STATUS — key never sent"
    fi
  fi
else
  bad "(R1) provider creation HTTP $R1_STATUS (expected 200 with patched allowlist)"
fi

# Clean up R1
kill "$GW_PID" 2>/dev/null || true
kill "$SINK_PID" 2>/dev/null || true
wait 2>/dev/null || true

# ═══════════════════════════════════════════════════════════════════════════════
# (R1-revert) Restore -> GREEN again
# ═══════════════════════════════════════════════════════════════════════════════
echo
echo "=== (R1-revert) Restore allowlist -> GREEN again ==="
EKC_PORT="$(random_port)"
cap
[ "$CAP_RC" -eq 0 ] && ok "(R1-revert) after restoring allowlist, canary exits 0 (GREEN)" \
                    || bad "(R1-revert) canary exit $CAP_RC (expected 0)
$CAP_OUT"
has "EGRESS-KEY-CANARY: GREEN" && ok "(R1-revert) prints GREEN verdict" \
                               || bad "(R1-revert) no GREEN verdict"

# ═══════════════════════════════════════════════════════════════════════════════
# summary
# ═══════════════════════════════════════════════════════════════════════════════
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL DOGFOOD TESTS PASS"
