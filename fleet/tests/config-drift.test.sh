#!/usr/bin/env bash
# config-drift.test.sh — FAIL-ON-REVERT tests for fleet/config-drift.sh.
#
# GUARDS the operator's "config siloed + drifts invisibly" fix: reverting the reconcile core
# (drift detection, unreachable-not-false-green, or the DRIFT count) flips these RED.
#
# Fully hermetic: uses LOCAL fixture registries pointing at fake providers.json/models.json under
# a temp dir (kind=local, `cat` read-cmd). NO dependency on the live 4-LOM or ~/.charon.
#
# Run:  bash fleet/tests/config-drift.test.sh   (exit 0 = all pass)
set -uo pipefail
FLEET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$FLEET_DIR/config-drift.sh"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# write_source <dir> <providers-json> <models-json>
write_source(){
  mkdir -p "$1"
  printf '%s' "$2" > "$1/providers.json"
  printf '%s' "$3" > "$1/models.json"
}
# registry <path> : appends rows; each row is a local `cat <dir>/{}` source.
add_row(){ printf '%s\tlocal\tcat %s/{}\t%s\n' "$1" "$2" "$3" >> "$4"; }

PROV_AB='{"alpha":{"base_url":"https://a.example/v1","key_env":"ALPHA_KEY"},"beta":{"base_url":"https://b.example/v1","key_env":"BETA_KEY"}}'
PROV_A='{"alpha":{"base_url":"https://a.example/v1","key_env":"ALPHA_KEY"}}'
PROV_A_DIFFURL='{"alpha":{"base_url":"https://DIFFERENT.example/v1","key_env":"ALPHA_KEY"}}'
MODELS='{"m1":{},"m2":{}}'

# ── Test 1: two sources DISAGREE (provider only in one) -> DRIFT, exit non-zero ──
write_source "$WORK/s1a" "$PROV_AB" "$MODELS"
write_source "$WORK/s1b" "$PROV_A"  "$MODELS"
REG1="$WORK/reg1.tsv"; : > "$REG1"
add_row srcA "$WORK/s1a" "fixture A" "$REG1"
add_row srcB "$WORK/s1b" "fixture B" "$REG1"
out="$(CONFIG_SOURCES_TSV="$REG1" bash "$SCRIPT" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ]; then ok "disagreeing sources exit non-zero (rc=$rc)"; else bad "disagreeing sources must exit non-zero (got 0)"; fi
if printf '%s' "$out" | grep -q 'DRIFT: 1'; then ok "reports DRIFT: 1 (beta present only in srcA)"; else bad "expected 'DRIFT: 1'"; echo "$out"; fi
if printf '%s' "$out" | grep -q 'beta.*DRIFT'; then ok "flags the beta row as DRIFT"; else bad "beta row not flagged DRIFT"; fi

# ── Test 2: identical sources -> exit 0, DRIFT: 0 ──
write_source "$WORK/s2a" "$PROV_AB" "$MODELS"
write_source "$WORK/s2b" "$PROV_AB" "$MODELS"
REG2="$WORK/reg2.tsv"; : > "$REG2"
add_row srcA "$WORK/s2a" "fixture A" "$REG2"
add_row srcB "$WORK/s2b" "fixture B" "$REG2"
out="$(CONFIG_SOURCES_TSV="$REG2" bash "$SCRIPT" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ]; then ok "identical sources exit 0"; else bad "identical sources must exit 0 (got $rc)"; echo "$out"; fi
if printf '%s' "$out" | grep -q 'DRIFT: 0'; then ok "identical sources report DRIFT: 0"; else bad "expected 'DRIFT: 0'"; echo "$out"; fi

# ── Test 3: base_url mismatch on a shared provider -> DRIFT ──
write_source "$WORK/s3a" "$PROV_A"         "$MODELS"
write_source "$WORK/s3b" "$PROV_A_DIFFURL" "$MODELS"
REG3="$WORK/reg3.tsv"; : > "$REG3"
add_row srcA "$WORK/s3a" "fixture A" "$REG3"
add_row srcB "$WORK/s3b" "fixture B" "$REG3"
out="$(CONFIG_SOURCES_TSV="$REG3" bash "$SCRIPT" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'alpha.*NO.*DRIFT'; then ok "base_url mismatch flagged as DRIFT + non-zero exit"; else bad "base_url mismatch must DRIFT (rc=$rc)"; echo "$out"; fi

# ── Test 4: unreachable source must NOT false-GREEN (own state, named, exit non-zero) ──
write_source "$WORK/s4a" "$PROV_AB" "$MODELS"
REG4="$WORK/reg4.tsv"; : > "$REG4"
add_row srcA "$WORK/s4a" "fixture A" "$REG4"
# a source whose read-cmd fails (missing dir) — must be reported UNREACHABLE, not in-sync
add_row deadsrc "$WORK/NOPE_MISSING" "unreachable fixture" "$REG4"
out="$(CONFIG_SOURCES_TSV="$REG4" bash "$SCRIPT" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ]; then ok "unreachable source exits non-zero (no false-GREEN)"; else bad "unreachable source must exit non-zero (got 0)"; echo "$out"; fi
if printf '%s' "$out" | grep -qi "UNREACHABLE.*deadsrc\|source 'deadsrc'.*UNREACHABLE"; then ok "unreachable source is NAMED"; else bad "unreachable source 'deadsrc' not named"; echo "$out"; fi
if printf '%s' "$out" | grep -q 'UNREACHABLE: 1'; then ok "reports UNREACHABLE: 1"; else bad "expected 'UNREACHABLE: 1'"; echo "$out"; fi

# ── Test 5: --advisory always exits 0 even with drift ──
out="$(CONFIG_SOURCES_TSV="$REG1" bash "$SCRIPT" --advisory 2>&1)"; rc=$?
if [ "$rc" -eq 0 ]; then ok "--advisory exits 0 despite drift"; else bad "--advisory must exit 0 (got $rc)"; fi
if printf '%s' "$out" | grep -q 'DRIFT: 1'; then ok "--advisory still prints the drift count"; else bad "--advisory must still print DRIFT count"; echo "$out"; fi

# ── Test 6: never prints a key VALUE (only names) — sanity leak check on fixtures with a value ──
PROV_SECRET='{"alpha":{"base_url":"https://a.example/v1","key_env":"ALPHA_KEY","api_key":"sk-SHOULD-NEVER-PRINT-1234567890"}}'
write_source "$WORK/s6a" "$PROV_SECRET" "$MODELS"
write_source "$WORK/s6b" "$PROV_SECRET" "$MODELS"
REG6="$WORK/reg6.tsv"; : > "$REG6"
add_row srcA "$WORK/s6a" "fixture A" "$REG6"
add_row srcB "$WORK/s6b" "fixture B" "$REG6"
out="$(CONFIG_SOURCES_TSV="$REG6" bash "$SCRIPT" 2>&1)"
if printf '%s' "$out" | grep -q 'sk-SHOULD-NEVER-PRINT'; then bad "LEAK: printed a key value"; echo "$out"; else ok "never prints a key value (names only)"; fi

echo "--- config-drift.test: $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ]
