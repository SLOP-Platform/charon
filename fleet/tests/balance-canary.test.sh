#!/usr/bin/env bash
# balance-canary.test.sh — FAIL-ON-REVERT dogfood for BALANCE-CANARY
# (fleet/balance-canary.sh, design of record fleet/board/BALANCE-CANARY.md).
#
# GREEN IS NOT PROOF. This is the mandatory e2e-dogfood the money-path ticket
# demands [[e2e-dogfood-norm-for-money-code]]: SEED a real fault of each
# persistence class and PROVE the canary goes RED on it, then GREEN when the
# single seeded field is reverted. A money-path canary that only passes the
# happy path is worse than none — a false GREEN here means a silent
# ledger-decrement no-op or a park-lifecycle regression ships undetected.
#
# FULLY HERMETIC / OFFLINE: a local Python-stdlib HTTP server stands in for the
# LIVE gateway on 127.0.0.1 (same shape as fleet/tests/flow-canary.test.sh). It
# serves the THREE surfaces the canary touches:
#   • GET  /charon/status            the observable balance/meter snapshot
#   • POST /v1/chat/completions      the served leg + X-Charon-Provider header;
#                                    decrements the served leg's tracked ledger
#   • POST /charon/balance           the drain/re-arm control (op=park|rearm)
# Every fault is seeded by rewriting a SCENARIO json the fake reads fresh per
# request. Persistence faults (ledger_flip / park_flip) are modelled by a
# per-provider READ COUNTER: the fake serves the "good" value on the FIRST
# status read after the triggering event and the "bad" (reset) value on the
# independent SECOND read — exactly the in-memory-only ledger/park regression
# the canary exists to catch. The REAL fleet/balance-canary.sh runs UNMODIFIED
# against it via its env overrides.
#
# Covers (one RED-then-GREEN pair per assertion class the ticket names, plus the
# persistence/exclusion branches so every assertion is fault-proven):
#   (H)   HEALTHY                 -> both stages GREEN, exit 0            [baseline]
#   (L1)  DECREMENT NO-OP         -> tracked balance never decrements     -> STAGE A RED
#   (L2)  LEDGER NOT PERSISTED    -> decrement resets on the 2nd read      -> STAGE A RED
#   (K1)  PARK NOT PERSISTED      -> parked flag resets on the 2nd read    -> STAGE B RED
#   (K2)  PARKED LEG SERVED       -> a parked leg is served (#188)         -> STAGE B RED
#   (RA)  RE-ADMIT NO-OP          -> re-arm does not clear the park        -> STAGE B RED
#   (FG)  FREE-LEG HEALTHY        -> untracked served leg, aggregate ledger-> GREEN
#   (FR)  FREE-LEG INERT METER    -> no aggregate spend recorded           -> STAGE A RED
# Each REDs, and reverting the single seeded field returns the canary to GREEN.
# A final revert-proof re-run confirms green-is-not-a-fluke.
#
# Run:  bash fleet/tests/balance-canary.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
CANARY="$SRC/balance-canary.sh"
[ -f "$CANARY" ] || { echo "FAIL: cannot find $CANARY" >&2; exit 1; }
[ -f "$SRC/flow-canary.sh" ] || { echo "FAIL: balance-canary requires $SRC/flow-canary.sh (sourced plumbing)" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
SCENARIO="$D/scenario.json"
STATE="$D/gw-state.json"
PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"

# ── fixture: tier-models.tsv (strong head = prepaid-head) ───────────────────
TIER_TSV="$D/tier-models.tsv"
printf 'economy\tfree-econ,gpt-x-nano\n'                >  "$TIER_TSV"
printf 'strong\tprepaid-head,together,nvidia\n'         >> "$TIER_TSV"
printf 'frontier\tfrontier-head,glm\n'                  >> "$TIER_TSV"

# ── the hermetic fake gateway ───────────────────────────────────────────────
# STATE (persisted, atomic) carries: providers{served,cost}, ledger{remaining},
# parked[], usage_cost, and the two read-flip arms (ledger_armed/park_armed).
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

def scenario(): return load(SCENARIO, {})
def state():    return load(STATE, {})

def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f: json.dump(s, f)
    os.replace(tmp, STATE)

DEC = 0.5  # per-served-request ledger decrement (USD)

class H(BaseHTTPRequestHandler):
    def _send(self, code, body_bytes, extra_headers=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    # ── GET /charon/status — the observable balance/meter snapshot ──────────
    def do_GET(self):
        if not self.path.startswith("/charon/status"):
            self._send(404, b"{}"); return
        sc = scenario(); st = state()
        head = sc.get("head_model", "prepaid-head")
        pool = sc.get("pool", ["prepaid-head", "opencode-zen", "together", "nvidia"])
        balcfg = sc.get("balance", {})
        ledger = st.get("ledger", {})
        parked = set(st.get("parked", []))
        la = st.get("ledger_armed"); pa = st.get("park_armed")
        dirty = False
        bal = {}
        for p, base in balcfg.items():
            e = {"funding_class": base.get("funding_class"),
                 "drained": bool(base.get("drained", False))}
            rem = ledger.get(p, base.get("remaining_usd"))
            if la and la.get("provider") == p:
                la["reads"] = la.get("reads", 0) + 1
                rem = la["dec"] if la["reads"] <= 1 else la["orig"]
                dirty = True
            e["remaining_usd"] = rem
            pk = p in parked
            if pa and pa.get("provider") == p:
                pa["reads"] = pa.get("reads", 0) + 1
                pk = pa["reads"] <= 1
                dirty = True
            e["parked"] = pk
            bal[p] = e
        if dirty:
            if la: st["ledger_armed"] = la
            if pa: st["park_armed"] = pa
            save_state(st)
        providers = {p: {"served": v.get("served", 0), "cost": v.get("cost", 0.0),
                         "failed": 0, "errors": 0, "last_status": 200}
                     for p, v in st.get("providers", {}).items()}
        snap = {
            "pools": {head: pool},
            "providers": providers,
            "cooldown_seconds": {},
            "usage": {"tokens_in": 0, "tokens_out": 0,
                      "cost_usd": st.get("usage_cost", 0.0)},
            "recent_failovers": [],
            "build_sha": "hermetic-fake",
            "balance": bal,
        }
        self._send(200, json.dumps(snap).encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        if self.path.startswith("/charon/balance"):
            self._balance(raw); return
        self._chat()

    # ── POST /v1/chat/completions — serve + advance meter + decrement ledger ─
    def _chat(self):
        sc = scenario(); st = state()
        served = sc.get("served_by", "opencode-zen")
        reasons = sc.get("failover_reasons", "")
        resolved = sc.get("resolved_model", "zen/glm-4.7")
        if not sc.get("meter_inert", False):
            cell = st.setdefault("providers", {}).setdefault(served, {"served": 0, "cost": 0.0})
            cell["served"] = cell.get("served", 0) + 1
            cell["cost"] = round(cell.get("cost", 0.0) + 1e-5, 8)
            st["usage_cost"] = round(st.get("usage_cost", 0.0) + 1e-5, 8)
        base_rem = (sc.get("balance", {}).get(served) or {}).get("remaining_usd")
        if base_rem is not None:
            led = st.setdefault("ledger", {})
            cur = led.get(served, base_rem)
            if sc.get("ledger_noop", False):
                led.setdefault(served, base_rem)          # no decrement
            elif sc.get("ledger_flip", False):
                # read1 shows decremented, read2+ reverts to orig (not persisted)
                st["ledger_armed"] = {"provider": served, "orig": cur,
                                      "dec": round(cur - DEC, 8), "reads": 0}
                led[served] = cur
            else:
                led[served] = round(cur - DEC, 8)         # healthy: persist decrement
        save_state(st)
        body = json.dumps({
            "model": resolved,
            "choices": [{"message": {"role": "assistant", "content": "PONG"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
        }).encode()
        extra = {"X-Charon-Provider": served}
        if reasons:
            extra["X-Charon-Failover-Reasons"] = reasons
        self._send(200, body, extra)

    # ── POST /charon/balance — drain / re-arm control (op=park|rearm) ───────
    def _balance(self, raw):
        sc = scenario(); st = state()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}
        prov = str(payload.get("provider") or "").strip()
        op = str(payload.get("op") or "").strip()
        if op == "park":
            if sc.get("park_flip", False):
                # parked reads true ONCE then resets (in-memory-only park)
                st["park_armed"] = {"provider": prov, "reads": 0}
            else:
                pk = set(st.get("parked", [])); pk.add(prov); st["parked"] = sorted(pk)
        elif op == "rearm":
            if not sc.get("rearm_noop", False):
                st["parked"] = [p for p in st.get("parked", []) if p != prov]
                st["park_armed"] = None
            # rearm_noop: leave the park in place (re-admit no-op)
        save_state(st)
        self._send(200, json.dumps({"ok": True, "provider": prov, "op": op}).encode())

    def log_message(self, *a, **k):
        return

HTTPServer(("127.0.0.1", int(sys.argv[3])), H).serve_forever()
PYEOF

python3 -u "$D/fake-gw.py" "$SCENARIO" "$STATE" "$PORT" >"$D/gw.log" 2>&1 &
GW_PID=$!
trap 'kill $GW_PID 2>/dev/null || true; rm -rf "$D"' EXIT
for _ in $(seq 1 50); do
  python3 -c "import socket,sys
s=socket.socket(); s.settimeout(0.2)
try: s.connect(('127.0.0.1', $PORT)); s.close(); sys.exit(0)
except Exception: sys.exit(1)" 2>/dev/null && break
  sleep 0.05
done

# ── scenario writer: base HEALTHY, override keys via python (jq-free) ────────
write_scenario(){ # <json-overrides>
  python3 - "$SCENARIO" "$1" <<'PY'
import json, sys
base = {
    "head_model": "prepaid-head",
    "pool": ["prepaid-head", "opencode-zen", "together", "nvidia"],
    "served_by": "opencode-zen",
    "failover_reasons": "",
    "resolved_model": "zen/glm-4.7",
    "meter_inert": False,
    "ledger_noop": False,
    "ledger_flip": False,
    "park_flip": False,
    "rearm_noop": False,
    "balance": {
        "opencode-zen": {"funding_class": 3, "remaining_usd": 10.0, "parked": False, "drained": False},
        "together":     {"funding_class": 3, "remaining_usd": 5.0,  "parked": False, "drained": False},
        "nvidia":       {"funding_class": 1, "remaining_usd": None, "parked": False, "drained": False},
        "openrouter":   {"funding_class": 1, "remaining_usd": None, "parked": False, "drained": False},
    },
}
base.update(json.loads(sys.argv[2]))
with open(sys.argv[1], "w") as f: json.dump(base, f)
PY
}

# ── run the REAL canary against the fake; STATE reset per run for determinism ─
run_canary(){ # [drain_provider]
  printf '{}' > "$STATE"    # each canary run starts from a clean gateway ledger/park state
  FC_GATEWAY_URL="http://127.0.0.1:$PORT" \
  FC_TOKEN="hermetic-fake-token" \
  FC_TIER="strong" \
  FC_TIER_TSV="$TIER_TSV" \
  FC_NONCE="fixed-nonce" \
  FC_REQ_TIMEOUT_S=10 FC_STATUS_TIMEOUT_S=5 \
  BC_DRAIN_PROVIDER="${1:-together}" \
    bash "$CANARY" 2>&1
  return "${PIPESTATUS[0]:-$?}"
}
cap(){ CAP_OUT="$(run_canary "${1:-together}")"; CAP_RC=$?; }

# revert-to-healthy helper: prove the seeded field was the SOLE cause of RED
revert_green(){ # <tag>
  write_scenario '{}'
  cap
  [ "$CAP_RC" -eq 0 ] && ok "$1: revert-to-healthy returns GREEN (exit 0) — the seed was the sole cause" \
                      || bad "$1: revert did NOT return GREEN (exit $CAP_RC)
$CAP_OUT"
}

# ── (H) HEALTHY baseline -> GREEN, exit 0 ───────────────────────────────────
write_scenario '{}'
cap
[ "$CAP_RC" -eq 0 ] && ok "(H) healthy: canary exits 0 (GREEN)" \
                    || bad "(H) healthy: canary exit $CAP_RC (expected 0)
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "BALANCE-CANARY: GREEN" \
  && ok "(H) healthy: prints GREEN verdict" || bad "(H) healthy: no GREEN verdict
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "DECREMENTED the tracked balance" \
  && ok "(H) healthy: STAGE A observed a real ledger decrement" || bad "(H) healthy: no decrement observed
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "decrement PERSISTED across an independent re-read" \
  && ok "(H) healthy: STAGE A proved decrement persistence" || bad "(H) healthy: no persistence proof
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "parked=true PERSISTED across an independent re-read" \
  && ok "(H) healthy: STAGE B proved park persistence" || bad "(H) healthy: no park persistence proof
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "EXCLUDED from the served path" \
  && ok "(H) healthy: STAGE B proved parked-leg exclusion" || bad "(H) healthy: no exclusion proof
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "RE-ADMITTED" \
  && ok "(H) healthy: STAGE B proved re-admit" || bad "(H) healthy: no re-admit proof
$CAP_OUT"

# ── (L1) DECREMENT NO-OP -> tracked balance never moves -> STAGE A RED ──────
write_scenario '{"ledger_noop": true}'
cap
[ "$CAP_RC" -ne 0 ] && ok "(L1) decrement-no-op: canary RED (exit $CAP_RC)" \
                    || bad "(L1) decrement-no-op: exited 0 — an inert ledger was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "DECREMENT NO-OP" \
  && ok "(L1) decrement-no-op: RED line names DECREMENT NO-OP" || bad "(L1) decrement-no-op: no matching RED line
$CAP_OUT"
revert_green "(L1) decrement-no-op"

# ── (L2) LEDGER NOT PERSISTED -> decrement resets on 2nd read -> STAGE A RED ─
write_scenario '{"ledger_flip": true}'
cap
[ "$CAP_RC" -ne 0 ] && ok "(L2) ledger-not-persisted: canary RED (exit $CAP_RC)" \
                    || bad "(L2) ledger-not-persisted: exited 0 — a non-persistent ledger was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "NON-PERSISTENT LEDGER" \
  && ok "(L2) ledger-not-persisted: RED line names NON-PERSISTENT LEDGER" || bad "(L2) ledger-not-persisted: no matching RED line
$CAP_OUT"
# the DECREMENT line still passes (read1 shows the drop) — proves the persistence
# assertion is what bit, independent of the decrement assertion.
printf '%s' "$CAP_OUT" | grep -q "DECREMENTED the tracked balance" \
  && ok "(L2) ledger-not-persisted: read1 still shows the decrement (persistence assertion isolated)" \
  || bad "(L2) ledger-not-persisted: decrement line missing — cannot isolate the persistence assertion
$CAP_OUT"
revert_green "(L2) ledger-not-persisted"

# ── (K1) PARK NOT PERSISTED -> parked flag resets on 2nd read -> STAGE B RED ─
write_scenario '{"park_flip": true}'
cap
[ "$CAP_RC" -ne 0 ] && ok "(K1) park-not-persisted: canary RED (exit $CAP_RC)" \
                    || bad "(K1) park-not-persisted: exited 0 — a non-persistent park was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "PARK NOT PERSISTED" \
  && ok "(K1) park-not-persisted: RED line names PARK NOT PERSISTED" || bad "(K1) park-not-persisted: no matching RED line
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "parked=true after the drain (read #1)" \
  && ok "(K1) park-not-persisted: read1 still shows the park (persistence assertion isolated)" \
  || bad "(K1) park-not-persisted: park-applied line missing — cannot isolate the persistence assertion
$CAP_OUT"
revert_green "(K1) park-not-persisted"

# ── (K2) PARKED LEG SERVED -> a parked leg is served (#188) -> STAGE B RED ───
# served_by == the drain target; after the canary parks it, the served request
# still returns it -> the exclusion is a dead no-op.
write_scenario '{"served_by": "together"}'
cap
[ "$CAP_RC" -ne 0 ] && ok "(K2) parked-served: canary RED (exit $CAP_RC)" \
                    || bad "(K2) parked-served: exited 0 — a served parked leg was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "DEAD NO-OP" \
  && ok "(K2) parked-served: RED line names the #188 DEAD NO-OP" || bad "(K2) parked-served: no matching RED line
$CAP_OUT"
revert_green "(K2) parked-served"

# ── (RA) RE-ADMIT NO-OP -> re-arm does not clear the park -> STAGE B RED ─────
write_scenario '{"rearm_noop": true}'
cap
[ "$CAP_RC" -ne 0 ] && ok "(RA) re-admit-no-op: canary RED (exit $CAP_RC)" \
                    || bad "(RA) re-admit-no-op: exited 0 — a non-clearing re-arm was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "RE-ADMIT NO-OP" \
  && ok "(RA) re-admit-no-op: RED line names RE-ADMIT NO-OP" || bad "(RA) re-admit-no-op: no matching RED line
$CAP_OUT"
revert_green "(RA) re-admit-no-op"

# ── (FG) FREE-LEG HEALTHY -> untracked served leg, aggregate ledger -> GREEN ─
# served leg 'nvidia' has remaining_usd=None -> STAGE A asserts on usage.cost_usd.
write_scenario '{"served_by": "nvidia"}'
cap
[ "$CAP_RC" -eq 0 ] && ok "(FG) free-leg healthy: canary GREEN (exit 0)" \
                    || bad "(FG) free-leg healthy: exit $CAP_RC (expected 0) — aggregate-ledger path broke
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -q "RECORDED aggregate spend" \
  && ok "(FG) free-leg healthy: STAGE A used the aggregate usage ledger for an untracked leg" \
  || bad "(FG) free-leg healthy: aggregate-ledger path not taken
$CAP_OUT"

# ── (FR) FREE-LEG INERT METER -> no aggregate spend recorded -> STAGE A RED ──
write_scenario '{"served_by": "nvidia", "meter_inert": true}'
cap
[ "$CAP_RC" -ne 0 ] && ok "(FR) free-leg inert: canary RED (exit $CAP_RC)" \
                    || bad "(FR) free-leg inert: exited 0 — an inert aggregate ledger was NOT caught
$CAP_OUT"
printf '%s' "$CAP_OUT" | grep -qE "DECREMENT NO-OP|INERT METER" \
  && ok "(FR) free-leg inert: RED line names the inert ledger/meter" || bad "(FR) free-leg inert: no matching RED line
$CAP_OUT"
revert_green "(FR) free-leg inert"

# ── REVERT PROOF: healthy again -> GREEN (green is not a fluke) ─────────────
write_scenario '{}'
cap
[ "$CAP_RC" -eq 0 ] && ok "(revert) after every seeded fault, healthy returns GREEN (exit 0) — the canary is not stuck-red" \
                    || bad "(revert) healthy re-run did NOT return GREEN (exit $CAP_RC)
$CAP_OUT"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL BALANCE-CANARY DOGFOOD TESTS PASS"
