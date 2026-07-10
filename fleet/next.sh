#!/usr/bin/env bash
# """": true
# next.sh — tell a session what ticket to work next in their wave.
#
# Usage:
#   SESSION=qui-gon-jinn WAVE=B1 bash fleet/next.sh
#
# Reads fleet/waves/smart-routing.json for wave definitions and
# session-notes/ for completed check-ins. Returns the first ticket
# in the wave that has NOT been check-in'd by this session.
#
# Output:
#   T0.8 GUARD | Guardrails: PII + keyword blocking
# or:
#   wave complete — all 9 tickets in B1 are check-in'd
# or:
#   unknown wave: B1
#
set -euo pipefail

SESSION="${SESSION:-unknown}"
WAVE="${WAVE:-}"
NOTES_DIR="/home/stack/charon-private/fleet/session-notes"
MANIFEST="/home/stack/charon-private/fleet/waves/smart-routing.json"

if [ ! -f "$MANIFEST" ]; then
    echo "no wave manifest at $MANIFEST"
    exit 1
fi
if [ -z "$WAVE" ]; then
    echo "usage: SESSION=<name> WAVE=<wave-name> bash fleet/next.sh"
    exit 1
fi

# ── find wave in manifest ───────────────────────────────────────────
WAVE_JSON=$(python3 -c "
import json, sys
with open('$MANIFEST') as f:
    data = json.load(f)
for w in data.get('waves', []):
    if w.get('name') == sys.argv[1]:
        print(json.dumps(w))
        sys.exit(0)
print('')
" "$WAVE" 2>/dev/null)

if [ -z "$WAVE_JSON" ]; then
    echo "unknown wave: $WAVE"
    echo "available waves:"
    python3 -c "
import json
with open('$MANIFEST') as f:
    data = json.load(f)
for w in data.get('waves', []):
    print(f'  {w[\"name\"]}  (owner: {w[\"owner\"]})  {w[\"goal\"][:60]}')
" 2>/dev/null
    exit 1
fi

# ── collect completed ticket IDs from check-ins ─────────────────────
declare -A DONE
shopt -s nullglob
for f in "$NOTES_DIR"/*-"${SESSION}".md; do
    while IFS= read -r line; do
        case "$line" in
            \[*\]) ticket=$(echo "$line" | sed 's/^\[.*\] *//; s/  .*//')
                     DONE["$ticket"]=1
                     ;;
        esac
    done < "$f"
done
shopt -u nullglob

# ── find first incomplete ticket ────────────────────────────────────
NEXT=$(python3 -c "
import json, sys
wave = json.loads(sys.argv[1])
done = set(sys.argv[2].split(',')) if sys.argv[2] else set()
for t in wave.get('tickets', []):
    if t['id'] not in done:
        print(json.dumps(t))
        sys.exit(0)
print('')
" "$WAVE_JSON" "${!DONE[*]// /,}" 2>/dev/null)

if [ -z "$NEXT" ]; then
    echo "wave complete — all tickets in $WAVE are check-in'd"
    exit 0
fi

TICKET=$(echo "$NEXT" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
NAME=$(echo "$NEXT" | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")
DESC=$(echo "$NEXT" | python3 -c "import json,sys; print(json.load(sys.stdin)['desc'])")

echo "${TICKET}  ${NAME}  |  ${DESC}"
