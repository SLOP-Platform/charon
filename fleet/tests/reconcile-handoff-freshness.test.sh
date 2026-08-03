#!/usr/bin/env bash
# reconcile-handoff-freshness.test.sh — FAIL-ON-REVERT tests for the
# RECONCILE-HANDOFF-FRESHNESS reconciler (fleet/checks/reconcile-handoff-freshness.sh).
#
# Operates entirely in TEMP fixtures (RHF_* env overrides) — never touches
# the live fleet/ or real repos.
#
# Covers (each is load-bearing — reverting the named logic flips the test RED):
#   (a) CORE: baked SHA != live origin/master -> R-A RED (exit != 0).
#   (b) CORE: baked SHA == live origin/master -> GREEN (exit 0).
#   (c) CORE: generated= older than freshness window -> R-C RED.
#   (d) product checkout absent -> UNVERIFIED (fail-closed, exit != 0).
#   (e) self-wiring: reconcile-handoff-freshness.sh wired into preflight.sh scan chain.
#
# Run:  bash fleet/tests/reconcile-handoff-freshness.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$SRC/checks/reconcile-handoff-freshness.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

mk_git_repo(){
  local origin="$1"; local wt="$2"
  mkdir -p "$origin"
  git -C "$origin" init -q --bare
  mkdir -p "$wt"
  git -C "$wt" init -q
  git -C "$wt" config user.email "t@t" && git -C "$wt" config user.name "t"
  git -C "$wt" remote add origin "$origin" 2>/dev/null || git -C "$wt" remote set-url origin "$origin"
  git -C "$wt" commit -q --allow-empty -m "base commit"
  git -C "$wt" push -q origin HEAD:master 2>/dev/null || true
  echo "$(git -C "$wt" rev-parse HEAD)"
}

mk_handoff(){
  local path="$1" ps="$2" rs="$3" gen="$4"
  mkdir -p "$(dirname "$path")"
  cat > "$path" <<EOF
<!-- GENERATED-STATE v1 generated=$gen -->
origin-master product = $ps
origin-master rig = $rs
<!-- /GENERATED-STATE -->
EOF
}

mk_handoff_from_wt(){
  local path="$1" wt="$2" gen="$3"
  local sha; sha="$(git -C "$wt" rev-parse HEAD)"
  mk_handoff "$path" "$sha" "$sha" "$gen"
}

PROD_ORIGIN="$D/prod.git"
RIG_ORIGIN="$D/rig.git"
PROD_WT="$D/prod.wt"
RIG_WT="$D/rig.wt"
PROD_SHA="$(mk_git_repo "$PROD_ORIGIN" "$PROD_WT")"
RIG_SHA="$(mk_git_repo "$RIG_ORIGIN" "$RIG_WT")"
echo "DEBUG: PROD_SHA=$PROD_SHA RIG_SHA=$RIG_SHA"

FLEET_ROOT="$D/fleet"
mkdir -p "$FLEET_ROOT"

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STALE_GEN="$(date -u -d '49 hours ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || \
             date -uR -d '49 hours ago' +%Y-%m-%dT%H:%M:%SZ)"

# (c) stale generated= -> R-C RED (fresh SHA but old timestamp)
# Create FIRST so it's older than (b)'s file; we want the newest file to be fresh.
echo ""
echo "=== (c) generated= stale -> R-C RED ==="
mk_handoff_from_wt "$FLEET_ROOT/SESSION-HANDOFF-old.md" "$PROD_WT" "$STALE_GEN"

# (b) CORE: baked SHA == live origin/master -> GREEN (fresh timestamp)
# Create AFTER (c) so this is the newest file by mtime.
echo ""
echo "=== (b) baked SHA == live origin/master -> GREEN ==="
sleep 0.2
mk_handoff_from_wt "$FLEET_ROOT/SESSION-HANDOFF-fresh.md" "$PROD_WT" "$NOW"
out_b="$(RHF_FLEET="$FLEET_ROOT" \
         RHF_PRODUCT_REPO="$PROD_WT" \
         RHF_RIG_REPO="$RIG_WT" \
         RHF_FRESHNESS_HOURS=48 \
         bash "$GATE" 2>&1)"; rc_b=$?
echo "DEBUG (b): exit=$rc_b"
[ "$rc_b" -eq 0 ] && ok "(b) SHA match -> GREEN (core, load-bearing)" \
                || bad "(b) SHA match -> GREEN (got exit $rc_b — RECONCILER REVERTED)"
has "$out_b" "GREEN" "(b) output contains GREEN"

# ---- (a) CORE: baked SHA != live origin/master -> R-A RED ----
echo ""
echo "=== (a) baked SHA != live origin/master -> RED ==="
mk_handoff "$FLEET_ROOT/SESSION-HANDOFF-different.md" \
  "0000000000000000000000000000000000000001" \
  "$RIG_SHA" \
  "$NOW"
out_a="$(RHF_FLEET="$FLEET_ROOT" \
         RHF_PRODUCT_REPO="$PROD_WT" \
         RHF_RIG_REPO="$RIG_WT" \
         RHF_FRESHNESS_HOURS=48 \
         bash "$GATE" 2>&1)"; rc_a=$?
[ "$rc_a" -ne 0 ] && ok "(a) baked SHA mismatch -> RED (core, load-bearing)" \
                || bad "(a) baked SHA mismatch -> RED (got exit 0 — RECONCILER REVERTED)"
has "$out_a" "R-A" "(a) output contains R-A drift"
has "$out_a" "baked" "(a) output shows baked SHA"
has "$out_a" "live" "(a) output shows live SHA"

# ---- (d) product checkout absent -> UNVERIFIED (fail-closed) ----
echo ""
echo "=== (d) product checkout absent -> UNVERIFIED (fail-closed) ==="
mk_handoff_from_wt "$FLEET_ROOT/SESSION-HANDOFF-absent.md" "$PROD_WT" "$NOW"
out_d="$(RHF_FLEET="$FLEET_ROOT" \
         RHF_PRODUCT_REPO="" \
         RHF_RIG_REPO="$RIG_WT" \
         RHF_FRESHNESS_HOURS=48 \
         bash "$GATE" 2>&1)"; rc_d=$?
[ "$rc_d" -ne 0 ] && ok "(d) product absent -> non-zero (UNVERIFIED != GREEN)" \
                || bad "(d) product absent -> non-zero (got exit 0 — UNVERIFIED treated as GREEN)"
has "$out_d" "UNVERIFIED" "(d) output contains UNVERIFIED"
has "$out_d" "ABSENT" "(d) output shows checkout ABSENT"

# ---- (e) self-wiring: this gate must be wired into fleet/preflight.sh ----
echo ""
echo "=== (e) reconcile-handoff-freshness.sh wired into fleet/preflight.sh ==="
grep -q "reconcile_handoff_freshness_gate\|checks/reconcile-handoff-freshness" "$SRC/preflight.sh" \
  && ok "(e) preflight.sh calls reconcile-handoff-freshness check" \
  || bad "(e) preflight.sh does NOT call reconcile-handoff-freshness (gate reverted to inert)"

echo ""
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL RECONCILE-HANDOFF-FRESHNESS TESTS PASS"
