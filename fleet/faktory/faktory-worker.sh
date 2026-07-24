#!/usr/bin/env bash
# faktory-worker.sh — reserve a charon-run-shaped job, run it, ACK on success / FAIL on error.
#
# Adopt-first: this is the thin worker loop over the Faktory substrate (faktory-client.sh). It does
# NOT implement queueing/retry/DLQ — Faktory owns all of that. The worker only: FETCH → exec the
# job's shell payload (the charon-run.sh invocation, off-Claude) → ACK (rc0) or FAIL (rc!=0).
#
# Usage:
#   faktory-worker.sh [--queue Q] [--once] [--idle-sleep S]
#     --queue Q      queue to reserve from (default: default)
#     --once         process at most one job then exit (exit 0 if a job ran, 3 if queue empty)
#     --idle-sleep S seconds to sleep when the queue is empty in loop mode (default 2)
#
# Job payload contract (jobtype "charon-run"): args is the argv of the command to run. The first
# arg is the executable/command; remaining args are its arguments. Typically:
#     args = ["bash","/home/stack/charon-private/fleet/charon-run.sh", "<cwd>","<outlog>","<brief>","<model1>",...]
# For an opaque single shell-string payload, args = ["<the whole command>"] is run via `bash -c`.
#
# Env: same as faktory-client.sh (FAKTORY_HOST/PORT/PASSWORD/WEB). NEVER routes through Anthropic/Claude
# (the payload is charon-run.sh, which targets the non-Claude 4-LOM gateway).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT="$SCRIPT_DIR/faktory-client.sh"

QUEUE="default"; ONCE=0; IDLE_SLEEP=2
while [ $# -gt 0 ]; do
  case "$1" in
    --queue) QUEUE="$2"; shift 2;;
    --once) ONCE=1; shift;;
    --idle-sleep) IDLE_SLEEP="$2"; shift 2;;
    -h|--help) sed -n '2,25p' "$0"; exit 0;;
    *) echo "faktory-worker: unknown option $1" >&2; exit 2;;
  esac
done

log() { printf '[faktory-worker] %s %s\n' "$(date -u +%FT%TZ)" "$*" >&2; }

# Run one job's payload. Reads the reserved job JSON on stdin. Returns the payload's exit code.
run_payload() {
  local job="$1"
  # Extract argv from the job JSON (python: robust JSON parse, emits NUL-delimited argv).
  local -a argv=()
  while IFS= read -r -d '' a; do argv+=("$a"); done < <(
    FK_JOB="$job" python3 - <<'PY'
import os, json, sys
job=json.loads(os.environ["FK_JOB"])
args=job.get("args",[])
# each element -> its shell token (stringify non-strings)
out=[]
for a in args:
    out.append(a if isinstance(a,str) else json.dumps(a))
# trailing NUL after EVERY element (incl. last) so `read -d ''` in bash captures a
# lone single-element argv (a missing trailing delimiter makes read return rc1 and drop it).
for s in out:
    sys.stdout.buffer.write(s.encode()+b"\0")
PY
  )
  if [ "${#argv[@]}" -eq 0 ]; then
    log "job has empty args; nothing to run"; return 2
  fi
  if [ "${#argv[@]}" -eq 1 ]; then
    # single opaque shell-string payload
    bash -c "${argv[0]}"
  else
    # explicit argv (e.g. bash charon-run.sh <cwd> <out> <brief> <models...>)
    "${argv[@]}"
  fi
}

process_one() {
  local job jid rc
  job="$("$CLIENT" reserve --queue "$QUEUE")" || return 3   # rc3 => queue empty
  [ -n "$job" ] || return 3
  jid="$(FK_JOB="$job" python3 -c 'import os,json;print(json.loads(os.environ["FK_JOB"])["jid"])')"
  log "reserved jid=$jid; running payload"
  run_payload "$job"; rc=$?
  if [ "$rc" -eq 0 ]; then
    "$CLIENT" ack --jid "$jid" && log "ACK jid=$jid (success)" || log "ACK FAILED jid=$jid"
  else
    "$CLIENT" fail --jid "$jid" --msg "payload exited rc=$rc" && log "FAIL jid=$jid (rc=$rc; requeued per policy)"
  fi
  return 0
}

if [ "$ONCE" -eq 1 ]; then
  process_one; exit $?
fi

log "worker starting; queue=$QUEUE"
while true; do
  process_one; rc=$?
  if [ "$rc" -eq 3 ]; then sleep "$IDLE_SLEEP"; fi
done
