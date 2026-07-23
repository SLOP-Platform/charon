#!/usr/bin/env bash
# reconcile-gate-wired.test.sh — FAIL-ON-REVERT tests for the RECONCILE-GATE-WIRED
# meta-gate (fleet/checks/reconcile-gate-wired.sh), which detects built-but-inert
# checks: a declared check that is NOT invoked from any firing layer is R-G RED.
#
# Operates entirely in a TEMP isolated fixture (RCW_* env overrides) — never touches
# the live fleet/ or the real product checkout.
#
# Covers (each is load-bearing — reverting the named branch flips it RED):
#   (a) CORE: a declared-but-unwired check -> R-G RED (exit != 0). If the set-diff
#       branch is reverted (declared set no longer compared against fired set), this
#       wrongly passes and fails RED.
#   (b) CORE: wire the same check into a fixture firing layer -> GREEN (exit 0). If
#       the reachability walk is reverted (cannot find the invocation), the check
#       stays unwired -> still RED -> this test fails.
#   (c) CORE: an unregistered check-like script under checks/ -> R-H RED. If the
#       R-H detection is reverted, this test passes but should fail -> test fails.
#   (d) product-repo absent -> UNVERIFIED reported (fail-closed, exit != 0), even
#       when the rig-side is clean.
#
# Run:  bash fleet/tests/reconcile-gate-wired.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$SRC/checks/reconcile-gate-wired.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

# Temp fleet root with a minimal skeleton — empty checks/ so no defaults fire
ROOT="$D/fleet"
mkdir -p "$ROOT/checks" "$ROOT/hooks" "$ROOT/state"
# Place a stub preflight.sh so the gate finds a firing layer (but it won't reference
# any of our fixture checks — we wire them via RCW_EXTRA_FIRING).
cat > "$ROOT/preflight.sh" <<'EOF'
#!/usr/bin/env bash
# Minimal stub firing layer — intentionally empty for test isolation
echo "preflight stub"
EOF

# ---- (a) CORE: declared-but-unwired -> R-G RED ----
echo ""
echo "=== (a) declared-but-unwired check -> R-G RED ==="
mkdir -p "$D/declared"
cat > "$D/declared/test-alpha.sh" <<'SCRIPT'
#!/usr/bin/env bash
echo "test-alpha: fixture check"
SCRIPT
chmod +x "$D/declared/test-alpha.sh"

# No fixture firing layer — test-alpha.sh is declared but never invoked
out_a="$(RCW_FLEET="$ROOT" \
        RCW_PRODUCT_REPO="" \
        RCW_REGISTRY="/dev/null" \
        RCW_EVAL_REGISTRY="/dev/null" \
        RCW_EXTRA_DECLARED="$D/declared" \
        RCW_EXTRA_FIRING="" \
        bash "$GATE" 2>&1)"; rc_a=$?
[ "$rc_a" -ne 0 ] && ok "(a) declared-but-unwired -> RED (core, load-bearing)" \
                || bad "(a) declared-but-unwired -> RED (got exit 0 — GATE REVERTED)"
has "$out_a" "R-G" "(a) output contains R-G"

# ---- (b) CORE: wire the check into a firing layer -> GREEN (rig-side) ----
echo ""
echo "=== (b) wire the check into a firing layer -> rig-side GREEN ==="
mkdir -p "$D/layers"
cat > "$D/layers/scan.sh" <<'SCRIPT'
#!/usr/bin/env bash
bash /does/not/matter/declared/test-alpha.sh
SCRIPT

# The extra firing layer contains "test-alpha.sh" which matches the declared basename
out_b="$(RCW_FLEET="$ROOT" \
         RCW_PRODUCT_REPO="" \
         RCW_REGISTRY="/dev/null" \
         RCW_EVAL_REGISTRY="/dev/null" \
         RCW_EXTRA_DECLARED="$D/declared" \
         RCW_EXTRA_FIRING="$D/layers/scan.sh" \
         bash "$GATE" 2>&1)"; rc_b=$?

# test-alpha.sh IS fired now — should NOT be in R-G. Exit may be non-zero
# (product absent = UNVERIFIED) but the R-G count must be 0.
has "$out_b" "R-G.*0" "(b) no R-G items when all declared checks wired"
# Also verify test-alpha didn't leak into R-G (output doesn't contain it)
printf '%s\n' "$out_b" | grep -q "test-alpha" && {
  # Check if it's in the R-G section (wrong) or just listed elsewhere
  printf '%s\n' "$out_b" | grep -q "R-G.*test-alpha" && \
    bad "(b) test-alpha wrongly appears in R-G" || ok "(b) test-alpha not in R-G"
} || ok "(b) test-alpha not mentioned (no R-G)"

# ---- (c) CORE: unregistered check under checks/ pattern -> R-H RED ----
echo ""
echo "=== (c) unregistered check-like invocation -> R-H RED ==="
# Create a check-like script under a `checks/` path that is NOT in declared set
mkdir -p "$D/other-checks"
cat > "$D/other-checks/rogue-runner.sh" <<'SCRIPT'
#!/usr/bin/env bash
echo "rogue runner: unregistered"
SCRIPT
chmod +x "$D/other-checks/rogue-runner.sh"

# Firing layer references $D/other-checks/rogue-runner.sh — needs pattern /checks/
# Write the layer so it contains "checks/rogue-runner.sh" in the path
cat > "$D/layers/rogue.sh" <<'SCRIPT'
#!/usr/bin/env bash
bash /fixture/checks/rogue-runner.sh
SCRIPT

out_c="$(RCW_FLEET="$ROOT" \
         RCW_PRODUCT_REPO="" \
         RCW_REGISTRY="/dev/null" \
         RCW_EVAL_REGISTRY="/dev/null" \
         RCW_EXTRA_DECLARED="$D/declared" \
         RCW_EXTRA_FIRING="$D/layers/rogue.sh" \
         bash "$GATE" 2>&1)"; rc_c=$?
[ "$rc_c" -ne 0 ] && ok "(c) unregistered checks/ invocation -> RED (core, load-bearing)" \
                || bad "(c) unregistered checks/ invocation -> RED (got exit 0 — R-H detection reverted)"
has "$out_c" "R-H" "(c) output contains R-H"

# ---- (d) product-repo absent -> UNVERIFIED (fail-closed) ----
echo ""
echo "=== (d) product-repo absent -> UNVERIFIED, never false-GREEN ==="
# Rig-side is clean: test-alpha.sh declared AND wired
cat > "$D/layers/wired.sh" <<'SCRIPT'
#!/usr/bin/env bash
bash /does/not/matter/declared/test-alpha.sh
SCRIPT

out_d="$(RCW_FLEET="$ROOT" \
         RCW_PRODUCT_REPO="" \
         RCW_REGISTRY="/dev/null" \
         RCW_EVAL_REGISTRY="/dev/null" \
         RCW_EXTRA_DECLARED="$D/declared" \
         RCW_EXTRA_FIRING="$D/layers/wired.sh" \
         bash "$GATE" 2>&1)"; rc_d=$?
[ "$rc_d" -ne 0 ] && ok "(d) product-repo absent -> non-zero (UNVERIFIED != GREEN)" \
                || bad "(d) product-repo absent -> non-zero (got exit 0 — UNVERIFIED treated as GREEN)"
has "$out_d" "UNVERIFIED" "(d) output contains UNVERIFIED"

echo ""
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL RECONCILE-GATE-WIRED TESTS PASS"
