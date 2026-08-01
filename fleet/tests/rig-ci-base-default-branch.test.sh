#!/usr/bin/env bash
# rig-ci-base-default-branch.test.sh — FAIL-ON-REVERT tests for RIG-CI-BASE-DEFAULT-BRANCH.
#
# THE DEFECT (reproduced 2026-08-01 while landing LAUNCHER-GATE-SETE-KILL).
# fleet/land-push.sh resolves the diff base for its scoped board check by probing a list of
# candidate refs. That list used to start with "origin/$_DSTG" — the DESTINATION BRANCH's own
# remote-tracking ref — so the gate's verdict depended on whether the branch had been pushed
# before:
#
#   1st push of a branch: refs/remotes/origin/<branch> does NOT exist -> falls through to
#                         origin/master -> the FULL branch diff is checked -> the owning ticket
#                         on master IS found -> GREEN.
#   2nd push of the SAME branch: that ref now EXISTS -> the base becomes the branch's own
#                         previous tip -> only the incremental commit is diffed -> a commit that
#                         touches just code reports "this change touches CODE owned by NO live
#                         board ticket", even though a master ticket plainly owns those files.
#
# The board/substrate/ownership questions are inherently "does the board on the DEFAULT BRANCH
# cover this change" — and the board exists ONLY on that branch, never in a feature branch's
# previous tip. Asking them against the branch tip is a category error.
#
# These tests EXTRACT the real candidate loop out of land-push.sh (they do not re-implement it)
# and run it against purpose-built ref layouts, so restoring the old ordering fails them.
#
# Run:  bash fleet/tests/rig-ci-base-default-branch.test.sh   (exit 0 = all pass, 1 = a failure)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the real fleet/ dir
LAND="$SRC/land-push.sh"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

[ -r "$LAND" ] || { echo "FAIL: cannot read $LAND"; exit 1; }

# Extract the base-candidate block verbatim: `_CIB=""` through the `done` closing the for loop.
# Extracting rather than copying is what makes this fail-on-revert — the test runs shipped code.
extract_base_block(){
  awk '/^ *_CIB=""$/{f=1} f{print} f&&/^ *done$/{exit}' "$LAND"
}
BLOCK="$(extract_base_block)"
[ -n "$BLOCK" ] || { echo "FAIL: could not extract the base-candidate block from land-push.sh"; exit 1; }
case "$BLOCK" in
  *for\ _cand\ in*) : ;;
  *) echo "FAIL: extracted block contains no candidate loop (markers moved?)"; exit 1;;
esac

# Build a throwaway repo carrying the requested remote-tracking refs, then run the extracted
# block against it and print whichever base it selected.
resolve_base(){
  local dstg="$1"; shift              # remaining args = remote-tracking refs to create
  local d; d="$(mktemp -d)"
  (
    cd "$d" || exit 1
    git init -q .
    git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
    local sha; sha="$(git rev-parse HEAD)"
    local r
    for r in "$@"; do git update-ref "refs/remotes/$r" "$sha"; done
  ) >/dev/null 2>&1
  local harness; harness="$(mktemp)"
  {
    echo 'set -uo pipefail'
    echo "REPO=$(printf '%q' "$d")"
    echo "_DSTG=$(printf '%q' "$dstg")"
    echo "$BLOCK"
    echo 'echo "BASE=${_CIB:-<none>}"'
  } > "$harness"
  bash "$harness" 2>/dev/null | sed -n 's/^BASE=//p'
  rm -f "$harness"; rm -rf "$d"
}

echo "== (1) THE REGRESSION: a feature branch already pushed once must still diff vs master =="
# Both refs exist — exactly the 2nd-push situation. Old order picked origin/feat/x (the branch's
# own tip) and produced the false 'code owned by NO live board ticket' RED.
check "1a 2nd push of a feature branch resolves to origin/master" \
  "$(resolve_base feat/x origin/master origin/feat/x)" "origin/master"

echo "== (2) 1st push (branch ref absent) is unchanged — still origin/master =="
check "2a 1st push resolves to origin/master" \
  "$(resolve_base feat/x origin/master)" "origin/master"

echo "== (3) the SAME verdict on both pushes — the invariant that was broken =="
first="$(resolve_base feat/x origin/master)"
second="$(resolve_base feat/x origin/master origin/feat/x)"
check "3a base is identical on 1st and 2nd push" "$first" "$second"

echo "== (4) pushing TO master is unchanged =="
check "4a destination master resolves to origin/master" \
  "$(resolve_base master origin/master)" "origin/master"

echo "== (5) a 'main'-defaulted repo resolves to origin/main =="
check "5a no origin/master, origin/main present -> origin/main" \
  "$(resolve_base feat/x origin/main)" "origin/main"
check "5b main-default, feature already pushed -> still origin/main" \
  "$(resolve_base feat/x origin/main origin/feat/x)" "origin/main"

echo "== (6) LAST-RESORT fallback preserved: neither default exists -> the destination ref =="
# Without this the loop would resolve nothing and land-push would refuse (exit 4) on repos that
# genuinely have no master/main — a regression the reorder must NOT introduce.
check "6a neither default present -> origin/\$_DSTG" \
  "$(resolve_base feat/x origin/feat/x)" "origin/feat/x"

echo "== (7) fail-closed preserved: no candidate ref at all -> empty base =="
# land-push turns an empty _CIB into a hard refusal (exit 4) rather than checking zero tickets
# and reporting GREEN. The reorder must keep that reachable.
check "7a no refs at all -> no base resolved" \
  "$(resolve_base feat/x)" "<none>"

echo
echo "== rig-ci-base-default-branch: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ] || exit 1
