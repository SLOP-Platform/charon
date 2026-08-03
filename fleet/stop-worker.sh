#!/usr/bin/env bash
# stop-worker.sh <PORT> — stop a spawned opencode worker, gracefully first.
# Ladder: SIGINT -> SIGTERM -> SIGKILL (5 x sleep 0.4 == 2s each stage).
# NOTE: exit codes are NOT guaranteed 0. Processes that do not exit within the 2s
# window escalate to the next signal. A tab with closeOnExit:graceful only
# auto-closes on exit 0 — non-zero exits leave the tab LITTERED. Store is
# SQLite+WAL and reads cleanly after a mid-turn kill; only the in-flight turn
# is lost. There is NO HTTP stop: /tui/execute-command is inert — question closed.
set -uo pipefail
PORT="${1:?usage: stop-worker.sh <PORT>}"
PID=$(ss -lptn "sport = :$PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
[ -n "${PID:-}" ] || { echo "stop-worker: nothing listening on :$PORT"; exit 0; }
echo "stop-worker: :$PORT -> pid $PID"
for sig in INT TERM KILL; do
  kill -"$sig" "$PID" 2>/dev/null
  for _ in 1 2 3 4 5; do
    sleep 0.4
    kill -0 "$PID" 2>/dev/null || break 2
  done
  echo "stop-worker: still alive after SIG$sig, escalating"
done
sleep 0.5
# VERIFY — pid gone AND port refuses. An unverified stop is not a stop.
gone=0; kill -0 "$PID" 2>/dev/null || gone=1
# curl -w '%{http_code}' ALWAYS writes exactly three digits to stdout:
#   * on success, the real HTTP status (200, 500, ...)
#   * on connection refused / timeout / DNS failure, the literal string `000`
# So `-w` already gives us the right code; the old `|| echo 000` was a footgun — on a
# refused connection curl exits non-zero AND prints `000`, so the fallback prints a
# SECOND `000`, the captured value becomes `000000`, the `[ "$code" = "000" ]` test
# fails, and a successful stop reports FAILED (bug 2 — observed live on :47099).
# A successful stop must therefore resolve to exactly the string `000`. STOP_HEALTH_URL
# overrides the URL for the test suite so we can drive refused / answering / 200 paths
# against a stub server without touching the live fleet.
url="${STOP_HEALTH_URL:-http://127.0.0.1:$PORT/api/health}"
code=$(curl -s -m 3 -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || true)
code="${code:-000}"
if [ "$gone" = 1 ] && [ "$code" = "000" ]; then echo "stop-worker: STOPPED (pid gone, port refuses)"; exit 0; fi
echo "stop-worker: FAILED to verify stop (pid_gone=$gone http=$code)" >&2; exit 1
