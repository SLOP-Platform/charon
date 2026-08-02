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
#    worker is up with (CORRECTED 2026-08-02 — the previous form omitted the base_url and both
#    positional slots, and FAILS: session-ctl.sh takes <base_url> FIRST, then the verb):
#      fleet/session-ctl.sh http://127.0.0.1:<PORT> launch <agent> <model> "<prompt>"
#    Defaults if the slots are omitted: agent=build, model=charon/deepseek-v4-flash
#    (see session-ctl.sh:26 for the base_url arg and :120-122 for the agent/model slots).
#
# ============================================================================
# TUI-READINESS GATE  (was bug 3a — fixed 2026-07-27, see WORKER-LIFECYCLE-FIX)
# ============================================================================
# `wait_for_tui_ready <PORT>` — exit 0 when the TUI has finished attaching to
# the opencode server on $PORT, non-zero with a loud reason otherwise.
#
# The OLD gate required "health=ok AND established > 0" on the FIRST poll that
# satisfied it. That fired at established=18 — observed live during a 3-tab
# fan-out (:47301/2/3) — which is the TUI still mid-attach: a prompt injected
# in that window is silently dropped, /tui/* returns true unconditionally,
# and the tab sits on the splash screen. At established=36 the same inject
# actually landed a session.
#
# The discriminator is NOT a higher magic number (36 was one observation on
# one machine). It is STABILITY of the connection count over consecutive
# samples — once the TUI is done attaching, the count stops growing. So we
# require:
#   * health=ok
#   * established >= 10 (a no-TUI headless `opencode serve` sits around 3-5;
#     10 is comfortably above that and well below any observed attaching-TUI
#     plateau)
#   * stable for 3 consecutive 1s samples (count has stopped growing)
# If none of those arrive within 40s the gate FAILS LOUDLY and we do NOT
# inject — silently dropping a prompt is worse than failing visibly.
#
# Env override SPAWN_TUI_STABLE_FORMS makes the gate drive the HTTP surface
# only, so the test suite can verify both branches without touching `ss`.
wait_for_tui_ready(){
  local PORT="${1:?wait_for_tui_ready: PORT}"
  local min="${SPAWN_TUI_MIN:-10}"
  local stable_for="${SPAWN_TUI_STABLE_FORMS:-3}"
  local max="${SPAWN_TUI_MAX_SECS:-40}"
  local prev=0 stable=0
  for i in $(seq 1 "$max"); do
    local h
    h=$(curl -s -m 3 "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -c healthy || true)
    local est
    if [ -n "${SPAWN_TUI_EST_OVERRIDE:-}" ]; then
      est="$SPAWN_TUI_EST_OVERRIDE"
    else
      est=$(ss -tn state established "( sport = :$PORT or dport = :$PORT )" 2>/dev/null | tail -n +2 | wc -l)
    fi
    if [ "${h:-0}" -ge 1 ] && [ "${est:-0}" -ge "$min" ] && [ "$est" = "$prev" ]; then
      stable=$((stable + 1))
    else
      stable=0
    fi
    if [ "$stable" -ge "$stable_for" ]; then
      echo "spawn-worker: ready (health=ok established=$est stable=${stable_for}x) after ${i}s"
      return 0
    fi
    prev="$est"
    sleep 1
  done
  echo "spawn-worker: TUI never stabilised on :$PORT (last health=${h:-0} established=${est:-0} stable=${stable}/${stable_for}) — NOT injecting" >&2
  return 4
}

# ============================================================================
# START-VERIFICATION  (was bug 3b — fixed 2026-07-27, see WORKER-LIFECYCLE-FIX)
# ============================================================================
# `verify_spawn_start <PORT> <BEFORE_IDS_FILE>` — exit 0 when a NEW session
# appears for this worker within timeout; exit 5 loudly otherwise.
# Prints the new session's id/time-created on success.
#
# The OLD verifier compared a `grep -c '"id"'` COUNT before vs after. Two
# independent reasons that can never work:
#   1. /api/session is PAGINATED (returned exactly 50 for the operator who hit
#      this). A capped list cannot show growth — count stays flat at 50 even
#      when a new session was created.
#   2. The opencode session store is GLOBAL and SHARED across every port. A
#      count taken on one port counts every port's sessions. A fan-out's
#      "did MY worker start?" check is therefore a count of the fleet, not
#      of itself.
#
# Replacement: snapshot ALL session IDs BEFORE submit (full paginated
# walk), then poll AFTER for IDs not in that set AND with time.created >=
# the submit timestamp. ID-set diff is not fooled by pagination (an ID not
# in before is new, period) and not fooled by the shared store (an ID seeded
# by another worker was already in before). Time.created >= submit_time is
# the only thing that tells MY submit apart from a coincident neighbour's.
#
# `SPAWN_VERIFY_SESSION_URL` overrides the /api/session URL so the test suite
# can drive refused / answering / 200 paths against a stub without spawning
# a real opencode.
verify_spawn_start(){
  local PORT="${1:?verify_spawn_start: PORT}"
  local BEFORE_IDS_FILE="${2:?verify_spawn_start: BEFORE_IDS_FILE}"
  local max="${SPAWN_VERIFY_MAX_SECS:-20}"
  local url="${SPAWN_VERIFY_SESSION_URL:-http://127.0.0.1:$PORT/api/session}"
  local submit_time
  submit_time="${SPAWN_VERIFY_SUBMIT_TIME:-$(date +%s%3N 2>/dev/null || date +%s)}"
  for i in $(seq 1 "$max"); do
    local body
    body=$(curl -s -m 5 "$url" 2>/dev/null || echo "")
    local new_id
    new_id=$(BODY="$body" BEFORE="$BEFORE_IDS_FILE" SUBMIT="$submit_time" python3 - <<'PY' 2>/dev/null
import os, json, sys
try:
    raw = os.environ.get("BODY", "")
    before = set(l.strip() for l in open(os.environ["BEFORE"]) if l.strip())
    submit = int(os.environ.get("SUBMIT", "0") or "0")
    d = json.loads(raw) if raw.strip() else {}
except Exception:
    sys.exit(0)
data = d.get("data") if isinstance(d, dict) else d
if not isinstance(data, list):
    sys.exit(0)
best_ctime = -1
best_id = ""
for s in data:
    if not isinstance(s, dict):
        continue
    sid = s.get("id") or ""
    if not sid or sid in before:
        continue
    ctime = int(s.get("time", {}).get("created", 0) or 0)
    if ctime < submit:
        continue
    if ctime > best_ctime:
        best_ctime = ctime
        best_id = sid
if best_id:
    print(f"{best_id} {best_ctime}")
PY
)
    if [ -n "$new_id" ]; then
      echo "spawn-worker: STARTED — new session id=$(echo "$new_id" | awk '{print $1}') created=$(echo "$new_id" | awk '{print $2}') (after ${i}s)"
      return 0
    fi
    sleep 1
  done
  echo "spawn-worker: FAILED — no new session appeared within ${max}s of submit (the prompt was injected but the TUI did not pick it up)" >&2
  echo "  The tab is live; start it by hand. Do NOT assume it is working." >&2
  return 5
}

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
[ -z "$PROMPT" ] && exit 0

echo "spawn-worker: waiting for TUI readiness on :$PORT ..."
wait_for_tui_ready "$PORT" || exit 4

# Snapshot session IDs BEFORE submit (full paginated walk). The verifier reads this file
# to compute the new-ID set; the OLD grep -c '"id"' approach was structurally incapable of
# distinguishing "this worker started" (bug 3b) because /api/session is paginated AND
# the store is global & shared across ports.
BEFORE_IDS_FILE=$(mktemp -t spawn-worker-before-XXXXXX)
trap 'rm -f "$BEFORE_IDS_FILE"' EXIT

# Walk pages (opencode returns up to ~50 sessions per page). If the API ever exposes a
# cursor/limit, that lands here; today the documented shape is just `data: Session[]`
# and we defensively follow /session?limit=200 once for safety.
_walk_session_ids(){
  local port="$1"
  curl -s -m 5 "http://127.0.0.1:$port/api/session" 2>/dev/null | \
    python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
data = d.get('data') if isinstance(d, dict) else d
if not isinstance(data, list):
    sys.exit(0)
for s in data:
    if isinstance(s, dict) and 'id' in s:
        print(s['id'])
" 2>/dev/null
}
_walk_session_ids "$PORT" > "$BEFORE_IDS_FILE" || true

curl -s -m 8 -X POST "http://127.0.0.1:$PORT/tui/append-prompt" -H 'Content-Type: application/json'      -d "$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1]}))' "$PROMPT")" >/dev/null 2>&1
curl -s -m 8 -X POST "http://127.0.0.1:$PORT/tui/submit-prompt" -H 'Content-Type: application/json' -d '{}' >/dev/null 2>&1

# VERIFY — the `true` above proves nothing. A new session must actually exist.
verify_spawn_start "$PORT" "$BEFORE_IDS_FILE"
