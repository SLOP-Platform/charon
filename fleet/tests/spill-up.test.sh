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

run_resolve(){ # <tier> <status-file>
  CHARON_TIER_MODELS="$D/tier-models.tsv" CHARON_SCORECARD_TSV="$D/scorecard-empty.tsv" \
  CHARON_GATEWAY_STATUS_FILE="$2" bash "$SRC/fleet-droid.sh" resolve "$1" "$D/ticket.md" 2>/dev/null
}

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

echo "== (d) EVERY band capped -> ladder exhausted -> resolve exits 7 (the stall), no chain =="
out="$(run_resolve economy "$D/snap-all-capped.json")"; rc=$?
check "d1 exhausted ladder exits 7" "$rc" "7"
check "d2 exhausted ladder prints no runnable chain" "$out" ""

echo "== (e) capped-filter unit seam: availability.py filter-capped drops capped, keeps live =="
kept="$(CHARON_GATEWAY_STATUS_FILE="$D/snap-eco-capped.json" \
        python3 "$SRC/capability/availability.py" filter-capped eco1 str1 2>/dev/null)"
check "e1 filter-capped keeps only the non-capped model" "$kept" "str1"
CHARON_GATEWAY_STATUS_FILE="$D/snap-eco-capped.json" \
  python3 "$SRC/capability/availability.py" filter-capped eco1 eco2 >/dev/null 2>&1; rc=$?
check "e2 filter-capped exits 7 when EVERY model is capped" "$rc" "7"

echo "== (f) fail-OPEN: unreadable snapshot -> models 'unknown' -> KEPT, no spurious spill =="
out="$(run_resolve economy "$D/does-not-exist.json")"
check "f1 gateway-status unavailable keeps the requested band (never spends up on a down endpoint)" "$out" "eco1,eco2"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL SPILL-UP TESTS PASS"
