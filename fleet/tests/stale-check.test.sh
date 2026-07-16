#!/usr/bin/env bash
# stale-check.test.sh — FAIL-ON-REVERT hermetic tests for fleet/stale-check.sh.
# stale-check flags a fixture session past the stall threshold and exits nonzero.
# REVERT CONTRACT: if someone strips the stale-detection logic out of stale-check.sh
# so it always exits 0, this test MUST fail (revert->silent->exit0->test catches it).
# Hermetic: fixture dirs, no network, no touching live board/state.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
ok(){ printf '  PASS: %s\n' "$*"; }
bad(){ printf '  FAIL: %s\n' "$*"; fail=1; }

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
CLAIMS="$TMP/claims"
LOOPGUARD="$TMP/loop-guard"
mkdir -p "$CLAIMS" "$LOOPGUARD"

now="$(date +%s)"

# (a) stale claim — last modified 1000s ago (threshold=900 → stale)
printf 'stub-droid-stale\n' > "$CLAIMS/STALE-TKT"
touch -d "@$((now - 1000))" "$CLAIMS/STALE-TKT"

# (b) fresh claim — 30s ago (under threshold → should NOT be flagged)
printf 'stub-droid-fresh\n' > "$CLAIMS/FRESH-TKT"
touch -d "@$((now - 30))" "$CLAIMS/FRESH-TKT"

# (c) loop-guard quarantine marker
cat > "$LOOPGUARD/QUAR-TKT" <<'EOF'
droid=stub-droid-quar
count=2
threshold=2
quarantined=2026-07-14T00:00:00Z
reason=repeated zero-commit re-claims (fixture)
EOF

export STALE_CLAIMS_DIR="$CLAIMS"
export STALE_LOOPGUARD_DIR="$LOOPGUARD"
export STALE_THRESHOLD_S=900

echo "== (1) stale-check flags STALE fixture and exits nonzero =="
out1="$(bash "$HERE/stale-check.sh" 2>&1)"
rc1=$?

if [ "$rc1" -ne 0 ]; then
  ok "exit code $rc1 (nonzero) for stale fixture"
else
  bad "exit code 0 despite stale fixture — revert detection failure"
fi
if echo "$out1" | grep -q 'STALE-TKT'; then
  ok "STALE-TKT (age 1000s > 900s) flagged"
else
  bad "STALE-TKT not flagged. Output: $out1"
fi

echo "== (2) FRESH fixture NOT flagged =="
if echo "$out1" | grep -q 'FRESH-TKT'; then
  bad "FRESH-TKT (age 30s) wrongly flagged. Output: $out1"
else
  ok "FRESH-TKT (age 30s) NOT flagged"
fi

echo "== (3) loop-guard quarantine marker flagged =="
if echo "$out1" | grep -q 'QUAR-TKT'; then
  ok "loop-guard quarantine QUAR-TKT flagged"
else
  bad "QUAR-TKT (quarantine marker) not flagged. Output: $out1"
fi

echo "== (4) no-stale no-quarantine scenario exits 0 =="
CLAIMS_CLEAN="$TMP/claims-clean"
LOOPGUARD_CLEAN="$TMP/loop-guard-clean"
mkdir -p "$CLAIMS_CLEAN" "$LOOPGUARD_CLEAN"

printf 'stub-droid-fresh\n' > "$CLAIMS_CLEAN/FRESH-ONLY"
touch -d "@$((now - 30))" "$CLAIMS_CLEAN/FRESH-ONLY"

out4="$(STALE_CLAIMS_DIR="$CLAIMS_CLEAN" STALE_LOOPGUARD_DIR="$LOOPGUARD_CLEAN" STALE_THRESHOLD_S=900 bash "$HERE/stale-check.sh" 2>&1)"
rc4=$?

if [ "$rc4" -eq 0 ]; then
  ok "exit code 0 when nothing stale/quarantined"
else
  bad "exit code $rc4 despite nothing stale/quarantined. Output: $out4"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "stale-check.test.sh: ALL PASS"
  exit 0
else
  echo "stale-check.test.sh: FAILURES ABOVE"
  exit 1
fi
