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
  # REAL content per branch, not an empty commit: a branch that adds NO content has nothing to
  # strand and is legitimately suppressed by the squash-awareness check, which would make this
  # cap fixture vacuous. Distinct content keeps all 7 genuine, unlanded findings.
  ( cd "$NOISE" && git checkout -q "feat/noise-$i" \
      && echo "noise-$i" > "noise-$i.txt" && git add -A && git commit -q -m "ahead-$i" \
      && git checkout -q master )
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

echo "== L. SQUASH-merge awareness: landed content is not stranded, unlanded content still is =="
# WHY: this repo merges via SQUASH, which creates a NEW sha, so the original branch commits are
# permanently unreachable from every remote ref even though the content is fully landed. On the
# live rig the naive reachability test reported FIVE already-merged branches (PRs #121/#123/#124/
# #125/#126) — findings that could never clear, on the detector's first real run.
# The fixture SQUASH-MERGES FOR REAL (`git merge --squash`) into a real repo rather than
# simulating the shape, and master is advanced BEFORE the squash so the merge-base is genuinely
# behind base tip — the actual production shape, not the easy aligned case.
SB="$TMP/sq-remote.git"; SQ="$TMP/sq"
git init -q --bare -b master "$SB"; git init -q -b master "$SQ"
echo base > "$SQ/base.txt"; git -C "$SQ" add -A; git -C "$SQ" commit -qm base
git -C "$SQ" remote add origin "$SB"; git -C "$SQ" push -q origin master; git -C "$SQ" fetch -q origin
sqrun(){ env SW_REPO="$SQ" SW_BASE=master SW_FLEET_DIR="$EMPTY" SW_LIMIT=0 "$@" bash "$SCRIPT" 2>&1; }

# a MULTI-commit branch — `git cherry`/per-commit patch-id cannot see this squash, which is why
# the detector compares the branch's NET diff instead. Three of the five real cases had 2-4 commits.
git -C "$SQ" checkout -q -b feat/squashed
echo l1 > "$SQ/sq.txt"; git -C "$SQ" add -A; git -C "$SQ" commit -qm s1
echo l2 >> "$SQ/sq.txt"; git -C "$SQ" add -A; git -C "$SQ" commit -qm s2
git -C "$SQ" checkout -q master
echo moved > "$SQ/unrelated.txt"; git -C "$SQ" add -A; git -C "$SQ" commit -qm "base moves on"
git -C "$SQ" merge -q --squash feat/squashed && git -C "$SQ" commit -qm "squashed work (#1)"
git -C "$SQ" push -q origin master; git -C "$SQ" fetch -q origin
# precondition: the branch really IS unreachable from every remote ref (i.e. the naive test fires)
UNREACH="$(git -C "$SQ" rev-list --count feat/squashed --not --remotes)"
[ "$UNREACH" -gt 0 ] && ok "L0 fixture is genuinely squash-merged (branch unreachable from remotes)" \
  || no "L0 fixture is not the squash shape (unreachable=$UNREACH)"
OUT="$(sqrun SW_PR_FIXTURE=/dev/null)"; RC=$?
nchk "L1 SQUASH-merged branch is NOT reported" "feat/squashed" "$OUT"
chk "L2 and the run is clean, not merely quiet" "clean: stranded-work" "$OUT"
[ "$RC" = 0 ] && ok "L3 rc=0 when the only branch is squash-merged" || no "L3 rc=0 (got $RC)"

# ANTI-OVER-BLOCK. A squash-awareness fix that suppresses everything is WORSE than the false
# positives it removes, so the unlanded direction is asserted in the same fixture.
git -C "$SQ" checkout -q -b feat/really-stranded master
echo genuinely-unlanded > "$SQ/stranded.txt"; git -C "$SQ" add -A; git -C "$SQ" commit -qm real
git -C "$SQ" checkout -q master
OUT="$(sqrun SW_PR_FIXTURE=/dev/null)"; RC=$?
chk "L4 genuinely unlanded branch IS still reported" "STRANDED[unpushed-branch]" "$OUT"
chk "L5 names the unlanded branch" "feat/really-stranded" "$OUT"
chk "L6 says explicitly that the content is not on base" "is NOT on master" "$OUT"
nchk "L7 the squash-merged branch is still suppressed alongside it" "feat/squashed" "$OUT"
[ "$RC" = 1 ] && ok "L8 rc=1 with a genuine finding" || no "L8 rc=1 (got $RC)"

# CONTENT-IDENTICAL BUT UNMERGED. Matching some OTHER branch's patch proves nothing — only a
# patch already on BASE clears a branch. A twin of an unlanded branch must still be reported.
git -C "$SQ" checkout -q -b feat/twin master
echo genuinely-unlanded > "$SQ/stranded.txt"; git -C "$SQ" add -A; git -C "$SQ" commit -qm twin
git -C "$SQ" checkout -q master
OUT="$(sqrun SW_PR_FIXTURE=/dev/null)"
chk "L9 content-identical-but-unmerged branch is reported" "feat/twin" "$OUT"
chk "L10 its unlanded twin is reported too" "feat/really-stranded" "$OUT"

# NEVER-FALSE-GREEN for the new path. When the scan window cannot reach the merge point and PR
# state is unreadable, the branch is reported as UNVERIFIED — never silently cleared. "Could not
# determine" rendering as clean is the false-receipt class this whole detector exists to refuse.
# base must advance PAST the squash commit so a 1-commit window genuinely cannot see it —
# otherwise the squash is still the tip and the case is decidable, not undecidable.
echo later > "$SQ/later.txt"; git -C "$SQ" add -A; git -C "$SQ" commit -qm "later base work"
git -C "$SQ" push -q origin master; git -C "$SQ" fetch -q origin
OUT="$(sqrun SW_PR_FIXTURE=/dev/null SW_SQUASH_SCAN=1 SW_NO_GH=1)"; RC=$?
chk "L11 undecidable merge status is reported as UNVERIFIED" "UNVERIFIED" "$OUT"
chk "L12 the undecidable branch is still named" "feat/squashed" "$OUT"
nchk "L13 undecidable NEVER renders as clean" "clean: stranded-work" "$OUT"
[ "$RC" = 1 ] && ok "L14 rc is non-clean when merge status is undecidable" || no "L14 rc=1 (got $RC)"
# and a MERGED PR in the PR data rescues the out-of-window case (the same rows shapes 3/4/5 read,
# so squash-awareness costs zero extra gh calls and needs no second fixture hook)
MPRF="$TMP/merged-prs.tsv"; printf '1\tMERGED\tfeat/squashed\t2\n' > "$MPRF"
OUT="$(sqrun SW_PR_FIXTURE="$MPRF" SW_SQUASH_SCAN=1)"
nchk "L15 a MERGED PR clears an out-of-window branch" "feat/squashed" "$OUT"
chk "L16 but the genuinely unlanded branch survives that fallback" "feat/really-stranded" "$OUT"

echo "== M. shape 6: AHEAD-OF-REMOTE is its own shape, not mislabelled as unpushed-branch =="
# WHY THIS ASSERTION HAS TEETH: `--not --remotes` ALREADY caught this branch before the relabel —
# it was simply reported under the wrong name. So a test that only asserted "it is reported" would
# have passed both before and after the fix and proved nothing. These assertions pin the LABEL and
# pin the ABSENCE of the wrong label, which is the only thing that actually changed.
MR="$TMP/ahead-remote.git"; MM="$TMP/ahead"
git init -q --bare -b master "$MR"; git init -q -b master "$MM"
echo base > "$MM/base.txt"; git -C "$MM" add -A; git -C "$MM" commit -qm base
git -C "$MM" remote add origin "$MR"; git -C "$MM" push -q origin master; git -C "$MM" fetch -q origin
# pushed once (so it TRACKS a remote) then grown locally — the live PR-with-a-stale-head shape
git -C "$MM" checkout -q -b feat/pushed-then-grown
echo one > "$MM/one.txt"; git -C "$MM" add -A; git -C "$MM" commit -qm one
git -C "$MM" push -q -u origin feat/pushed-then-grown 2>/dev/null
echo two > "$MM/two.txt"; git -C "$MM" add -A; git -C "$MM" commit -qm two
# and a branch that genuinely never touched a remote, to prove the two shapes still separate
git -C "$MM" checkout -q -b feat/never-pushed-at-all master
echo n > "$MM/n.txt"; git -C "$MM" add -A; git -C "$MM" commit -qm never
git -C "$MM" checkout -q master
mrun(){ env SW_REPO="$MM" SW_BASE=master SW_FLEET_DIR="$EMPTY" SW_LIMIT=0 "$@" bash "$SCRIPT" 2>&1; }
OUT="$(mrun SW_PR_FIXTURE=/dev/null)"
chk "M1 ahead-of-remote is its OWN shape"        "STRANDED[ahead-of-remote]"        "$OUT"
chk "M2 it names the tracking branch"            "feat/pushed-then-grown"           "$OUT"
chk "M3 it names the upstream it is ahead of"    "origin/feat/pushed-then-grown"    "$OUT"
if printf '%s\n' "$OUT" | grep -q '^STRANDED\[unpushed-branch\].*feat/pushed-then-grown'; then
  no "M4 tracking branch must NOT still be labelled unpushed-branch (the mislabel is the defect)"
else ok "M4 tracking branch is no longer mislabelled unpushed-branch"; fi
if printf '%s\n' "$OUT" | grep -q '^STRANDED\[unpushed-branch\].*feat/never-pushed-at-all'; then
  ok "M5 a genuinely never-pushed branch is STILL unpushed-branch (shapes did not collapse)"
else no "M5 never-pushed branch lost its unpushed-branch label"; fi

echo "== N. shape 7: STASHES (per-repo, on no branch and no remote) =="
NOUT="$(mrun SW_PR_FIXTURE=/dev/null)"
nchk "N1 no stash reported when the stash list is empty" "STRANDED[stash]" "$NOUT"
echo stashed-work > "$MM/base.txt"; git -C "$MM" stash push -q -m "wip-that-would-vanish" 2>/dev/null
OUT="$(mrun SW_PR_FIXTURE=/dev/null)"
chk "N2 a stash entry IS detected"        "STRANDED[stash]"          "$OUT"
chk "N3 it names the stash"               "wip-that-would-vanish"    "$OUT"
# PER-REPO, not per-worktree: refs/stash lives in the common git dir, so N linked worktrees must
# not multiply one stash into N findings (an unreadable report gets skimmed past = switched off).
git -C "$MM" worktree add -q "$TMP/ahead-wt" master 2>/dev/null
OUT="$(mrun SW_PR_FIXTURE=/dev/null)"
NST="$(printf '%s\n' "$OUT" | grep -c '^STRANDED\[stash\]' || true)"
[ "$NST" = 1 ] && ok "N4 one stash list -> exactly ONE finding despite 2 worktrees" \
                || no "N4 stash reported $NST times (must be per-repo, not per-worktree)"

echo "== O. shape 8: DETACHED HEAD, emitted BEFORE the dirty-check early-exit =="
# THE POINT OF THIS TEST: the worktree is left CLEAN. `git status --porcelain` is empty, so the
# shape-2 `continue` fires; if shape 8 is emitted after it (or if the porcelain `detached` field is
# discarded as it was before), this goes RED. A clean detached HEAD is still stranded.
DR="$TMP/det-remote.git"; DD="$TMP/det"
git init -q --bare -b master "$DR"; git init -q -b master "$DD"
echo base > "$DD/base.txt"; git -C "$DD" add -A; git -C "$DD" commit -qm base
git -C "$DD" remote add origin "$DR"; git -C "$DD" push -q origin master; git -C "$DD" fetch -q origin
DWT="$TMP/det-wt"; git -C "$DD" worktree add -q --detach "$DWT" master
echo orphan > "$DWT/orphan.txt"; git -C "$DWT" add -A; git -C "$DWT" commit -qm "orphan commit on no branch"
drun(){ env SW_REPO="$DD" SW_BASE=master SW_FLEET_DIR="$EMPTY" SW_LIMIT=0 "$@" bash "$SCRIPT" 2>&1; }
OUT="$(drun SW_PR_FIXTURE=/dev/null)"
[ -z "$(git -C "$DWT" status --porcelain)" ] && ok "O1 fixture worktree is genuinely CLEAN" \
                                              || no "O1 fixture is dirty — test would prove nothing"
chk "O2 clean detached HEAD with orphan commits IS detected" "STRANDED[detached-head]" "$OUT"
chk "O3 it names the worktree"                               "det-wt"                  "$OUT"
nchk "O4 it is NOT reported as a dirty worktree"             "STRANDED[dirty-worktree]" "$OUT"
# PRECISION GUARD: a detached checkout PINNED to a commit that IS on a branch/remote is a pinned
# baseline, not lost work. Reporting it is the day-one false-positive class that gets detectors
# switched off — so it must stay silent.
PWT="$TMP/det-pinned"; git -C "$DD" worktree add -q --detach "$PWT" master
OUT="$(drun SW_PR_FIXTURE=/dev/null)"
nchk "O5 a detached checkout pinned to a reachable commit is NOT reported" "det-pinned" "$OUT"
chk  "O6 the genuinely orphaned one still is"                              "det-wt"     "$OUT"

echo "== P. the CRON WRAPPER: fail-loud, heartbeat, and state-change dedupe =="
WRAP="$HERE/../checks/stranded-work-cron.sh"
[ -f "$WRAP" ] && ok "P1 wrapper exists (the session-independent caller)" || no "P1 wrapper missing at $WRAP"
PF="$TMP/pfleet"; mkdir -p "$PF/checks" "$PF/state"
cp "$HERE/../pending.sh" "$PF/pending.sh"
prun(){ env SWC_FLEET="$PF" SWC_STATE="$PF/state" SW_REPO="$MM" SW_BASE=master SW_FLEET_DIR="$EMPTY" "$@" bash "$WRAP" 2>&1; }

# P2/P3: THE §L TRAP. A crontab line aimed at a path this checkout lacks registers perfectly and
# then silently never executes. The wrapper must NOT no-op: loud, non-zero, AND still heartbeat
# (so "cron fired but is broken" stays distinguishable from "cron was removed").
OUT="$(prun SW_PR_FIXTURE=/dev/null)"; RC=$?
chk "P2 missing detector fails LOUD"        "detector not found"  "$OUT"
[ "$RC" = 2 ] && ok "P3a rc=2 on missing detector (never a silent 0)" || no "P3a rc=2 (got $RC)"
[ -f "$PF/state/.stranded-work.heartbeat" ] && ok "P3b heartbeat written EVEN on failure" \
                                            || no "P3b no heartbeat on the failure path"
grep -q 'MISSING' "$PF/state/OPERATOR-ACTIONS.md" 2>/dev/null \
  && ok "P3c missing detector raised an OPERATOR ACTION" || no "P3c no operator action raised"

# now give it a real detector and a repo with real findings
cp "$SCRIPT" "$PF/checks/stranded-work.sh"; : > "$PF/state/OPERATOR-ACTIONS.md"; rm -f "$PF/state/.stranded-work.hash"
OUT="$(prun SW_PR_FIXTURE=/dev/null)"; RC=$?
[ "$RC" = 1 ] && ok "P4 wrapper propagates the detector's findings rc" || no "P4 rc=1 expected (got $RC)"
R1="$(grep -c 'STRANDED WORK' "$PF/state/OPERATOR-ACTIONS.md" 2>/dev/null || true)"
[ "$R1" = 1 ] && ok "P5 first run appends exactly one operator action" || no "P5 expected 1 row, got $R1"

# P6 IS THE MANDATORY DEDUPE LEG. Without state-change hashing a 20-minute cadence over a standing
# backlog appends ~72 rows/day and buries the fail-loud channel under its own output.
prun SW_PR_FIXTURE=/dev/null >/dev/null 2>&1
prun SW_PR_FIXTURE=/dev/null >/dev/null 2>&1
R2="$(grep -c 'STRANDED WORK' "$PF/state/OPERATOR-ACTIONS.md" 2>/dev/null || true)"
[ "$R2" = 1 ] && ok "P6 unchanged findings across 3 runs still ONE row (state-change hashed)" \
              || no "P6 backlog re-appended: $R2 rows after 3 identical runs"
# P7 IS THE HALF THE HASH ALONE CANNOT DO. Three consecutive LIVE runs on the rig produced
# "256 / 259 / 258 finding(s)" because other agents were landing work in between — all three were
# real state changes with different text, so the hash correctly let all three through and the
# board grew three rows anyway. A recurring report of a MOVING number is ONE standing item.
# The changed value must reach the operator; the row count must not move.
L0="$(cut -f1 "$PF/state/OPERATOR-ACTIONS.md" | head -1)"
git -C "$MM" checkout -q -b feat/brand-new-strand master
echo more > "$MM/more.txt"; git -C "$MM" add -A; git -C "$MM" commit -qm more
git -C "$MM" checkout -q master
prun SW_PR_FIXTURE=/dev/null >/dev/null 2>&1
R3="$(grep -c 'STRANDED WORK' "$PF/state/OPERATOR-ACTIONS.md" 2>/dev/null || true)"
[ "$R3" = 1 ] && ok "P7a a CHANGED finding-set updates the SAME row (still 1 row)" \
              || no "P7a state change grew the board to $R3 rows"
grep -q 'feat/brand-new-strand\|finding' "$PF/state/OPERATOR-ACTIONS.md" \
  && ok "P7b the updated row carries the new state (dedupe is not a mute button)" \
  || no "P7b state change was swallowed"
L1="$(cut -f1 "$PF/state/OPERATOR-ACTIONS.md" | head -1)"
[ "$L0" = "$L1" ] && ok "P7c the label is PRESERVED across the update (never reused/renumbered)" \
                  || no "P7c label moved $L0 -> $L1"
# P8: pending.sh's own guards, independent of the wrapper
BB="$TMP/bb"; mkdir -p "$BB/state"; cp "$HERE/../pending.sh" "$BB/pending.sh"
bash "$BB/pending.sh" add "identical item" >/dev/null 2>&1
bash "$BB/pending.sh" add "identical item" >/dev/null 2>&1
BBN="$(grep -c 'identical item' "$BB/state/OPERATOR-ACTIONS.md" 2>/dev/null || true)"
[ "$BBN" = 1 ] && ok "P8a pending.sh add is idempotent on identical text" \
               || no "P8a pending.sh appended the same text $BBN times"
bash "$BB/pending.sh" add --key "COUNT:" "COUNT: 1 thing" >/dev/null 2>&1
bash "$BB/pending.sh" add --key "COUNT:" "COUNT: 2 things" >/dev/null 2>&1
bash "$BB/pending.sh" add --key "COUNT:" "COUNT: 3 things" >/dev/null 2>&1
KN="$(grep -c 'COUNT:' "$BB/state/OPERATOR-ACTIONS.md" 2>/dev/null || true)"
[ "$KN" = 1 ] && ok "P8b --key upsert keeps a moving value to ONE row" || no "P8b keyed add made $KN rows"
grep -q 'COUNT: 3 things' "$BB/state/OPERATOR-ACTIONS.md" \
  && ok "P8c and that row holds the LATEST value" || no "P8c keyed row is stale"
# a NON-keyed add must still append — the upsert must not become a global mute
bash "$BB/pending.sh" add "an unrelated item" >/dev/null 2>&1
grep -q 'an unrelated item' "$BB/state/OPERATOR-ACTIONS.md" \
  && ok "P8d unrelated items still reach the board" || no "P8d the upsert swallowed an unrelated item"

echo "== Q. DOGFOOD: the cadence gate needs BOTH legs and FAILS when either is reverted =="
# Leg A alone is THE TRAP: a crontab line whose command does not exist registers fine and never
# executes. Leg B alone cannot tell "entry deleted" from "about to run". The live gate is
# detect_stranded_work in preflight.sh; these assertions prove it cannot be satisfied by one leg.
PRESRC2="$(sed 's/#.*$//' "$PRE")"
printf '%s\n' "$PRESRC2" | grep -q 'stranded-work-cron.sh' \
  && ok "Q1 preflight checks leg A (crontab registration)" \
  || no "Q1 preflight never inspects the crontab — registration leg absent"
printf '%s\n' "$PRESRC2" | grep -q '_stranded_hb_fresh' \
  && ok "Q2 preflight checks leg B (heartbeat freshness)" \
  || no "Q2 preflight never checks the heartbeat — anti-silence leg absent"
printf '%s\n' "$PRESRC2" | grep -q 'wd_probe_fresh' \
  && ok "Q3 freshness uses the watchdog SSOT grammar (wd_probe_fresh), not a private copy" \
  || no "Q3 freshness predicate was re-implemented instead of reusing wd_probe_fresh"

# EXECUTABLE fail-on-revert: drive the real preflight function with both legs seamed.
# The cadence block is EXTRACTED FROM THE REAL preflight.sh (not re-typed here) and executed, so
# deleting or weakening either leg in preflight.sh makes these assertions go red — a copy of the
# logic in the test would prove only that the copy works.
QF="$TMP/qfleet"; mkdir -p "$QF/state"; QSH="$TMP/cadence-under-test.sh"
{
  echo 'HERE="$1"'
  sed -n '/^_stranded_hb_fresh(){/,/^}/p' "$PRE"
  echo '_cadence_under_test(){'
  sed -n '/# --- CADENCE LIVENESS/,/^  fi$/p' "$PRE"
  echo '}'
  echo '_cadence_under_test'
} > "$QSH"
grep -q '_stranded_hb_fresh' "$QSH" && grep -q 'crontab' "$QSH" \
  && ok "Q3b the extracted block really is preflight's own cadence code" \
  || no "Q3b extraction failed — the executable legs below would be vacuous"
qcad(){ # qcad <crontab-output> <heartbeat-age-s|none>  -> the cadence verdict lines
  local cron="$1" age="$2" hb="$QF/state/.stranded-work.heartbeat"
  rm -f "$hb"
  if [ "$age" != none ]; then echo "beat" > "$hb"; touch -d "@$(( $(date +%s) - age ))" "$hb" 2>/dev/null; fi
  STRANDED_HB_TTL=5400 STRANDED_CRONTAB_CMD="echo $cron" bash "$QSH" "$QF" 2>&1
}
OUT="$(qcad '*/20_*_*_*_*_/x/checks/stranded-work-cron.sh' 60)"
chk "Q4 BOTH legs green -> clean receipt" "clean: stranded-work-cadence" "$OUT"
# REVERT LEG A: entry removed from the crontab. Heartbeat still fresh.
OUT="$(qcad 'no-such-entry' 60)"
nchk "Q5 leg A reverted (entry removed) -> NOT clean" "clean: stranded-work-cadence" "$OUT"
chk  "Q6 and it says which leg failed"                "leg A registered: NO"          "$OUT"
# REVERT LEG B: entry still registered, but the command never executes -> heartbeat goes stale.
# This is the exact trap: registration alone must NOT buy a green line.
OUT="$(qcad '*/20_*_*_*_*_/x/checks/stranded-work-cron.sh' 99999)"
nchk "Q7 leg B reverted (registered but not executing) -> NOT clean" "clean: stranded-work-cadence" "$OUT"
chk  "Q8 and it names the stale heartbeat"                          "REGISTERED BUT NOT EXECUTING" "$OUT"
OUT="$(qcad '*/20_*_*_*_*_/x/checks/stranded-work-cron.sh' none)"
chk  "Q9 missing heartbeat is reported, never silently green"       "heartbeat:   MISSING"         "$OUT"
grep -q 'stranded-work-cron.sh' "$HERE/../checks/rig-ci-scope.sh" \
  && ok "Q10 the wrapper is in scope for CI review" || ok "Q10 (wrapper is not a CI suite — n/a)"

echo
echo "stranded-work.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
