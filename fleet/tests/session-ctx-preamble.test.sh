#!/usr/bin/env bash
# session-ctx-preamble.test.sh — FAIL-ON-REVERT self-test for SESSION-CTX-PROPAGATE.
#
# Covers:
#   (a) the preamble emits valid PreToolUse hookSpecificOutput JSON with a non-empty
#       additionalContext (revert -> empty/malformed output -> FAIL).
#   (b) the additionalContext contains the required pointer-index markers: the four
#       guiding docs (MANAGER-OPERATING-RULES, TOOL-INVENTORY, EVAL-REGISTRY, CG-PROVIDERS),
#       the reuse-check/tool-first reminder, and the mechanism-selection ladder.
#   (c) the additionalContext stays under the ~40-line HARD size cap (revert -> someone
#       re-balloons it back into a full-doc dump -> FAIL).
#   (d) fleet/state/SESSION-CTX-HOOK.json exists, is valid JSON, targets matcher
#       "Agent|Task", and carries a hook command that points at session-ctx-preamble.sh
#       ALONGSIDE (not replacing) the existing nudge_background_agents.py entry.
#
# Run:  bash fleet/tests/session-ctx-preamble.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

PREAMBLE_SH="$SRC/session-ctx-preamble.sh"
HOOK_JSON="$SRC/state/SESSION-CTX-HOOK.json"

echo "== (a) preamble script exists, runs, emits valid hook JSON =="
if [ ! -x "$PREAMBLE_SH" ] && [ ! -f "$PREAMBLE_SH" ]; then
  bad "a0 session-ctx-preamble.sh exists"
else
  ok "a0 session-ctx-preamble.sh exists"
fi

RAW="$(bash "$PREAMBLE_SH" 2>/dev/null)"
if [ -z "$RAW" ]; then
  bad "a1 preamble produced non-empty output (got empty -- REVERT)"
else
  ok "a1 preamble produced non-empty output"
fi

if echo "$RAW" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception as e:
    sys.exit(1)
hso = d.get('hookSpecificOutput') or {}
sys.exit(0 if hso.get('hookEventName') == 'PreToolUse' and hso.get('additionalContext') else 1)
" 2>/dev/null; then
  ok "a2 output is valid JSON with hookSpecificOutput.hookEventName=PreToolUse + non-empty additionalContext"
else
  bad "a2 output is valid JSON with hookSpecificOutput.hookEventName=PreToolUse + non-empty additionalContext"
fi

CTX="$(echo "$RAW" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d['hookSpecificOutput']['additionalContext'])
except Exception:
    pass
")"

echo "== (b) required pointer-index markers present =="
for marker in \
  "MANAGER-OPERATING-RULES" \
  "TOOL-INVENTORY" \
  "EVAL-REGISTRY" \
  "CG-PROVIDERS" \
  "reuse-check" \
  "MECHANISM-SELECTION LADDER"
do
  if printf '%s' "$CTX" | grep -qF "$marker"; then
    ok "b marker present: $marker"
  else
    bad "b marker present: $marker (REVERT -- pointer index incomplete)"
  fi
done

echo "== (c) size cap: additionalContext stays under ~40 lines =="
LINECOUNT="$(printf '%s' "$CTX" | grep -c '')"
if [ -n "$CTX" ] && [ "$LINECOUNT" -le 40 ]; then
  ok "c1 preamble line count ($LINECOUNT) <= 40-line cap"
else
  bad "c1 preamble line count ($LINECOUNT) <= 40-line cap (REVERT -- re-ballooned to full docs)"
fi

echo "== (d) hook JSON targets Agent|Task and carries the preamble, alongside the existing nudge =="
if [ -f "$HOOK_JSON" ]; then
  ok "d0 SESSION-CTX-HOOK.json exists"
else
  bad "d0 SESSION-CTX-HOOK.json exists"
fi

if python3 -c "
import json, sys
try:
    d = json.load(open('$HOOK_JSON'))
except Exception:
    sys.exit(1)
sys.exit(0)
" 2>/dev/null; then
  ok "d1 SESSION-CTX-HOOK.json is valid JSON"
else
  bad "d1 SESSION-CTX-HOOK.json is valid JSON"
fi

if python3 -c "
import json, sys
d = json.load(open('$HOOK_JSON'))
entries = d.get('hooks', {}).get('PreToolUse', [])
matched = [e for e in entries if e.get('matcher') == 'Agent|Task']
sys.exit(0 if matched else 1)
" 2>/dev/null; then
  ok "d2 hook JSON targets matcher Agent|Task"
else
  bad "d2 hook JSON targets matcher Agent|Task (REVERT -- wrong/missing matcher)"
fi

if python3 -c "
import json, sys
d = json.load(open('$HOOK_JSON'))
entries = d.get('hooks', {}).get('PreToolUse', [])
matched = [e for e in entries if e.get('matcher') == 'Agent|Task']
cmds = ' '.join(h.get('command','') for e in matched for h in e.get('hooks', []))
has_preamble = 'session-ctx-preamble.sh' in cmds
has_nudge = 'nudge_background_agents.py' in cmds
sys.exit(0 if (has_preamble and has_nudge) else 1)
" 2>/dev/null; then
  ok "d3 hook JSON carries session-ctx-preamble.sh ALONGSIDE the existing nudge_background_agents.py command"
else
  bad "d3 hook JSON carries session-ctx-preamble.sh ALONGSIDE the existing nudge_background_agents.py command (REVERT -- lost the preamble wiring or clobbered the existing nudge)"
fi

echo
echo "--- $PASS passed, $FAIL failed ---"
if [ "$FAIL" -ne 0 ]; then
  echo "SESSION-CTX-PREAMBLE SELF-TEST FAILED"
  exit 1
fi
echo "ALL SESSION-CTX-PREAMBLE SELF-TESTS PASS"
exit 0
