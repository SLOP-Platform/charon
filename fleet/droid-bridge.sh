#!/usr/bin/env bash
# droid-bridge.sh — thin bash client for the session-bridge, so a droid tab can be
# PUSHED work by the manager instead of only PULLING it from the board.
#
# WIRING, NOT INVENTION. Every primitive already exists and is reused as-is:
#   - transport  : session-bridge/proxy.py, the existing line-oriented JSON-RPC
#                  forwarder (the same one fleet/checks/bridge-health.py drives).
#                  No new socket client, no new RPC, no daemon change.
#   - delivery   : `nudge` writes the target's queue; `board(session_id=…)` returns it
#                  AND refreshes the 600s lease — so THE POLL IS THE HEARTBEAT, free.
#   - liveness   : the daemon's own lease/expiry/graduated-purge. This script adds NO
#                  second notion of "alive"; DROID-LIFECYCLE-REAP consumes the bridge's.
#   - dedup      : session-bridge/idempotency.py `claim(session_id, message_id)` — built,
#                  tested, and documented as "NOT yet wired into any consumer". This is
#                  that consumer. A redelivered dispatch is skipped, never double-run.
# Verified by execution against a scratch daemon before this file was written:
#   register -> lease_token + 600s lease; nudge -> {"ok":true,"seq":1};
#   board(session_id=…) -> the message with id/from/text/seq/delivered_at, and
#   expires_in_seconds back to 600.
#
# USAGE
#   droid-bridge.sh register   <sid> <name> <repo> [status]  # prints lease_token
#   droid-bridge.sh unregister <sid>
#   droid-bridge.sh update     <sid> <status>                # pending|in-progress|blocked|done
#   droid-bridge.sh poll       <sid> <repo>                  # prints "<ticket> <msg_id>"
#   droid-bridge.sh ack        <sid> <lease_token> <msg_id>
#   droid-bridge.sh dispatch   <from_sid> <target_sid> <ticket>   # MANAGER side
#   droid-bridge.sh reply      <from_sid> <target_sid> <text>     # droid -> manager
#
# EXIT CODES (the caller's whole control flow keys off these — keep them distinct):
#   0  ok / dispatch found
#   1  no dispatch waiting (poll only) — the normal idle answer, NOT an error
#   2  bridge unreachable (daemon down, socket missing, proxy error, timeout)
#   3  usage error
set -uo pipefail

BRIDGE_PROXY="${BRIDGE_PROXY:-$HOME/.config/opencode/session-bridge/proxy.py}"
BRIDGE_IDEMPOTENCY_DIR="${BRIDGE_IDEMPOTENCY_DIR:-$HOME/.config/opencode/session-bridge}"
BRIDGE_RPC_TIMEOUT_S="${BRIDGE_RPC_TIMEOUT_S:-15}"
# A dispatch carries a TICKET ID AND NOTHING ELSE. This prefix is the entire wire
# vocabulary — see `no dark work` in poll() below.
DISPATCH_PREFIX="DISPATCH ticket="

_usage(){ sed -n '/^# USAGE/,/^# EXIT CODES/p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 3; }

# _rpc <tool> <arguments-json> — prints the tool's own result JSON on stdout.
# rc 0 = the tool answered with ok:true; rc 2 = unreachable/error/not-ok.
_rpc(){
  local tool="$1" args="$2"
  [ -r "$BRIDGE_PROXY" ] || { echo "droid-bridge: proxy not found at $BRIDGE_PROXY" >&2; return 2; }
  printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"%s","arguments":%s}}\n' \
    "$tool" "$args" \
  | timeout "$BRIDGE_RPC_TIMEOUT_S" python3 "$BRIDGE_PROXY" 2>/dev/null \
  | python3 -c '
import json, sys
line = sys.stdin.readline()
if not line.strip():
    sys.exit(2)                      # daemon down: proxy emits nothing usable
try:
    env = json.loads(line)
    inner = json.loads(env["result"]["content"][0]["text"])
except Exception:
    sys.exit(2)
if not inner.get("ok"):
    sys.stderr.write("droid-bridge: bridge refused: %s\n" % inner.get("error", inner))
    sys.exit(2)
json.dump(inner, sys.stdout)
'
}

_json_str(){ python3 -c 'import json,sys; json.dump(sys.argv[1], sys.stdout)' "$1"; }

cmd_register(){
  local sid="${1:-}" name="${2:-}" repo="${3:-charon}" status="${4:-pending}"
  [ -n "$sid" ] && [ -n "$name" ] || _usage
  local out
  out="$(_rpc register "$(python3 -c '
import json, sys
print(json.dumps({"session_id": sys.argv[1], "name": sys.argv[2],
                  "repo": sys.argv[3], "status": sys.argv[4]}))
' "$sid" "$name" "$repo" "$status")")" || return 2
  printf '%s' "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("lease_token",""))'
}

cmd_unregister(){
  local sid="${1:-}"; [ -n "$sid" ] || _usage
  _rpc unregister "{\"session_id\":$(_json_str "$sid")}" >/dev/null
}

cmd_update(){
  local sid="${1:-}" status="${2:-}"; [ -n "$sid" ] && [ -n "$status" ] || _usage
  _rpc update "{\"session_id\":$(_json_str "$sid"),\"status\":$(_json_str "$status")}" >/dev/null
}

cmd_dispatch(){   # MANAGER side. Assigns work to an ALREADY-REGISTERED droid; never spawns one.
  local from="${1:-}" target="${2:-}" ticket="${3:-}"
  [ -n "$from" ] && [ -n "$target" ] && [ -n "$ticket" ] || _usage
  _rpc nudge "{\"session_id\":$(_json_str "$from"),\"target\":$(_json_str "$target"),\"message\":$(_json_str "${DISPATCH_PREFIX}${ticket}")}" >/dev/null
}

cmd_reply(){
  local from="${1:-}" target="${2:-}" text="${3:-}"
  [ -n "$from" ] && [ -n "$target" ] || _usage
  _rpc nudge "{\"session_id\":$(_json_str "$from"),\"target\":$(_json_str "$target"),\"message\":$(_json_str "$text")}" >/dev/null
}

cmd_ack(){
  local sid="${1:-}" tok="${2:-}" mid="${3:-}"
  [ -n "$sid" ] && [ -n "$tok" ] && [ -n "$mid" ] || _usage
  _rpc ack "{\"session_id\":$(_json_str "$sid"),\"lease_token\":$(_json_str "$tok"),\"message_ids\":[$(_json_str "$mid")]}" >/dev/null
}

# poll <sid> <repo> — ONE tick. Prints "<ticket-id> <message-id>" and exits 0 when a
# dispatch is waiting; exits 1 when the queue holds nothing for us; exits 2 when the
# bridge is unreachable. The board() call itself refreshes this session's lease, so a
# polling droid is provably alive without any separate heartbeat.
#
# NO DARK WORK: only messages whose text is exactly "<DISPATCH_PREFIX><TICKET-ID>" are
# considered, the ticket id is constrained to [A-Za-z0-9._-]+, and NOTHING else from the
# message is ever used. There is no field on the wire that can carry an instruction, a
# path, a branch, or a command — the droid can only ever be told WHICH BOARD TICKET to
# consider, and every existing gate (claim, lease, parallelizability, leak-guard) still
# runs against it afterwards.
#
# IDEMPOTENCY: session-bridge/idempotency.py's claim() is consulted before a dispatch is
# reported to the caller. Delivery is at-least-once (REDELIVER_WINDOW_S), so without this
# a redelivered copy would launch the same ticket twice.
cmd_poll(){
  local sid="${1:-}" repo="${2:-charon}"; [ -n "$sid" ] || _usage
  local out
  out="$(_rpc board "{\"repo\":$(_json_str "$repo"),\"session_id\":$(_json_str "$sid")}")" || return 2
  printf '%s' "$out" | BRIDGE_IDEMPOTENCY_DIR="$BRIDGE_IDEMPOTENCY_DIR" python3 -c '
import json, os, re, sys
sid, prefix = sys.argv[1], sys.argv[2]
try:
    msgs = json.load(sys.stdin).get("nudge_messages") or []
except Exception:
    sys.exit(2)
sys.path.insert(0, os.environ["BRIDGE_IDEMPOTENCY_DIR"])
try:
    from idempotency import claim as _claim
except Exception:
    # Dedup module unavailable: fail CLOSED on the DUPLICATE question by refusing to
    # report any dispatch, rather than risking a double launch. Loud, never silent.
    sys.stderr.write("droid-bridge: idempotency ledger unavailable — refusing to consume dispatches\n")
    sys.exit(2)
ok = re.compile(r"^[A-Za-z0-9._-]+$")
for m in sorted(msgs, key=lambda x: x.get("seq") or 0):
    text = (m.get("text") or "").strip()
    if not text.startswith(prefix):
        continue
    ticket = text[len(prefix):].strip()
    if not ok.match(ticket):
        sys.stderr.write("droid-bridge: ignoring dispatch with a malformed ticket id: %r\n" % ticket)
        continue
    mid = m.get("id") or ""
    if not _claim(sid, mid):
        sys.stderr.write("droid-bridge: duplicate dispatch %s (already acted on) — skipping\n" % mid)
        continue
    print(ticket, mid)
    sys.exit(0)
sys.exit(1)
' "$sid" "$DISPATCH_PREFIX"
}

case "${1:-}" in
  register)   shift; cmd_register   "$@" ;;
  unregister) shift; cmd_unregister "$@" ;;
  update)     shift; cmd_update     "$@" ;;
  poll)       shift; cmd_poll       "$@" ;;
  ack)        shift; cmd_ack        "$@" ;;
  dispatch)   shift; cmd_dispatch   "$@" ;;
  reply)      shift; cmd_reply      "$@" ;;
  *)          _usage ;;
esac
