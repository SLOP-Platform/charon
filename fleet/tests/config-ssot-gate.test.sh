#!/usr/bin/env bash
# config-ssot-gate.test.sh — PLANE CANARY DOGFOOD for the config-ssot plane.
#
# REGISTRY: fleet/plane-canary-registry.tsv row 9, ticket CONFIG-SSOT-CANARY-REGISTER.
#   plane=config-ssot  canary=fleet/checks/config-ssot-gate.sh
#   dogfood=fleet/tests/config-ssot-gate.test.sh  wired_in=preflight
#
# This IS a fail-on-revert fault-seed test. It SEEDS a real manifest/reader
# divergence (KEY-ENV mismatch — exactly the shape the egress-key exfil class
# rides), runs the UNMODIFIED fleet/checks/config-ssot-gate.sh against hermetic
# fixtures, and asserts the gate goes RED (non-zero exit). Correcting the
# fixture flips GREEN; reverting the fix flips RED again — so no assertion is a
# tautology.
#
# FULLY HERMETIC / OFFLINE. Fixtures are written into a temp dir and routed via
# CONFIG_MANIFEST_TSV, CHARON_LOCAL_PROVIDERS, GATEWAY_PROVIDERS_RCMD. No live
# ~/.charon, no live 4-LOM, nothing leaves the box.
#
# Run:  bash fleet/tests/config-ssot-gate.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$SRC/checks/config-ssot-gate.sh"
[ -f "$GATE" ] || { echo "FAIL: cannot find $GATE" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# write_manifest <path> <provider>:<key>:<url> ...
write_manifest(){
  local path="$1"; shift
  {
    printf 'provider\tkey_env\tbase_url\ttiers\tnote\n'
    for row in "$@"; do
      IFS=: read -r name key url <<< "$row"
      printf '%s\t%s\t%s\tpaid\tnote-for-%s\n' "$name" "$key" "$url" "$name"
    done
  } > "$path"
}

write_providers(){ printf '%s' "$2" > "$1"; }

# run_gate <manifest> <local-providers-path> <gateway-providers-path>
GATEWAY_RCMD="cat {}"
run_gate(){
  local m="$1" lp="$2" gp="$3"
  CONFIG_MANIFEST_TSV="$m" CHARON_LOCAL_PROVIDERS="$lp" \
    GATEWAY_PROVIDERS_RCMD="$GATEWAY_RCMD" GATEWAY_PROVIDERS_PATH="$gp" \
    bash "$GATE" 2>&1
}

# ── Test 1: seeded KEY-ENV mismatch on local -> RED ──
M1="$WORK/m1.tsv"
write_manifest "$M1" "alpha:ALPHA_KEY:https://a/v1" "beta:BETA_KEY:https://b/v1"
L1="$WORK/l1.json"
write_providers "$L1" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"},"beta":{"key_env":"WRONG_KEY_ENV","base_url":"https://b/v1"}}'
G1="$WORK/g1.json"
write_providers "$G1" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"},"beta":{"key_env":"BETA_KEY","base_url":"https://b/v1"}}'
rc=0
out="$(run_gate "$M1" "$L1" "$G1")" || rc=$?
[ "$rc" != 0 ] && ok "1 seeded KEY-ENV mismatch on local -> RED (rc=$rc)" \
              || bad "1 seeded KEY-ENV mismatch must RED (rc=$rc)"
printf '%s' "$out" | grep -q "KEY-ENV MISMATCH.*beta" && ok "1 names KEY-ENV MISMATCH on beta" \
                                                 || bad "1 must name KEY-ENV MISMATCH on beta"

# ── Test 1-fix: correct the key_env -> GREEN ──
write_providers "$L1" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"},"beta":{"key_env":"BETA_KEY","base_url":"https://b/v1"}}'
rc=0
out="$(run_gate "$M1" "$L1" "$G1")" || rc=$?
[ "$rc" = 0 ] && ok "1-fix corrected key_env -> GREEN (rc=0)" \
              || bad "1-fix corrected key_env must GREEN (rc=$rc)"
printf '%s' "$out" | grep -q "SSOT-GATE: GREEN" && ok "1-fix emits GREEN verdict" \
                                              || bad "1-fix must print GREEN"

# ── Test 1-revert: re-seed the mismatch -> RED again (not a tautology) ──
write_providers "$L1" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"},"beta":{"key_env":"WRONG_KEY_ENV","base_url":"https://b/v1"}}'
rc=0
out="$(run_gate "$M1" "$L1" "$G1")" || rc=$?
[ "$rc" != 0 ] && ok "1-revert re-seeded KEY-ENV mismatch -> RED again (rc=$rc, not a tautology)" \
              || bad "1-revert re-seeded mismatch must RED (rc=$rc) — tautology bug?"

# ── Test 2: seeded BASE-URL mismatch on local (a 2nd drift class) -> RED ──
M2="$WORK/m2.tsv"
write_manifest "$M2" "gamma:GAMMA_KEY:https://g/v1"
L2="$WORK/l2.json"
write_providers "$L2" '{"gamma":{"key_env":"GAMMA_KEY","base_url":"https://DIFFERENT.example/v1"}}'
G2="$WORK/g2.json"
write_providers "$G2" '{"gamma":{"key_env":"GAMMA_KEY","base_url":"https://g/v1"}}'
rc=0
out="$(run_gate "$M2" "$L2" "$G2")" || rc=$?
[ "$rc" != 0 ] && ok "2 seeded BASE-URL mismatch on local -> RED (rc=$rc)" \
              || bad "2 seeded BASE-URL mismatch must RED (rc=$rc)"
printf '%s' "$out" | grep -q "BASE-URL MISMATCH.*gamma" && ok "2 names BASE-URL MISMATCH on gamma" \
                                                      || bad "2 must name BASE-URL MISMATCH on gamma"

# ── Test 2-fix: correct the base_url -> GREEN ──
write_providers "$L2" '{"gamma":{"key_env":"GAMMA_KEY","base_url":"https://g/v1"}}'
rc=0
out="$(run_gate "$M2" "$L2" "$G2")" || rc=$?
[ "$rc" = 0 ] && ok "2-fix corrected base_url -> GREEN (rc=0)" \
              || bad "2-fix corrected base_url must GREEN (rc=$rc)"

# ── Test 2-revert: re-seed the mismatch -> RED again ──
write_providers "$L2" '{"gamma":{"key_env":"GAMMA_KEY","base_url":"https://DIFFERENT.example/v1"}}'
rc=0
out="$(run_gate "$M2" "$L2" "$G2")" || rc=$?
[ "$rc" != 0 ] && ok "2-revert re-seeded BASE-URL mismatch -> RED again (not a tautology)" \
              || bad "2-revert re-seeded mismatch must RED — tautology bug?"

# ── Test 3: local source UNREACHABLE must NOT false-GREEN (load-bearing) ──
M3="$WORK/m3.tsv"
write_manifest "$M3" "delta:DELTA_KEY:https://d/v1"
L3="$WORK/l3.json"
# point the local providers path at a nonexistent file
CHARON_LOCAL_PROVIDERS="/dev/null/NOPE/missing.json"
rc=0
out="$(CONFIG_MANIFEST_TSV="$M3" CHARON_LOCAL_PROVIDERS="$CHARON_LOCAL_PROVIDERS" \
       GATEWAY_PROVIDERS_RCMD="$GATEWAY_RCMD" GATEWAY_PROVIDERS_PATH="$G1" \
       bash "$GATE" 2>&1)" || rc=$?
[ "$rc" != 0 ] && ok "3 unreachable local source -> RED (no false-GREEN)" \
              || bad "3 unreachable local must RED (rc=$rc)"
printf '%s' "$out" | grep -q "UNREACHABLE" && ok "3 reports UNREACHABLE for the local source" \
                                         || bad "3 must report UNREACHABLE"

echo "--- config-ssot-gate.test: $PASS passed, $FAIL failed ---"
[ "$FAIL" = 0 ] || exit 1
echo "ALL CONFIG-SSOT PLANE DOGFOOD TESTS PASS"
