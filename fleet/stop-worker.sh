#!/usr/bin/env bash
# stop-worker.sh <PORT> — stop a spawned opencode worker, gracefully first.
# Verified ladder: SIGINT -> SIGTERM -> SIGKILL. INT/TERM exit 0 in <1s, port refuses, proxy child
# reaped, and the WT tab AUTO-CLOSES (closeOnExit: graceful). SIGKILL exits 9 and LEAVES TAB LITTER,
# so it is a fallback only. Store is SQLite+WAL and reads cleanly after a mid-turn kill; only the
# in-flight turn is lost. There is NO HTTP stop: /tui/execute-command is inert even with real
# dot-form ids (app.exit, session.interrupt) — question closed.
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
code=$(curl -s -m 3 -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/health" 2>/dev/null || echo 000)
if [ "$gone" = 1 ] && [ "$code" = "000" ]; then echo "stop-worker: STOPPED (pid gone, port refuses)"; exit 0; fi
echo "stop-worker: FAILED to verify stop (pid_gone=$gone http=$code)" >&2; exit 1
