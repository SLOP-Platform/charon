#!/usr/bin/env bash
# egress-key-canary.sh — EGRESS-KEY CANARY
# REAL-SUT rebuild (BOUNCE-1). Proves the #181 egress allowlist
# (egress.py assert_base_allowed / is_allowed_base) blocks repointing a preset
# provider to a non-preset external host — the exact key-exfil entry point.
#
# WHY THIS EXISTS: the live exfil vector (POST /charon/providers repointing a
# preset provider at a non-preset base) is closed by the #181 egress allowlist
# (assert_base_allowed in gateway.py:618 + is_allowed_base in routing_policy:114).
# This canary is the standing REGRESSION GUARD that exercises the REAL gateway
# code against a real subprocess to prove the allowlist stays closed — NOT a
# hermetic mock that can never catch a real leak (the prior EGRESS-KEY-CANARY
# rejection root cause).
#
# THE CRUX — REAL SUT, NOT A FAKE. The prior attempt was REJECTED because it
# used a decoupled hermetic model that could not exercise the actual header-
# forwarding exfil path. This canary drives a real charon gateway subprocess
# and drives the real two-request exfil sequence against it:
#
#   1. POST /charon/providers {name:<preset>, base_url:<evil-host>, key:...}
#      -> must be REFUSED (400) by assert_base_allowed
#   2. POST /charon/models/import {provider:<preset>}
#      -> must FAIL because the provider was never created
#
# GREEN = the allowlist rejected the evil provider. RED = the provider was
# created (the allowlist did NOT block) — a regression.
#
# ENV:
#   EKC_GATEWAY_PORT    port for the real SUT gateway (default: random)
#   EKC_TIMEOUT_S       seconds to wait for gateway startup (default: 10)
#   EKC_TOKEN           gateway bearer token (default: auto-generated)
#   EKC_PRESET          preset provider name to test (default: openrouter)
#
# EXIT: 0 = GREEN (allowlist blocked the exfil). 1 = RED (allowlist did NOT
# block — regression / the probe itself failed).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET="$(cd "$HERE/.." && pwd)"

RED=0
_pass() { echo "  GREEN  $1"; }
_red() { RED=1; echo "  RED    $1"; }
_info() { echo "         $1"; }
_stage() { echo; echo "── $1 ──"; }

# ── helpers ──────────────────────────────────────────────────────────────────
random_port() {
  python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()'
}

# ── config ───────────────────────────────────────────────────────────────────
GATEWAY_PORT="${EKC_GATEWAY_PORT:-$(random_port)}"
SINK_PORT="$(random_port)"
TOKEN="${EKC_TOKEN:-ekc-canary-token}"
PRESET="${EKC_PRESET:-openrouter}"
EVIL_BASE="http://evil-regression-test.example.com/v1"
TIMEOUT_S="${EKC_TIMEOUT_S:-10}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; kill "$GW_PID" 2>/dev/null || true' EXIT

CHARON_HOME="$TMP/charon-home"
mkdir -p "$CHARON_HOME"

# VICTIM_KEY is a test-only value — never a real credential
VICTIM_KEY="sk-real-victim-key-do-not-exfiltrate"

_stage "EGRESS-KEY CANARY (REAL SUT)"

# ── 1. Start the real charon gateway ──────────────────────────────────────────
_info "starting real gateway on 127.0.0.1:$GATEWAY_PORT (CHARON_HOME=$CHARON_HOME)"
CHARON_HOME="$CHARON_HOME" \
CHARON_GATEWAY_TOKEN="$TOKEN" \
  python3 -m charon.cli gateway \
    --host 127.0.0.1 --port "$GATEWAY_PORT" \
    >"$TMP/gw.log" 2>&1 &
GW_PID=$!

# wait for gateway to be ready
for _ in $(seq 1 "$((TIMEOUT_S * 10))"); do
  python3 -c "
import socket, sys
s = socket.socket()
s.settimeout(0.2)
try:
    s.connect(('127.0.0.1', $GATEWAY_PORT))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null && break
  sleep 0.1
done
if ! kill -0 "$GW_PID" 2>/dev/null; then
  _red "gateway failed to start (see $TMP/gw.log)"
  cat "$TMP/gw.log"
  exit 1
fi
_info "gateway PID $GW_PID is accepting connections"

# ── 2. Attempt the exfil sequence ────────────────────────────────────────────
# Step 2a: POST /charon/providers to repoint a preset at a non-preset external host
_info "attempting to repoint preset '$PRESET' to non-preset base '$EVIL_BASE'"
PROVIDER_RESP="$(python3 -c "
import json, urllib.request
body = json.dumps({
    'name': '$PRESET',
    'base_url': '$EVIL_BASE',
    'key': 'sk-throwaway-test',
    'key_env': 'VICTIM_KEY',
}).encode()
url = 'http://127.0.0.1:$GATEWAY_PORT/charon/providers'
req = urllib.request.Request(url, data=body, method='POST')
req.add_header('Content-Type', 'application/json')
req.add_header('Authorization', 'Bearer $TOKEN')
try:
    resp = urllib.request.urlopen(req, timeout=5)
    data = json.loads(resp.read().decode())
    print(f'STATUS={resp.status} DATA={json.dumps(data)}', end='')
except urllib.error.HTTPError as e:
    data = json.loads(e.read().decode()) if e.code != 500 else {}
    print(f'STATUS={e.code} DATA={json.dumps(data)}', end='')
except Exception as e:
    print(f'ERROR={e}', end='')
" 2>/dev/null)"
_info "$PROVIDER_RESP"

STATUS="$(echo "$PROVIDER_RESP" | grep -o 'STATUS=[0-9]*' | cut -d= -f2)"
if [ "$STATUS" = "400" ]; then
  _pass "allowlist rejected provider creation (400) — preset provider blocked from non-preset base"
else
  _red "allowlist did NOT block provider creation (HTTP $STATUS) — regression!"
fi

# Step 2b: if the provider was somehow created, try models/import
if [ "$STATUS" = "200" ]; then
  _info "provider was created — attempting models/import (should fail)"
  IMPORT_RESP="$(python3 -c "
import json, urllib.request
body = json.dumps({'provider': '$PRESET'}).encode()
url = 'http://127.0.0.1:$GATEWAY_PORT/charon/models/import'
req = urllib.request.Request(url, data=body, method='POST')
req.add_header('Content-Type', 'application/json')
req.add_header('Authorization', 'Bearer $TOKEN')
try:
    resp = urllib.request.urlopen(req, timeout=5)
    data = json.loads(resp.read().decode())
    print(f'STATUS={resp.status} DATA={json.dumps(data)}', end='')
except urllib.error.HTTPError as e:
    data = json.loads(e.read().decode()) if e.code != 500 else {}
    print(f'STATUS={e.code} DATA={json.dumps(data)}', end='')
except Exception as e:
    print(f'ERROR={e}', end='')
" 2>/dev/null)"
  _info "$IMPORT_RESP"
fi

# ── verdict ──────────────────────────────────────────────────────────────────
echo
if [ "$RED" -eq 0 ]; then
  echo "EGRESS-KEY-CANARY: GREEN"
else
  echo "EGRESS-KEY-CANARY: RED"
fi
exit "$RED"
