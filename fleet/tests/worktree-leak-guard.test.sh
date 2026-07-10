#!/usr/bin/env bash
# worktree-leak-guard.test.sh — FAIL-ON-REVERT tests for the #1 worktree-leak guard
# (fleet/leak-guard.sh). Exercises the ACTUAL functions the launcher uses, against real temp
# git repos. It NEVER touches the live fleet or /home/stack/code/charon.
#
# Covers:
#   (a) leak_worktree_setup creates the worktree off origin/master (launcher owns create/cd).
#   (b) leak_worktree_setup REFUSES (rc 2) when a needs-push marker exists — protects stranded work.
#   (c) leak_worktree_setup FAILS LOUDLY (rc 1) when it cannot create — never returns 0-into-main.
#   (d) leak_detect: LEAK when 0 commits + clean worktree + main newly dirty; CLEAN otherwise.
#   (e) safe_worktree_remove REFUSES (rc 2, worktree preserved) when a needs-push marker exists,
#       and removes cleanly when it does not.
# Reverting any guard flips one of these assertions -> the test fails.
#
# Run:  bash fleet/tests/worktree-leak-guard.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# shellcheck source=/dev/null
source "$SRC/leak-guard.sh"

# Build a fresh origin(bare)+charon(clone with origin/master). Echoes: "<charon> <origin>".
mk_charon(){
  local root; root="$(mktemp -d)"
  git init -q --bare "$root/origin.git"
  git init -q "$root/charon"
  ( cd "$root/charon"
    git checkout -q -b master
    echo base > base.txt; git add base.txt; git commit -q -m base
    git remote add origin "$root/origin.git"
    git push -q origin master
    git fetch -q origin ) >/dev/null 2>&1
  echo "$root/charon"
}

echo "== (a) leak_worktree_setup creates the worktree off origin/master =="
charon="$(mk_charon)"; wt="$charon-fleet-TICK"; branch="feat/tick"
rc=0; leak_worktree_setup "$charon" "$wt" "$branch" "" || rc=$?
check "a1 setup returns 0" "$rc" "0"
[ -d "$wt" ] && ok "a2 worktree dir created" || bad "a2 worktree dir created"
check "a3 worktree is on the ticket branch" "$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null)" "$branch"
check "a4 branch tips at origin/master" \
  "$(git -C "$wt" rev-parse HEAD)" "$(git -C "$charon" rev-parse origin/master)"
rm -rf "$(dirname "$charon")"

echo "== (b) leak_worktree_setup REFUSES when a needs-push marker exists =="
charon="$(mk_charon)"; wt="$charon-fleet-TICK"; branch="feat/tick"
leak_worktree_setup "$charon" "$wt" "$branch" "" >/dev/null 2>&1   # first create the worktree
echo committed > "$wt/work.txt"; git -C "$wt" add work.txt; git -C "$wt" commit -q -m stranded
np="$(mktemp)"; : > "$np"
rc=0; leak_worktree_setup "$charon" "$wt" "$branch" "$np" >/dev/null 2>&1 || rc=$?
check "b1 setup REFUSES (rc 2) with needs-push marker" "$rc" "2"
[ -f "$wt/work.txt" ] && ok "b2 stranded work preserved (not wiped)" || bad "b2 stranded work preserved"
rm -f "$np"; rm -rf "$(dirname "$charon")"

echo "== (c) leak_worktree_setup FAILS LOUD (rc 1) when it cannot create =="
rc=0; leak_worktree_setup "/no/such/repo/path" "/tmp/nope-wt" "feat/x" "" >/dev/null 2>&1 || rc=$?
check "c1 setup returns 1 (fatal) — never 0 into main" "$rc" "1"

echo "== (d) leak_detect =="
charon="$(mk_charon)"; wt="$charon-fleet-D"; branch="feat/d"
leak_worktree_setup "$charon" "$wt" "$branch" "" >/dev/null 2>&1
main_before="$(git -C "$charon" status --porcelain)"
# LEAK: worktree untouched (0 commits, clean) but the droid wrote into the MAIN checkout.
echo leaked > "$charon/stray.py"
check "d1 LEAK when main newly dirty + empty worktree" \
  "$(leak_detect "$charon" "$wt" "$branch" "$main_before")" "LEAK"
# CLEAN: the droid DID commit in its worktree (main dirtiness is irrelevant then).
echo real > "$wt/real.py"; git -C "$wt" add real.py; git -C "$wt" commit -q -m real
check "d2 CLEAN when the worktree has a commit" \
  "$(leak_detect "$charon" "$wt" "$branch" "$main_before")" "CLEAN"
rm -rf "$(dirname "$charon")"
# CLEAN: empty worktree but main NOT newly dirty (both clean) — nothing leaked.
charon="$(mk_charon)"; wt="$charon-fleet-E"; branch="feat/e"
leak_worktree_setup "$charon" "$wt" "$branch" "" >/dev/null 2>&1
mb="$(git -C "$charon" status --porcelain)"
check "d3 CLEAN when main not newly dirty" \
  "$(leak_detect "$charon" "$wt" "$branch" "$mb")" "CLEAN"
rm -rf "$(dirname "$charon")"

echo "== (e) safe_worktree_remove refuses on needs-push, removes otherwise =="
charon="$(mk_charon)"; wt="$charon-fleet-R"; branch="feat/r"; npdir="$(mktemp -d)"
leak_worktree_setup "$charon" "$wt" "$branch" "" >/dev/null 2>&1
: > "$npdir/R"                                   # live needs-push marker for id R
rc=0; safe_worktree_remove "$charon" "$wt" "R" "$npdir" >/dev/null 2>&1 || rc=$?
check "e1 REFUSES (rc 2) with live needs-push marker" "$rc" "2"
[ -d "$wt" ] && ok "e2 worktree preserved on refusal" || bad "e2 worktree preserved on refusal"
rm -f "$npdir/R"                                 # marker landed/cleared
rc=0; safe_worktree_remove "$charon" "$wt" "R" "$npdir" >/dev/null 2>&1 || rc=$?
check "e3 removes (rc 0) once marker is gone" "$rc" "0"
[ -d "$wt" ] && bad "e4 worktree removed" || ok "e4 worktree removed"
rm -rf "$(dirname "$charon")" "$npdir"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL WORKTREE-LEAK-GUARD TESTS PASS"
