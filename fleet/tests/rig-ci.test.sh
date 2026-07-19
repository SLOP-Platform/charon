#!/usr/bin/env bash
# rig-ci.test.sh — FAIL-ON-REVERT tests for the rig's CI gate
# (.github/workflows/rig-ci.yml + fleet/checks/rig-ci-scope.sh).
#
# GREEN IS NOT PROOF. `checks=0` was the rig's status quo and it LOOKED fine. These tests exist so
# the gate has been SEEN TO FAIL: each one asserts on a real exit code from the real check script
# run against a throwaway git fixture — never on a PR page, never on "the file exists".
#
# Fully hermetic/offline: every fixture is a fresh `mktemp -d` git repo. NEVER touches the live
# fleet/state/, never runs gh/network, never invokes preflight/land (reentrancy: a gate that
# re-invokes CI is a fork bomb).
#
# Covers:
#   (1) BROKEN SHELL FAILS  — a branch carrying a syntax-broken *.sh drives the shell-syntax step
#                             to a NON-ZERO rc.
#       (1r) REVERT PROOF   — reverting .github/workflows/rig-ci.yml (or its syntax step) leaves
#                             nothing to run that check, so (1) can no longer fail.
#   (2) CLEAN PASSES        — an unmodified branch off master -> every step rc=0 (anti-over-block).
#   (3) FALSE-RED GUARD     — the board step against a checkout with an EMPTY fleet/state/ must NOT
#                             red on a done-but-unmarked ticket.
#       (3r) REVERT PROOF   — reverting the diff-scoping (whole-board scan instead of PR-changed
#                             files) makes (3) go RED. This is what proves the fresh-checkout
#                             constraint was solved, not hand-waved.
#   (4) ALLOWLIST GUARD     — CI_SUITES is a literal allowlist, not a fleet/tests/*.sh sweep
#                             (a benchmark grader suite added later must be excluded BY DEFAULT).
#
# Run:  bash fleet/tests/rig-ci.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
REPO="$(cd "$SRC/.." && pwd)"                                  # repo root
SCOPE="$SRC/checks/rig-ci-scope.sh"
WF="$REPO/.github/workflows/rig-ci.yml"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

GOOD_TICKET='tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/%s
depends_on:
owns: fleet/%s.sh
repo: charon-private
ds: |
  ## Dependencies & sequence
  depends_on: NONE. wave: test.
'

# Build a fixture repo: master commit, then a feature branch. Echoes the repo path.
mk_repo(){
  local d; d="$(mktemp -d)"
  git -C "$d" init -q -b master
  mkdir -p "$d/fleet/checks" "$d/fleet/board" "$d/fleet/state"
  cp "$SCOPE" "$d/fleet/checks/rig-ci-scope.sh"
  printf '#!/usr/bin/env bash\necho ok\n' > "$d/fleet/ok.sh"
  git -C "$d" add -A >/dev/null; git -C "$d" commit -q -m base
  git -C "$d" checkout -q -b feat/fixture
  printf '%s' "$d"
}

run_scope(){ # run_scope <repo> <subcommand>  -> prints output, returns rc
  local d="$1" sub="$2"; shift 2
  RIG_CI_ROOT="$d" RIG_CI_BASE=master RIG_CI_HEAD=HEAD \
    bash "${RIG_CI_SCRIPT:-$d/fleet/checks/rig-ci-scope.sh}" "$sub" 2>&1
}

# ---------------------------------------------------------------------------------------------
# (1) BROKEN SHELL FAILS — assert on rc, not on a PR page.
# ---------------------------------------------------------------------------------------------
d1="$(mk_repo)"
printf '#!/usr/bin/env bash\nif [ 1 = 1 ]; then\n  echo unclosed\n' > "$d1/fleet/broken.sh"
git -C "$d1" add -A >/dev/null; git -C "$d1" commit -q -m broken
out1="$(run_scope "$d1" syntax)"; rc1=$?
if [ "$rc1" -ne 0 ] && grep -q 'shell-syntax: fleet/broken.sh' <<<"$out1"; then
  ok "(1) syntax-broken *.sh in the PR diff -> shell-syntax step rc=$rc1 (NON-ZERO)"
else
  bad "(1) broken *.sh did not red the syntax step (rc=$rc1): $out1"
fi

# (1r) REVERT PROOF: without the workflow (or its syntax step) nothing runs the check, so (1)
#      can never fail in CI. Assert the workflow exists AND actually wires the syntax step.
if [ -f "$WF" ] && grep -q 'rig-ci-scope.sh syntax' "$WF"; then
  ok "(1r) workflow wires the shell-syntax step (reverting rig-ci.yml makes test 1 unable to fail)"
else
  bad "(1r) .github/workflows/rig-ci.yml missing or does not invoke 'rig-ci-scope.sh syntax'"
fi

# ---------------------------------------------------------------------------------------------
# (2) CLEAN PASSES (anti-over-block) — a gate that reds on a clean tree gets turned off.
# ---------------------------------------------------------------------------------------------
d2="$(mk_repo)"
# shellcheck disable=SC2059
printf "$GOOD_TICKET" clean clean > "$d2/fleet/board/CLEAN-TICKET.md"
printf '#!/usr/bin/env bash\necho fine\n' > "$d2/fleet/fine.sh"
git -C "$d2" add -A >/dev/null; git -C "$d2" commit -q -m clean
out2s="$(run_scope "$d2" syntax)";  rc2s=$?
out2b="$(run_scope "$d2" board)";   rc2b=$?
if [ "$rc2s" -eq 0 ] && [ "$rc2b" -eq 0 ]; then
  ok "(2) clean branch -> syntax rc=0 and board rc=0"
else
  bad "(2) clean branch went RED (syntax rc=$rc2s, board rc=$rc2b): $out2s | $out2b"
fi

# ---------------------------------------------------------------------------------------------
# (3) FALSE-RED GUARD — EMPTY fleet/state/ must not red done-but-unmarked tickets.
#     Fixture: an OLD, non-conforming ticket that is DONE in the live world but has no marker here
#     (state/ is gitignored, so CI never sees one). The PR touches only a clean NEW ticket.
# ---------------------------------------------------------------------------------------------
d3="$(mk_repo)"
git -C "$d3" checkout -q master
printf 'tier: strong\nbranch: feat/oldie\nowns: fleet/oldie.sh\n' > "$d3/fleet/board/OLD-DONE-TICKET.md"
git -C "$d3" add -A >/dev/null; git -C "$d3" commit -q -m oldie   # no work_class, no repo, no D&S
git -C "$d3" checkout -q feat/fixture
git -C "$d3" merge -q master -m merge
# shellcheck disable=SC2059
printf "$GOOD_TICKET" newone newone > "$d3/fleet/board/NEW-TICKET.md"
git -C "$d3" add -A >/dev/null; git -C "$d3" commit -q -m newticket
[ -z "$(ls -A "$d3/fleet/state")" ] || bad "(3) fixture fleet/state/ is not empty"
out3="$(run_scope "$d3" board)"; rc3=$?
if [ "$rc3" -eq 0 ]; then
  ok "(3) board step vs EMPTY fleet/state/ -> rc=0 (no false RED on the done-but-unmarked ticket)"
else
  bad "(3) board step false-REDed on an empty fleet/state/ (rc=$rc3): $out3"
fi

# (3r) REVERT PROOF: neuter the diff-scoping so the board step scans the WHOLE board instead of the
#      PR-changed files — exactly the naive implementation the fresh-checkout constraint forbids.
#      The old done-but-unmarked ticket is then inspected and (3) goes RED.
rev="$d3/fleet/checks/rig-ci-scope.REVERTED.sh"
python3 - "$SCOPE" "$rev" <<'PY'
import sys, re
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
new = re.sub(r"(_scoped_board_files\(\)\{\n).*?(\n\})",
             r'\1  (cd "$ROOT" && ls fleet/board/*.md) 2>/dev/null || true\2',
             s, count=1, flags=re.S)
assert new != s, "could not neuter _scoped_board_files — the revert test would prove nothing"
open(dst, "w").write(new)
PY
grep -q 'ls fleet/board' "$rev" || bad "(3r) could not build the reverted (unscoped) variant"
out3r="$(RIG_CI_SCRIPT="$rev" run_scope "$d3" board)"; rc3r=$?
if [ "$rc3r" -ne 0 ]; then
  ok "(3r) reverting the diff-scoping (whole-board scan) -> rc=$rc3r RED, proving (3)'s green comes from the scoping"
else
  bad "(3r) unscoped variant still passed (rc=$rc3r) — test 3 proves nothing: $out3r"
fi

# ---------------------------------------------------------------------------------------------
# (4) ALLOWLIST GUARD — CI must never glob fleet/tests/.
# ---------------------------------------------------------------------------------------------
code_only(){ grep -v '^[[:space:]]*#' "$SCOPE"; }
if grep -q 'CI_SUITES=(' "$SCOPE" && ! code_only | grep -qE 'fleet/tests/\*|tests/\*\.test\.sh'; then
  ok "(4) CI test scope is a literal ALLOWLIST (no fleet/tests/* sweep)"
else
  bad "(4) rig-ci-scope.sh appears to sweep fleet/tests/* — grader suites would run in CI"
fi

rm -rf "$d1" "$d2" "$d3"
echo "----"
echo "rig-ci.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
