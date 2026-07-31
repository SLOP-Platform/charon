#!/usr/bin/env bash
# spill-up.test.sh — FAIL-ON-REVERT tests for CRIPPLE #2 (proactive capped-exclusion WIRED into the
# live dispatcher) + CRIPPLE #3 (cost-band SPILL-UP escalation) of P0 FLEET-DEMAND-DRIVEN-ROUTING.
#
# Drives the REAL fleet-droid.sh via its `resolve <tier> <ticketfile>` dev/test hook — the SAME
# unified resolver (resolve_runnable_chain: reorder + detention + CAPPED filter + spill-up) the main
# claim loop calls, so production path == test path. Fully hermetic (NO network) via env seams the
# dispatcher already honors:
#   CHARON_TIER_MODELS         -> throwaway tier-models.tsv (never the operator-gated real one)
#   CHARON_SCORECARD_TSV       -> empty scorecard fixture (no grades/detention -> reorder is a
#                                 pass-through; isolates the capped/spill behavior under test)
#   CHARON_GATEWAY_STATUS_FILE -> a /charon/status JSON snapshot read INSTEAD of the gateway HTTP
#                                 endpoint (GatewayStatusAvailability's file seam), so capped state
#                                 is deterministic with zero network dependency.
#
# Reverting CRIPPLE #3 (removing the spill-up loop / next_tier_up, so a capped band just stalls)
# makes test (a) FAIL: `resolve economy` would exit 7 (stall) instead of escalating to strong's
# chain. Reverting CRIPPLE #2 (removing the capped_filter step) makes test (a) FAIL too: economy
# would be reported runnable and its capped chain returned instead of spilling up.
#
# COST CAP (money path) — cases (d)(g)(h)(i)(j)(k)(l)(m)(n). Spill-up must be BOUNDED by
# `SPILL_UP_COST_CEILING` in the cost-band SSOT (fleet/state/TIER-CANON.md), read via the
# CHARON_TIER_CANON file seam so each case differs ONLY in the cap value:
#   (g) the cap REFUSES an above-ceiling spill even though the expensive band is the only runnable
#       one -> DETAIN (exit 7, no chain) + a greppable `COST-CAP:` line + a `cost-cap-detain` row
#       in the provider-exhaustion ledger. Deleting the cap check makes (g) FAIL: the resolver
#       would happily return frontier's chain and exit 0.
#   (h) raising the ceiling in the SSOT permits that exact spill -> proves the cap is CONFIGURABLE
#       and that (g)'s refusal is the cap, not some unrelated stall.
#   (i)(j)(k) an ABSENT / malformed / empty ceiling FAILS CLOSED (cost spill-up disabled), never
#       "no cap". Adding any in-code default ceiling makes these FAIL.
#   (l)(m) the cap governs ESCALATION only — a declared band at/above the ceiling still runs, but
#       declaring it buys no above-ceiling spill.
#   (n) the DETENTION carve-out: a wholly HARD-detained band DOES escalate above the ceiling
#       (safety escalation is not cost-bounded), but loudly and with a `cost-cap-bypass-detention`
#       ledger row — observable, never a silent hole. fleet/tests/test_detention.sh case 6a covers
#       the same carve-out from the detention side (both run against the REAL TIER-CANON ceiling).
#
# CAPPED-FILTER FAIL-OPEN DEFECT (money path) — cases (f)(f2)(f3). capped_filter_chain used to
# swallow availability.py's stderr and map EVERY error to "keep all, exit 0", so a dispatcher
# without a gateway token (the live gateway answers 401) had the whole capped-exclusion no-op
# undetectably. These cases pin the fail-CLOSED replacement:
#   (f)  an unreadable snapshot DETAINS (exit 7, no chain) + `CAPPED-FILTER-UNAVAILABLE:` line +
#        `capped-filter-unavailable` ledger row, and STILL detains with the ceiling raised to
#        frontier — proving it is the capped-filter failing closed, not the cost cap. Restoring
#        the old `2>/dev/null` + fail-open keep-all makes f1/f2 FAIL (chain 'eco1,eco2', exit 0).
#   (f2) ERROR vs EMPTY at the CLI seam: unreadable = exit 8 with EMPTY stdout, positively
#        all-capped = exit 7, healthy-nothing-capped = exit 0 with survivors. Collapsing 8 back
#        into 0/7 makes fe1/fe4 FAIL. This is the non-vacuity guard on the whole fix: a zero-item
#        result caused by an error is distinguishable from every legitimate zero-item result.
#   (f3) the LIVE-SHAPED path: a local stdlib HTTP stand-in that answers 401 like the real gateway
#        (with every token env cleared) over the REAL HTTP code path — no status-file seam.
#
# Run:  bash fleet/tests/spill-up.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

# --- fixtures ---------------------------------------------------------------------------------
# Three cost bands, ascending: economy -> strong -> frontier (matches TIER-CANON's axis).
printf 'economy\teco1,eco2\nstrong\tstr1,str2\nfrontier\tfro1\n' > "$D/tier-models.tsv"
printf 'tier: economy\nwork_class: routing\n' > "$D/ticket.md"
: > "$D/scorecard-empty.tsv"   # no grades, no detention -> reorder pass-through, detention keeps all

# Snapshot A: ONLY the economy models are capped (their sole provider is parked); strong+frontier
# providers are live. capped(model) == every provider serving it is parked/drained/cooled.
cat > "$D/snap-eco-capped.json" <<'JSON'
{"pools":{"eco1":["provDrained"],"eco2":["provDrained"],
          "str1":["provLive"],"str2":["provLive"],"fro1":["provLive"]},
 "balance":{"provDrained":{"parked":true},"provLive":{"parked":false}},
 "cooldown_seconds":{}}
JSON

# Snapshot B: nothing capped (all providers live) — proves NO spurious spill.
cat > "$D/snap-clean.json" <<'JSON'
{"pools":{"eco1":["provLive"],"eco2":["provLive"],
          "str1":["provLive"],"str2":["provLive"],"fro1":["provLive"]},
 "balance":{"provLive":{"parked":false}},"cooldown_seconds":{}}
JSON

# Snapshot C: EVERY band capped -> ladder exhausted.
cat > "$D/snap-all-capped.json" <<'JSON'
{"pools":{"eco1":["provDrained"],"eco2":["provDrained"],
          "str1":["provDrained"],"str2":["provDrained"],"fro1":["provDrained"]},
 "balance":{"provDrained":{"parked":true}},"cooldown_seconds":{}}
JSON

# Snapshot D: economy AND strong capped, frontier LIVE. This is the shape the COST CAP exists for —
# a run of capped cheap legs whose only runnable band is the most expensive one.
cat > "$D/snap-frontier-only.json" <<'JSON'
{"pools":{"eco1":["provDrained"],"eco2":["provDrained"],
          "str1":["provDrained"],"str2":["provDrained"],"fro1":["provLive"]},
 "balance":{"provDrained":{"parked":true},"provLive":{"parked":false}},
 "cooldown_seconds":{}}
JSON

# --- COST-CAP fixtures: alternate cost-band SSOT docs, fed via the CHARON_TIER_CANON file seam ----
# Each carries the canonical axis; they differ ONLY in the SPILL_UP_COST_CEILING line, so every
# cost-cap assertion below is attributable to the CAP VALUE and nothing else.
LEDGER="$D/exhaust-ledger.tsv"          # THROWAWAY provider-exhaustion ledger — never the live one
REAL_CANON="$SRC/state/TIER-CANON.md"   # the real SSOT (ceiling: strong) — cases a-g/l use it
{ printf '    CANONICAL_COST_TIERS = economy, strong, frontier\n'
  printf '    SPILL_UP_COST_CEILING = frontier\n'; } > "$D/canon-ceiling-frontier.md"
{ printf '    CANONICAL_COST_TIERS = economy, strong, frontier\n'
  printf '    SPILL_UP_COST_CEILING = economy\n';  } > "$D/canon-ceiling-economy.md"
printf '    CANONICAL_COST_TIERS = economy, strong, frontier\n'  > "$D/canon-no-key.md"
{ printf '    CANONICAL_COST_TIERS = economy, strong, frontier\n'
  printf '    SPILL_UP_COST_CEILING = unlimited\n'; } > "$D/canon-malformed.md"
{ printf '    CANONICAL_COST_TIERS = economy, strong, frontier\n'
  printf '    SPILL_UP_COST_CEILING =\n';           } > "$D/canon-empty-value.md"

run_resolve(){ # <tier> <status-file> [tier-canon-file]  — stderr captured to $D/stderr.txt
  CHARON_TIER_MODELS="$D/tier-models.tsv" CHARON_SCORECARD_TSV="$D/scorecard-empty.tsv" \
  CHARON_GATEWAY_STATUS_FILE="$2" CHARON_EXHAUST_LEDGER="$LEDGER" \
  CHARON_TIER_CANON="${3:-$REAL_CANON}" \
  bash "$SRC/fleet-droid.sh" resolve "$1" "$D/ticket.md" 2>"$D/stderr.txt"
}
# greppable-line + ledger-row assertions (no pipes -> nothing can mask a failure; a MISSING
# stderr/ledger file yields 'no', so a vacuous "nothing was examined" run reads RED, not green).
saw_stderr(){ if grep -q -- "$1" "$D/stderr.txt" 2>/dev/null; then echo yes; else echo no; fi; }
led_row(){    if grep -q -- "$1" "$LEDGER"       2>/dev/null; then echo yes; else echo no; fi; }

echo "== (a) economy fully CAPPED, strong clean -> resolve economy SPILLS UP to strong's chain =="
out="$(run_resolve economy "$D/snap-eco-capped.json")"; rc=$?
check "a1 spill-up returns strong's chain when economy is all-capped" "$out" "str1,str2"
check "a2 spill-up exits 0 (runnable), not the stall" "$rc" "0"

echo "== (b) NO capped models -> resolve economy stays on economy's OWN chain (no spurious spill) =="
out="$(run_resolve economy "$D/snap-clean.json")"
check "b1 no spill when the requested band is runnable" "$out" "eco1,eco2"

echo "== (c) requesting strong directly (clean) -> strong's chain, unchanged =="
out="$(run_resolve strong "$D/snap-clean.json")"
check "c1 a runnable requested band resolves to its own chain" "$out" "str1,str2"

echo "== (d) EVERY band capped -> nothing runnable -> resolve exits 7 (the stall), no chain."
echo "       Under the REAL SSOT ceiling ('strong') the walk stops at the CAP; with the ceiling"
echo "       raised to 'frontier' it walks to the top band and stops at genuine LADDER EXHAUSTION =="
out="$(run_resolve economy "$D/snap-all-capped.json")"; rc=$?
check "d1 nothing runnable exits 7" "$rc" "7"
check "d2 nothing runnable prints no chain" "$out" ""
out="$(run_resolve economy "$D/snap-all-capped.json" "$D/canon-ceiling-frontier.md")"; rc=$?
check "d3 ceiling=frontier: exits 7 at true ladder exhaustion" "$rc" "7"
check "d4 ceiling=frontier: reports the TOP band exhausted, not a cap refusal" \
      "$(saw_stderr 'cost-band ladder EXHAUSTED')" "yes"

echo "== (e) capped-filter unit seam: availability.py filter-capped drops capped, keeps live =="
kept="$(CHARON_GATEWAY_STATUS_FILE="$D/snap-eco-capped.json" \
        python3 "$SRC/capability/availability.py" filter-capped eco1 str1 2>/dev/null)"
check "e1 filter-capped keeps only the non-capped model" "$kept" "str1"
CHARON_GATEWAY_STATUS_FILE="$D/snap-eco-capped.json" \
  python3 "$SRC/capability/availability.py" filter-capped eco1 eco2 >/dev/null 2>&1; rc=$?
check "e2 filter-capped exits 7 when EVERY model is capped" "$rc" "7"

echo "== (f) FAIL-CLOSED: an UNREADABLE gateway snapshot is NOT 'nothing capped'. The capped-"
echo "       exclusion did not run, so the band's chain is not trusted and no spill is taken off"
echo "       an error -> DETAIN (exit 7), loud greppable line + ledger row =="
rm -f "$LEDGER"
out="$(run_resolve economy "$D/does-not-exist.json")"; rc=$?
check "f1 unreadable gateway status DETAINS (exit 7), never a silent keep-all" "$rc" "7"
check "f2 unreadable gateway status hands back NO chain" "$out" ""
check "f3 the failure is LOUD and greppable" "$(saw_stderr 'CAPPED-FILTER-UNAVAILABLE')" "yes"
check "f4 the failure is ledgered like cost-cap-config-invalid" "$(led_row 'capped-filter-unavailable')" "yes"
check "f5 the underlying availability error is SURFACED, not swallowed" \
      "$(saw_stderr 'CANNOT READ gateway /charon/status')" "yes"
# ...and the detain is the UNAVAILABLE path, not the cost cap: with the ceiling raised to
# 'frontier' (every spill permitted) it STILL detains and still never escalates.
rm -f "$LEDGER"
out="$(run_resolve economy "$D/does-not-exist.json" "$D/canon-ceiling-frontier.md")"; rc=$?
check "f6 ceiling=frontier: still detains (no spill-up bought with an error)" "$rc" "7"
check "f7 ceiling=frontier: still no chain" "$out" ""
check "f8 ceiling=frontier: attributed to the capped-filter, not the cost cap" \
      "$(led_row 'capped-filter-unavailable')" "yes"

echo "== (f2) ERROR vs EMPTY at the CLI seam: a zero-survivor result caused by an ERROR must never"
echo "        read the same as 'the gateway says nothing is capped' or 'the gateway says all capped' =="
err_out="$(CHARON_GATEWAY_STATUS_FILE="$D/does-not-exist.json" \
           python3 "$SRC/capability/availability.py" filter-capped eco1 str1 2>"$D/cli-err.txt")"
err_rc=$?
allcap_out="$(CHARON_GATEWAY_STATUS_FILE="$D/snap-all-capped.json" \
           python3 "$SRC/capability/availability.py" filter-capped eco1 eco2 2>/dev/null)"
allcap_rc=$?
clean_out="$(CHARON_GATEWAY_STATUS_FILE="$D/snap-clean.json" \
           python3 "$SRC/capability/availability.py" filter-capped eco1 str1 2>/dev/null)"
clean_rc=$?
check "fe1 unreadable snapshot exits 8 (UNAVAILABLE), a code of its own" "$err_rc" "8"
check "fe2 unreadable snapshot prints NO survivors (cannot be read as 'all un-capped')" "$err_out" ""
check "fe3 unreadable snapshot explains itself on stderr" \
      "$(if grep -q -- 'CANNOT READ' "$D/cli-err.txt" 2>/dev/null; then echo yes; else echo no; fi)" "yes"
check "fe4 POSITIVELY all-capped is a DIFFERENT code (7), not 8" "$allcap_rc" "7"
check "fe5 all-capped also prints no survivors — so rc alone separates it from the error" "$allcap_out" ""
check "fe6 healthy snapshot with nothing capped exits 0 and keeps everything" "$clean_rc" "0"
check "fe7 healthy 'nothing capped' is distinguishable from the error by BOTH rc and stdout" \
      "$clean_out" "$(printf 'eco1\nstr1')"

echo "== (f3) LIVE-SHAPED AUTH FAILURE: a local stand-in gateway that answers 401 exactly like the"
echo "        real one ('missing or invalid bearer token') -> the dispatcher DETAINS, loudly =="
cat > "$D/gw401.py" <<'PY'
import http.server, socketserver, sys, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"detail":"missing or invalid bearer token"}'
        self.send_response(401); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
srv = socketserver.TCPServer(("127.0.0.1", 0), H)
print(srv.server_address[1], flush=True)
srv.serve_forever()
PY
python3 "$D/gw401.py" > "$D/gw401.port" 2>/dev/null &
GW_PID=$!
trap 'kill "$GW_PID" 2>/dev/null; rm -rf "$D"' EXIT
GW_PORT=""
for _ in $(seq 1 50); do GW_PORT="$(head -n1 "$D/gw401.port" 2>/dev/null || true)"; [ -n "$GW_PORT" ] && break; sleep 0.1; done
if [ -z "$GW_PORT" ]; then
  bad "f9 local 401 stand-in gateway failed to start"
  bad "f10 local 401 stand-in gateway failed to start"
  bad "f11 local 401 stand-in gateway failed to start"
else
  rm -f "$LEDGER"
  # NOTE: no CHARON_GATEWAY_STATUS_FILE here — this exercises the real HTTP path. Every token env
  # availability.py honors is cleared, reproducing "dispatcher runs without a gateway token".
  out="$(env -u CHARON_GATEWAY_TOKEN -u CHARON_API_KEY -u OPENAI_API_KEY -u CHARON_GATEWAY_STATUS_FILE \
         CHARON_GATEWAY_URL="http://127.0.0.1:$GW_PORT" \
         CHARON_TIER_MODELS="$D/tier-models.tsv" CHARON_SCORECARD_TSV="$D/scorecard-empty.tsv" \
         CHARON_EXHAUST_LEDGER="$LEDGER" CHARON_TIER_CANON="$REAL_CANON" \
         bash "$SRC/fleet-droid.sh" resolve economy "$D/ticket.md" 2>"$D/stderr.txt")"
  rc=$?
  check "f9 401 (no bearer token) DETAINS the dispatch, exit 7" "$rc" "7"
  check "f10 401 hands back NO chain — the un-vetted band is never offered" "$out" ""
  check "f11 401 is ledgered as capped-filter-unavailable" "$(led_row 'capped-filter-unavailable')" "yes"
fi

echo "== (g) COST CAP: economy+strong capped, frontier LIVE, ceiling='strong' (the REAL SSOT)"
echo "       -> the resolver REFUSES to spill into frontier: DETAIN (exit 7), loud line + ledger row =="
out="$(run_resolve economy "$D/snap-frontier-only.json")"; rc=$?
check "g1 cap-hit exits 7 (DETAIN) instead of escalating into the capped-out top band" "$rc" "7"
check "g2 cap-hit returns NO chain (the expensive band is never handed to the work client)" "$out" ""
check "g3 cap-hit prints a greppable COST-CAP refusal line" "$(saw_stderr 'COST-CAP: REFUSING to spill')" "yes"
check "g4 cap-hit is recorded in the provider-exhaustion ledger" "$(led_row 'cost-cap-detain')" "yes"

echo "== (h) the cap is CONFIGURABLE, not a hardcoded stop: same capped world, ceiling='frontier'"
echo "       -> the SAME spill IS allowed and returns frontier's chain =="
out="$(run_resolve economy "$D/snap-frontier-only.json" "$D/canon-ceiling-frontier.md")"; rc=$?
check "h1 raising the ceiling in the SSOT permits the frontier spill" "$out" "fro1"
check "h2 permitted spill exits 0" "$rc" "0"
check "h3 no refusal line when the hop is within the ceiling" "$(saw_stderr 'COST-CAP: REFUSING to spill')" "no"

echo "== (i)(j)(k) FAIL CLOSED: an absent / malformed / empty ceiling is NEVER 'no cap' — cost"
echo "       spill-up is DISABLED, so economy-capped does NOT reach the perfectly-clean strong band =="
for cf in canon-no-key canon-malformed canon-empty-value; do
  rm -f "$LEDGER"
  out="$(run_resolve economy "$D/snap-eco-capped.json" "$D/$cf.md")"; rc=$?
  check "$cf: fail-closed exits 7 (no cost spill-up)"        "$rc"  "7"
  check "$cf: fail-closed returns NO chain"                  "$out" ""
  check "$cf: fail-closed prints the loud config line"       "$(saw_stderr 'COST-CAP: no usable SPILL_UP_COST_CEILING')" "yes"
  check "$cf: fail-closed is ledgered as a config fault"     "$(led_row 'cost-cap-config-invalid')" "yes"
done

echo "== (l) the cap governs ESCALATION only: a ticket DECLARING a band at/above the ceiling still"
echo "       runs in its own band (ceiling='economy', resolve strong, clean) =="
out="$(run_resolve strong "$D/snap-clean.json" "$D/canon-ceiling-economy.md")"; rc=$?
check "l1 declared band above the ceiling still resolves to its own chain" "$out" "str1,str2"
check "l2 declared-band resolve exits 0" "$rc" "0"

echo "== (m) ...but a high-declared band cannot SIDESTEP the cap: ceiling='economy', resolve strong"
echo "       with strong capped and frontier live -> refused, DETAIN =="
out="$(run_resolve strong "$D/snap-frontier-only.json" "$D/canon-ceiling-economy.md")"; rc=$?
check "m1 declaring a higher band does not buy an above-ceiling spill" "$rc" "7"
check "m2 no chain handed back on the refused spill" "$out" ""

echo "== (n) DETENTION CARVE-OUT: a wholly HARD-detained band escalates ABOVE the ceiling —"
echo "       safety escalation is NOT cost-bounded, but it is loud + ledgered =="
# scorecard fixture: str1 + str2 both FABRICATED on money-path (verdict=BLOCK with gate=pass) ->
# model-detention.sh HARD-detains them for that work_class, so the whole `strong` band is unrunnable
# for SAFETY reasons rather than cost. Columns match the grader-owned scorecard schema:
#   date source ref work_class tier model verdict gate score time_s cost_usd corrections note
printf '# fixture scorecard (fail-on-revert) — NOT the grader-owned tsv\n' > "$D/scorecard-detained.tsv"
printf '2026-07-05\tlive\td1\tmoney-path\t-\tstr1\tBLOCK\tpass\t-\t-\t-\t-\tgreen-but-fake\n' >> "$D/scorecard-detained.tsv"
printf '2026-07-05\tlive\td2\tmoney-path\t-\tstr2\tBLOCK\tpass\t-\t-\t-\t-\tgreen-but-fake\n' >> "$D/scorecard-detained.tsv"
printf 'tier: strong\nwork_class: money-path\n' > "$D/ticket-money.md"
rm -f "$LEDGER"
out="$(CHARON_TIER_MODELS="$D/tier-models.tsv" CHARON_SCORECARD_TSV="$D/scorecard-detained.tsv" \
       CHARON_GATEWAY_STATUS_FILE="$D/snap-clean.json" CHARON_EXHAUST_LEDGER="$LEDGER" \
       CHARON_TIER_CANON="$REAL_CANON" \
       bash "$SRC/fleet-droid.sh" resolve strong "$D/ticket-money.md" 2>"$D/stderr.txt")"; rc=$?
check "n1 all-HARD-detained band escalates above the ceiling to frontier's chain" "$out" "fro1"
check "n2 safety escalation exits 0 (the work runs, on a costlier band)" "$rc" "0"
check "n3 the above-ceiling safety hop is LOUD" "$(saw_stderr 'safety escalation overrides the cost cap')" "yes"
check "n4 the above-ceiling safety hop is LEDGERED (observable, not a silent hole)" \
      "$(led_row 'cost-cap-bypass-detention')" "yes"

echo
echo "--- $PASS passed, $FAIL failed ---"
# NON-VACUITY GUARD: a run that silently skipped cases (a bad fixture, an early `return`, a rename)
# must read RED, not "0 failed". Bump this when adding/removing a check.
EXPECTED_CHECKS=55
if [ "$((PASS+FAIL))" -ne "$EXPECTED_CHECKS" ]; then
  echo "FAIL: VACUOUS RUN — executed $((PASS+FAIL)) checks, expected $EXPECTED_CHECKS" >&2
  exit 1
fi
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL SPILL-UP TESTS PASS"
