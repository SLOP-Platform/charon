#!/usr/bin/env bash
# failover-canary.test.sh — FAIL-ON-REVERT dogfood for FAILOVER-CANARY
# (fleet/failover-canary.sh, design of record fleet/board/FAILOVER-CANARY.md).
#
# GREEN IS NOT PROOF. This SEEDS a real fault of each required class and PROVES
# fleet/failover-canary.sh goes RED on a broken cascade, then GREEN once the
# cascade behaves correctly (flow-canary.test.sh's proven shape).
#
# FULLY HERMETIC / OFFLINE: a local Python stdlib HTTP server stands in for the
# LIVE gateway on 127.0.0.1 (flow-canary.test.sh's fake-gw.py pattern, extended
# to simulate the routing-brain's per-leg cascade decision instead of a single
# fixed served_by). It serves /charon/status (the pool + balance snapshot) and
# /v1/chat/completions (route + X-Charon-Provider / X-Charon-Failover-Reasons),
# computing the cascade from a `faults` map in $SCENARIO that this test rewrites
# between cases — no live network, nothing leaves the box. The REAL
# fleet/failover-canary.sh runs UNMODIFIED against it, driven the same way a
# real Toxiproxy deployment would drive it: FO_SEED_HEAD_CMD / FO_RESTORE_
# HEAD_CMD / FO_SEED_ALLDOWN_CMD / FO_RESTORE_ALLDOWN_CMD hooks that flip the
# fault state (production wires these to Toxiproxy's HTTP control API instead —
# see failover-canary.sh's header comment for the real curl/toxiproxy example;
# this repo's build validated a real downloaded toxiproxy-server binary
# genuinely cuts+restores a connection via its `reset_peer` toxic, confirming
# the ADOPT is real, not aspirational — that validation is not re-run here
# because a downloaded binary would break "no live network" for future offline
# CI runs; the hermetic fake is what's committed and graded).
#
# Covers (one RED-then-GREEN pair per class the ticket names, plus the
# park-exclusion #188 class the ticket's accept criterion (b) requires):
#   (H)     HEALTHY               -> BASELINE clean, exit 0                 [baseline]
#   (C429)  head-429   correct cascade  -> exit 0 GREEN
#   (C429B) head-429   NOT cascaded (bug)-> exit != 0 RED
#   (CTO)   head-timeout(unreachable) correct cascade -> exit 0 GREEN
#   (CTOB)  head-timeout NOT cascaded (bug) -> exit != 0 RED
#   (C500)  head-500   correct NO-cascade relay -> exit 0 GREEN
#   (C500B) head-500   WRONGLY cascaded (bug)   -> exit != 0 RED
#   (AD)    all-legs-down (every leg 429) clean 503 exhaustion -> exit 0 GREEN
#   (ADH)   all-legs-down HANGS (bug)            -> exit != 0 RED (curl timeout caught)
#   (ADR)   all-legs-down raw unstructured passthrough (bug) -> exit != 0 RED
#   (PA)    parked leg ATTEMPTED mid-cascade (#188 bug)      -> exit != 0 RED
#   (PE)    parked leg correctly EXCLUDED from cascade       -> exit 0 GREEN
# Revert-proof: (H) re-run after every seeded fault returns GREEN.
#
# Run:  bash fleet/tests/failover-canary.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
CANARY="$SRC/failover-canary.sh"
[ -f "$CANARY" ] || { echo "FAIL: cannot find $CANARY" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
SCENARIO="$D/scenario.json"
PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"

TIER_TSV="$D/tier-models.tsv"
printf 'strong\tminimax-m3-free\n' > "$TIER_TSV"

# ── the hermetic fake gateway: simulates the routing-brain's cascade ────────
# Reads $SCENARIO fresh on every request. `faults` maps provider -> one of
# "429" | "503" | "500" | "unreachable". Cascade rule mirrors src/charon/
# proxy.py's _EXHAUSTION_STATUSES={429,402,503} + forwarder.py's connection-
# error branch: "429"/"503"/"unreachable" are fail-over-eligible (skip,
# record, continue); "500" is NOT (relay immediately, no cascade, matching
# the real R6 behavior) — UNLESS `force_cascade_on_500` is set (the (C500B)
# bug-injection case, simulating an over-eager regression). Parked/drained
# providers are excluded from the candidate chain BEFORE iteration — UNLESS
# `simulate_park_bug` is set (the (PA) #188 bug-injection case, which instead
# attempts the parked leg mid-cascade exactly like the dead-no-op regression
# class flow-canary.sh's STAGE 3 exists to catch).
cat > "$D/fake-gw.py" <<'PYEOF'
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

SCENARIO = sys.argv[1]

def scenario():
    try:
        with open(SCENARIO) as f: return json.load(f)
    except Exception: return {}

FAILOVER_ELIGIBLE = {"429", "503"}  # + "unreachable" checked separately

class H(BaseHTTPRequestHandler):
    def _send(self, code, body_obj, extra_headers=None):
        body = json.dumps(body_obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/charon/status"):
            sc = scenario()
            head = sc.get("head_model", "minimax-m3-free")
            pool = sc.get("pool", [])
            balance = sc.get("balance", {})
            snap = {"pools": {head: pool}, "providers": {}, "balance": balance,
                    "cooldown_seconds": {}, "usage": {}, "recent_failovers": [],
                    "build_sha": "hermetic-fake"}
            self._send(200, snap)
        else:
            self._send(404, {})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        sc = scenario()
        pool = list(sc.get("pool", []))
        balance = sc.get("balance", {})
        faults = sc.get("faults", {})
        hang_s = float(sc.get("hang_seconds", 0) or 0)
        if hang_s:
            import time
            time.sleep(hang_s)

        parked = set(p for p, v in balance.items()
                     if v.get("parked") or v.get("drained"))
        simulate_park_bug = bool(sc.get("simulate_park_bug", False))
        candidates = pool if simulate_park_bug else [p for p in pool if p not in parked]

        if sc.get("raw_passthrough_bug", False):
            # simulate a broken all-down that relays a raw, unstructured upstream
            # body instead of the gateway's own synthesized error envelope.
            self._send(500, {"some_upstream_field": "raw error, not ours"})
            return

        failovers = []
        for i, p in enumerate(candidates):
            fault = faults.get(p)
            if not fault:
                reasons_hdr = "; ".join(f"{f['provider']}={f['status']}" for f in failovers)
                extra = {"X-Charon-Provider": p}
                if reasons_hdr:
                    extra["X-Charon-Failover-Reasons"] = reasons_hdr
                self._send(200, {"model": "resolved/" + p,
                                  "choices": [{"message": {"role": "assistant", "content": "PONG"}}]},
                            extra)
                return
            force_cascade_500 = sc.get("force_cascade_on_500", False)
            eligible = (fault in FAILOVER_ELIGIBLE) or (fault == "unreachable") or \
                       (fault == "500" and force_cascade_500)
            if not eligible:
                # R6: not fail-over-eligible -> relay this leg's status as-is, NOW,
                # regardless of remaining legs (matches proxy.py/forwarder.py).
                self._send(int(fault), {"error": {"message": f"upstream {p} returned {fault}"}},
                            {"X-Charon-Provider": p})
                return
            failovers.append({"provider": p, "status": fault})
            # continue to next candidate

        # every candidate exhausted
        if failovers and all(f["status"] in ("429", "503") for f in failovers):
            self._send(503, {"error": {"message": "all providers exhausted",
                                        "type": "all_providers_exhausted",
                                        "providers_tried": failovers,
                                        "failover_reasons": [f"{f['provider']}={f['status']}" for f in failovers]}})
        else:
            self._send(502, {"error": {"message": "all upstreams unreachable"}})

    def log_message(self, *a, **k):
        return

HTTPServer(("127.0.0.1", int(sys.argv[2])), H).serve_forever()
PYEOF

python3 -u "$D/fake-gw.py" "$SCENARIO" "$PORT" >"$D/gw.log" 2>&1 &
GW_PID=$!
trap 'kill $GW_PID 2>/dev/null || true; rm -rf "$D"' EXIT
for _ in $(seq 1 50); do
  python3 -c "import socket,sys
s=socket.socket(); s.settimeout(0.2)
try: s.connect(('127.0.0.1', $PORT)); s.close(); sys.exit(0)
except Exception: sys.exit(1)" 2>/dev/null && break
  sleep 0.05
done

# scenario writer: base healthy scenario, override keys via python (jq-free)
write_scenario(){ # <json-overrides>
  python3 - "$SCENARIO" "$1" <<'PY'
import json, sys
base = {
    "head_model": "minimax-m3-free",
    "pool": ["nvidia", "nanogpt", "openrouter", "cline-pass"],
    "faults": {},
    "balance": {
        "nvidia": {"funding_class": 1, "parked": False, "drained": False},
        "nanogpt": {"funding_class": 2, "parked": False, "drained": False},
        "openrouter": {"funding_class": 1, "parked": False, "drained": False},
        "cline-pass": {"funding_class": 2, "parked": False, "drained": False},
    },
}
base.update(json.loads(sys.argv[2]))
with open(sys.argv[1], "w") as f: json.dump(base, f)
PY
}

# fault-hook commands the canary itself `bash -c`-evals — these are what a real
# Toxiproxy deployment would be wired to instead (see failover-canary.sh header).
SEED_HEAD_429="python3 -c \"
import json
d=json.load(open('$SCENARIO')); d.setdefault('faults',{})['nvidia']='429'
json.dump(d, open('$SCENARIO','w'))\""
SEED_HEAD_UNREACHABLE="python3 -c \"
import json
d=json.load(open('$SCENARIO')); d.setdefault('faults',{})['nvidia']='unreachable'
json.dump(d, open('$SCENARIO','w'))\""
SEED_HEAD_500="python3 -c \"
import json
d=json.load(open('$SCENARIO')); d.setdefault('faults',{})['nvidia']='500'
json.dump(d, open('$SCENARIO','w'))\""
CLEAR_HEAD="python3 -c \"
import json
d=json.load(open('$SCENARIO')); d['faults']={}
json.dump(d, open('$SCENARIO','w'))\""
SEED_ALLDOWN_429="python3 -c \"
import json
d=json.load(open('$SCENARIO'))
d['faults']={p:'429' for p in d.get('pool',[])}
json.dump(d, open('$SCENARIO','w'))\""
CLEAR_ALLDOWN="$CLEAR_HEAD"

run_canary(){ # <extra env assigns already exported by caller>
  FO_GATEWAY_URL="http://127.0.0.1:$PORT" \
  FO_TOKEN="hermetic-fake-token" \
  FO_TIER="strong" \
  FO_TIER_TSV="$TIER_TSV" \
  FO_REQ_TIMEOUT_S=3 FO_STATUS_TIMEOUT_S=5 \
    bash "$CANARY" 2>&1
  return "${PIPESTATUS[0]:-$?}"
}
cap(){ CAP_OUT="$(run_canary)"; CAP_RC=$?; }

# ══════════════════════════════════════════════════════════════════════════
# (H) HEALTHY baseline — no fault, no hooks set -> GREEN, exit 0
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{}'
unset FO_SEED_HEAD_CMD FO_RESTORE_HEAD_CMD FO_SEED_ALLDOWN_CMD FO_RESTORE_ALLDOWN_CMD FO_EXPECT_CASCADE FO_EXPECT_STATUS FO_FAULT_LABEL
cap
[ "$CAP_RC" -eq 0 ] && ok "(H) healthy: canary exits 0 (GREEN)" \
                    || bad "(H) healthy: canary exit $CAP_RC (expected 0)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "FAILOVER-CANARY: GREEN" \
  && ok "(H) healthy: prints GREEN verdict" \
  || bad "(H) healthy: no GREEN verdict"
printf '%s' "$CAP_OUT" | grep -q "served-by 'nvidia' is a member of the" \
  && ok "(H) healthy: head-tier leg 'nvidia' confirmed serving" \
  || bad "(H) healthy: baseline did not confirm head serving"

# ══════════════════════════════════════════════════════════════════════════
# (C429) head-429 -> CORRECT cascade -> GREEN
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{}'
export FO_FAULT_LABEL="head-429" FO_EXPECT_CASCADE=1
export FO_SEED_HEAD_CMD="$SEED_HEAD_429" FO_RESTORE_HEAD_CMD="$CLEAR_HEAD"
unset FO_SEED_ALLDOWN_CMD FO_RESTORE_ALLDOWN_CMD
cap
[ "$CAP_RC" -eq 0 ] && ok "(C429) head-429 correct cascade: canary exits 0 (GREEN)" \
                    || bad "(C429) head-429 correct cascade: canary exit $CAP_RC (expected 0)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "served-by moved off the faulted head to 'nanogpt'" \
  && ok "(C429) served-by correctly moved to the next leg 'nanogpt'" \
  || bad "(C429) did not observe the served-by moving to 'nanogpt'"
printf '%s' "$CAP_OUT" | grep -q "names the failed head 'nvidia'" \
  && ok "(C429) X-Charon-Failover-Reasons correctly names 'nvidia' as failed" \
  || bad "(C429) reasons header did not name the failed head"

# ══════════════════════════════════════════════════════════════════════════
# (C429B) head-429 but the cascade is BROKEN (still serves head) -> RED
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{}'
# force_cascade_on_500 unrelated; simulate broken-non-cascade by making the
# fake refuse to skip the faulted head — done by pointing "faults" at a
# provider name that ISN'T actually in the pool, so nvidia (unfaulted from the
# fake's POV) serves normally even though the canary believes it seeded a fault.
SEED_BROKEN_429="python3 -c \"
import json
d=json.load(open('$SCENARIO')); d.setdefault('faults',{})['NOT-IN-POOL']='429'
json.dump(d, open('$SCENARIO','w'))\""
export FO_FAULT_LABEL="head-429-broken" FO_EXPECT_CASCADE=1
export FO_SEED_HEAD_CMD="$SEED_BROKEN_429" FO_RESTORE_HEAD_CMD="$CLEAR_HEAD"
cap
[ "$CAP_RC" -ne 0 ] && ok "(C429B) broken cascade (head not actually faulted): canary exits non-zero (RED)" \
                    || bad "(C429B) broken cascade: canary exited 0 — a non-cascading head was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "cascade did not occur" \
  && ok "(C429B) RED line names the non-cascade" \
  || bad "(C429B) no non-cascade red line"

# ══════════════════════════════════════════════════════════════════════════
# (CTO) head-timeout (connection-level "unreachable") -> correct cascade -> GREEN
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{}'
export FO_FAULT_LABEL="head-timeout" FO_EXPECT_CASCADE=1
export FO_SEED_HEAD_CMD="$SEED_HEAD_UNREACHABLE" FO_RESTORE_HEAD_CMD="$CLEAR_HEAD"
cap
[ "$CAP_RC" -eq 0 ] && ok "(CTO) head-timeout correct cascade: canary exits 0 (GREEN)" \
                    || bad "(CTO) head-timeout correct cascade: canary exit $CAP_RC (expected 0)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "names the failed head 'nvidia'" \
  && ok "(CTO) reasons header names 'nvidia' as unreachable" \
  || bad "(CTO) reasons header missing the unreachable head"

# ══════════════════════════════════════════════════════════════════════════
# (CTOB) head-timeout NOT cascaded (bug) -> RED
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{}'
SEED_BROKEN_UNREACHABLE="python3 -c \"
import json
d=json.load(open('$SCENARIO')); d.setdefault('faults',{})['NOT-IN-POOL']='unreachable'
json.dump(d, open('$SCENARIO','w'))\""
export FO_FAULT_LABEL="head-timeout-broken" FO_EXPECT_CASCADE=1
export FO_SEED_HEAD_CMD="$SEED_BROKEN_UNREACHABLE" FO_RESTORE_HEAD_CMD="$CLEAR_HEAD"
cap
[ "$CAP_RC" -ne 0 ] && ok "(CTOB) broken cascade (timeout not actually seeded): canary exits non-zero (RED)" \
                    || bad "(CTOB) broken cascade: canary exited 0 — NOT caught
$CAP_OUT"

# ══════════════════════════════════════════════════════════════════════════
# (C500) head-500 -> CORRECT no-cascade clean relay -> GREEN
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{}'
export FO_FAULT_LABEL="head-500" FO_EXPECT_CASCADE=0 FO_EXPECT_STATUS=500
export FO_SEED_HEAD_CMD="$SEED_HEAD_500" FO_RESTORE_HEAD_CMD="$CLEAR_HEAD"
cap
[ "$CAP_RC" -eq 0 ] && ok "(C500) head-500 correct no-cascade relay: canary exits 0 (GREEN)" \
                    || bad "(C500) head-500 correct no-cascade relay: canary exit $CAP_RC (expected 0)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "relayed HTTP 500 as-is" \
  && ok "(C500) confirms the clean same-leg 500 relay (no cascade attempted)" \
  || bad "(C500) did not confirm the clean relay"

# ══════════════════════════════════════════════════════════════════════════
# (C500B) head-500 WRONGLY cascaded (over-eager bug) -> RED
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{"force_cascade_on_500": true}'
export FO_FAULT_LABEL="head-500-broken" FO_EXPECT_CASCADE=0 FO_EXPECT_STATUS=500
export FO_SEED_HEAD_CMD="$SEED_HEAD_500" FO_RESTORE_HEAD_CMD="$CLEAR_HEAD"
cap
[ "$CAP_RC" -ne 0 ] && ok "(C500B) over-eager cascade on a non-eligible 500: canary exits non-zero (RED)" \
                    || bad "(C500B) over-eager cascade: canary exited 0 — NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -qE "expected a clean relay of HTTP 500|served-by unexpectedly moved" \
  && ok "(C500B) RED line names the unexpected cascade on a non-eligible status" \
  || bad "(C500B) no red line naming the over-eager cascade"

# ══════════════════════════════════════════════════════════════════════════
# (AD) all-legs-down (every leg 429) -> clean 503 exhaustion -> GREEN
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{}'
unset FO_SEED_HEAD_CMD FO_RESTORE_HEAD_CMD FO_EXPECT_CASCADE FO_EXPECT_STATUS
export FO_FAULT_LABEL="all-legs-down"
export FO_SEED_ALLDOWN_CMD="$SEED_ALLDOWN_429" FO_RESTORE_ALLDOWN_CMD="$CLEAR_ALLDOWN"
cap
[ "$CAP_RC" -eq 0 ] && ok "(AD) all-legs-down clean exhaustion: canary exits 0 (GREEN)" \
                    || bad "(AD) all-legs-down clean exhaustion: canary exit $CAP_RC (expected 0)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "names the exhaustion" \
  && ok "(AD) structured error.message names the exhaustion — loud, not silent" \
  || bad "(AD) no loud-exhaustion confirmation"

# ══════════════════════════════════════════════════════════════════════════
# (ADH) all-legs-down HANGS (bug) -> RED (hang caught, not a timeout-passthrough)
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{"hang_seconds": 6}'
cap
[ "$CAP_RC" -ne 0 ] && ok "(ADH) all-down hang: canary exits non-zero (RED)" \
                    || bad "(ADH) all-down hang: canary exited 0 — a HANG was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "HUNG" \
  && ok "(ADH) RED line explicitly names the HANG (not a generic failure)" \
  || bad "(ADH) no explicit HANG red line"

# ══════════════════════════════════════════════════════════════════════════
# (ADR) all-legs-down raw unstructured passthrough (bug) -> RED
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{"raw_passthrough_bug": true}'
cap
[ "$CAP_RC" -ne 0 ] && ok "(ADR) raw passthrough on all-down: canary exits non-zero (RED)" \
                    || bad "(ADR) raw passthrough: canary exited 0 — NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "looks like a raw passthrough" \
  && ok "(ADR) RED line names the raw-passthrough (no structured error.message)" \
  || bad "(ADR) no raw-passthrough red line"

# ══════════════════════════════════════════════════════════════════════════
# (PA) parked leg ATTEMPTED mid-cascade (#188 bug) -> RED
# ══════════════════════════════════════════════════════════════════════════
# Baseline state is CLEAN (no fault yet, nanogpt parked but never in the cascade
# path until nvidia is faulted) — the fault is applied via the seed hook, same
# as every other case, so the BASELINE stage above sees a genuinely clean run.
write_scenario '{"simulate_park_bug": true,
  "balance": {
    "nvidia": {"funding_class":1,"parked":false,"drained":false},
    "nanogpt": {"funding_class":2,"parked":true,"drained":false},
    "openrouter": {"funding_class":1,"parked":false,"drained":false},
    "cline-pass": {"funding_class":2,"parked":false,"drained":false}}}'
unset FO_SEED_ALLDOWN_CMD FO_RESTORE_ALLDOWN_CMD
export FO_FAULT_LABEL="head-429" FO_EXPECT_CASCADE=1
export FO_SEED_HEAD_CMD="$SEED_HEAD_429" FO_RESTORE_HEAD_CMD="$CLEAR_HEAD"
cap
[ "$CAP_RC" -ne 0 ] && ok "(PA) parked leg attempted mid-cascade: canary exits non-zero (RED)" \
                    || bad "(PA) parked leg attempted: canary exited 0 — #188-class bug NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -qE "DEAD NO-OP|exclusion did not fire" \
  && ok "(PA) RED line names the #188 dead-no-op / non-firing exclusion" \
  || bad "(PA) no #188 park-exclusion red line"

# ══════════════════════════════════════════════════════════════════════════
# (PE) parked leg correctly EXCLUDED from cascade -> GREEN
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{
  "balance": {
    "nvidia": {"funding_class":1,"parked":false,"drained":false},
    "nanogpt": {"funding_class":2,"parked":true,"drained":false},
    "openrouter": {"funding_class":1,"parked":false,"drained":false},
    "cline-pass": {"funding_class":2,"parked":false,"drained":false}}}'
export FO_FAULT_LABEL="head-429" FO_EXPECT_CASCADE=1
export FO_SEED_HEAD_CMD="$SEED_HEAD_429" FO_RESTORE_HEAD_CMD="$CLEAR_HEAD"
cap
[ "$CAP_RC" -eq 0 ] && ok "(PE) parked leg correctly excluded: canary exits 0 (GREEN)" \
                    || bad "(PE) parked leg correctly excluded: canary exit $CAP_RC (expected 0)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "served-by moved off the faulted head to 'openrouter'" \
  && ok "(PE) cascade correctly skipped the parked 'nanogpt' and served 'openrouter'" \
  || bad "(PE) cascade did not skip to 'openrouter' past the parked leg"

# ══════════════════════════════════════════════════════════════════════════
# REVERT PROOF — back to healthy, all hooks cleared -> GREEN again
# ══════════════════════════════════════════════════════════════════════════
write_scenario '{}'
unset FO_SEED_HEAD_CMD FO_RESTORE_HEAD_CMD FO_SEED_ALLDOWN_CMD FO_RESTORE_ALLDOWN_CMD FO_EXPECT_CASCADE FO_EXPECT_STATUS FO_FAULT_LABEL
cap
[ "$CAP_RC" -eq 0 ] && ok "(revert) after every seeded fault, reverting to healthy returns GREEN (exit 0) — the canary is not stuck-red" \
                    || bad "(revert) healthy re-run did NOT return GREEN (exit $CAP_RC)
$CAP_OUT"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL FAILOVER-CANARY DOGFOOD TESTS PASS"
