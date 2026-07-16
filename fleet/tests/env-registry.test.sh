#!/usr/bin/env bash
# env-registry.test.sh — FAIL-ON-REVERT self-test for ENV-REGISTRY-WIRE.
#
# Covers (a)-(g):
#   (a) env-registry.sh exists + is executable; runs without error and emits a non-empty
#       summary (revert -> script missing / not executable -> FAIL).
#   (b) The surfaced summary lists the LIVE gateway endpoint (revert -> endpoint line
#       gone -> FAIL — see SESSION-RECALL-CHALLENGE.md §1e: "env-registry gap" cost the
#       session multiple rediscovery probes for exactly this fact).
#   (c) The surfaced summary lists the LIVE SERVED MODELS from tier-models.tsv (the
#       exact failover chain the droid work executor hands the gateway). Revert ->
#       models line absent/empty -> FAIL.
#   (d) The surfaced summary lists the TIER->MODEL CHAIN for at least frontier/strong/
#       economy (the three cost-band tiers per fleet/state/TIER-CANON.md). Revert ->
#       tier line absent -> FAIL.
#   (e) The surfaced summary carries a HOST MAP line naming the gateway + opencode
#       auth config (so a session doesn't have to spelunk for the token source).
#       Revert -> host-map line absent -> FAIL.
#   (f) NON-VACUOUS: zero served models = RED. A truncated/empty tier-models.tsv must
#       fail loud (exit 2), never emit a silent empty summary. Revert -> if the script
#       were to swallow the failure and print a happy empty line, this test would catch
#       the silent empty pass.
#   (g) The script can be invoked to REFRESH an external registry file via
#       CHARON_ENV_REGISTRY_OUTPUT (the "prefer refreshing CG-PROVIDERS.md over a new
#       file" design lever). A revert that hardcodes an output path / always writes
#       a new file would fail this.
#
# Run:  bash fleet/tests/env-registry.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

ENV_REG_SH="$SRC/env-registry.sh"
TIER_TSV="$SRC/tier-models.tsv"
TEST_OUT="$(mktemp -t env-registry-test-XXXXXX.out)"
trap 'rm -f "$TEST_OUT" 2>/dev/null || true' EXIT

echo "== (a) env-registry.sh exists, executable, emits non-empty output =="
if [ ! -f "$ENV_REG_SH" ]; then
  bad "a0 env-registry.sh exists"
  echo
  echo "--- $PASS passed, $FAIL failed ---"
  echo "ENV-REGISTRY SELF-TEST FAILED"
  exit 1
fi
ok "a0 env-registry.sh exists"
if [ ! -x "$ENV_REG_SH" ]; then
  bad "a1 env-registry.sh is executable (run: chmod +x)"
else
  ok "a1 env-registry.sh is executable"
fi

# Use an isolated opencode config path (offline) so the test is deterministic in CI
# AND doesn't require a live gateway. The "live" path is exercised by the operator
# run; the test asserts the SURFACED summary is non-empty and contains the required
# pointers, regardless of probe status.
OFFLINE_TMP="$(mktemp -d -t env-registry-test-XXXXXX)"
mkdir -p "$OFFLINE_TMP/.config/opencode"
echo '{}' > "$OFFLINE_TMP/.config/opencode/opencode.json"
SUMMARY="$(CHARON_OPENCODE_CONFIG="$OFFLINE_TMP/.config/opencode/opencode.json" \
            CHARON_GATEWAY_URL="http://127.0.0.1:1" \
            bash "$ENV_REG_SH" 2>/dev/null)"
rm -rf "$OFFLINE_TMP"

if [ -z "$SUMMARY" ]; then
  bad "a2 env-registry.sh produced non-empty output (got empty -- REVERT)"
else
  ok "a2 env-registry.sh produced non-empty output ($(printf '%s' "$SUMMARY" | wc -l) lines)"
fi

echo "== (b) surfaced summary lists the LIVE gateway endpoint =="
if printf '%s' "$SUMMARY" | grep -qE '^gateway:[[:space:]].*://'; then
  ok "b1 summary has a 'gateway:' line with a URL"
else
  bad "b1 summary has a 'gateway:' line with a URL (REVERT -- gateway endpoint absent)"
fi
if printf '%s' "$SUMMARY" | grep -qE '10\.0\.1\.60:8080'; then
  ok "b2 summary names the live 4-LOM gateway host (10.0.1.60:8080)"
else
  bad "b2 summary names the live 4-LOM gateway host (REVERT -- env-registry gap returns)"
fi

echo "== (c) surfaced summary lists the LIVE served models from tier-models.tsv =="
# NON-VACUOUS: at least ONE of the actual tier-models.tsv model ids must appear on a
# 'models:' line. The tier-models.tsv is git-tracked and stable, so a specific known
# model (deepseek-v4-pro) is the assertion anchor — it would change on a real chain
# edit and the test would need to follow, which is the correct fail-on-revert behavior.
models_line="$(printf '%s' "$SUMMARY" | grep -E '^models:' | head -1)"
if [ -n "$models_line" ]; then
  ok "c1 summary has a 'models:' line"
else
  bad "c1 summary has a 'models:' line (REVERT -- served-models line absent)"
fi
if printf '%s' "$models_line" | grep -qE '\[.+,.+\]'; then
  ok "c2 models: line has at least 2 models in the served list"
else
  bad "c2 models: line has at least 2 models in the served list (REVERT -- empty models line)"
fi
# Anchor: at least one well-known model from the canonical tier-models.tsv chain must
# surface. deepseek-v4-pro is the frontier leg; it has been in the chain across the
# light-models-eval revision per tier-models.tsv's REVISED 2026-07-12 comment.
if printf '%s' "$SUMMARY" | grep -qE 'deepseek-v4-pro'; then
  ok "c3 summary lists the live served model deepseek-v4-pro (frontier)"
else
  bad "c3 summary lists the live served model deepseek-v4-pro (REVERT -- tier-models.tsv chain not surfaced)"
fi

echo "== (d) surfaced summary lists the TIER->MODEL CHAIN for frontier/strong/economy =="
for tier in frontier strong economy; do
  # frontier appears on the 'tiers:' line ("tiers:      frontier=..."), while strong +
  # economy are indented continuation lines ("            strong=..."). Match the substring
  # anywhere on a line so both layouts pass.
  if printf '%s' "$SUMMARY" | grep -qE "(^|[[:space:]])${tier}="; then
    ok "d tier line present: $tier=..."
  else
    bad "d tier line present: $tier=... (REVERT -- $tier chain absent from summary)"
  fi
done

echo "== (e) surfaced summary carries the HOST MAP =="
if printf '%s' "$SUMMARY" | grep -qE '^host-map:'; then
  ok "e1 summary has a 'host-map:' line"
else
  bad "e1 summary has a 'host-map:' line (REVERT -- session has to re-spelunk the gateway + token source)"
fi
if printf '%s' "$SUMMARY" | grep -qE 'opencode.*\.json'; then
  ok "e2 host-map names the opencode config (Bearer token source)"
else
  bad "e2 host-map names the opencode config (REVERT -- token source lost)"
fi

echo "== (f) NON-VACUOUS — zero served models = RED (never a silent empty pass) =="
# Drive the script with a tier-models.tsv whose three tier rows are blank. parse_tier_chain
# returns "" for each, so served is empty, and emit_compact must exit 2. If the script
# were to swallow that and print a happy empty summary line, the served-model assertion
# in (c) would also catch it — but (f) is the dedicated gate for the silent-empty pass.
EMPTY_DIR="$(mktemp -d -t env-registry-empty-XXXXXX)"
{
  echo "# empty fixture: all three tier rows blank"
  echo "frontier	"
  echo "strong	"
  echo "economy	"
} > "$EMPTY_DIR/tier-models.tsv"
RC=0
set +e
( cd "$EMPTY_DIR" && CHARON_FLEET_ROOT="$EMPTY_DIR" bash "$ENV_REG_SH" ) >/dev/null 2>&1
RC=$?
set -e 2>/dev/null || true
rm -rf "$EMPTY_DIR"
if [ "$RC" -ne 0 ]; then
  ok "f zero served models -> exit $RC (RED, never a silent empty pass)"
else
  bad "f zero served models -> exit $RC (REVERT — empty tier-models.tsv must fail loud)"
fi

echo "== (g) CHARON_ENV_REGISTRY_OUTPUT refresh path writes the surfaced summary =="
set +e
( CHARON_ENV_REGISTRY_OUTPUT="$TEST_OUT" bash "$ENV_REG_SH" ) >/dev/null 2>&1
WR=$?
set -e 2>/dev/null || true
if [ "$WR" -eq 0 ] && [ -s "$TEST_OUT" ]; then
  ok "g1 CHARON_ENV_REGISTRY_OUTPUT=<file> writes the surfaced summary (refresh CG-PROVIDERS.md path)"
else
  bad "g1 CHARON_ENV_REGISTRY_OUTPUT=<file> writes the surfaced summary (REVERT -- refresh path lost; the script would always print to stdout or always write a new file)"
fi
if [ -s "$TEST_OUT" ] && grep -qE '^gateway:' "$TEST_OUT"; then
  ok "g2 written file has the same gateway endpoint line (proves the refresh is a verbatim emit, not a degraded path)"
else
  bad "g2 written file has the same gateway endpoint line (REVERT -- refresh emits a different/degraded format)"
fi

echo
echo "--- $PASS passed, $FAIL failed ---"
if [ "$FAIL" -ne 0 ]; then
  echo "ENV-REGISTRY SELF-TEST FAILED"
  exit 1
fi
echo "ALL ENV-REGISTRY SELF-TESTS PASS"
exit 0
