#!/usr/bin/env bash
set -euo pipefail
# session-ctl.sh — thin curl wrapper over opencode's HTTP control plane.
# 6 verbs: list | steer | stop | reply | watch | launch
# Usage: session-ctl.sh <base_url> <verb> [args...]
#   session-ctl.sh http://localhost:47311 list
#   session-ctl.sh http://localhost:47311 steer <session-id> <message>
#   session-ctl.sh http://localhost:47311 stop <session-id>
#   session-ctl.sh http://localhost:47311 reply <session-id> <answer>
#   session-ctl.sh http://localhost:47311 watch
#   session-ctl.sh http://localhost:47311 launch <agent> <model> <prompt>

BASE="${1:?usage: session-ctl.sh <base_url> <verb> [args...]}"; shift
CURL="curl -s --max-time 30"
json_enc() { printf '%s' "$1" | python3 -c 'import sys,json;print(json.dumps(sys.stdin.read()))'; }

case "${1:-}" in
  list)
    $CURL "$BASE/api/session/active"
    echo
    $CURL "$BASE/api/session" | python3 -c "
import sys,json
data=json.load(sys.stdin)['data']
for s in sorted(data, key=lambda x: x['time']['updated'], reverse=True)[:20]:
    print(f\"  {s['id'][:20]:20s} {s.get('title','')[:50]:50s} {s.get('cost',0):.4f}\")
"
    ;;
  steer)
    SID="${2:?steer <session-id> <message>}"; shift 2
    MSG=$(json_enc "$*")
    $CURL -X POST "$BASE/api/session/$SID/prompt" \
      -H 'content-type: application/json' \
      -d "{\"prompt\":{\"text\":$MSG},\"delivery\":\"steer\"}"
    echo
    ;;
  stop)
    SID="${2:?stop <session-id>}"
    $CURL -X POST "$BASE/api/session/$SID/interrupt"
    echo
    ;;
  reply)
    SID="${2:?reply <session-id> <answer>}"; shift 2
    ANSWER=$(json_enc "$*")
    REQ=$($CURL "$BASE/api/permission/request" | python3 -c "
import sys,json
for r in json.load(sys.stdin).get('data',[]):
    if r.get('sessionID','').startswith('$SID') or r.get('sessionID')=='$SID':
        print(r['id']); break
" 2>/dev/null || echo "")
    if [ -n "$REQ" ]; then
      $CURL -X POST "$BASE/api/session/$SID/permission/$REQ/reply" \
        -H 'content-type: application/json' \
        -d "{\"answer\":$ANSWER}"
    else
      echo "No pending permission request for $SID"
    fi
    echo
    ;;
  watch)
    echo "Watching $BASE/api/event ... (Ctrl-C to stop)"
    curl -s -N "$BASE/api/event"
    ;;
  launch)
    AGENT="${2:-build}"; MODEL="${3:-charon/deepseek-v4-flash}"; shift 3
    PROMPT=$(json_enc "$*")
    DIR=$(json_enc "$(pwd)")
    SID=$($CURL -X POST "$BASE/api/session" \
      -H 'content-type: application/json' \
      -d "{\"agent\":\"$AGENT\",\"model\":{\"providerID\":\"charon\",\"id\":\"$MODEL\"},\"location\":{\"directory\":$DIR}}" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')
    echo "Launched session $SID"
    $CURL -X POST "$BASE/api/session/$SID/prompt" \
      -H 'content-type: application/json' \
      -d "{\"prompt\":{\"text\":$PROMPT}}"
    echo
    ;;
  *)
    echo "Usage: session-ctl.sh <base_url> <verb> [args...]"
    echo "Verbs: list | steer <id> <msg> | stop <id> | reply <id> <ans> | watch | launch [agent] [model] <prompt>"
    exit 1
    ;;
esac
