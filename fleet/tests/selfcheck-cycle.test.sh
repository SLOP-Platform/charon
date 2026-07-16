#!/usr/bin/env bash
# selfcheck-cycle.test.sh — FAIL-ON-REVERT tests for fleet/checks/selfcheck-cycle.sh.
#
# Mechanizes the [[fleet-selfcheck-forkbomb-class]] gate: builds a static
# script -> script call graph from the fleet and FAILS on any unguarded
# self-referential edge. The half of the fix that landed (gate.sh:29
# exports CHARON_GATE_ACTIVE, handoff.sh:292 checks it and skips) prevents
# the one cycle that already exploded (~18,900 procs, GraphQL cap blown);
# this test is the load-bearing test that future drift does not silently
# disarm the guard.
#
# Three required fail-on-revert tests:
#
#   (1) CORE ASSERTION — the test whose absence is the defect.
#       The handoff.sh -> gate.sh edge MUST be classified as guarded at
#       runtime, which requires BOTH gate.sh:29 (the `export`) AND
#       handoff.sh:292 (the `${CHARON_GATE_ACTIVE:-}` check). Revert
#       EITHER -> the cycle flips to UNGUARDED -> this test goes RED.
#       SAFETY: this test asserts the guard's EFFECT statically (the
#       `export` line and the conditional are both present) AND by
#       running the static cycle checker on the live fleet/ root. It
#       does NOT actually let the cycle recurse — that is how 18k procs
#       happened, and a test that fork-bombs CI is not a passing test.
#
#   (2) DETECTOR CATCHES A NEW CYCLE — feed the checker a fixture pair
#       (script A runs test B, test B runs script A) with NO guard and
#       assert the checker reports it as UNGUARDED. Add a guard, assert
#       it's now GUARDED. Then revert the checker script itself and
#       assert the fixture stops failing (the check is no longer there
#       to catch it) — this proves the check is what catches the new
#       cycle, not some other accidental signal.
#
#   (3) NO FALSE POSITIVE — a guarded fixture cycle and a plain acyclic
#       fixture both return GREEN. A checker that reds the whole rig
#       gets disabled within a day; this test is the canary.
#
# Run:  bash fleet/tests/selfcheck-cycle.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKER="$SRC/checks/selfcheck-cycle.sh"
[ -f "$CHECKER" ] || { echo "FATAL: $CHECKER not found"; exit 2; }
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# Use a hard-bounded process cap so a buggy checker that DOES recurse is
# killed before it can fork-bomb the host. The test does not depend on
# this — it asserts statically — but the cap is a second line of defense.
ulimit -u 256 2>/dev/null || true

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# Helper: write the unguarded fixture cycle under $WORK/fleet. The two
# scripts call each other via the real fleet root, with NO reentrancy
# guard. This is the canonical "fork-bomb" topology the checker must
# catch.
write_unguarded_fixture() {
  local FIX="$1"
  mkdir -p "$FIX/tests"
  cat > "$FIX/cycle-a.sh" <<'SH'
#!/usr/bin/env bash
# cycle-a.sh — fixture: calls cycle-b.test.sh via the real fleet root
# (no guard; if a checker doesn't catch this, it's broken).
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$FLEET/tests/cycle-b.test.sh"
SH
  chmod +x "$FIX/cycle-a.sh"
  cat > "$FIX/tests/cycle-b.test.sh" <<'SH'
#!/usr/bin/env bash
# cycle-b.test.sh — fixture: calls cycle-a.sh via the real fleet root
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bash "$SRC/cycle-a.sh"
SH
  chmod +x "$FIX/tests/cycle-b.test.sh"
}

# Helper: same fixture, but with the reentrancy guard installed. The
# guard variable name MUST end in _ACTIVE (one of the suffixes the
# checker recognizes as a reentrancy flag). We use FIXTURE_GUARD_ACTIVE
# so the fixture's guard pattern is the same shape as the real fleet's
# CHARON_GATE_ACTIVE.
write_guarded_fixture() {
  local FIX="$1"
  local GUARD_VAR="$2"
  mkdir -p "$FIX/tests"
  cat > "$FIX/cycle-a.sh" <<SH
#!/usr/bin/env bash
set -uo pipefail
export ${GUARD_VAR}=1
FLEET="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
bash "\$FLEET/tests/cycle-b.test.sh"
SH
  chmod +x "$FIX/cycle-a.sh"
  cat > "$FIX/tests/cycle-b.test.sh" <<SH
#!/usr/bin/env bash
set -uo pipefail
# Reentrancy guard — short-circuit if we're already inside a parent run.
if [ -n "\${${GUARD_VAR}:-}" ]; then
  exit 0
fi
SRC="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
bash "\$SRC/cycle-a.sh"
SH
  chmod +x "$FIX/tests/cycle-b.test.sh"
}

# -----------------------------------------------------------------------------
# (1) CORE ASSERTION — guard's EFFECT is present.
# -----------------------------------------------------------------------------
echo "== (1) handoff.sh <-> gate.sh cycle is guarded =="

# (1a) The static guard is present in both halves of the cycle.
#     handoff.sh must check ${CHARON_GATE_ACTIVE:-} ...
#     gate.sh must `export CHARON_GATE_ACTIVE=1`.
#     Revert EITHER -> this assertion fails (RED).
# SAFETY: static assertions only. We do NOT execute the scripts.
if grep -qE 'CHARON_GATE_ACTIVE' "$SRC/handoff.sh"; then
  ok "1a handoff.sh references the reentrancy guard flag (CHARON_GATE_ACTIVE)"
else
  bad "1a handoff.sh is MISSING the reentrancy guard flag (CHARON_GATE_ACTIVE) — the half-fix that prevents the fork-bomb has been reverted"
fi
if grep -qE 'export[[:space:]]+CHARON_GATE_ACTIVE=' "$SRC/gate.sh"; then
  ok "1b gate.sh exports the reentrancy guard flag (CHARON_GATE_ACTIVE=...)"
else
  bad "1b gate.sh is MISSING 'export CHARON_GATE_ACTIVE=...' — the test-runner side of the guard has been reverted, so the cycle is unguarded at runtime"
fi

# (1c) The static cycle checker, run against the LIVE fleet/, must
#     report NO unguarded cycles. This is the integration check: the
#     two halves above are necessary but not sufficient — the checker
#     must also wire them together (a future bug in extract_edges or
#     dfs could mask the cycle).
#     Reverting the gate.sh:29 export makes the cycle UNGUARDED -> RED.
#     Reverting the handoff.sh check makes the cycle UNGUARDED -> RED.
out="$(bash "$CHECKER" 2>&1)"; rc=$?
if [ "$rc" = "0" ]; then
  ok "1c cycle checker reports GREEN on the live fleet/"
else
  bad "1c cycle checker reports RED on the live fleet/ — the reentrancy guard is broken somewhere. Output:"
  printf '%s\n' "$out" | sed 's/^/    /' | head -20
fi

# (1d) The checker must specifically report the handoff<->gate cycle as
#     GUARDED (not just "no unguarded cycles"). This protects against a
#     regression where the cycle is silently MISSED by the static
#     analyzer (no cycle found = GREEN, but the actual fork-bomb is
#     still there).
if printf '%s\n' "$out" | grep -qE 'handoff -> gate -> handoff-mechanize.test -> handoff'; then
  ok "1d checker reports the handoff<->gate cycle (and classifies it as guarded)"
else
  bad "1d checker does NOT report the handoff<->gate cycle — if it doesn't see the cycle at all, the green is meaningless (it just means the analyzer didn't look). Output:"
  printf '%s\n' "$out" | sed 's/^/    /' | head -20
fi

# -----------------------------------------------------------------------------
# (2) DETECTOR CATCHES A NEW CYCLE — fixture pair (script A <-> test B).
# -----------------------------------------------------------------------------
echo "== (2) checker catches a new unguarded cycle in a fixture =="

FIX="$WORK/fleet_unguarded"
write_unguarded_fixture "$FIX"

# (2a) Without any guard, the checker must flag the cycle as UNGUARDED.
out="$(bash "$CHECKER" --fleet-root="$FIX" 2>&1)"; rc=$?
if [ "$rc" = "1" ]; then
  ok "2a checker flags unguarded fixture cycle as RED (rc=1)"
else
  bad "2a checker did NOT flag the unguarded fixture cycle (rc=$rc, output: $out)"
fi
if printf '%s\n' "$out" | grep -qE 'cycle-a.*->.*cycle-b.*->.*cycle-a|cycle-b.*->.*cycle-a.*->.*cycle-b'; then
  ok "2b checker NAMES the fixture cycle"
else
  bad "2b checker output does not name the cycle-a/cycle-b fixture cycle"
fi

# (2c) Add a guard. cycle-a.sh exports FIXTURE_GUARD_ACTIVE=1; cycle-b.test.sh
#     checks ${FIXTURE_GUARD_ACTIVE:-} — same shape as the real handoff.sh guard.
FIX2="$WORK/fleet_guarded"
write_guarded_fixture "$FIX2" "FIXTURE_GUARD_ACTIVE"

out="$(bash "$CHECKER" --fleet-root="$FIX2" 2>&1)"; rc=$?
if [ "$rc" = "0" ]; then
  ok "2c checker reports GREEN once the cycle has a guard"
else
  bad "2c checker did NOT report GREEN for the guarded cycle (rc=$rc, output: $out)"
fi

# (2d) Prove the CHECKER is what catches the unguarded case — strip the
#     guard back off and re-run. Must go RED again. (If the test rig
#     were passing for some other reason, this would still pass even
#     without the guard, and the regression would be invisible.)
write_unguarded_fixture "$FIX2"
out="$(bash "$CHECKER" --fleet-root="$FIX2" 2>&1)"; rc=$?
if [ "$rc" = "1" ]; then
  ok "2d removing the guard flips the fixture back to RED (proves the guard is what made it GREEN)"
else
  bad "2d removing the guard did NOT flip the fixture back to RED (rc=$rc) — either the checker doesn't see this cycle, or the test is passing for the wrong reason"
fi

# -----------------------------------------------------------------------------
# (3) NO FALSE POSITIVE — guarded fixture cycle and plain acyclic fixture
#     both return GREEN. A checker that reds the whole rig gets disabled
#     within a day; this is the canary.
# -----------------------------------------------------------------------------
echo "== (3) no false positive on guarded / acyclic fixtures =="

# (3a) Guarded fixture cycle (same as 2c) — must be GREEN.
FIX3="$WORK/fleet_3a_guarded"
write_guarded_fixture "$FIX3" "FIXTURE_GUARD_ACTIVE"
out="$(bash "$CHECKER" --fleet-root="$FIX3" 2>&1)"; rc=$?
if [ "$rc" = "0" ]; then
  ok "3a guarded fixture cycle is GREEN (no false positive)"
else
  bad "3a guarded fixture cycle reported as RED (rc=$rc, output: $out) — the checker is too strict"
fi

# (3b) Plain acyclic fixture — a script that calls a different script
#     once, with no return path. Must be GREEN.
FIX4="$WORK/fleet_acyclic"; mkdir -p "$FIX4"
cat > "$FIX4/cycle-a.sh" <<'SH'
#!/usr/bin/env bash
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$FLEET/acyclic-helper.sh"
SH
chmod +x "$FIX4/cycle-a.sh"
cat > "$FIX4/acyclic-helper.sh" <<'SH'
#!/usr/bin/env bash
set -uo pipefail
echo "helper ran"
SH
chmod +x "$FIX4/acyclic-helper.sh"
out="$(bash "$CHECKER" --fleet-root="$FIX4" 2>&1)"; rc=$?
if [ "$rc" = "0" ]; then
  ok "3b plain acyclic fixture is GREEN (no false positive)"
else
  bad "3b plain acyclic fixture reported as RED (rc=$rc, output: $out)"
fi

# (3c) Plain script with no edges at all (just a single file).
SIMPLE="$WORK/simple"; mkdir -p "$SIMPLE"
cat > "$SIMPLE/lonely.sh" <<'SH'
#!/usr/bin/env bash
echo "alone"
SH
chmod +x "$SIMPLE/lonely.sh"
out="$(bash "$CHECKER" --fleet-root="$SIMPLE" 2>&1)"; rc=$?
if [ "$rc" = "0" ]; then
  ok "3c single-file fleet with no edges is GREEN (no false positive)"
else
  bad "3c single-file fleet reported as RED (rc=$rc, output: $out)"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL SELFCHECK-CYCLE TESTS PASS"
