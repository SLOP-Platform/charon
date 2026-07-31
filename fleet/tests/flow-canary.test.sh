#!/usr/bin/env bash
# flow-canary.test.sh — FAIL-ON-REVERT dogfood for FLOW-CANARY
# (fleet/flow-canary.sh, design of record fleet/board/FLOW-CANARY.md).
#
# GREEN IS NOT PROOF. This is the mandatory e2e-dogfood the ticket demands:
# SEED a real fault of each observable-effect class and PROVE the canary goes
# RED on it, then GREEN when reverted. A canary that only passes the happy path
# is worthless — money-path + it's the proactive guard, so a fake-green is
# worse than none.
#
# FULLY HERMETIC / OFFLINE: a local Python stdlib HTTP server stands in for the
# LIVE gateway on 127.0.0.1 (same pattern as fleet/tests/leg-preflight.test.sh's
# section (i) real-urllib fake). It serves BOTH /charon/status (the observable
# snapshot the canary asserts against) and /v1/chat/completions (the route +
# headers). Every fault is seeded by rewriting a SCENARIO json the fake reads
# fresh on each request — no live network, nothing leaves the box. The REAL
# fleet/flow-canary.sh is run UNMODIFIED against it via its env overrides.
#
# Covers (one RED-then-GREEN pair per assertion class the ticket names):
#   (H)  HEALTHY               -> all four stages GREEN, exit 0            [baseline]
#   (R1) MIS-ROUTE             -> served leg not in the pool               -> ROUTE RED
#   (R2a) FREE-FIRST VIOLATION -> a lower-priority leg serves while a      -> ROUTE RED
#        higher-priority non-parked candidate is skipped (PAYG over class-1)
#   (R2b) NO CRY-WOLF          -> a sanctioned class-3 drain-then-park leg -> GREEN
#        serving as the best candidate (the OLD fc-in-{1,2} model false-RED'd
#        this; the SSOT order 1<3<2<4 ranks class-3 second)
#   (M)  INERT METER (#167)    -> served counter does not advance          -> METER RED
#   (M2) DRAINING FREE RIDE    -> a class-3 drain leg advances served but  -> METER RED
#        cost stays 0 (the OLD >=0 check was decorative; FIX-3 asserts >0)
#   (P1) PARKED-SERVED (#188)  -> the served leg is itself parked          -> PARK RED
#   (P2) PARKED-ATTEMPTED(#188)-> a parked leg appears in the failover path-> PARK RED
#   (P3) VACUOUS-PARK POSITIVE -> a parked provider NOT in the head-model  -> PARK RED
#        pool claims "EXCLUDED" (vacuous — FIX-4 downgrades it from GREEN)
#   (C1) STRAY `standard`      -> tier ranks carry a non-canonical tier    -> CONFIG RED
#   (C2) UNSERVED HEAD MODEL   -> the tier head model is not in any pool   -> CONFIG RED
# Each REDs, and reverting the single seeded field returns the canary to GREEN
# (the (H) baseline re-run after each proves the revert).
#
# Run:  bash fleet/tests/flow-canary.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
CANARY="$SRC/flow-canary.sh"
[ -f "$CANARY" ] || { echo "FAIL: cannot find $CANARY" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
SCENARIO="$D/scenario.json"
STATE="$D/meter-state.json"
PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"

# ── fixture: tier-models.tsv (head model = minimax-m3-free) ─────────────────
TIER_TSV="$D/tier-models.tsv"
printf 'economy\tdeepseek-v4-flash-free,gpt-5.4-nano\n' >  "$TIER_TSV"
printf 'strong\tminimax-m3-free,deepseek-v4-flash,glm-5.2\n' >> "$TIER_TSV"
printf 'frontier\tdeepseek-v4-pro,glm-5.2\n' >> "$TIER_TSV"

# ── fixture: `charon tier ranks` stand-ins ──────────────────────────────────
RANKS_GOOD="$D/ranks-good.sh"; cat > "$RANKS_GOOD" <<'EOF'
#!/usr/bin/env bash
printf 'economy 1\nstrong 2\nfrontier 3\n'
EOF
RANKS_STANDARD="$D/ranks-standard.sh"; cat > "$RANKS_STANDARD" <<'EOF'
#!/usr/bin/env bash
printf 'economy 1\nstrong 2\nfrontier 3\nstandard 2\n'
EOF
chmod +x "$RANKS_GOOD" "$RANKS_STANDARD"

# ── the hermetic fake gateway ───────────────────────────────────────────────
# Reads $SCENARIO fresh on every request; persists a per-provider served/cost
# counter to $STATE and advances it on each completion UNLESS the scenario pins
# meter_inert=true. This is the observable surface the canary asserts on.
cat > "$D/fake-gw.py" <<'PYEOF'
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

SCENARIO = sys.argv[1]
STATE = sys.argv[2]

def load(p, default):
    try:
        with open(p) as f: return json.load(f)
    except Exception:
        return default

def scenario():
    return load(SCENARIO, {})

def state():
    return load(STATE, {})

def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f: json.dump(s, f)
    os.replace(tmp, STATE)

class H(BaseHTTPRequestHandler):
    def _send(self, code, body_bytes, extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self):
        if self.path.startswith("/charon/status"):
            sc = scenario()
            st = state()
            head = sc.get("head_model", "minimax-m3-free")
            pool = sc.get("pool", ["nvidia", "nanogpt", "openrouter", "cline-pass"])
            balance = sc.get("balance", {})
            providers = {}
            for p, v in st.items():
                providers[p] = {"served": v.get("served", 0), "cost": v.get("cost", 0.0),
                                "failed": 0, "errors": 0, "last_status": 200}
            snap = {
                "pools": {head: pool},
                "providers": providers,
                "cooldown_seconds": {},
                "usage": {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
                "recent_failovers": [],
                "build_sha": "hermetic-fake",
                "balance": balance,
            }
            self._send(200, json.dumps(snap).encode())
        else:
            self._send(404, b"{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        sc = scenario()
        served_by = sc.get("served_by", "openrouter")
        reasons = sc.get("failover_reasons", "")
        resolved = sc.get("resolved_model", "minimax/minimax-m3")
        # advance the meter for the SERVED leg unless the scenario pins it inert.
        # `cost_inert` advances the served counter ONLY (for FIX-3: a draining
        # leg whose cost-delta stays 0 — the fake-green the old >=0 asserted).
        if not sc.get("meter_inert", False):
            st = state()
            cell = st.get(served_by, {"served": 0, "cost": 0.0})
            cell["served"] = cell.get("served", 0) + 1
            if not sc.get("cost_inert", False):
                cell["cost"] = round(cell.get("cost", 0.0) + 1e-5, 8)
            st[served_by] = cell
            save_state(st)
        body = json.dumps({
            "model": resolved,
            "choices": [{"message": {"role": "assistant", "content": "PONG"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
        }).encode()
        extra = {"X-Charon-Provider": served_by}
        if reasons:
            extra["X-Charon-Failover-Reasons"] = reasons
        self._send(200, body, extra)

    def log_message(self, *a, **k):
        return

HTTPServer(("127.0.0.1", int(sys.argv[3])), H).serve_forever()
PYEOF

python3 -u "$D/fake-gw.py" "$SCENARIO" "$STATE" "$PORT" >"$D/gw.log" 2>&1 &
GW_PID=$!
trap 'kill $GW_PID 2>/dev/null || true; rm -rf "$D"' EXIT
# wait for the fake to accept connections
for _ in $(seq 1 50); do
  python3 -c "import socket,sys
s=socket.socket(); s.settimeout(0.2)
try: s.connect(('127.0.0.1', $PORT)); s.close(); sys.exit(0)
except Exception: sys.exit(1)" 2>/dev/null && break
  sleep 0.05
done

# scenario writer: base healthy scenario, override keys via jq-free python
write_scenario(){ # <json-overrides>
  python3 - "$SCENARIO" "$1" <<'PY'
import json, sys
base = {
    "head_model": "minimax-m3-free",
    "pool": ["nvidia", "openrouter", "huggingface", "cline-pass"],
    "served_by": "openrouter",
    "failover_reasons": "cline-pass=429",
    "resolved_model": "minimax/minimax-m3",
    "meter_inert": False,
    "balance": {
        "nvidia": {"funding_class": 1, "parked": False, "drained": False},
        "nanogpt": {"funding_class": 2, "parked": False, "drained": False},
        "openrouter": {"funding_class": 1, "parked": False, "drained": False},
        "cline-pass": {"funding_class": 2, "parked": False, "drained": False},
        "deepseek": {"funding_class": 3, "parked": False, "drained": False},
        "huggingface": {"funding_class": 1, "parked": True, "drained": False},
    },
}
base.update(json.loads(sys.argv[2]))
with open(sys.argv[1], "w") as f: json.dump(base, f)
PY
}

# The funding-class priority SSOT. The canary reads
# `charon.routing_policy._FUNDING_CLASS_ORDER` live; the hermetic dogfood pins
# the known-good order (1<3<2<4) so it never depends on a `charon` install in
# the test box. This is the SAME order the live SSOT defines — re-deriving it
# here is NOT reimplementation, it is a hermetic pin of the SSOT's value (the
# canary's _funding_order_json prefers the live import; this override only
# fires in the dogfood).
FC_ORDER_JSON='{"1":0,"3":1,"2":2,"4":3,"None":5}'

# run the REAL canary against the fake, ranks stand-in selectable
run_canary(){ # <ranks-script>
  FC_GATEWAY_URL="http://127.0.0.1:$PORT" \
  FC_TOKEN="hermetic-fake-token" \
  FC_TIER="strong" \
  FC_TIER_TSV="$TIER_TSV" \
  FC_TIER_RANKS_CMD="bash ${1:-$RANKS_GOOD}" \
  FC_FUNDING_ORDER_JSON="$FC_ORDER_JSON" \
  FC_NONCE="fixed-nonce" \
  FC_REQ_TIMEOUT_S=10 FC_STATUS_TIMEOUT_S=5 \
    bash "$CANARY" 2>&1
  return "${PIPESTATUS[0]:-$?}"
}
# capture output + rc without a subshell eating the code
cap(){ CAP_OUT="$(run_canary "$1")"; CAP_RC=$?; }

# ── (H) HEALTHY baseline -> GREEN, exit 0 ───────────────────────────────────
write_scenario '{}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -eq 0 ] && ok "(H) healthy scenario: canary exits 0 (GREEN)" \
                    || bad "(H) healthy scenario: canary exit $CAP_RC (expected 0)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "FLOW-CANARY: GREEN" \
  && ok "(H) healthy scenario: prints GREEN verdict" \
  || bad "(H) healthy scenario: no GREEN verdict"
printf '%s' "$CAP_OUT" | grep -q "advanced by 1" \
  && ok "(H) healthy: meter observed a served-count advance (not inert)" \
  || bad "(H) healthy: meter did not observe an advance"

# ── (R1) MIS-ROUTE -> served leg not in pool -> ROUTE RED ───────────────────
write_scenario '{"served_by": "deepinfra", "failover_reasons": ""}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -ne 0 ] && ok "(R1) mis-route: canary exits non-zero (RED)" \
                    || bad "(R1) mis-route: canary exited 0 — a MIS-ROUTE was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "MIS-ROUTE" \
  && ok "(R1) mis-route: RED line names MIS-ROUTE (served leg not in pool)" \
  || bad "(R1) mis-route: no MIS-ROUTE red line"

# ── (R2a) FREE-FIRST VIOLATION -> class-4 PAYG serves over an available ───
#   class-1 free leg (a REAL priority-order violation, NOT the old fc-in-{1,2}
#   model that cried-wolf on a sanctioned class-3 drain leg). 'kobold' is PAYG
#   (fc4, SSOT order 3); 'nvidia' (fc1, order 0) is in the pool and NOT parked
#   — a higher-priority non-parked candidate was skipped -> ROUTE RED.
write_scenario '{"pool": ["nvidia", "kobold"], "served_by": "kobold", "failover_reasons": "", "balance": {
  "nvidia": {"funding_class": 1, "parked": false, "drained": false},
  "kobold": {"funding_class": 4, "parked": false, "drained": false}}}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -ne 0 ] && ok "(R2a) free-first: canary exits non-zero (RED)" \
                    || bad "(R2a) free-first: canary exited 0 — a REAL priority-order violation (PAYG over class-1 free) was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "free-first ordering violated" \
  && ok "(R2a) free-first: RED line names the free-first violation (PAYG fc4 served over an available class-1)" \
  || bad "(R2a) free-first: no free-first red line"

# ── (R2b) NO CRY-WOLF -> a sanctioned class-3 drain-then-park leg serves ────
#   while NO higher-priority non-parked candidate exists -> GREEN.
#   The OLD canary hardcoded `fc∈{1,2}=free` and would RED a class-3 leg here —
#   a false-RED on a sanctioned drain. The SSOT order (1<3<2<4) ranks class-3
#   SECOND; 'deepseek' (fc3) is the only keyed/non-parked candidate in this
#   pool (the class-4 PAYG leg is also non-parked but LOWER priority), so a
#   class-3 leg serving is the free-first pick — NOT a violation.
write_scenario '{"pool": ["deepseek", "kobold"], "served_by": "deepseek", "failover_reasons": "", "balance": {
  "deepseek": {"funding_class": 3, "parked": false, "drained": false},
  "kobold": {"funding_class": 4, "parked": false, "drained": false}}}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -eq 0 ] && ok "(R2b) no-cry-wolf: a sanctioned class-3 drain-then-park leg serving returns GREEN (not false-RED)" \
                    || bad "(R2b) no-cry-wolf: canary exit $CAP_RC — the canary CRIED-WOLF on a sanctioned class-3 drain leg (the OLD fc-in-{1,2} model re-derived instead of reading the SSOT)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "FLOW-CANARY: GREEN" \
  && ok "(R2b) no-cry-wolf: prints GREEN verdict for a class-3-serving run" \
  || bad "(R2b) no-cry-wolf: no GREEN verdict for a sanctioned class-3 leg
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "free-first.*highest-priority non-parked candidate" \
  && ok "(R2b) no-cry-wolf: free-first GREEN line confirms the SSOT order was respected for a class-3 drain leg" \
  || bad "(R2b) no-cry-wolf: free-first did not confirm the SSOT order applied to a class-3 leg
$CAP_OUT"

# ── (M) INERT METER (#167) -> served counter flat -> METER RED ──────────────
write_scenario '{"meter_inert": true}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -ne 0 ] && ok "(M) inert meter: canary exits non-zero (RED)" \
                    || bad "(M) inert meter: canary exited 0 — an INERT METER was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "INERT METER" \
  && ok "(M) inert meter: RED line names INERT METER (#167 class)" \
  || bad "(M) inert meter: no INERT METER red line"

# ── (M2) DRAINING-LEG FREE RIDE (#167/ISSUE) -> cost-delta stays 0 on a ─────
#   class-3 drain-then-park leg while the served counter advances. The OLD
#   canary's cost-delta check was `>= 0` (decorative) — it would have GREEN'd a
#   draining leg that took a free ride. FIX-3 asserts `> 0` for a draining (fc3
#   / drained) leg, so a paying leg with a flat cost now METER-REDs.
#   Pool is just the fc3 leg (so free-first GREENs — it's the only candidate);
#   cost_inert=True makes the fake advance served but NOT cost.
write_scenario '{"pool": ["deepseek"], "served_by": "deepseek", "failover_reasons": "",
  "cost_inert": true, "balance": {
    "deepseek": {"funding_class": 3, "parked": false, "drained": false}}}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -ne 0 ] && ok "(M2) draining-free-ride: canary exits non-zero (RED)" \
                    || bad "(M2) draining-free-ride: canary exited 0 — a class-3 leg taking a free ride (cost-delta 0) was NOT caught (the old decorative >=0 would have passed)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "free ride" \
  && ok "(M2) draining-free-ride: RED line names the draining-leg free-ride (cost-delta not >0)" \
  || bad "(M2) draining-free-ride: no free-ride red line"

# ── (P1) PARKED-SERVED (#188) -> the served leg is itself parked -> PARK RED ─
write_scenario '{"served_by": "openrouter", "failover_reasons": "", "balance": {
  "nvidia": {"funding_class":1,"parked":false,"drained":false},
  "openrouter": {"funding_class":1,"parked":true,"drained":false},
  "cline-pass": {"funding_class":2,"parked":false,"drained":false}}}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -ne 0 ] && ok "(P1) parked-served: canary exits non-zero (RED)" \
                    || bad "(P1) parked-served: canary exited 0 — a parked SERVED leg was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "DEAD NO-OP" \
  && ok "(P1) parked-served: RED line names the DEAD NO-OP (#188 class)" \
  || bad "(P1) parked-served: no dead-no-op red line"

# ── (P2) PARKED-ATTEMPTED (#188) -> parked leg in the failover path -> PARK RED
write_scenario '{"served_by": "openrouter", "failover_reasons": "cline-pass=429", "balance": {
  "nvidia": {"funding_class":1,"parked":false,"drained":false},
  "openrouter": {"funding_class":1,"parked":false,"drained":false},
  "cline-pass": {"funding_class":2,"parked":true,"drained":false}}}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -ne 0 ] && ok "(P2) parked-attempted: canary exits non-zero (RED)" \
                    || bad "(P2) parked-attempted: canary exited 0 — a parked ATTEMPTED leg was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "exclusion did not fire" \
  && ok "(P2) parked-attempted: RED line names the non-firing exclusion (#188 class)" \
  || bad "(P2) parked-attempted: no exclusion red line"

# ── (P3) VACUOUS-PARK POSITIVE (#188 + FIX-4) -> a parked provider that is ──
#   NOT a candidate of the head-model pool claims "EXCLUDED" — but the claim is
#   vacuous (the forwarder never considered it). The OLD canary GREEN'd this;
#   FIX-4 downgrades the vacuous-park positive to a RED so the "exclusion
#   proven" verdict can't be misread from a provider that was never a candidate.
#   Pool = [nvidia(f1),openrouter(f1)]; 'huggingface' is parked but NOT in the
#   pool. openrouter serves (free-first GREEN); the park positive fires but is
#   vacuous -> PARK RED.
write_scenario '{"pool": ["nvidia", "openrouter"], "served_by": "openrouter", "failover_reasons": "",
  "balance": {
    "nvidia": {"funding_class": 1, "parked": false, "drained": false},
    "openrouter": {"funding_class": 1, "parked": false, "drained": false},
    "huggingface": {"funding_class": 1, "parked": true, "drained": false}}}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -ne 0 ] && ok "(P3) vacuous-park: canary exits non-zero (RED)" \
                    || bad "(P3) vacuous-park: canary exited 0 — a parked-but-not-a-pool-candidate 'EXCLUDED' claim was GREEN'd (vacuous positive)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "VACUOUS" \
  && ok "(P3) vacuous-park: RED line names the VACUOUS-park positive (excluded provider was not a candidate)" \
  || bad "(P3) vacuous-park: no VACUOUS red line"

# ── (C1) STRAY `standard` -> non-canonical tier ranks -> CONFIG RED ─────────
write_scenario '{}'
cap "$RANKS_STANDARD"
[ "$CAP_RC" -ne 0 ] && ok "(C1) stray-standard: canary exits non-zero (RED)" \
                    || bad "(C1) stray-standard: canary exited 0 — a stray 'standard' tier was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "NON-canonical" \
  && ok "(C1) stray-standard: RED line names the non-canonical tier drift" \
  || bad "(C1) stray-standard: no config red line"

# ── (C2) UNSERVED HEAD MODEL -> head model absent from pools -> CONFIG RED ──
# empty pool list for the head model = not served
write_scenario '{"pool": []}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -ne 0 ] && ok "(C2) unserved-model: canary exits non-zero (RED)" \
                    || bad "(C2) unserved-model: canary exited 0 — an unserved head model was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "not served" \
  && ok "(C2) unserved-model: RED line names the unserved head model (config drift)" \
  || bad "(C2) unserved-model: no unserved red line"

# ── REVERT PROOF: back to healthy -> GREEN again ────────────────────────────
write_scenario '{}'
cap "$RANKS_GOOD"
[ "$CAP_RC" -eq 0 ] && ok "(revert) after every seeded fault, reverting to healthy returns GREEN (exit 0) — the canary is not stuck-red" \
                    || bad "(revert) healthy re-run did NOT return GREEN (exit $CAP_RC)
$CAP_OUT"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL FLOW-CANARY DOGFOOD TESTS PASS"
