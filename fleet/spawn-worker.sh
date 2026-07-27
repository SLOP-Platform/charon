#!/usr/bin/env bash
# spawn-worker.sh — open a NAMED, COLOURED Windows Terminal TAB running an opencode worker.
# Usage: spawn-worker.sh <TAB-NAME> <MODEL> <PORT> <COLOR> [WINDOW] [WORKDIR]
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
"$WT" -w "$WINDOW" new-tab --title "$NAME" --tabColor "$COLOR" --suppressApplicationTitle \
      wsl.exe -d Ubuntu-24.04 -- bash "$RUN"
