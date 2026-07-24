#!/usr/bin/env bash
# faktory-client.sh — the ONE durable job/lease substrate CLI (Faktory adoption).
#
# ANCHOR CONTRACT (CLAIM-LEASE-EXACTLY-ONCE / T1 codes against THIS surface — do not drift):
#   faktory-client.sh <cmd> [args]  ; exit 0 success / non-zero failure
#     push    --queue Q --jobtype T --jid <ticket-id> --arg <json> [--reserve-for S] [--retry N]
#             # enqueue; prints the jid on stdout
#     reserve --queue Q [--timeout S]
#             # FETCH one job; prints job JSON {jid,args,...} on stdout, or empty + rc1 if none
#     ack     --jid <id>
#             # terminal success; the job is durably GONE (survives container restart)
#     fail    --jid <id> [--msg M]
#             # terminal fail; requeues per the job's reserve_for / retry policy
#     info    --jid <id>
#             # prints the job's current SET/state (enqueued:<q>|scheduled|retries|dead|working),
#             # rc1 if the jid is absent from all live sets (used by T1's idempotent-enqueue check)
#
# Payload convention: jobtype "charon-run", args = the charon-run.sh invocation. reserve_for default 1800s.
# Durability: an ACKed jid MUST NOT be re-fetchable after container recreation (RDB volume mount).
#
# WHY a wrapper (adopt-first, no reinvented queue): Faktory (contribsys/faktory, single ~15MB
# container, embedded Redis-protocol RDB at /root/.faktory/db) IS the queue + lease + retry + DLQ.
# This script is a thin, contract-shaped shell surface over Faktory's plaintext wire protocol
# (HELLO/PUSH/FETCH/ACK/FAIL/INFO) — it does NOT implement any queue logic itself.
#
# Config (env; no secrets committed):
#   FAKTORY_HOST      default 10.0.1.60   (4-LOM — where the durable server runs)
#   FAKTORY_PORT      default 7419        (protocol port)
#   FAKTORY_PASSWORD  required iff the server was started with a password (ours is)
#   FAKTORY_WEB       default http://$FAKTORY_HOST:7420  (web UI; sole OSS read surface for `info --jid`)
#
# `info` mechanism note: OSS Faktory has NO wire-protocol per-jid query (the TRACK command is
# Enterprise-only). The authenticated Web UI is the real, non-destructive per-job read surface,
# so `info` scans the live sets (enqueued queues + scheduled/retries/dead/busy) via the Web UI.
set -euo pipefail

FAKTORY_HOST="${FAKTORY_HOST:-10.0.1.60}"
FAKTORY_PORT="${FAKTORY_PORT:-7419}"
FAKTORY_WEB="${FAKTORY_WEB:-http://${FAKTORY_HOST}:7420}"
FAKTORY_PASSWORD="${FAKTORY_PASSWORD:-}"

die() { printf 'faktory-client: %s\n' "$*" >&2; exit 2; }

# ── wire-protocol core (python does socket I/O + the iterated-sha256 HELLO handshake;
#    pure bash cannot do 6091 rounds of sha256 in one process). CLI/exit-code surface stays bash.
_wire() {
  # $1 = op (push|fetch|ack|fail); structured payload via env FK_JSON / FK_QUEUE / FK_TIMEOUT.
  FK_OP="$1" FK_HOST="$FAKTORY_HOST" FK_PORT="$FAKTORY_PORT" FK_PW="$FAKTORY_PASSWORD" \
  python3 - <<'PY'
import os, sys, json, socket, hashlib
host=os.environ["FK_HOST"]; port=int(os.environ["FK_PORT"]); pw=os.environ.get("FK_PW","")
op=os.environ["FK_OP"]
try:
    s=socket.create_connection((host,port),timeout=15); s.settimeout(15)
except OSError as e:
    sys.stderr.write("connect failed: %s\n"%e); sys.exit(3)
f=s.makefile("rwb")
def readline():
    ln=f.readline()
    if not ln: sys.stderr.write("connection closed by server\n"); sys.exit(3)
    return ln.decode("utf-8","replace").rstrip("\r\n")
def send(x): f.write((x+"\r\n").encode()); f.flush()
def expect_ok(ctx):
    r=readline()
    if not r.startswith("+"): sys.stderr.write("%s failed: %s\n"%(ctx,r)); sys.exit(1)
    return r
# HELLO handshake
hi=readline()
if not hi.startswith("+HI"): sys.stderr.write("bad greeting: %s\n"%hi); sys.exit(3)
meta=json.loads(hi[3:].strip())
hello={"v":meta.get("v",2),"hostname":socket.gethostname(),"wid":"faktory-client-%d"%os.getpid(),
       "pid":os.getpid(),"labels":["faktory-client"]}
salt=meta.get("s")
if salt:
    if not pw: sys.stderr.write("server requires a password; set FAKTORY_PASSWORD\n"); sys.exit(3)
    h=(pw+salt).encode()
    for _ in range(int(meta.get("i",1))): h=hashlib.sha256(h).digest()
    hello["pwdhash"]=h.hex()
send("HELLO "+json.dumps(hello)); expect_ok("HELLO")

if op=="push":
    job=json.loads(os.environ["FK_JSON"])
    send("PUSH "+json.dumps(job)); expect_ok("PUSH")
    print(job["jid"])
elif op=="fetch":
    q=os.environ.get("FK_QUEUE","default")
    send("FETCH "+q)
    hdr=readline()
    if hdr.startswith("$"):
        n=int(hdr[1:])
        if n<0:            # $-1 → no job available
            sys.exit(1)
        data=f.read(n); f.read(2)   # payload + trailing CRLF
        sys.stdout.write(data.decode("utf-8","replace")+"\n")
    elif hdr in ("*-1","$-1","*0"):
        sys.exit(1)
    else:
        sys.stderr.write("unexpected FETCH reply: %s\n"%hdr); sys.exit(3)
elif op=="ack":
    send("ACK "+json.dumps({"jid":os.environ["FK_JID"]})); expect_ok("ACK")
elif op=="fail":
    body={"jid":os.environ["FK_JID"],"errtype":"ShellNonZeroExit",
          "message":os.environ.get("FK_MSG","job failed")}
    send("FAIL "+json.dumps(body)); expect_ok("FAIL")
else:
    sys.stderr.write("unknown op %s\n"%op); sys.exit(2)
try: send("END")
except Exception: pass
s.close()
PY
}

cmd_push() {
  local queue="default" jobtype="charon-run" jid="" reserve_for="1800" retry="25"
  local -a rawargs=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --queue) queue="$2"; shift 2;;
      --jobtype) jobtype="$2"; shift 2;;
      --jid) jid="$2"; shift 2;;
      --arg) rawargs+=("$2"); shift 2;;
      --reserve-for) reserve_for="$2"; shift 2;;
      --retry) retry="$2"; shift 2;;
      *) die "push: unknown option $1";;
    esac
  done
  [ -n "$jid" ] || die "push: --jid is required"
  local job
  job="$(FK_QUEUE="$queue" FK_JOBTYPE="$jobtype" FK_JID="$jid" FK_RF="$reserve_for" FK_RETRY="$retry" \
        FK_ARGS_NL="$(printf '%s\n' "${rawargs[@]+"${rawargs[@]}"}")" \
        python3 - <<'PY'
import os, json
raw=os.environ.get("FK_ARGS_NL","")
args=[]
for line in raw.split("\n"):
    if line=="": continue
    try: args.append(json.loads(line))
    except Exception: args.append(line)
job={"jid":os.environ["FK_JID"],"jobtype":os.environ["FK_JOBTYPE"],
     "queue":os.environ["FK_QUEUE"],"args":args,
     "retry":int(os.environ["FK_RETRY"]),"reserve_for":int(os.environ["FK_RF"])}
print(json.dumps(job))
PY
)"
  FK_JSON="$job" _wire push
}

cmd_reserve() {
  local queue="default" timeout=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --queue) queue="$2"; shift 2;;
      --timeout) timeout="$2"; shift 2;;   # accepted for contract-compat; Faktory FETCH blocks ~2s
      *) die "reserve: unknown option $1";;
    esac
  done
  FK_QUEUE="$queue" FK_TIMEOUT="$timeout" _wire fetch
}

cmd_ack() {
  local jid=""
  while [ $# -gt 0 ]; do
    case "$1" in --jid) jid="$2"; shift 2;; *) die "ack: unknown option $1";; esac
  done
  [ -n "$jid" ] || die "ack: --jid is required"
  FK_JID="$jid" _wire ack
}

cmd_fail() {
  local jid="" msg="job failed"
  while [ $# -gt 0 ]; do
    case "$1" in
      --jid) jid="$2"; shift 2;;
      --msg) msg="$2"; shift 2;;
      *) die "fail: unknown option $1";;
    esac
  done
  [ -n "$jid" ] || die "fail: --jid is required"
  FK_JID="$jid" FK_MSG="$msg" _wire fail
}

# info --jid <id>: report the live SET the jid is in, rc1 if absent. Real, non-destructive read
# via the authenticated Web UI (the only OSS per-job read surface — see header note).
cmd_info() {
  local jid=""
  while [ $# -gt 0 ]; do
    case "$1" in --jid) jid="$2"; shift 2;; *) die "info: unknown option $1";; esac
  done
  [ -n "$jid" ] || die "info: --jid is required"
  local auth=(); [ -n "$FAKTORY_PASSWORD" ] && auth=(-u ":$FAKTORY_PASSWORD")
  # discover live queue names via the wire INFO command (aggregate stats include queue map)
  local queues
  queues="$(FK_HOST="$FAKTORY_HOST" FK_PORT="$FAKTORY_PORT" FK_PW="$FAKTORY_PASSWORD" python3 - <<'PY'
import os,sys,json,socket,hashlib
host=os.environ["FK_HOST"];port=int(os.environ["FK_PORT"]);pw=os.environ.get("FK_PW","")
try: s=socket.create_connection((host,port),timeout=15)
except OSError: sys.exit(0)
f=s.makefile("rwb")
def rl(): return f.readline().decode().rstrip("\r\n")
hi=rl(); meta=json.loads(hi[3:].strip())
hello={"v":meta.get("v",2),"hostname":"info","wid":"info-%d"%os.getpid(),"pid":os.getpid(),"labels":["info"]}
salt=meta.get("s")
if salt:
    h=(pw+salt).encode()
    for _ in range(int(meta.get("i",1))): h=hashlib.sha256(h).digest()
    hello["pwdhash"]=h.hex()
f.write(("HELLO "+json.dumps(hello)+"\r\n").encode()); f.flush(); rl()
f.write(b"INFO\r\n"); f.flush()
hdr=rl()
if hdr.startswith("$"):
    n=int(hdr[1:]); data=f.read(n).decode()
    info=json.loads(data)
    print(" ".join((info.get("faktory",{}).get("queues") or {}).keys()))
s.close()
PY
)"
  # scan enqueued queues first, then the standard sets
  local q page
  for q in $queues default; do
    page="$(curl -fsS "${auth[@]}" "$FAKTORY_WEB/queues/$q" 2>/dev/null || true)"
    if printf '%s' "$page" | grep -qF -- "$jid"; then echo "enqueued:$q"; return 0; fi
  done
  local set url
  for set in scheduled:scheduled retries:retries dead:morgue working:busy; do
    url="${set#*:}"; page="$(curl -fsS "${auth[@]}" "$FAKTORY_WEB/$url" 2>/dev/null || true)"
    if printf '%s' "$page" | grep -qF -- "$jid"; then echo "${set%%:*}"; return 0; fi
  done
  return 1
}

main() {
  [ $# -ge 1 ] || die "usage: faktory-client.sh <push|reserve|ack|fail|info> [args]"
  local cmd="$1"; shift
  case "$cmd" in
    push) cmd_push "$@";;
    reserve) cmd_reserve "$@";;
    ack) cmd_ack "$@";;
    fail) cmd_fail "$@";;
    info) cmd_info "$@";;
    -h|--help|help) sed -n '2,40p' "$0";;
    *) die "unknown command: $cmd";;
  esac
}
main "$@"
