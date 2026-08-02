#!/usr/bin/env bash
# fleet/checks/sg-worker-liveness.sh — is each SG worker session actually PROGRESSING?
#
# WHY THIS EXISTS (operator, 2026-08-02): five SG tabs were launched and the operator saw five
# IDLE opencode TUIs. The work WAS running — but headlessly, in API-created sessions the TUI does
# not display — and the manager had no way to tell the difference. The operator asked the right
# question: "not hearing from them didn't trigger a warning for you to monitor them?"
#
# THE FAILURE CLASS: /api/health returning {"healthy":true} proves the SERVER is up. It proves
# NOTHING about whether a session is making progress. A launch that is verified only by /api/health
# is the same green-is-not-proof mistake this rig documents everywhere else. Liveness must be
# measured on the WORK, not on the container that hosts it.
#
# WHAT IT MEASURES: for every session with token activity, how long since `time.updated` moved.
# A session whose updated timestamp is older than STALL_SEC is STALLED and is reported LOUD.
#
# EXIT CODES — deliberately distinct, because "could not check" must never read as "all fine":
#   0  every active session is progressing
#   1  at least one session is STALLED (findings printed)
#   8  could not reach ANY worker port / unparseable response — status UNKNOWN, not healthy
set -uo pipefail

PORTS="${SG_PORTS:-4101 4102 4103 4104 4105}"
STALL_SEC="${SG_STALL_SEC:-900}"

python3 - "$STALL_SEC" $PORTS <<'PY'
import json, sys, time, urllib.request

stall = int(sys.argv[1]); ports = [int(p) for p in sys.argv[2:]]
rows, reached = [], False
for p in ports:
    try:
        raw = urllib.request.urlopen(f"http://127.0.0.1:{p}/api/session", timeout=5).read()
        rows = json.loads(raw).get("data", [])
        reached = True
        break          # ports share one session store; first reachable port is authoritative
    except Exception:
        continue

if not reached:
    print("sg-worker-liveness: UNKNOWN — no worker port answered. NOT reporting healthy.",
          file=sys.stderr)
    sys.exit(8)

now = time.time() * 1000
active = [s for s in rows if s.get("tokens", {}).get("input", 0)]
if not active:
    print("sg-worker-liveness: UNKNOWN — server up but ZERO sessions have token activity. "
          "A launched worker that never consumed a token did not start.", file=sys.stderr)
    sys.exit(8)

stalled = []
for s in active:
    age = (now - s.get("time", {}).get("updated", 0)) / 1000.0
    if age > stall:
        stalled.append((age, s))

active.sort(key=lambda x: x.get("time", {}).get("updated", 0), reverse=True)
print(f"sg-worker-liveness: {len(active)} active session(s), "
      f"{len(stalled)} stalled (threshold {stall}s)")
for s in active[:6]:
    age = (now - s.get("time", {}).get("updated", 0)) / 1000.0
    t = s.get("tokens", {})
    print(f"   {age:7.0f}s  in={t.get('input',0):>7} out={t.get('output',0):>6} "
          f"${s.get('cost',0):.3f}  {str(s.get('title'))[:44]}")

if stalled:
    for age, s in sorted(stalled, reverse=True):
        print(f"STALLED[{age:.0f}s] {str(s.get('title'))[:60]} — no progress; "
              f"investigate or relaunch", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PY
