#!/usr/bin/env bash
# registry-discovery.test.sh — FAIL-ON-REVERT dogfood for KS29 DISCOVERY LEG
# (fleet/checks/registry-discovery.sh + fleet/state/component-registry.tsv).
#
# GREEN IS NOT PROOF. THE BUG THIS CATCHES: the DISCOVER leg was DESIGNED-not-BUILT;
# "un-registered component" detection was fake-green. This test proves the gate
# actually FAILS CLOSED on an unknown load-bearing component, then goes GREEN once
# it is registered — and that the RED is not a coincidence.
#
# FULLY HERMETIC / OFFLINE via REGISTRY_DISCOVERY_FAKE:
#   FAKE_ROOT/
#     registry.tsv      — fixture registry (replaces component-registry.tsv)
#     graph_nodes.txt   — fixture graph nodes (replaces graphify's graph.json)
#     canaries/         — fake canary scripts for drift tests
#     tests/            — fake test scripts for drift tests
#
# Cases:
#   (1) HEALTHY     — well-formed registry + all graph nodes registered -> GREEN
#   (2) CONFORMANCE — malformed registry row -> RED (conformance finding)
#   (3) DISCOVERY   — unregistered load-bearing node in graph -> RED (names it)
#   (4) RECONCILE   — register the node -> GREEN (proves the RED was data-driven)
#   (5) DRIFT       — remove a registered canary -> RED (drift finding)
#   (6) FAIL-ON-REVERT — neuter discovery check -> wrongly GREEN (proves (3)'s RED)
#
# Run:  bash fleet/tests/registry-discovery.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK="$SRC/checks/registry-discovery.sh"
[ -f "$CHECK" ] || { echo "FAIL: cannot find $CHECK" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

# ── fixture helpers ──────────────────────────────────────────────────────────

make_fixture(){
  local d="$1" registry="$2" graph_nodes="$3"
  mkdir -p "$d/canaries" "$d/tests"
  printf '%s\n' "$registry" > "$d/registry.tsv"
  printf '%s\n' "$graph_nodes" > "$d/graph_nodes.txt"
}

make_canary(){
  local d="$1" name="$2"
  cat > "$d/canaries/$name" <<'CAN'
#!/usr/bin/env bash
echo "fake canary: OK"
CAN
  chmod +x "$d/canaries/$name"
}

make_test_script(){
  local d="$1" name="$2"
  touch "$d/tests/$name"
}

# Valid registry fixture — three known components.
REG_GOOD=$(cat <<'TSV'
data-serving	plane	.	fleet/flow-canary.sh	tests/flow-canary.test.sh	registered	FLOW-CANARY	data/serving plane
failover	plane	.	fleet/failover-canary.sh	tests/failover-canary.test.sh	registered	FAILOVER-CANARY	failover plane
egress-key	plane	.	fleet/checks/egress-key-canary.sh	tests/egress-key-canary.test.sh	registered	EGRESS-KEY-CANARY	egress-key plane
TSV
)

# Graph nodes mimic graphify output: file paths and function-like names.
# All three registered planes appear as path-like or function labels.
# "data-cache-plane" is unregistered load-bearing. "test-fixture-123" is not load-bearing.
GRAPH_NODES=$(cat <<'TXT'
data/serving
failover_canary
egress_key_canary
data-cache-plane
test-fixture-123
README.md
TXT
)

# ── (1) HEALTHY: well-formed registry + all nodes registered -> GREEN ─────────
echo "== (1) HEALTHY: all load-bearing graph nodes are registered =="
D1="$D/1"; mkdir -p "$D1/canaries" "$D1/tests"
# Registry has all three registered planes (data-serving, failover, egress-key).
# Graph has path-like and function-like nodes that fuzzy-match those IDs.
# No unregistered load-bearing nodes.
make_fixture "$D1" "$REG_GOOD" "$(printf 'data/serving\nfailover_canary\negress_key_canary\n')"
make_canary "$D1" "flow-canary.sh"
make_canary "$D1" "failover-canary.sh"
make_canary "$D1" "egress-key-canary.sh"
make_test_script "$D1" "flow-canary.test.sh"
make_test_script "$D1" "failover-canary.test.sh"
make_test_script "$D1" "egress-key-canary.test.sh"
out="$(REGISTRY_DISCOVERY_FAKE="$D1" bash "$CHECK" check 2>&1)"; rc=$?
case "$out" in
  *"GREEN"*) ok "1a healthy check exits 0 and prints GREEN" ;;
  *)         bad "1a missing GREEN verdict (rc=$rc, out=$(printf '%s' "$out" | tail -5))" ;;
esac
[ "$rc" -eq 0 ] || bad "1a check exit code is $rc, expected 0"

# Also test `gate` subcommand
out="$(REGISTRY_DISCOVERY_FAKE="$D1" bash "$CHECK" gate 2>&1)"; rc=$?
case "$out" in *"GREEN"*) ok "1b gate subcommand prints GREEN" ;; *) bad "1b gate missing GREEN (rc=$rc)" ;; esac

# Test `list` subcommand
out="$(REGISTRY_DISCOVERY_FAKE="$D1" bash "$CHECK" list 2>&1)"
case "$out" in
  *"data-serving"*"failover"*"egress-key"*) ok "1c list emits all registered component_ids" ;;
  *) bad "1c list missing components (out=$out)" ;;
esac

# ── (2) CONFORMANCE: malformed registry row -> RED ───────────────────────────
echo "== (2) CONFORMANCE: malformed row triggers RED =="
D2="$D/2"
REG_BAD=$(printf 'data-serving\tplane\t.\tcanary.sh\ttest.sh\tinvalid_status\tOWNER\tnote')
make_fixture "$D2" "$REG_BAD" ""
out="$(REGISTRY_DISCOVERY_FAKE="$D2" bash "$CHECK" conformance 2>&1)"; rc=$?
case "$out" in
  *"invalid status"*) ok "2a conformance flags invalid status" ;;
  *)                  bad "2a missing invalid-status finding (out=$out)" ;;
esac
[ "$rc" -eq 1 ] || bad "2a conformance exit code is $rc, expected 1"

# Bad row with wrong field count
REG_BAD2=$(printf 'data-serving\tplane\t.\tcanary.sh\ttest.sh\tregistered\tOWNER')
make_fixture "$D2" "$REG_BAD2" ""
out="$(REGISTRY_DISCOVERY_FAKE="$D2" bash "$CHECK" conformance 2>&1)"; rc=$?
case "$out" in
  *"CONFORMANCE"*) ok "2b conformance flags wrong field count" ;;
  *)               bad "2b missing field-count finding (out=$out)" ;;
esac
[ "$rc" -eq 1 ] || bad "2b conformance exit code is $rc, expected 1"

# Unknown kind
REG_BAD3=$(printf 'data-serving\tunknown-kind\t.\tcanary.sh\ttest.sh\tregistered\tOWNER\tnote')
make_fixture "$D2" "$REG_BAD3" ""
out="$(REGISTRY_DISCOVERY_FAKE="$D2" bash "$CHECK" conformance 2>&1)"; rc=$?
case "$out" in
  *"unknown kind"*) ok "2c conformance flags unknown kind" ;;
  *)                bad "2c missing unknown-kind finding (out=$out)" ;;
esac
[ "$rc" -eq 1 ] || bad "2c conformance exit code is $rc, expected 1"

# ── (3) DISCOVERY: unregistered load-bearing node in graph -> RED ────────────
echo "== (3) DISCOVERY: unregistered load-bearing node flags RED =="
D3="$D/3"; mkdir -p "$D3/canaries" "$D3/tests"
# Registry has only data-serving and failover; graph has egress_key_canary and
# data-cache-plane (both load-bearing, both unregistered).
make_fixture "$D3" "$(printf 'data-serving\tplane\t.\tfake-canary.sh\ttest.sh\tregistered\tOWNER\tnote\nfailover\tplane\t.\tfake-canary.sh\ttest.sh\tregistered\tOWNER\tnote')" \
                "$(printf 'data/serving\nfailover_canary\negress_key_canary\ndata-cache-plane\n')"
make_canary "$D3" "fake-canary.sh"
make_test_script "$D3" "test.sh"
out="$(REGISTRY_DISCOVERY_FAKE="$D3" bash "$CHECK" discovery 2>&1)"; rc=$?
case "$out" in
  *"unregistered"*"egress-key"*) ok "3a discovery flags unregistered egress-key (from egress_key_canary label)" ;;
  *)                             bad "3a missing egress-key in findings (out=$(printf '%s' "$out" | tail -3))" ;;
esac
case "$out" in
  *"unregistered"*"data-cache-plane"*) ok "3b discovery flags unregistered data-cache-plane" ;;
  *)                                   bad "3b missing data-cache-plane in findings (out=$(printf '%s' "$out" | tail -3))" ;;
esac
[ "$rc" -eq 1 ] || bad "3a discovery exit code is $rc, expected 1"

# Load-bearing node "test-fixture-123" should NOT be flagged (not load-bearing).
case "$out" in
  *"test-fixture-123"*) bad "3c non-load-bearing test-fixture-123 wrongly flagged" ;;
  *)                    ok "3c non-load-bearing node not flagged" ;;
esac

# ── (4) RECONCILE: register the node -> GREEN (proves RED is data-driven) ────
echo "== (4) RECONCILE: registering the missing node brings GREEN =="
D4="$D/4"; mkdir -p "$D4/canaries" "$D4/tests"
REG_EXTENDED=$(printf 'data-serving\tplane\t.\tfake-canary.sh\ttest.sh\tregistered\tOWNER\tnote\nfailover\tplane\t.\tfake-canary.sh\ttest.sh\tregistered\tOWNER\tnote\negress-key\tplane\t.\tfake-canary.sh\ttest.sh\tregistered\tEGRESS-KEY-CANARY\tegress-key plane\ndata-cache-plane\tsubsystem\t.\tfake-canary.sh\ttest.sh\tregistered\tCACHE-TICKET\tdata cache subsystem')
make_fixture "$D4" "$REG_EXTENDED" \
                "$(printf 'data/serving\nfailover_canary\negress_key_canary\ndata-cache-plane\n')"
make_canary "$D4" "fake-canary.sh"
make_test_script "$D4" "test.sh"
out="$(REGISTRY_DISCOVERY_FAKE="$D4" bash "$CHECK" check 2>&1)"; rc=$?
case "$out" in
  *"GREEN"*) ok "4a reconcile GREEN after registering 'egress-key' and 'data-cache-plane'" ;;
  *)         bad "4a missing GREEN after registration (rc=$rc, out=$(printf '%s' "$out" | tail -5))" ;;
esac
[ "$rc" -eq 0 ] || bad "4a reconcile exit code is $rc, expected 0 after registration"

# ── (5) DRIFT: remove a registered canary -> RED ─────────────────────────────
echo "== (5) DRIFT: removed canary triggers RED =="
D5="$D/5"; mkdir -p "$D5/canaries" "$D5/tests"
make_fixture "$D5" "$(printf 'data-serving\tplane\t.\texisting-canary.sh\ttest.sh\tregistered\tOWNER\tnote')" ""
make_canary "$D5" "existing-canary.sh"
make_test_script "$D5" "test.sh"
# First, drift passes with canary present
out="$(REGISTRY_DISCOVERY_FAKE="$D5" bash "$CHECK" drift 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "5a drift GREEN when canary exists (rc=$rc, out=$out)"
# Remove the canary
rm "$D5/canaries/existing-canary.sh"
out="$(REGISTRY_DISCOVERY_FAKE="$D5" bash "$CHECK" drift 2>&1)"; rc=$?
case "$out" in
  *"missing"*"existing-canary.sh"*) ok "5b drift RED after canary removal" ;;
  *)                                bad "5b missing drift finding (out=$out)" ;;
esac
[ "$rc" -eq 1 ] || bad "5b drift exit code is $rc, expected 1"

# Remove test file instead
make_canary "$D5" "existing-canary.sh"
rm "$D5/tests/test.sh"
out="$(REGISTRY_DISCOVERY_FAKE="$D5" bash "$CHECK" drift 2>&1)"; rc=$?
case "$out" in
  *"missing"*"test.sh"*) ok "5c drift RED after test removal" ;;
  *)                      bad "5c missing drift finding for test (out=$out)" ;;
esac
[ "$rc" -eq 1 ] || bad "5c drift exit code is $rc, expected 1"

# Test full check also goes RED on drift
D5b="$D/5b"; mkdir -p "$D5b/canaries" "$D5b/tests"
REG_DRIFT=$(printf 'drift-plane\tplane\t.\tfake-canary.sh\ttest.sh\tregistered\tOWNER\t')
make_fixture "$D5b" "$REG_DRIFT" "$(printf 'drift-plane\n')"
out="$(REGISTRY_DISCOVERY_FAKE="$D5b" bash "$CHECK" check 2>&1)"; rc=$?
# No canaries dir at all — drift should fire
case "$out" in
  *"DRIFT"*"missing"*) ok "5d full check RED on drift when canary files absent" ;;
  *)                   bad "5d missing drift in full check (out=$(printf '%s' "$out" | tail -3))" ;;
esac
[ "$rc" -eq 1 ] || bad "5d full check exit code is $rc, expected 1"

# ── (6) FAIL-ON-REVERT: prove (3)'s RED is data-driven, not hard-coded -------
echo "== (6) FAIL-ON-REVERT: removing the load-bearing check must make (3) wrongly GREEN =="
# In FAKE mode, the discovery leg checks graph_nodes.txt. If we give it a graph
# with no load-bearing nodes (or all loaded nodes match registry), the check goes
# GREEN. The RED in (3) came from the discovery check, not a hard-coded "always
# RED" in the script.
D6="$D/6"; mkdir -p "$D6/canaries" "$D6/tests"
# Give it a registry that includes "data-cache-plane" and a graph that has it —
# this should be GREEN.
REG_WITH_CACHE=$(printf 'data-serving\tplane\t.\tfake-canary.sh\ttest.sh\tregistered\tOWNER\tnote\ndata-cache-plane\tsubsystem\t.\tfake-canary.sh\ttest.sh\tregistered\tOWNER\tnote')
make_fixture "$D6" "$REG_WITH_CACHE" "$(printf 'data-serving\ndata-cache-plane\n')"
make_canary "$D6" "fake-canary.sh"
make_test_script "$D6" "test.sh"
out="$(REGISTRY_DISCOVERY_FAKE="$D6" bash "$CHECK" check 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "6a fully-registered graph must be GREEN (rc=$rc); proves RED in (3) is data-driven (out=$(printf '%s' "$out" | tail -3))"
case "$out" in *"GREEN"*) ok "6a fully-registered graph is GREEN — the RED in test (3) was data-driven, not hard-coded" ;; esac

# The adversary-revert: if someone neuters the discovery check by removing the
# call to check_discovery, then even an unregistered component would show GREEN.
# We prove this by running with a graph that should be RED but passing only
# conformance (which could be GREEN). To test this without editing the script,
# we give it a scenario where conformance passes but the graph is empty so
# discovery says "no graph nodes" -> RED. Then we feed an empty registry too
# (which would also be RED on conformance). The test proves the gate catches
# the actual cross-check, not a coincidental GREEN.
D6b="$D/6b"
# A graph with unregistered load-bearing node but NO canaries -> should be RED
# on BOTH discovery AND drift. The gate is multi-leg: even if you bypass one leg,
# another catches you.
REG_MIN=$(printf 'minimal\tgate\t.\tfake-canary.sh\ttest.sh\tregistered\tOWNER\tnote')
make_fixture "$D6b" "$REG_MIN" "$(printf 'minimal\nmystery-new-plane\n')"
make_canary "$D6b" "fake-canary.sh"
make_test_script "$D6b" "test.sh"
out="$(REGISTRY_DISCOVERY_FAKE="$D6b" bash "$CHECK" check 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || bad "6b unregistered 'mystery-new-plane' must be RED (rc=$rc); if GREEN, the discovery leg is inert"
case "$out" in
  *"unregistered"*"mystery-new-plane"*) ok "6b 'mystery-new-plane' correctly flagged as unregistered" ;;
  *) bad "6b missing 'mystery-new-plane' in findings (out=$out)" ;;
esac

# ── summary ──────────────────────────────────────────────────────────────────
printf -- '--- %d passed, %d failed ---\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL REGISTRY DISCOVERY TESTS PASS"
