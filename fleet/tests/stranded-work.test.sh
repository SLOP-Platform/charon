#!/usr/bin/env bash
# stranded-work.test.sh — FAIL-ON-REVERT tests for fleet/checks/stranded-work.sh.
#
# WHY THESE ASSERTIONS EXIST
#   The detector's whole value is that it CANNOT be quietly hollowed out: the rig's recurring
#   defect is not "a check is missing", it is "a check still prints a green line after its body
#   stopped meaning anything". Each of the five detection shapes therefore gets a test that goes
#   RED if that shape's block is deleted, plus assertions that (a) an unreadable PR API produces
#   UNDETERMINED and never "clean", and (b) a fresh checkout with an EMPTY fleet/state/ produces
#   NO findings — a detector that reds spuriously gets disabled [[gates-must-actually-run]].
#
# HERMETIC: real git repos built under `mktemp -d`, real `git worktree add`, and the REAL script.
# The only stub is PR state, injected as a TSV via SW_PR_FIXTURE — `gh` is never invoked and no
# network is touched (SW_NO_GH is also exercised, for the offline path).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../checks/stranded-work.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ok   $*"; }
no(){ FAIL=$((FAIL+1)); echo "  FAIL $*"; }
chk(){ # chk <desc> <needle> <haystack>
  case "$3" in *"$2"*) ok "$1";; *) no "$1 (missing: $2)";; esac; }
nchk(){ case "$3" in *"$2"*) no "$1 (unexpected: $2)";; *) ok "$1";; esac; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

# ── fixture: bare "remote" + a clone with master pushed ────────────────────────────────────────
BARE="$TMP/remote.git"; REPO="$TMP/repo"; FLEETD="$TMP/fleet"
mkdir -p "$FLEETD/state"
git init -q --bare -b master "$BARE"
git init -q -b master "$REPO"
echo one > "$REPO/a.txt"
git -C "$REPO" add -A && git -C "$REPO" commit -qm base
git -C "$REPO" remote add origin "$BARE"
git -C "$REPO" push -q origin master
git -C "$REPO" fetch -q origin

run(){ env SW_REPO="$REPO" SW_BASE=master SW_FLEET_DIR="$FLEETD" "$@" bash "$SCRIPT" 2>&1; }

echo "== A. baseline: nothing stranded, PR state readable =="
OUT="$(run SW_PR_FIXTURE=/dev/null)"; RC=$?
chk "A1 clean receipt when truly clean" "clean: stranded-work" "$OUT"
[ "$RC" = 0 ] && ok "A2 rc=0 when clean" || no "A2 rc=0 when clean (got $RC)"

echo "== B. shape 1: local branch with commits on no remote ref =="
git -C "$REPO" checkout -q -b feat/never-pushed
echo x > "$REPO/b.txt"; git -C "$REPO" add -A; git -C "$REPO" commit -qm stranded
git -C "$REPO" checkout -q master
OUT="$(run SW_PR_FIXTURE=/dev/null)"; RC=$?
chk "B1 unpushed branch DETECTED" "STRANDED[unpushed-branch]" "$OUT"
chk "B2 names the branch" "feat/never-pushed" "$OUT"
[ "$RC" = 1 ] && ok "B3 rc=1 on findings" || no "B3 rc=1 on findings (got $RC)"
nchk "B4 does not also claim clean" "clean: stranded-work" "$OUT"
git -C "$REPO" branch -q -D feat/never-pushed   # fixture teardown only, inside mktemp

echo "== C. shape 2: dirty worktree with no live claim =="
WT="$TMP/wt/TICKET-X"
git -C "$REPO" worktree add -q -b feat/wt-work "$WT" master
echo dirty > "$WT/uncommitted.txt"
OUT="$(run SW_PR_FIXTURE=/dev/null)"
chk "C1 dirty unclaimed worktree DETECTED" "STRANDED[dirty-worktree]" "$OUT"
chk "C2 names the worktree" "TICKET-X" "$OUT"
mkdir -p "$FLEETD/state/claims"; : > "$FLEETD/state/claims/TICKET-X"
OUT="$(run SW_PR_FIXTURE=/dev/null)"
nchk "C3 a LIVE-CLAIMED worktree is NOT stranded" "STRANDED[dirty-worktree]" "$OUT"
rm -f "$FLEETD/state/claims/TICKET-X"
mkdir -p "$FLEETD/state/needs-push"; : > "$FLEETD/state/needs-push/TICKET-X"
OUT="$(run SW_PR_FIXTURE=/dev/null)"
nchk "C4 a needs-push marker also suppresses it" "STRANDED[dirty-worktree]" "$OUT"
rm -rf "$FLEETD/state/needs-push"

echo "== D. shape 3: pushed branch, unmerged, NO PR =="
# The branch must be genuinely AHEAD of base — a branch pointing at base has nothing stranded.
git -C "$WT" add -A; git -C "$WT" commit -qm "real work"
git -C "$REPO" push -q origin feat/wt-work; git -C "$REPO" fetch -q origin
OUT="$(run SW_PR_FIXTURE=/dev/null)"
chk "D1 pushed-but-PR-less branch DETECTED" "STRANDED[pushed-no-pr]" "$OUT"
chk "D2 names the branch" "feat/wt-work" "$OUT"
PRF="$TMP/prs.tsv"; printf '7\tOPEN\tfeat/wt-work\t3\n' > "$PRF"
OUT="$(run SW_PR_FIXTURE="$PRF")"
nchk "D3 a branch WITH a PR is not pushed-no-pr" "STRANDED[pushed-no-pr]" "$OUT"
nchk "D4 an OPEN PR with checks>0 is not pr-no-checks" "STRANDED[pr-no-checks]" "$OUT"

echo "== E. shape 4: CLOSED PR whose branch still carries unlanded commits =="
printf '81\tCLOSED\tfeat/wt-work\t0\n' > "$PRF"
OUT="$(run SW_PR_FIXTURE="$PRF")"
chk "E1 closed-but-unlanded DETECTED" "STRANDED[closed-pr-unlanded]" "$OUT"
chk "E2 names the PR number" "#81" "$OUT"
printf '81\tCLOSED\tfeat/gone-forever\t0\n' > "$PRF"
OUT="$(run SW_PR_FIXTURE="$PRF")"
nchk "E3 closed PR whose branch is GONE is not flagged" "STRANDED[closed-pr-unlanded]" "$OUT"
# a MERGED PR's branch has nothing left to strand
git -C "$REPO" checkout -q master
git -C "$REPO" merge -q --no-ff -m merge feat/wt-work
git -C "$REPO" push -q origin master; git -C "$REPO" fetch -q origin
printf '81\tCLOSED\tfeat/wt-work\t0\n' > "$PRF"
OUT="$(run SW_PR_FIXTURE="$PRF")"
nchk "E4 closed PR fully contained in base is not flagged" "STRANDED[closed-pr-unlanded]" "$OUT"

echo "== F. shape 5: OPEN PR with ZERO checks (false-receipt class) =="
printf '99\tOPEN\tfeat/wt-work\t0\n' > "$PRF"
OUT="$(run SW_PR_FIXTURE="$PRF")"
chk "F1 zero-check OPEN PR DETECTED" "STRANDED[pr-no-checks]" "$OUT"
chk "F2 names the PR number" "#99" "$OUT"
printf '99\tOPEN\tfeat/wt-work\t1\n' > "$PRF"
OUT="$(run SW_PR_FIXTURE="$PRF")"
nchk "F3 one check is enough to clear it" "STRANDED[pr-no-checks]" "$OUT"

echo "== G. never-false-green: unreadable PR state is UNDETERMINED, never clean =="
# Run against a PRISTINE clone so the ONLY thing the run can report is the undetermined PR state —
# otherwise a local finding would mask whether rc/UNDETERMINED are correct.
EMPTY="$TMP/emptyfleet"; mkdir -p "$EMPTY"       # deliberately NO state/ subdir at all
CLEAN="$TMP/clean"; git clone -q "$BARE" "$CLEAN"
OUT="$(SW_REPO="$CLEAN" SW_BASE=master SW_FLEET_DIR="$EMPTY" SW_NO_GH=1 bash "$SCRIPT" 2>&1)"; RC=$?
chk "G1 reports UNDETERMINED" "UNDETERMINED" "$OUT"
nchk "G2 does NOT report clean" "clean: stranded-work" "$OUT"
[ "$RC" = 3 ] && ok "G3 rc=3 on undetermined" || no "G3 rc=3 on undetermined (got $RC)"
chk "G4 says which shapes went unchecked" "NOT checked" "$OUT"

echo "== H. fresh checkout, EMPTY fleet/state: no false positives =="
OUT="$(SW_REPO="$CLEAN" SW_BASE=master SW_FLEET_DIR="$EMPTY" SW_PR_FIXTURE=/dev/null bash "$SCRIPT" 2>&1)"; RC=$?
nchk "H1 no findings on a pristine clone" "STRANDED[" "$OUT"
[ "$RC" = 0 ] && ok "H2 rc=0 on a pristine clone with empty state" || no "H2 rc=0 (got $RC)"

echo "== I. missing checkout is SKIPPED, not flagged =="
OUT="$(SW_REPO="$TMP/does-not-exist" SW_FLEET_DIR="$EMPTY" SW_PR_FIXTURE=/dev/null bash "$SCRIPT" 2>&1)"; RC=$?
chk "I1 absent repo path is skipped" "no checkout on this box" "$OUT"
[ "$RC" = 0 ] && ok "I1b rc=0 (absent repo is not a finding)" || no "I1b rc=0 (got $RC)"

echo "== I2. output cap keeps the report readable without hiding the count =="
# The first live run emitted 100+ dirty-worktree lines. An unreadable report is a disabled report,
# but suppressing DETAIL must never suppress the COUNT or flip the exit status.
NOISE="$TMP/noise"; git clone -q "$BARE" "$NOISE"; git -C "$NOISE" fetch -q origin
for i in 1 2 3 4 5 6 7; do
  git -C "$NOISE" branch -q "feat/noise-$i" "origin/master"
  git -C "$NOISE" commit -q --allow-empty -m "n$i" 2>/dev/null
  ( cd "$NOISE" && git checkout -q "feat/noise-$i" && git commit -q --allow-empty -m "ahead-$i" && git checkout -q master )
done
OUT="$(SW_REPO="$NOISE" SW_BASE=master SW_FLEET_DIR="$EMPTY" SW_PR_FIXTURE=/dev/null bash "$SCRIPT" 2>&1)"; RC=$?
CNT="$(printf '%s\n' "$OUT" | grep -c '^STRANDED\[unpushed-branch\] /')"
[ "$CNT" -le 5 ] && ok "I2a detail lines are capped ($CNT shown)" || no "I2a detail not capped ($CNT lines)"
chk "I2b suppression is announced, not silent" "suppressed" "$OUT"
chk "I2c the FULL count is still reported" "7 x unpushed-branch" "$OUT"
[ "$RC" = 1 ] && ok "I2d capping does not change the exit status" || no "I2d rc (got $RC)"
OUT="$(SW_LIMIT=0 SW_REPO="$NOISE" SW_BASE=master SW_FLEET_DIR="$EMPTY" SW_PR_FIXTURE=/dev/null bash "$SCRIPT" 2>&1)"
CNT="$(printf '%s\n' "$OUT" | grep -c '^STRANDED\[unpushed-branch\] /')"
[ "$CNT" -eq 7 ] && ok "I2e SW_LIMIT=0 prints every finding" || no "I2e SW_LIMIT=0 printed $CNT/7"

echo "== J. safety + reentrancy contract =="
# CODE only — the header comment legitimately NAMES preflight/validate_board while explaining why
# it must never call them, so the assertion has to look past comments or it would fire on prose.
SRC="$(sed 's/#.*$//' "$SCRIPT")"
nchk "J1 no recursive delete" "rm -rf" "$SRC"
nchk "J2 no branch deletion" "branch -D" "$SRC"
nchk "J3 no worktree removal" "worktree remove" "$SRC"
nchk "J4 no push" "git push" "$SRC"
nchk "J5 never invokes preflight (fork-bomb class)" "preflight.sh" "$SRC"
nchk "J6 never invokes validate_board (fork-bomb class)" "validate_board.sh" "$SRC"
nchk "J7 no PR mutation" "gh pr close" "$SRC"
nchk "J8 no PR merge" "gh pr merge" "$SRC"
OUT="$(STRANDED_WORK_ACTIVE=1 SW_REPO="$REPO" SW_FLEET_DIR="$FLEETD" bash "$SCRIPT" 2>&1)"; RC=$?
chk "J9 reentrancy guard short-circuits a nested run" "reentrancy guard" "$OUT"
[ "$RC" = 0 ] && ok "J10 nested run exits 0 without scanning" || no "J10 (got $RC)"

echo "== K. wiring: the detector is actually reachable from a trigger =="
PRE="$HERE/../preflight.sh"
# CODE only, and the DEFINITION alone is not enough: a defined-but-never-called detector is exactly
# the "runs only when a human types its name" failure this ticket exists to prevent. Assert the
# CALL inside cmd_detect's dispatch list, so deleting the call line goes RED even though the
# function (and every comment naming it) survives.
PRESRC="$(sed 's/#.*$//' "$PRE")"
case "$PRESRC" in *"detect_stranded_work(){"*) ok "K1a preflight.sh defines the detector";;
  *) no "K1a preflight.sh does not define detect_stranded_work";; esac
if printf '%s\n' "$PRESRC" | grep -qE '^[[:space:]]+detect_stranded_work[[:space:]]*$'; then
  ok "K1b cmd_detect actually CALLS it (wired, not just defined)"
else
  no "K1b detect_stranded_work is never CALLED — an unwired tool does not meet the requirement"
fi
grep -q 'stranded-work.test.sh' "$HERE/../checks/rig-ci-scope.sh" \
  && ok "K2 this suite is in the CI allowlist" || no "K2 suite absent from CI_SUITES allowlist"

echo
echo "stranded-work.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
