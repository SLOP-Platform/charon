#!/usr/bin/env bash
set -euo pipefail
# session-ctl.sh — thin curl wrapper over opencode's HTTP control plane.
# Verbs: list | steer | stop | reply | watch | launch | health | board | resolve
# Usage:
#   session-ctl.sh <base_url> <verb> [args...]
#   session-ctl.sh -R <registry> <verb> [args...]
#   session-ctl.sh http://localhost:47311 list
#   session-ctl.sh http://localhost:47311 steer <session-id> <message>
#   session-ctl.sh http://localhost:47311 stop <session-id>
#   session-ctl.sh http://localhost:47311 reply <session-id> <answer>
#   session-ctl.sh http://localhost:47311 watch
#   session-ctl.sh http://localhost:47311 launch <agent> <model> <prompt>
#   session-ctl.sh -R fleet/session-registry.tsv board
#   session-ctl.sh -R fleet/session-registry.tsv resolve <name>

REGISTRY=""
while getopts "R:" opt 2>/dev/null; do
  case "$opt" in
    R) REGISTRY="$OPTARG" ;;
  esac
done
shift $((OPTIND - 1))

if [ -z "$REGISTRY" ]; then
  BASE="${1:?usage: session-ctl.sh <base_url> <verb> [args...]}"; shift
else
  BASE=""
fi

CURL="curl -s --max-time 30"
json_enc() { printf '%s' "$1" | python3 -c 'import sys,json;print(json.dumps(sys.stdin.read()))'; }

resolve_registry() {
  local name="$1" regfile="${REGISTRY:-/dev/null}"
  local result
  result=$(awk -F'\t' -v n="$name" '
    /^#/ { next }
    /^[[:space:]]*$/ { next }
    $1 == n { printf "http://%s:%s", ($3==""?"localhost":$3), $2; exit }
  ' "$regfile")
  if [ -z "$result" ]; then
    echo "session-ctl: name '$name' not found in registry $regfile" >&2
    return 1
  fi
  echo "$result"
}

check_health() {
  local url="$1"
  $CURL "$url/api/health" 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
h=d.get('healthy',False)
print('UP' if h else 'UNHEALTHY')
" 2>/dev/null || echo "DEAD"
}

case "${1:-}" in
  list)
    [ -z "$BASE" ] && { echo "session-ctl: list requires <base_url>" >&2; exit 1; }
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
    [ -z "$BASE" ] && { echo "session-ctl: steer requires <base_url>" >&2; exit 1; }
    SID="${2:?steer <session-id> <message>}"; shift 2 2>/dev/null || true
    MSG=$(json_enc "$*")
    $CURL -X POST "$BASE/api/session/$SID/prompt" \
      -H 'content-type: application/json' \
      -d "{\"prompt\":{\"text\":$MSG},\"delivery\":\"steer\"}"
    echo
    ;;

  stop)
    [ -z "$BASE" ] && { echo "session-ctl: stop requires <base_url>" >&2; exit 1; }
    SID="${2:?stop <session-id>}"
    RESP=$($CURL -X POST "$BASE/api/session/$SID/interrupt" 2>&1)
    RC=$?
    echo "$RESP"
    if [ $RC -ne 0 ]; then
      echo "session-ctl: STOP failed (curl exit $RC)" >&2
      exit $RC
    fi
    ;;

  reply)
    [ -z "$BASE" ] && { echo "session-ctl: reply requires <base_url>" >&2; exit 1; }
    SID="${2:?reply <session-id> <answer>}"; shift 2 2>/dev/null || true
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
    [ -z "$BASE" ] && { echo "session-ctl: watch requires <base_url>" >&2; exit 1; }
    echo "Watching $BASE/api/event ... (Ctrl-C to stop)"
    curl -s -N "$BASE/api/event"
    ;;

  launch)
    [ -z "$BASE" ] && { echo "session-ctl: launch requires <base_url>" >&2; exit 1; }
    AGENT="${2:-build}"; MODEL="${3:-charon/deepseek-v4-flash}"; shift 3 2>/dev/null || true
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

  health)
    [ -z "$BASE" ] && { echo "session-ctl: health requires <base_url>" >&2; exit 1; }
    STATUS=$(check_health "$BASE")
    echo "health: $STATUS"
    [ "$STATUS" = "UP" ] && exit 0 || exit 1
    ;;

  resolve)
    if [ -z "$REGISTRY" ]; then
      echo "session-ctl: resolve requires -R <registry>" >&2
      exit 1
    fi
    NAME="${2:?resolve <name>}"
    RESOLVED=$(resolve_registry "$NAME")
    echo "$RESOLVED"
    ;;

  board)
    [ -z "$REGISTRY" ] && { echo "session-ctl: board requires -R <registry>" >&2; exit 1; }
    echo "=== fleet board ==="
    echo
    REACHABLE=""
    REACHABLE_URL=""
    while IFS=$'\t' read -r name port host sid rest; do
      [ -z "$name" ] && continue
      [[ "$name" =~ ^# ]] && continue
      HOST="${host:-localhost}"
      URL="${BASE:-http://${HOST}:${port}}"
      STATUS=$(check_health "$URL" || true)
      if [ "$STATUS" = "UP" ]; then
        echo "  $name  port=$port  $STATUS"
        if [ -z "$REACHABLE_URL" ]; then
          REACHABLE_URL="$URL"
        fi
        REACHABLE="$REACHABLE $name"
      else
        echo "  $name  port=$port  $STATUS"
      fi
    done < "$REGISTRY"

    if [ -z "$REACHABLE_URL" ]; then
      echo
      echo "session-ctl: no reachable session in registry" >&2
      exit 1
    fi

    echo
    echo "--- sessions (via $REACHABLE_URL) ---"
    $CURL "$REACHABLE_URL/api/session" | python3 -c "
import sys,json
data=json.load(sys.stdin).get('data',[])
if not data:
    print('  (no sessions)')
    sys.exit(0)
for s in sorted(data, key=lambda x: x['time']['updated'], reverse=True)[:20]:
    sid=s['id'][:24]
    title=(s.get('title','') or '')[:48]
    model=(s.get('model',{}).get('id','') or '')[:30]
    typ=str(s.get('type','') or '')
    updated=str(s.get('time',{}).get('updated',''))[:19] if s.get('time',{}).get('updated') else ''
    cost=s.get('cost',0)
    print(f'  {sid:24s} {title:48s} {model:30s} {typ:8s} {updated:19s} \${cost:.4f}')
if len(data)>20:
    print(f'  ... and {len(data)-20} more')
" || { echo "session-ctl: board query failed" >&2; exit 1; }
    ;;

  *)
    echo "Usage: session-ctl.sh [-R <registry>] <base_url|name> <verb> [args...]"
    echo "Verbs: list | steer <id> <msg> | stop <id> | reply <id> <ans> | watch"
    echo "       launch [agent] [model] <prompt> | health | resolve <name> | board"
    echo ""
    echo "  session-ctl.sh http://localhost:47311 list"
    echo "  session-ctl.sh -R fleet/session-registry.tsv board"
    echo "  session-ctl.sh -R fleet/session-registry.tsv resolve obi-wan-kenobi"
    exit 1
    ;;
esac
