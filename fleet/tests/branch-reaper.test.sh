#!/usr/bin/env bash
# branch-reaper.test.sh — FAIL-ON-REVERT self-test for fleet/branch-reaper.sh.
#
# Operates on a TEMP git repo fixture (never the live fleet or /home/stack/code/charon).
# GREEN-IS-NOT-PROOF: exit 0 does NOT prove correct reaping — asserts the unmerged branch
# AND a claimed worktree SURVIVE (the exact data-loss risk a too-broad reaper causes).
#
# Covers:
#   (a) DRY-RUN default: a merged branch is reported as REAP-able but is NOT deleted.
#   (b) --apply: a merged branch IS deleted (real `git branch --merged` check, not a stub).
#   (c) FAIL-ON-REVERT (the core guard): an UNMERGED branch SURVIVES `--apply`. Reverting
#       the `--merged` filter (`git branch` without it) would wrong-list it -> this test RED.
#   (d) LIVE-CLAIM WORKTREE GUARD: a fleet worktree dir with a live state/claims/<id>
#       marker is NEVER reaped under --apply.
#   (e) LIVE needs-push GUARD: a worktree with a state/needs-push/<id> marker is preserved
#       (committed-but-unlanded work must never be destroyed).
#   (f) STALE worktree (no live claim) IS reaped under --apply.
#   (g) idempotent second --apply run is exit 0 and changes nothing.
#
# Run:  bash fleet/tests/branch-reaper.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# Build a temp repo with a master + a merged throwaway branch + an unmerged branch.
# Echoes the repo path. The merged branch's commit is folded into master; the unmerged
# branch's commit is NOT reachable from master.
mk_repo(){
  local root; root="$(mktemp -d)"
  git init -q "$root/repo"
  ( cd "$root/repo"
    git checkout -q -b master
    printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
    # merged throwaway: a commit on a side branch that gets fast-forwarded into master
    git checkout -q -b throwaway-merged
    printf 'm\n' > m.txt; git add m.txt; git commit -q -m merged-throwaway
    git checkout -q master
    git merge -q --ff-only throwaway-merged
    # unmerged branch: a commit NOT reachable from master
    git checkout -q -b live-unmerged
    printf 'u\n' > u.txt; git add u.txt; git commit -q -m unmerged-work
    git checkout -q master
  ) >/dev/null 2>&1
  echo "$root/repo"
}

# Set up a fleet state tree under <root>/fleet with claims + needs-push marker dirs.
mk_fleet(){
  local root="$1"
  mkdir -p "$root/fleet/state/claims" "$root/fleet/state/needs-push"
  echo "$root/fleet"
}

run_reaper(){
  # run_reaper <repo> <fleet_dir> <wt_glob> [args...]
  local repo="$1" fleet="$2" glob="$3"; shift 3
  REAPER_REPO="$repo" REAPER_FLEET_DIR="$fleet" REAPER_WT_GLOB="$glob" \
    REAPER_BASE=master REAPER_PROTECTED="" \
    bash "$SRC/branch-reaper.sh" "$@"
}

echo "== (a) DRY-RUN default: merged branch reported REAP-able but NOT deleted =="
root="$(mktemp -d)"; repo="$(mk_repo)"; fleet="$(mk_fleet "$root")"
out="$(run_reaper "$repo" "$fleet" "$root/none-*" 2>&1)"; rc=$?
check "a1 dry-run exit 0" "$rc" "0"
echo "$out" | grep -q "REAP.*throwaway-merged" && ok "a2 merged branch flagged REAP-able" \
                                                || bad "a2 merged branch flagged REAP-able"
git -C "$repo" show-ref --verify --quiet "refs/heads/throwaway-merged" \
  && ok "a3 merged branch NOT deleted in dry-run" \
  || bad "a3 merged branch NOT deleted in dry-run (got deleted!)"

echo "== (b) --apply deletes the merged branch =="
out="$(run_reaper "$repo" "$fleet" "$root/none-*" --apply 2>&1)"; rc=$?
check "b1 apply exit 0" "$rc" "0"
git -C "$repo" show-ref --verify --quiet "refs/heads/throwaway-merged" \
  && bad "b2 merged branch deleted under --apply" \
  || ok "b2 merged branch deleted under --apply"

echo "== (c) FAIL-ON-REVERT: unmerged branch SURVIVES --apply =="
git -C "$repo" show-ref --verify --quiet "refs/heads/live-unmerged" \
  && ok "c1 unmerged branch SURVIVED apply (guard intact)" \
  || bad "c1 unmerged branch was DELETED under --apply (guard reverted — DATA LOSS)"
# NEGATIVE: prove the guard is what protects. If branch-reaper listed the unmerged branch
# as REAP-able in its dry-run, the guard is broken. The unmerged branch must NOT appear in
# the `--merged master` candidate list, so it must NEVER appear as REAP-able.
dry="$(run_reaper "$repo" "$fleet" "$root/none-*" 2>&1)"
echo "$dry" | grep -q "REAP.*live-unmerged" \
  && bad "c2 unmerged branch wrongly listed as REAP-able (guard reverted)" \
  || ok "c2 unmerged branch NOT listed as REAP-able (merged-filter guard intact)"

echo "== (d) LIVE-CLAIM worktree GUARD: claimed worktree SURVIVES --apply =="
root2="$(mktemp -d)"; repo2="$(mk_repo)"; fleet2="$(mk_fleet "$root2")"
wt_dir="$root2/repo-fleet-CL1"
git -C "$repo2" worktree add -q "$wt_dir" -b feat/cl1 master >/dev/null 2>&1
printf 'live\n' > "$fleet2/state/claims/CL1"      # LIVE claim marker — droid working it
out="$(run_reaper "$repo2" "$fleet2" "$root2/repo-fleet-*" --apply 2>&1)"; rc=$?
check "d1 apply with live claim exit 0" "$rc" "0"
echo "$out" | grep -q "KEEP.*$wt_dir" && ok "d2 claimed worktree flagged KEEP" \
                                        || bad "d2 claimed worktree flagged KEEP"
[ -d "$wt_dir" ] && ok "d3 claimed worktree SURVIVED (live claim marker protected it)" \
                  || bad "d3 claimed worktree SURVIVED (was reaped — DATA LOSS)"

echo "== (e) LIVE needs-push GUARD: worktree with needs-push marker preserved =="
root3="$(mktemp -d)"; repo3="$(mk_repo)"; fleet3="$(mk_fleet "$root3")"
wt3="$root3/repo-fleet-NP1"
git -C "$repo3" worktree add -q "$wt3" -b feat/np1 master >/dev/null 2>&1
printf 'stranded\n' > "$fleet3/state/needs-push/NP1"   # committed-but-unlanded work
out="$(run_reaper "$repo3" "$fleet3" "$root3/repo-fleet-*" --apply 2>&1)"; rc=$?
check "e1 apply with needs-push exit 0" "$rc" "0"
[ -d "$wt3" ] && ok "e2 needs-push worktree SURVIVED (committed-unlanded work protected)" \
               || bad "e2 needs-push worktree SURVIVED (was reaped — DATA LOSS)"

echo "== (f) STALE worktree (no live claim) IS reaped under --apply =="
root4="$(mktemp -d)"; repo4="$(mk_repo)"; fleet4="$(mk_fleet "$root4")"
wt4="$root4/repo-fleet-STALE1"
git -C "$repo4" worktree add -q "$wt4" -b feat/stale1 master >/dev/null 2>&1
# NO claims/STALE1, NO needs-push/STALE1 -> stale, fair to reap.
out="$(run_reaper "$repo4" "$fleet4" "$root4/repo-fleet-*" --apply 2>&1)"; rc=$?
check "f1 apply exit 0" "$rc" "0"
echo "$out" | grep -q "REAP.*$wt4" && ok "f2 stale worktree flagged REAP-able" \
                                      || bad "f2 stale worktree flagged REAP-able"
[ -d "$wt4" ] && bad "f3 stale worktree reaped (dir still exists)" \
                || ok "f3 stale worktree reaped"

echo "== (g) idempotent second --apply run is exit 0, changes nothing =="
rc=0; run_reaper "$repo4" "$fleet4" "$root4/repo-fleet-*" --apply >/dev/null 2>&1 || rc=$?
check "g1 second apply exit 0" "$rc" "0"
out="$(run_reaper "$repo4" "$fleet4" "$root4/repo-fleet-*" --apply 2>&1)"
echo "$out" | grep -q "worktrees: 0 reaped" && ok "g2 second run reaps 0 worktrees" \
                                             || bad "g2 second run reaps 0 worktrees"
echo "$out" | grep -q "branches: 0 reaped" && ok "g3 second run reaps 0 branches" \
                                             || bad "g3 second run reaps 0 branches"

# cleanup
rm -rf "$root" "$root2" "$root3" "$root4"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL BRANCH-REAPER TESTS PASS"
