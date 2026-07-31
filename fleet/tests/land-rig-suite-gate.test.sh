#!/usr/bin/env bash
# land-rig-suite-gate.test.sh — FAIL-ON-REVERT tests for LAND-GATE-RIG-SUITE.
#
# THE DEFECT: fleet/land.sh's gate AUTO-DETECT selected, for the RIG repo, exactly ONE command:
#     elif [ -f "$REPO/fleet/validate_board.sh" ]; then
#       GATE_PARTS+=("bash $REPO/fleet/validate_board.sh $REPO/fleet")
# validate_board.sh is a BOARD-STRUCTURE check over fleet/board/*.md. It asserts nothing about
# whether the rig's own code works. fleet/gate.sh — the canonical fleet suite — was NEVER invoked
# on a rig land. Proven live on PR #264: land.sh ran that one command, printed "GREEN board
# structurally valid", and merged onto a master carrying 8 RED test suites. Rig merges were not
# test-gated at all, contrary to MANAGER-OPERATING-RULES §8.
#
# THE FLIP: LAND_RIG_TESTS=1 arms the suite; default 0 = DISABLED. It ships DISABLED because
# master carries 8 failing suites today (`bash fleet/gate.sh` -> "70 passed, 8 failed", rc=1) and
# arming it would refuse every rig land. These tests pin BOTH states, so neither the arming
# behaviour nor the shipped-off default can regress silently.
#
# CONVENTION, NOT ENFORCEMENT — deliberately not tested here because it is not testable here:
# land.sh binds only callers who use land.sh. `gh pr merge` / the web UI bypass it entirely. The
# durable fix is forge-native branch protection with a required status check
# (fleet/state/GATE-FORGE-PROTECTION-agen-kolar.md -> FORGE-PRIMARY-GITEA).
#
# NON-FIXTURE: runs the REAL fleet/land.sh + push-verify.sh (copied verbatim into a temp FLEET so
# the AUTONOMOUS lever is hermetic — the CODE is the real code). HERMETIC: throwaway repo + a
# local BARE remote under mktemp -d, and a `gh` STUB first on PATH. Nothing leaves the box.
#
# ── FAIL-ON-REVERT (each assertion names the exact revert that turns it RED) ─────────────────
#   R1 — delete the `if [ "${LAND_RIG_TESTS:-0}" = "1" ] ... GATE_PARTS+=("bash $REPO/fleet/gate.sh")`
#        block (i.e. restore the board-only rig gate).      RED: assertions 1, 1b, 2, 2b.
#   R2 — change the default to `${LAND_RIG_TESTS:-1}` (arm it by default / ship it ON).
#                                                            RED: assertions 3, 3b.
#   R3 — REPLACE the validate_board.sh line with the gate.sh line instead of ADDING to it.
#                                                            RED: assertion 4.
set -uo pipefail
FLEET_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0; passes=0
ok(){  passes=$((passes+1)); printf '  ok   %s\n' "$1"; }
bad(){ fails=$((fails+1));   printf '  FAIL %s\n' "$1"; }

D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT

# A hermetic copy of the REAL scripts under test + an AUTONOMOUS lever they can see.
F="$D/fleet"; mkdir -p "$F/state"
cp "$FLEET_SRC/land.sh" "$FLEET_SRC/push-verify.sh" "$F/"
: > "$F/state/AUTONOMOUS"

# `gh` STUB, FIRST on PATH: land.sh steps 6+ shell out to gh. Without this the test would reach
# the real gh and the network. The stub fails everything, so a land that gets PAST the gate dies
# at the PR step with a DISTINCT exit code (7) — which is itself the "gate did not refuse" signal.
mkdir -p "$D/bin"
cat > "$D/bin/gh" <<'EOS'
#!/usr/bin/env bash
echo "gh-stub: refusing '$*' (hermetic test)" >&2
exit 1
EOS
chmod +x "$D/bin/gh"
export PATH="$D/bin:$PATH"

# ── the fixture RIG repo: a clean tree + a local bare remote + the two gate scripts ──────────
REMOTE="$D/remote.git"; git init -q --bare -b master "$REMOTE"
R="$D/repo"; git init -q -b master "$R"
git -C "$R" config user.email t@t; git -C "$R" config user.name t
git -C "$R" remote add origin "$REMOTE"
mkdir -p "$R/fleet"

# The gate scripts land.sh AUTO-DETECTS. Each drops a marker so we can prove INVOCATION, not just
# exit status — "the gate refused" and "the gate ran" are different claims and both are asserted.
cat > "$R/fleet/validate_board.sh" <<EOS
#!/usr/bin/env bash
echo ran-validate-board >> "$D/marker.board"
echo "GREEN board structurally valid"
exit 0
EOS
# gate.sh's colour is switched by a control FILE, not by editing the script, so the RED and GREEN
# runs exercise byte-identical land.sh input.
cat > "$R/fleet/gate.sh" <<EOS
#!/usr/bin/env bash
echo ran-gate >> "$D/marker.gate"
exit "\$(cat "$D/gate.rc")"
EOS
chmod +x "$R/fleet/validate_board.sh" "$R/fleet/gate.sh"

echo base > "$R/f"
git -C "$R" add -A; git -C "$R" commit -qm base
git -C "$R" push -q origin master
git -C "$R" checkout -q -b work
echo work > "$R/f"; git -C "$R" commit -qam work

reset_markers(){ rm -f "$D/marker.board" "$D/marker.gate"; }
run_land(){  # run_land <branch> — always from a CLEAN tree, so step 1 is a no-op
  ( cd "$R" && bash "$F/land.sh" "$1" "$R" --base master 2>&1 )
}

# ── 1. FLIP ON + RED suite -> land REFUSES at the gate (exit 4), nothing published ───────────
#    REVERT R1 to make this RED.
echo 1 > "$D/gate.rc"; reset_markers
out="$(LAND_RIG_TESTS=1 run_land red-branch)"; rc=$?
if [ "$rc" -eq 4 ] && printf '%s' "$out" | grep -q 'GATE RED.*fleet/gate.sh'; then
  ok "1 flip ON + red suite: land REFUSES with exit 4 naming fleet/gate.sh (rc=$rc)"
else
  bad "1 flip ON + red suite did NOT refuse at the gate (rc=$rc, want 4): $out"
fi
[ -s "$D/marker.gate" ] \
  && ok "1b the rig suite was actually INVOKED (marker written), not merely assumed" \
  || bad "1b fleet/gate.sh was never invoked — the gate 'refused' for some other reason"
if [ -z "$(git -C "$R" ls-remote origin refs/heads/red-branch)" ]; then
  ok "1c a red suite published NOTHING to origin"
else
  bad "1c the branch was pushed despite a RED suite"
fi

# ── 2. FLIP ON + GREEN suite -> the gate PASSES and the land proceeds ────────────────────────
#    REVERT R1 to make this RED (gate.sh never runs, so 2b's marker is absent).
echo 0 > "$D/gate.rc"; reset_markers
out="$(LAND_RIG_TESTS=1 run_land green-branch)"; rc=$?
if [ "$rc" -ne 4 ] && printf '%s' "$out" | grep -q '^land: gate GREEN'; then
  ok "2 flip ON + green suite: gate GREEN, land proceeds past the gate (rc=$rc, not 4)"
else
  bad "2 flip ON + green suite was blocked at the gate (rc=$rc): $out"
fi
[ -s "$D/marker.gate" ] \
  && ok "2b the rig suite ran on the green path too (not skipped into a vacuous green)" \
  || bad "2b fleet/gate.sh was not invoked on the green path — 'gate GREEN' means nothing"

# ── 3. FLIP OFF (the SHIPPED default) -> the suite is NOT run, even when it would be RED ─────
#    This pins "ships DISABLED". REVERT R2 (default to 1) to make it RED.
echo 1 > "$D/gate.rc"; reset_markers
out="$(run_land off-branch)"; rc=$?          # LAND_RIG_TESTS deliberately UNSET
[ ! -s "$D/marker.gate" ] \
  && ok "3 flip OFF (default): fleet/gate.sh NOT invoked — ships disabled as designed" \
  || bad "3 fleet/gate.sh RAN with the flip unset — it is armed by default, which blocks every rig land"
if [ "$rc" -ne 4 ]; then
  ok "3b flip OFF: a red suite does NOT block the land (rc=$rc) — pre-existing reds stay landable"
else
  bad "3b flip OFF still refused at the gate (rc=4): $out"
fi

# ── 4. the board check is ADDED TO, never REPLACED ───────────────────────────────────────────
#    REVERT R3 to make this RED.
echo 0 > "$D/gate.rc"; reset_markers
out="$(LAND_RIG_TESTS=1 run_land both-branch)"
if [ -s "$D/marker.board" ] && [ -s "$D/marker.gate" ]; then
  ok "4 flip ON runs BOTH validate_board.sh and fleet/gate.sh (structure check not dropped)"
else
  bad "4 flip ON did not run both gates (board=$([ -s "$D/marker.board" ] && echo yes || echo no) suite=$([ -s "$D/marker.gate" ] && echo yes || echo no)): $out"
fi

echo "land-rig-suite-gate: $passes passed, $fails failed"
[ "$fails" -eq 0 ]
