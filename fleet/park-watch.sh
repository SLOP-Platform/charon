#!/usr/bin/env bash
# fleet/park-watch.sh — DID A PARK ACTUALLY STOP TRAFFIC? Answer it with a number, not a claim.
#
# WHY THIS EXISTS (measured 2026-08-02): a manager parked six providers via
# `POST /charon/balance {"op":"park"}`. Every call returned `{"ok":true,"parked":true}` — and the
# park DID NOTHING. Proof: `opencode-go` had `served=5833` before the park and `served=5962`
# after. **+129 requests served while "parked".** `/charon/status` exposes NO `parked` field, so
# the API's own success response was the only signal available, and it was wrong.
#
# THE OBSERVABLE: per-provider `served` counters in /charon/status. A genuinely parked provider's
# `served` STOPS INCREMENTING. That delta is the only ground truth available today.
#
# Usage:
#   bash fleet/park-watch.sh                 # snapshot now
#   bash fleet/park-watch.sh --watch 60      # snapshot, wait 60s, re-snapshot, print DELTAS
#
# Exit codes — "could not check" must never read as "park is working":
#   0  ran; deltas printed        2  a provider believed parked SERVED traffic (park is a no-op)
#   8  could not read the gateway (UNKNOWN — NOT a pass)
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCH=0
[ "${1:-}" = "--watch" ] && WATCH="${2:-60}"

# PARKED: the providers a human/park-call believes are parked. Keep in sync by hand until the
# gateway exposes parked state — that gap is ticket GATEWAY-PARK-DRAINED-PROVIDER.
PARKED="${PARK_WATCH_PARKED:-opencode-go opencode-zen openrouter nanogpt cline-pass neuralwatt}"

python3 - "$WATCH" "$PARKED" <<'PY'
import json, subprocess, sys, time, urllib.request

watch = int(sys.argv[1]); parked = set(sys.argv[2].split())

def snap():
    tok = subprocess.run(
        ["bash", "-c",
         "source /home/stack/charon-private/fleet/env-registry.sh >/dev/null 2>&1; bearer_token"],
        capture_output=True, text=True).stdout.strip()
    if not tok:
        print("park-watch: UNKNOWN — could not derive the gateway token.", file=sys.stderr)
        sys.exit(8)
    req = urllib.request.Request("http://10.0.1.60:8080/charon/status",
                                 headers={"Authorization": "Bearer " + tok})
    try:
        body = urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print(f"park-watch: UNKNOWN — gateway unreadable ({e}). NOT reporting parks healthy.",
              file=sys.stderr)
        sys.exit(8)
    return {k: v.get("served", 0) for k, v in json.loads(body).get("providers", {}).items()}

a = snap()
if not watch:
    print("  %-14s %9s  %s" % ("provider", "served", "believed-parked"))
    for k in sorted(a):
        print("  %-14s %9s  %s" % (k, a[k], "PARKED" if k in parked else ""))
    print("\n  Re-run with --watch <sec> to get DELTAS. A parked provider's served must NOT move.")
    sys.exit(0)

print(f"  sampling {watch}s ...")
time.sleep(watch)
b = snap()
bad = []
print("  %-14s %9s %9s %8s  %s" % ("provider", "before", "after", "delta", "verdict"))
for k in sorted(set(a) | set(b)):
    d = b.get(k, 0) - a.get(k, 0)
    v = ""
    if k in parked:
        v = "⛔ PARK IS A NO-OP — served while parked" if d > 0 else "ok (no traffic)"
        if d > 0:
            bad.append((k, d))
    print("  %-14s %9s %9s %+8d  %s" % (k, a.get(k, 0), b.get(k, 0), d, v))

if bad:
    print("\npark-watch: %d provider(s) SERVED TRAFFIC WHILE BELIEVED PARKED:" % len(bad),
          file=sys.stderr)
    for k, d in bad:
        print(f"  {k}: +{d} requests", file=sys.stderr)
    print("The park API returns ok:true regardless — do NOT trust it. See "
          "GATEWAY-PARK-DRAINED-PROVIDER.", file=sys.stderr)
    sys.exit(2)
print("\npark-watch: no believed-parked provider served traffic in this window.")
PY
