#!/usr/bin/env bash
# config-ssot.test.sh — FAIL-ON-REVERT tests for the SSOT manifest + gate + sync stack.
#
# GUARDS the operator's "config siloed + drifts invisibly" class fix. Reverting any of the
# load-bearing pieces — manifest parsing, MISSING-LOCALLY / MISSING-ON-GATEWAY / UNREACHABLE
# classification, or the IDEMPOTENT sync write — flips these RED.
#
# Fully hermetic: every fixture (manifest, local providers.json, gateway read-cmd) is written
# into a temp dir and pointed at via env vars (CONFIG_MANIFEST_TSV, CHARON_LOCAL_PROVIDERS,
# GATEWAY_PROVIDERS_RCMD). NEVER touches the live 4-LOM or ~/.charon.
#
# Run:  bash fleet/tests/config-ssot.test.sh   (exit 0 = all pass)
set -uo pipefail
FLEET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$FLEET_DIR/checks/config-ssot-gate.sh"
SYNC="$FLEET_DIR/config-sync.sh"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# write_manifest <path> <provider>:<key>:<url> <provider>:<key>:<url> ...
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

# write_providers <path> <json-content>
write_providers(){ printf '%s' "$2" > "$1"; }

# Read-cmd template: {} -> the full gateway file path. Production default is
# `docker exec -i charon-gateway-1 cat /data/{}` (substitutes the basename into /data).
# Tests use a plain `cat {}` against a temp file, plus GATEWAY_PROVIDERS_PATH=<full-path>.
GATEWAY_RCMD="cat {}"

# run_gate <manifest> <local-providers-path> [gateway-providers-path-or-empty-for-unreachable]
run_gate(){
  local m="$1" lp="$2" gp="${3:-}"
  if [ -n "$gp" ]; then
    CONFIG_MANIFEST_TSV="$m" CHARON_LOCAL_PROVIDERS="$lp" \
       GATEWAY_PROVIDERS_RCMD="$GATEWAY_RCMD" GATEWAY_PROVIDERS_PATH="$gp" \
       bash "$GATE" 2>&1
  else
    CONFIG_MANIFEST_TSV="$m" CHARON_LOCAL_PROVIDERS="$lp" \
       GATEWAY_PROVIDERS_RCMD="cat {}/NOPE/missing.json" GATEWAY_PROVIDERS_PATH="never_read.json" \
       bash "$GATE" 2>&1
  fi
}

# ── Test 1: in-sync -> GREEN (exit 0) ──
M1="$WORK/m1.tsv"; write_manifest "$M1" "alpha:ALPHA_KEY:https://a/v1" "beta:BETA_KEY:https://b/v1"
L1="$WORK/l1.json"; write_providers "$L1" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"},"beta":{"key_env":"BETA_KEY","base_url":"https://b/v1"}}'
G1="$WORK/g1.json"; write_providers "$G1" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"},"beta":{"key_env":"BETA_KEY","base_url":"https://b/v1"}}'
rc=0
out="$(run_gate "$M1" "$L1" "$G1")" || rc=$?
if [ "$rc" = 0 ]; then ok "1 in-sync -> GREEN (rc=0)"; else bad "1 in-sync must be GREEN (rc=$rc)"; printf '%s\n' "$out" | tail -10; fi
printf '%s' "$out" | grep -q "SSOT-GATE: GREEN" && ok "1 emits GREEN verdict line" || bad "1 must print GREEN"

# ── Test 2: local missing a manifest row -> RED, names the drift, names the fix command ──
M2="$WORK/m2.tsv"; write_manifest "$M2" "alpha:ALPHA_KEY:https://a/v1" "beta:BETA_KEY:https://b/v1" "gamma:GAMMA_KEY:https://g/v1"
L2="$WORK/l2.json"; write_providers "$L2" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"}}'
G2="$WORK/g2.json"; write_providers "$G2" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"},"beta":{"key_env":"BETA_KEY","base_url":"https://b/v1"},"gamma":{"key_env":"GAMMA_KEY","base_url":"https://g/v1"}}'
rc=0
out="$(run_gate "$M2" "$L2" "$G2")" || rc=$?
[ "$rc" != 0 ] && ok "2 seeded local-drift -> RED (rc=$rc)" || bad "2 seeded drift must RED"
printf '%s' "$out" | grep -q "MISSING-LOCALLY.*beta" && ok "2 names MISSING-LOCALLY beta" || bad "2 must name beta as MISSING-LOCALLY"
printf '%s' "$out" | grep -q "MISSING-LOCALLY.*gamma" && ok "2 names MISSING-LOCALLY gamma" || bad "2 must name gamma as MISSING-LOCALLY"
printf '%s' "$out" | grep -q "config-sync.sh" && ok "2 names the fix command (config-sync.sh)" || bad "2 must name config-sync.sh as the fix"

# ── Test 3: gateway missing a manifest row -> RED, names MISSING-ON-GATEWAY ──
M3="$WORK/m3.tsv"; write_manifest "$M3" "alpha:ALPHA_KEY:https://a/v1" "delta:DELTA_KEY:https://d/v1"
L3="$WORK/l3.json"; write_providers "$L3" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"},"delta":{"key_env":"DELTA_KEY","base_url":"https://d/v1"}}'
G3="$WORK/g3.json"; write_providers "$G3" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"}}'
rc=0
out="$(run_gate "$M3" "$L3" "$G3")" || rc=$?
[ "$rc" != 0 ] && ok "3 gateway missing a row -> RED" || bad "3 gateway missing a row must RED"
printf '%s' "$out" | grep -q "MISSING-ON-GATEWAY.*delta" && ok "3 names MISSING-ON-GATEWAY delta" || bad "3 must name delta as MISSING-ON-GATEWAY"

# ── Test 4: base_url mismatch on a shared provider -> RED, names the mismatch ──
M4="$WORK/m4.tsv"; write_manifest "$M4" "alpha:ALPHA_KEY:https://a/v1"
L4="$WORK/l4.json"; write_providers "$L4" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://WRONG/v1"}}'
G4="$WORK/g4.json"; write_providers "$G4" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"}}'
rc=0
out="$(run_gate "$M4" "$L4" "$G4")" || rc=$?
[ "$rc" != 0 ] && ok "4 base_url mismatch -> RED" || bad "4 base_url mismatch must RED"
printf '%s' "$out" | grep -q "BASE-URL MISMATCH.*alpha" && ok "4 names BASE-URL MISMATCH alpha" || bad "4 must name alpha as BASE-URL MISMATCH"

# ── Test 5: UNREACHABLE source must NOT false-GREEN (the load-bearing bug this gate exists to close) ──
M5="$WORK/m5.tsv"; write_manifest "$M5" "alpha:ALPHA_KEY:https://a/v1"
L5="$WORK/l5.json"; write_providers "$L5" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"}}'
rc=0
out="$(run_gate "$M5" "$L5" "")" || rc=$?
[ "$rc" != 0 ] && ok "5 unreachable gateway -> RED (no false-GREEN)" || bad "5 unreachable gateway must RED (got 0)"
printf '%s' "$out" | grep -q "UNREACHABLE (1)" && ok "5 reports 1 UNREACHABLE source" || bad "5 must report UNREACHABLE count"
printf '%s' "$out" | grep -q "gateway:" && ok "5 names the unreachable source as 'gateway'" || bad "5 must name gateway as the unreachable source"

# ── Test 6: --advisory exits 0 even with drift (so preflight can boot) ──
M6="$WORK/m6.tsv"; write_manifest "$M6" "alpha:ALPHA_KEY:https://a/v1" "ghost:GHOST_KEY:https://g/v1"
L6="$WORK/l6.json"; write_providers "$L6" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"}}'
G6="$WORK/g6.json"; write_providers "$G6" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"}}'
rc=0
out="$(CONFIG_MANIFEST_TSV="$M6" CHARON_LOCAL_PROVIDERS="$L6" \
       GATEWAY_PROVIDERS_RCMD="$GATEWAY_RCMD" GATEWAY_PROVIDERS_PATH="$G6" \
       bash "$GATE" --advisory 2>&1)" || rc=$?
[ "$rc" = 0 ] && ok "6 --advisory exits 0 despite drift" || bad "6 --advisory must exit 0 (got $rc)"
printf '%s' "$out" | grep -qE "DRIFT \([0-9]+\)" && ok "6 --advisory still prints the drift count" || bad "6 --advisory must still print DRIFT count"

# ── Test 7: UNEXPECTED-LOCAL — a row on local that's not on the manifest is named, not silently passed ──
M7="$WORK/m7.tsv"; write_manifest "$M7" "alpha:ALPHA_KEY:https://a/v1"
L7="$WORK/l7.json"; write_providers "$L7" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"},"orphan":{"key_env":"ORPHAN_KEY","base_url":"https://o/v1"}}'
G7="$WORK/g7.json"; write_providers "$G7" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"}}'
rc=0
out="$(run_gate "$M7" "$L7" "$G7")" || rc=$?
[ "$rc" != 0 ] && ok "7 unexpected local row -> RED" || bad "7 unexpected local must RED"
printf '%s' "$out" | grep -q "UNEXPECTED-LOCAL.*orphan" && ok "7 names UNEXPECTED-LOCAL orphan" || bad "7 must name orphan as UNEXPECTED-LOCAL"

# ── Test 8: manifest is well-formed-only — a malformed row (NF!=5) is a HARD ERROR, not a silent skip ──
M8="$WORK/m8.tsv"; printf 'provider\tkey_env\tbase_url\ttiers\tnote\nalpha\tALPHA_KEY\n' > "$M8"
L8="$WORK/l8.json"; write_providers "$L8" '{}'
out="$(run_gate "$M8" "$L8" "")" ; rc=$?
[ "$rc" = 3 ] && ok "8 malformed manifest row -> HARD ERROR (rc=3, not silent skip)" || bad "8 malformed manifest must HARD-ERROR (rc=$rc)"
printf '%s' "$out" | grep -q "malformed" && ok "8 explains the malformed row" || bad "8 must explain the malformed row"

# ── Test 9: SYNC writes the manifest to local idempotently (drift -> in-sync) ──
M9="$WORK/m9.tsv"; write_manifest "$M9" "alpha:ALPHA_KEY:https://a/v1" "beta:BETA_KEY:https://b/v1"
L9="$WORK/l9.json"; write_providers "$L9" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://WRONG/v1"}}'
CHARON_LOCAL_PROVIDERS="$L9" CONFIG_MANIFEST_TSV="$M9" bash "$SYNC" >/dev/null 2>&1 || true
written="$(cat "$L9")"
printf '%s' "$written" | grep -q '"alpha":' && ok "9 SYNC wrote alpha to local" || bad "9 SYNC did not write alpha"
printf '%s' "$written" | grep -q '"beta":' && ok "9 SYNC wrote beta to local" || bad "9 SYNC did not write beta"
printf '%s' "$written" | grep -q 'https://a/v1' && ok "9 SYNC restored alpha's base_url from manifest" || bad "9 SYNC did not restore alpha's base_url"
bak_before="$(ls "$L9".bak-* 2>/dev/null | wc -l)"
CHARON_LOCAL_PROVIDERS="$L9" CONFIG_MANIFEST_TSV="$M9" bash "$SYNC" >/dev/null 2>&1 || true
bak_after="$(ls "$L9".bak-* 2>/dev/null | wc -l)"
[ "$bak_before" = "$bak_after" ] && ok "9 second SYNC is a no-op (no backup churn; idempotent)" \
                                   || bad "9 second SYNC must not backup (before=$bak_before, after=$bak_after)"

# ── Test 10: GATEWAY write path is REFUSED without --force (production write never accidental) ──
out="$(bash "$SYNC" --gateway 2>&1)"; rc=$?
[ "$rc" = 2 ] && ok "10 --gateway without --force is REFUSED (rc=2)" || bad "10 --gateway must be REFUSED (rc=$rc)"
printf '%s' "$out" | grep -q "REFUSED" && ok "10 refusal is loud (prints REFUSED)" || bad "10 refusal must print REFUSED"
printf '%s' "$out" | grep -q "write-path=exec" && ok "10 refusal documents --write-path=exec" || bad "10 refusal must document exec path"
printf '%s' "$out" | grep -q "write-path=volume" && ok "10 refusal documents --write-path=volume" || bad "10 refusal must document volume path"

# ── Test 10b: GATEWAY --force --dry-run prints the exact docker-exec commands without applying ──
out="$(bash "$SYNC" --gateway --force --dry-run 2>&1)"; rc=$?
[ "$rc" = 0 ] && ok "10b --gateway --force --dry-run exits 0" || bad "10b dry-run must exit 0 (got $rc)"
printf '%s' "$out" | grep -q "DRYRUN" && ok "10b dry-run prints DRYRUN marker" || bad "10b dry-run must print DRYRUN"
printf '%s' "$out" | grep -q "charon providers set\|providers set" && ok "10b dry-run prints the charon providers set command" \
                                                          || bad "10b dry-run must print providers set command"
printf '%s' "$out" | grep -q "charon-gateway-1" && ok "10b dry-run names the target container" || bad "10b must name charon-gateway-1"

# ── Test 11: FAIL-ON-REVERT — neuter the unreachable-hard-RED check, expect unreachable to flip GREEN ──
rev="$WORK/gate.reverted.sh"
sed 's#unreach.append(("gateway", gw_path, "read-failed or invalid JSON"))#pass#' \
    "$GATE" > "$rev"
chmod +x "$rev"
rc=0
out="$(CONFIG_MANIFEST_TSV="$M5" CHARON_LOCAL_PROVIDERS="$L5" \
       GATEWAY_PROVIDERS_RCMD="cat {}/NOPE/missing.json" GATEWAY_PROVIDERS_PATH="never_read.json" \
       bash "$rev" 2>&1)" || rc=$?
[ "$rc" = 0 ] && ok "11 reverting the unreachable-hard-RED check flips unreachable -> GREEN (check is load-bearing)" \
              || bad "11 reverted gate should GREEN unreachable (got exit $rc) — sed did not neuter the check"

# ── Test 12: never prints a key VALUE (a fixture with an api_key value remains value-free in output) ──
M12="$WORK/m12.tsv"; write_manifest "$M12" "alpha:ALPHA_KEY:https://a/v1"
L12="$WORK/l12.json"; write_providers "$L12" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1","api_key":"sk-SHOULD-NEVER-PRINT-1234567890"}}'
G12="$WORK/g12.json"; write_providers "$G12" '{"alpha":{"key_env":"ALPHA_KEY","base_url":"https://a/v1"}}'
out="$(run_gate "$M12" "$L12" "$G12")"
if printf '%s' "$out" | grep -q 'sk-SHOULD-NEVER-PRINT'; then bad "12 LEAK: printed a key value"; else ok "12 never prints a key value"; fi

echo "--- config-ssot.test: $PASS passed, $FAIL failed ---"
[ "$FAIL" = 0 ]
