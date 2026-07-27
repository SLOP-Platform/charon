#!/usr/bin/env bash
# spawn-worker.sh — open a NAMED, COLOURED Windows Terminal TAB running an opencode worker.
# Usage: spawn-worker.sh <TAB-NAME> <MODEL> <PORT> <COLOR> [WINDOW] [WORKDIR] [PROMPT]
#
# Every choice here is a VERIFIED research finding (RESEARCH-SESSION-SPAWN-2026-07-27.md):
#  * `-w 1` targets the FIRST-CREATED window and lands in the operator's window. `-w 0` does NOT —
#    it follows GUI focus, and a WSL subprocess is not "using" its parent window. `$WT_SESSION` is a
#    PANE guid, not a window id, and spawns a new window.
#  * --suppressApplicationTitle is MANDATORY: opencode sets its own title, so without it every tab
#    reads "OpenCode" and the names are useless.
#  * This script exists because `wt` eats `;` as a COMMAND SEPARATOR — `cd X; opencode` silently
#    becomes "open another tab". Passing ONE script path collapses three quoting layers to zero.
#  * MODEL is REQUIRED with no default. opencode's default is gpt-5.4, whose pool is
#    [nanogpt, openrouter] — BOTH DEAD. A defaulted spawn lands the whole fleet on a dead pool.
#  * The prompt is NOT passed here: `--prompt` was verified NOT to auto-submit. Push it after the
#    worker is up with: fleet/session-ctl.sh launch <port> "<prompt>"
set -uo pipefail
NAME="${1:?usage: spawn-worker.sh TAB-NAME MODEL PORT COLOR [WINDOW]}"
MODEL="${2:?MODEL is required - no default by design, opencode default pool is dead}"
PORT="${3:?PORT is required so session-ctl.sh can address this worker}"
COLOR="${4:-#3b82f6}"
WINDOW="${5:-1}"
# CWD matters: it is opencode's project context. Rig work -> charon-private; PRODUCT work ->
# /home/stack/code/charon (the operator's usual launch dir). Default is the rig because the
# manager lives there; pass it explicitly for product tickets.
WORKDIR="${6:-/home/stack/charon-private}"
PROMPT="${7:-}"
WT=/mnt/c/Users/$(/mnt/c/Windows/System32/cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')/AppData/Local/Microsoft/WindowsApps/wt.exe
[ -x "$WT" ] || WT=$(command -v wt.exe 2>/dev/null) || { echo "spawn-worker: wt.exe not found" >&2; exit 2; }

# Free-tier legs pass a one-shot probe and then collapse under a real session's request volume.
case "$MODEL" in
  *-free|gemini-*|gpt-5.4)
    echo "spawn-worker: REFUSING model '$MODEL' — free-tier/default legs cannot carry a session." >&2
    echo "  Use a sustained-capable leg: deepseek-v4-pro, deepseek-v4-flash, minimax-m3-together." >&2
    exit 3;;
esac

# Resolve opencode ABSOLUTELY: the spawned tab runs a NON-LOGIN bash, so ~/.local/bin is not on
# PATH and a bare `opencode` exits 127. Do not rely on the child inheriting a profile.
OC_BIN=$(command -v opencode 2>/dev/null || echo /home/stack/.local/bin/opencode)
[ -x "$OC_BIN" ] || { echo "spawn-worker: opencode not found at $OC_BIN" >&2; exit 2; }

RUN=$(mktemp /tmp/spawn-worker-XXXXXX.sh)
{
  echo '#!/usr/bin/env bash'
  echo "cd '$WORKDIR' || exit 1"
  echo "exec '$OC_BIN' --port $PORT --model charon/$MODEL"
} > "$RUN"
chmod +x "$RUN"
echo "spawn-worker: tab='$NAME' model=$MODEL port=$PORT window=$WINDOW cwd=$WORKDIR"
# FOCUS FIX (verified): a bare `new-tab` STEALS FOCUS and eats the operator's keystrokes.
# Chain a focus-tab back to the home tab in the SAME wt invocation. The ';' must be a QUOTED
# STANDALONE ARG or wt swallows it as a shell separator. Residual steal ~40-90ms; holds across a
# 4-spawn fan-out. Only fails if the operator is typing in a DIFFERENT wt window (cross-window
# activation can only be undone after the fact).
"$WT" -w "$WINDOW" new-tab --title "$NAME" --tabColor "$COLOR" --suppressApplicationTitle \
      wsl.exe -d Ubuntu-24.04 -- bash "$RUN" \
      ';' focus-tab -t "${CHARON_WT_HOME_TAB:-0}"

# ---------------------------------------------------------------------------------------------
# OPTIONAL: inject the opening prompt so the worker starts WITHOUT a human keystroke.
#
# Everything below is a VERIFIED finding — do not "simplify" it:
#  * The right mechanism for a TUI worker is POST /tui/append-prompt then POST /tui/submit-prompt
#    on the WORKER'S OWN PORT. It is NOT /api/session/{id}/prompt, and it is NOT session-ctl
#    `launch` — those create a session in the GLOBAL store that no TUI drives, producing dead
#    "admittedSeq:1" rows and four tabs sitting on the splash screen. That exact mistake was made
#    on 2026-07-27 and cost a full dogfood run.
#  * A TUI creates its session LAZILY, at first submit. So there is no pre-turn session id to
#    address — which is why port-addressing is the only workable handle.
#  * /tui/* returns `true` UNCONDITIONALLY. It means "event published", not "a TUI received it";
#    it returned true for nonsense command names. NEVER treat that response as proof.
#  * /api/health goes healthy BEFORE the TUI client attaches. Injecting in that window is
#    SILENTLY DROPPED. Gate on health AND established loopback connections (a live TUI holds
#    ~18-36; a headless `serve` holds 0).
[ -z "$PROMPT" ] && exit 0

echo "spawn-worker: waiting for TUI readiness on :$PORT ..."
ready=0
for i in $(seq 1 40); do
  h=$(curl -s -m 3 "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -c healthy || true)
  est=$(ss -tn state established "( sport = :$PORT or dport = :$PORT )" 2>/dev/null | tail -n +2 | wc -l)
  if [ "${h:-0}" -ge 1 ] && [ "${est:-0}" -gt 0 ]; then ready=1; echo "spawn-worker: ready (health=ok established=$est) after ${i}s"; break; fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "spawn-worker: TUI never became ready on :$PORT — NOT injecting (it would be silently dropped)" >&2; exit 4; }

before=$(curl -s -m 5 "http://127.0.0.1:$PORT/api/session" 2>/dev/null | grep -o '"id"' | wc -l)
curl -s -m 8 -X POST "http://127.0.0.1:$PORT/tui/append-prompt" -H 'Content-Type: application/json'      -d "$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1]}))' "$PROMPT")" >/dev/null 2>&1
curl -s -m 8 -X POST "http://127.0.0.1:$PORT/tui/submit-prompt" -H 'Content-Type: application/json' -d '{}' >/dev/null 2>&1

# VERIFY — the `true` above proves nothing. A new session must actually exist.
sleep 4
after=$(curl -s -m 5 "http://127.0.0.1:$PORT/api/session" 2>/dev/null | grep -o '"id"' | wc -l)
if [ "${after:-0}" -gt "${before:-0}" ]; then
  echo "spawn-worker: prompt ACCEPTED and a session was created (sessions ${before} -> ${after})"
else
  echo "spawn-worker: WARNING — prompt submitted but NO new session appeared (${before} -> ${after})." >&2
  echo "  The tab is live; start it by hand. Do NOT assume it is working." >&2
  exit 5
fi
