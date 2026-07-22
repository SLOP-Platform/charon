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
#   (5) VACUOUS-GREEN GUARD — an UNRESOLVABLE diff scope must REFUSE. The pre-fix `_merge_base`
#                             fell back to the LITERAL "$BASE", git diff failed silently, and the
#                             board step reported "0 changed ticket(s) checked" rc=0 OVER A
#                             MALFORMED TICKET. 5a control / 5b unresolvable HEAD / 5c unresolvable
#                             BASE / 5d anti-over-block (a genuine zero is still green).
#       (5r) REVERT PROOF   — restoring the fail-OPEN merge-base reproduces the vacuous green,
#                             which is what makes 5b/5c load-bearing rather than decorative.
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

# A WELL-FORMED ticket that passes EVERY marker-independent check cmd_board runs — INCLUDING the
# substrate-first gate, which cmd_board delegates to per changed ticket. work_class ci-infra is in
# the gate's ALWAYS set, so the ticket must carry a substrate answer; it uses the self-contained
# `substrate: N/A` + `substrate-novel:` shape (no EVAL-REGISTRY fixture required) so these tests stay
# hermetic and stay focused on the DIFF-SCOPING behaviour they exist to prove.
GOOD_TICKET='tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/%s
depends_on:
owns: fleet/%s.sh
repo: charon-private
substrate: N/A
substrate-novel: this is a throwaway rig-ci test fixture whose only purpose is to exercise the diff scoping brain and no external tool models a fixture board like that
ds: |
  ## Dependencies & sequence
  depends_on: NONE. wave: test.
'

# Build a fixture repo: master commit, then a feature branch. Echoes the repo path.
# cmd_board delegates to fleet/checks/substrate-first-gate.sh (which execs substrate_first_gate.py),
# so the fixture must carry those scripts in the SAME fleet/checks/ dir as the scope script — cmd_board
# resolves the gate from its own $HERE. Copying them (rather than pointing at the live tree) keeps each
# fixture a self-contained, offline checkout, exactly the fresh-checkout shape CI runs. They live in
# the BASE commit, so they never appear in any fixture's PR diff.
mk_repo(){
  local d; d="$(mktemp -d)"
  git -C "$d" init -q -b master
  mkdir -p "$d/fleet/checks" "$d/fleet/board" "$d/fleet/state"
  cp "$SCOPE" "$d/fleet/checks/rig-ci-scope.sh"
  cp "$SRC/checks/substrate-first-gate.sh" "$d/fleet/checks/substrate-first-gate.sh"
  cp "$SRC/checks/substrate_first_gate.py" "$d/fleet/checks/substrate_first_gate.py"
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
# (5) VACUOUS-GREEN GUARD — an UNRESOLVABLE DIFF SCOPE must REFUSE, never report a green receipt
#     for having checked nothing.
#
#     THE LIVE DEFECT THIS REPRODUCES (passed locally, failed on the GitHub runner):
#     rig-ci.yml set RIG_CI_BASE/RIG_CI_HEAD as JOB-LEVEL env, so the `tests` step inherited them.
#     The suites under fleet/tests/ build throwaway fixture repos in $TMPDIR, and github.sha does
#     not exist in those fixtures. `_merge_base` then fell back to the LITERAL "$BASE" string,
#     `git diff` failed to /dev/null, the changed list came back empty, and cmd_board printed
#     "board: 0 changed ticket(s) checked" with rc=0 — a MALFORMED TICKET PASSING A GREEN GATE.
#     Locally the vars are unset, refs resolve, and the defect is invisible. That asymmetry is
#     exactly why this test drives an unresolvable scope EXPLICITLY rather than trusting a clean
#     local run.
# ---------------------------------------------------------------------------------------------
d5="$(mk_repo)"
# shellcheck disable=SC2059
printf "$GOOD_TICKET" wellformed wellformed > "$d5/fleet/board/WELLFORMED.md"
printf 'repo: charon-private\nwork_class: NOT-A-REAL-CLASS\nbranch: feat/x\nowns: /absolute/path\n\n## Dependencies & Sequence\nw1\n' \
  > "$d5/fleet/board/MALFORMED.md"
git -C "$d5" add -A >/dev/null; git -C "$d5" commit -q -m tickets
FOREIGN_SHA="$(printf 'deadbeef%s' "$(git -C "$d5" rev-parse HEAD | cut -c9-)")"

# (5a) CONTROL — with a RESOLVABLE scope the check really does examine the changed tickets and
#      reds the malformed one. Without this, 5b/5c could pass for the wrong reason.
out5a="$(run_scope "$d5" board)"; rc5a=$?
if [ "$rc5a" -ne 0 ] && grep -qE 'board: [1-9][0-9]* changed ticket\(s\) checked' <<<"$out5a"; then
  ok "(5a) resolvable scope -> tickets actually examined, malformed one REDs (rc=$rc5a)"
else
  bad "(5a) control failed (rc=$rc5a) — 5b/5c would prove nothing: $out5a"
fi

# (5b) THE CI CONDITION: a HEAD sha that does not exist in this repo (the leaked github.sha).
out5b="$(RIG_CI_ROOT="$d5" RIG_CI_BASE=master RIG_CI_HEAD="$FOREIGN_SHA" \
         bash "$d5/fleet/checks/rig-ci-scope.sh" board 2>&1)"; rc5b=$?
if [ "$rc5b" -ne 0 ] && grep -q 'does not resolve to a commit' <<<"$out5b" \
   && ! grep -q '0 changed ticket(s) checked' <<<"$out5b"; then
  ok "(5b) unresolvable HEAD (leaked foreign sha) -> REFUSES, no vacuous green (rc=$rc5b)"
else
  bad "(5b) unresolvable HEAD did not refuse (rc=$rc5b): $out5b"
fi

# (5c) unresolvable BASE — the shallow-clone / missing-base-ref shape.
out5c="$(RIG_CI_ROOT="$d5" RIG_CI_BASE=origin/nope RIG_CI_HEAD=HEAD \
         bash "$d5/fleet/checks/rig-ci-scope.sh" board 2>&1)"; rc5c=$?
if [ "$rc5c" -ne 0 ] && grep -q 'no resolvable diff base' <<<"$out5c" \
   && ! grep -q '0 changed ticket(s) checked' <<<"$out5c"; then
  ok "(5c) unresolvable BASE -> REFUSES, no vacuous green (rc=$rc5c)"
else
  bad "(5c) unresolvable BASE did not refuse (rc=$rc5c): $out5c"
fi

# (5d) ANTI-OVER-BLOCK — a resolvable scope whose diff genuinely carries no ticket files is still
#      a legitimate GREEN at n=0. The fix must distinguish "nothing to check" from "could not
#      compute the diff", not simply red on every zero.
#      The changed file is a NON-CODE, NON-TICKET note: this isolates the board diff-scoping property
#      cmd_board asserts here from the separate pr-has-ticket rule (code with no board ticket is its
#      own RED, exercised in the substrate-gate suite, not this one).
d5b="$(mk_repo)"
printf 'just a note, not code and not a board ticket\n' > "$d5b/fleet/nonticket.txt"
git -C "$d5b" add -A >/dev/null; git -C "$d5b" commit -q -m nonticket
out5d="$(run_scope "$d5b" board)"; rc5d=$?
if [ "$rc5d" -eq 0 ] && grep -q 'board: 0 changed ticket(s) checked' <<<"$out5d"; then
  ok "(5d) resolvable scope with genuinely zero ticket files -> still GREEN (no over-block)"
else
  bad "(5d) over-blocked a legitimate zero-ticket diff (rc=$rc5d): $out5d"
fi

# (5r) REVERT PROOF: restore the fail-OPEN `_merge_base` (literal-\$BASE fallback) and neuter the
#      _require_scope guard — i.e. the exact pre-fix code. The unresolvable-HEAD run must then go
#      back to rc=0 with "0 changed ticket(s) checked": a GREEN receipt over the malformed ticket.
#      If this ever stops reproducing, 5b/5c are no longer proving anything.
rev5="$d5/fleet/checks/rig-ci-scope.FAILOPEN.sh"
python3 - "$SCOPE" "$rev5" <<'PY'
import sys, re
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
# 1) put back the fail-open merge-base + unguarded _changed_files
s2 = re.sub(r"_resolve_scope\(\)\{.*?\n\}\n",
            '_resolve_scope(){ git -C "$ROOT" merge-base "$BASE" "$HEAD_REF" 2>/dev/null || echo "$BASE"; }\n',
            s, count=1, flags=re.S)
assert s2 != s, "could not neuter _resolve_scope — the revert test would prove nothing"
s3 = re.sub(r"_changed_files\(\)\{.*?\n\}\n",
            '_changed_files(){ git -C "$ROOT" diff --name-only --diff-filter=ACMR "$(_resolve_scope)" "$HEAD_REF" 2>/dev/null; }\n',
            s2, count=1, flags=re.S)
assert s3 != s2, "could not neuter _changed_files — the revert test would prove nothing"
# 2) neuter the pre-loop refusal guard
s4 = re.sub(r"_require_scope\(\)\{.*?\n\}\n", '_require_scope(){ return 0; }\n', s3, count=1, flags=re.S)
assert s4 != s3, "could not neuter _require_scope — the revert test would prove nothing"
open(dst, "w").write(s4)
PY
if bash -n "$rev5" 2>/dev/null; then
  out5r="$(RIG_CI_ROOT="$d5" RIG_CI_BASE=master RIG_CI_HEAD="$FOREIGN_SHA" \
           bash "$rev5" board 2>&1)"; rc5r=$?
  if [ "$rc5r" -eq 0 ] && grep -q 'board: 0 changed ticket(s) checked' <<<"$out5r"; then
    ok "(5r) fail-OPEN variant reproduces the vacuous green (rc=0 over a malformed ticket) — 5b/5c are load-bearing"
  else
    bad "(5r) could not reproduce the pre-fix vacuous green (rc=$rc5r) — 5b/5c may prove nothing: $out5r"
  fi
else
  bad "(5r) reverted variant is not valid bash — revert proof inconclusive"
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

rm -rf "$d1" "$d2" "$d3" "$d5" "$d5b"
echo "----"
echo "rig-ci.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
