#!/usr/bin/env bash
# session-ctx-preamble.test.sh — FAIL-ON-REVERT self-test for SESSION-CTX-PROPAGATE.
#
# Covers:
#   (a) the preamble emits valid SubagentStart hookSpecificOutput JSON with hookEventName
#       exactly "SubagentStart" and a non-empty additionalContext. Reverting the event name
#       back to "PreToolUse" (the WRONG lever -- its additionalContext never reaches a
#       sub-agent) or emptying additionalContext -> FAIL.
#   (b) the additionalContext contains the required pointer-index markers: the guiding docs
#       (MANAGER-OPERATING-RULES, TOOL-INVENTORY), the reuse-check/tool-first reminder, and
#       the mechanism-selection ladder.
#   (c) the additionalContext points ONLY at git-tracked, fresh-worktree-present paths --
#       it must NOT reference the gitignored local-only state files EVAL-REGISTRY.md or
#       CG-PROVIDERS.md (they are absent in the worktrees where sub-agents run -> dangling).
#   (d) the additionalContext stays under the ~40-line HARD size cap (revert -> someone
#       re-balloons it into a full-doc dump -> FAIL).
#   (e) fleet/state/SESSION-CTX-HOOK.json exists, is valid JSON, registers a SubagentStart
#       hook (NOT PreToolUse), and carries a hook command pointing at session-ctx-preamble.sh.
#
# Run:  bash fleet/tests/session-ctx-preamble.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

PREAMBLE_SH="$SRC/session-ctx-preamble.sh"
HOOK_JSON="$SRC/state/SESSION-CTX-HOOK.json"

echo "== (a) preamble script exists, runs, emits valid SubagentStart hook JSON =="
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
except Exception:
    sys.exit(1)
hso = d.get('hookSpecificOutput') or {}
sys.exit(0 if hso.get('hookEventName') == 'SubagentStart' and hso.get('additionalContext') else 1)
" 2>/dev/null; then
  ok "a2 valid JSON with hookSpecificOutput.hookEventName=SubagentStart + non-empty additionalContext"
else
  bad "a2 valid JSON with hookSpecificOutput.hookEventName=SubagentStart + non-empty additionalContext (REVERT -- wrong event name or empty context)"
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
  "reuse-check" \
  "MECHANISM-SELECTION LADDER"
do
  if printf '%s' "$CTX" | grep -qF "$marker"; then
    ok "b marker present: $marker"
  else
    bad "b marker present: $marker (REVERT -- pointer index incomplete)"
  fi
done

echo "== (c) no dangling gitignored local-only pointers in additionalContext =="
for absent in "EVAL-REGISTRY.md" "CG-PROVIDERS.md"
do
  if printf '%s' "$CTX" | grep -qF "$absent"; then
    bad "c pointer must NOT reference gitignored local-only file: $absent (dangles in fresh worktrees)"
  else
    ok "c no dangling pointer to $absent"
  fi
done

echo "== (d) size cap: additionalContext stays under ~40 lines =="
LINECOUNT="$(printf '%s' "$CTX" | grep -c '')"
if [ -n "$CTX" ] && [ "$LINECOUNT" -le 40 ]; then
  ok "d1 preamble line count ($LINECOUNT) <= 40-line cap"
else
  bad "d1 preamble line count ($LINECOUNT) <= 40-line cap (REVERT -- re-ballooned to full docs)"
fi

echo "== (e) hook JSON registers a SubagentStart hook pointing at the preamble =="
if [ -f "$HOOK_JSON" ]; then
  ok "e0 SESSION-CTX-HOOK.json exists"
else
  bad "e0 SESSION-CTX-HOOK.json exists"
fi

if python3 -c "
import json, sys
try:
    json.load(open('$HOOK_JSON'))
except Exception:
    sys.exit(1)
sys.exit(0)
" 2>/dev/null; then
  ok "e1 SESSION-CTX-HOOK.json is valid JSON"
else
  bad "e1 SESSION-CTX-HOOK.json is valid JSON"
fi

if python3 -c "
import json, sys
d = json.load(open('$HOOK_JSON'))
hooks = d.get('hooks', {})
# MUST be a SubagentStart hook, and MUST NOT be a PreToolUse hook (the wrong lever).
sys.exit(0 if ('SubagentStart' in hooks and 'PreToolUse' not in hooks) else 1)
" 2>/dev/null; then
  ok "e2 hook JSON registers SubagentStart (and NOT PreToolUse -- the wrong lever)"
else
  bad "e2 hook JSON registers SubagentStart (and NOT PreToolUse) (REVERT -- reverted to a PreToolUse hook that cannot reach sub-agents)"
fi

if python3 -c "
import json, sys
d = json.load(open('$HOOK_JSON'))
entries = d.get('hooks', {}).get('SubagentStart', [])
cmds = ' '.join(h.get('command','') for e in entries for h in e.get('hooks', []))
sys.exit(0 if 'session-ctx-preamble.sh' in cmds else 1)
" 2>/dev/null; then
  ok "e3 SubagentStart hook command points at session-ctx-preamble.sh"
else
  bad "e3 SubagentStart hook command points at session-ctx-preamble.sh (REVERT -- lost the preamble wiring)"
fi

echo
echo "--- $PASS passed, $FAIL failed ---"
if [ "$FAIL" -ne 0 ]; then
  echo "SESSION-CTX-PREAMBLE SELF-TEST FAILED"
  exit 1
fi
echo "ALL SESSION-CTX-PREAMBLE SELF-TESTS PASS"
exit 0
