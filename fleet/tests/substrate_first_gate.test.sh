#!/usr/bin/env bash
# substrate_first_gate.test.sh — fail-on-revert suite for the BASE-REF owns resolution added
# to substrate_first_gate.py's `pr-has-ticket` rule (ticket SUBSTRATE-FIRST-OWNS-BASE-REF).
#
# THE INVARIANT UNDER TEST (ratchet — must stay STRONGER, never weaker):
#   A touched CODE file is SATISFIED when an EXISTING board ticket on the BASE ref `owns:` it
#   — NOT only when a board/*.md is touched in the PR diff. Code owned by NO live ticket STILL
#   REDs. If the base-board owns cannot be resolved, RED (fail-closed).
#
# The three accept cases (drive the ACTUAL gate against real git fixtures — no stubbed values):
#   (a) a code change whose file IS in a base-ref ticket's owns: => GREEN
#   (b) a code change to a file owned by NO ticket           => RED
#   (c) REVERT the base-ref owns-resolution => case (a) goes RED again (proves it is load-bearing)
#   (d) base-board owns unresolvable => RED (fail-closed) — bonus, guards the fail-closed branch.
#
# HERMETIC: every fixture is a throwaway `git init` repo under mktemp -d. It never reads the
# live board, never touches fleet/state/, never hits the network.
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]: this suite imports the gate MODULE and runs
# git on a throwaway repo ONLY. It must NEVER call rig-ci-scope.sh, validate_board.sh,
# preflight.sh or land*.sh — those invoke the gate, and a test that invokes its own caller is
# the fork bomb.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKS="$HERE/../checks"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "  ok   $1"; }
bad(){  FAIL=$((FAIL+1)); echo "  FAIL $1"; }

# ---- build a hermetic repo: base has a board ticket owning src/charon/feature.py ----------
REPO="$TMP/repo"
mkdir -p "$REPO/fleet/board" "$REPO/src/charon"
git -C "$REPO" init -q .
git -C "$REPO" config user.email t@t
git -C "$REPO" config user.name t
cat >"$REPO/fleet/board/FEAT.md" <<'TIC'
repo: charon-private
work_class: greenfield-feature
difficulty: 3
branch: feat/the-feature
owns: src/charon/feature.py
note: the ticket was minted + landed SEPARATELY (real fleet workflow), so it already lives on
  the base ref while the code-only PR touches no board/*.md.
TIC
echo 'def feature(): return 0' >"$REPO/src/charon/feature.py"
git -C "$REPO" add -A
git -C "$REPO" commit -qm base
BASE="$(git -C "$REPO" rev-parse HEAD)"

# branch A: a CODE-ONLY change to the base-ticket-OWNED file (no board/*.md in the diff).
git -C "$REPO" checkout -q -b feat-a
echo 'def feature(): return 1  # changed' >"$REPO/src/charon/feature.py"
git -C "$REPO" add -A
git -C "$REPO" commit -qm 'code only: owned file'
HEAD_A="$(git -C "$REPO" rev-parse HEAD)"

# branch B: a CODE-ONLY change to a file NO ticket owns (no board/*.md in the diff).
git -C "$REPO" checkout -q "$BASE"
git -C "$REPO" checkout -q -b feat-b
echo 'def wildcat(): return 2' >"$REPO/src/charon/unowned.py"
git -C "$REPO" add -A
git -C "$REPO" commit -qm 'code only: unowned file'
HEAD_B="$(git -C "$REPO" rev-parse HEAD)"

# run cmd_pr_has_ticket against a given range, optionally reverting the owns resolution.
# args: <base> <head> [revert|failclosed]   ; prints the gate output, returns the gate rc.
run_gate(){
  local base="$1" head="$2" mode="${3:-}"
  RIG_CI_BASE="$base" RIG_CI_HEAD="$head" python3 - "$CHECKS" "$REPO" "$mode" <<'PY'
import sys
checks, repo, mode = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, checks)
import substrate_first_gate as g
if mode == "revert":
    # Simulate the PRE-FIX gate: the base-ref owns resolution did not exist, so a touched
    # code file was never matched against any base ticket's owns. Restoring that (no owns
    # resolved, but base still 'resolvable') must send the OWNED-file case (a) back to RED.
    g.base_board_owns = lambda root: ([], True)
elif mode == "failclosed":
    # base board unresolvable -> the gate must fail closed (RED).
    g.base_board_owns = lambda root: ([], False)
gate = g.Gate("/nonexistent/registry.md", repo)  # pr-has-ticket does not read the registry
sys.exit(g.cmd_pr_has_ticket(gate))
PY
}

echo "== substrate_first_gate: base-ref owns resolution =="

# (a) code change to a base-ref-OWNED file => GREEN
a_out="$(run_gate "$BASE" "$HEAD_A" 2>&1)"; a_rc=$?
if [ "$a_rc" -eq 0 ]; then ok "(a) code change to a base-ref ticket's owns: file is GREEN [rc=$a_rc]"
else bad "(a) base-ref-owned code REDded — the fix does not satisfy owned code"; printf '%s\n' "$a_out" | sed 's/^/        /'; fi

# (b) code change to a file owned by NO ticket => RED
b_out="$(run_gate "$BASE" "$HEAD_B" 2>&1)"; b_rc=$?
if [ "$b_rc" -ne 0 ]; then ok "(b) code change to an UNOWNED file is RED (ratchet holds) [rc=$b_rc]"
else bad "(b) unowned code passed — the ratchet leaks"; printf '%s\n' "$b_out" | sed 's/^/        /'; fi

# (c) REVERT the base-ref owns resolution => case (a) goes RED again (load-bearing proof)
c_out="$(run_gate "$BASE" "$HEAD_A" revert 2>&1)"; c_rc=$?
if [ "$c_rc" -ne 0 ]; then ok "(c) reverting the owns resolution sends the OWNED case back to RED [rc=$c_rc]"
else bad "(c) case (a) stayed GREEN with the owns resolution reverted — the fix is NOT load-bearing"; printf '%s\n' "$c_out" | sed 's/^/        /'; fi

# (d) base-board owns unresolvable => RED (fail-closed)
d_out="$(run_gate "$BASE" "$HEAD_A" failclosed 2>&1)"; d_rc=$?
if [ "$d_rc" -ne 0 ] && grep -q 'fail-closed' <<<"$d_out"; then
  ok "(d) an unresolvable base board fails CLOSED [rc=$d_rc]"
else bad "(d) unresolvable base board did NOT fail closed"; printf '%s\n' "$d_out" | sed 's/^/        /'; fi

echo
echo "substrate_first_gate.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
