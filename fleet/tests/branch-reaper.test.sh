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
#   (h) REAL DIRTY GUARD: a worktree with an UNCOMMITTED MODIFIED file survives --apply,
#       even with NO claim/needs-push marker. Reverting the `git status --porcelain` check
#       in _rp_keep_reason/_lg_wt_target_ok makes this RED.
#   (i) same for an UNTRACKED file (porcelain reports `??`).
#   (j) UNPUSHED-COMMIT GUARD: a CLEAN worktree whose HEAD is on no remote survives.
#       Reverting the `rev-list --count HEAD --not --remotes` check makes this RED.
#   (k) ANTI-OVER-BLOCK: a genuinely clean, fully-pushed, unclaimed worktree IS still reaped.
#       A guard that keeps everything is as useless as one that keeps nothing.
#   (l) FAIL-CLOSED: a worktree whose state cannot be determined (unreadable/broken .git)
#       survives. "Could not check" must never resolve to "clean".
#
# Added 2026-07-19 after an adversarial review gutted THREE guards and this suite stayed
# 38/38 green. Green was not evidence; each of the following is revert-sensitive by
# construction (the RED demonstration for each is recorded in the commit message):
#   (m) HIGH-1 CATASTROPHIC-TARGET GUARD: a candidate that IS the live checkout, and one that
#       CONTAINS it, are REFUSEd by name. Replacing _lg_wt_catastrophic's call site with `:`
#       drops the REFUSE lines -> RED. (Previously the single most destructive guard in the
#       file had no test at all.)
#   (n) HIGH-2 DEGENERATE GLOB: REAPER_WT_GLOB='*' yields an EMPTY family prefix, which makes
#       the family restriction match everything and the glob expand against CWD. The reviewer
#       used exactly this to rm -rf an unrelated repo. Asserts the run ABORTS and that an
#       unrelated clean+pushed repo sitting in cwd is never even listed as REAP-able.
#   (o) MED-2 MISCONFIGURATION EXITS NON-ZERO: no repo, unknown key, and no-keys-at-all each
#       exit non-zero. A reaper that silently no-ops on bad config is a false green.
#   (p) HIGH-3 REGISTRY / MULTI-TARGET PATH: the rig-awareness code (the 64x scope growth) is
#       driven for real against TWO fixture repos via a stub repo-registry.sh, so `return 0`
#       before the registry loop is RED. Every other test takes the legacy early-return.
#   (q) MED-1 WORKTREE MARKER: a branch checked out in ANOTHER worktree is '+ '-marked by
#       `git branch`. Asserts no name is ever reported with a marker, and that a PROTECTED
#       branch so marked is still recognised as protected (it previously bypassed the list).
#   (r) MED-3 FAIL-CLOSED STATUS PROBE: a worktree that is clean, fully pushed and unclaimed
#       but whose `git status` ERRORS (corrupt index) survives. This is the only fixture that
#       reaches branch-reaper.sh's own exit-code probe; without it that probe is dead code.
#
# DEFENSIVE (HIGH-3, coupled hazard): every run_reaper call sets REAPER_KEYS="" as well as the
# legacy REAPER_REPO/REAPER_WT_GLOB overrides. This suite invokes --apply nine times and was
# kept off /home/stack/code/charon and /home/stack/charon-private by ONE `if` in _rp_targets.
# If that early-return is ever broken, the empty key list now resolves to NO targets and the
# run aborts, instead of pointing nine --apply runs at the live rig.
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
#
# The fixture also gets a BARE ORIGIN with master pushed. That is load-bearing, not decor:
# the unpushed-commit guard keeps any worktree whose HEAD is not reachable from a remote ref,
# so without a real remote EVERY worktree would be (correctly) kept and the reaping tests
# could never distinguish a working guard from a reaper that does nothing.
TMPDIRS=()            # LOW-3: every mktemp -d root, so cleanup can remove ALL of them
mk_repo(){
  local root; root="$(mktemp -d)"; TMPDIRS+=("$root")
  git init -q --bare "$root/origin.git"
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
    git remote add origin "$root/origin.git"
    git push -q origin master
  ) >/dev/null 2>&1
  echo "$root/repo"
}

# Set up a fleet state tree under <root>/fleet with claims + needs-push marker dirs.
mk_fleet(){
  local root="$1"
  mkdir -p "$root/fleet/state/claims" "$root/fleet/state/needs-push"
  echo "$root/fleet"
}

# mktmp — a tracked mktemp -d (LOW-3: nothing allocated by this suite may leak).
mktmp(){ local d; d="$(mktemp -d)"; TMPDIRS+=("$d"); echo "$d"; }

run_reaper(){
  # run_reaper <repo> <fleet_dir> <wt_glob> [args...]
  local repo="$1" fleet="$2" glob="$3"; shift 3
  # REAPER_KEYS="" is DEFENSIVE, not decorative — see the header note. If the legacy
  # single-target early-return in _rp_targets ever breaks, this makes the run abort with no
  # targets rather than aim --apply at the live rig checkouts.
  REAPER_REPO="$repo" REAPER_FLEET_DIR="$fleet" REAPER_WT_GLOB="$glob" REAPER_KEYS="" \
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

echo "== (h) REAL DIRTY GUARD: worktree with an uncommitted MODIFIED file SURVIVES --apply =="
root5="$(mktemp -d)"; repo5="$(mk_repo)"; fleet5="$(mk_fleet "$root5")"
wt5="$root5/repo-fleet-DIRTY1"
git -C "$repo5" worktree add -q "$wt5" -b feat/dirty1 master >/dev/null 2>&1
printf 'uncommitted edit\n' >> "$wt5/base.txt"        # tracked file, modified, NOT committed
# NO claims/DIRTY1, NO needs-push/DIRTY1 -> the OLD marker-proxy guard would have reaped it.
out="$(run_reaper "$repo5" "$fleet5" "$root5/repo-fleet-*" --apply 2>&1)"; rc=$?
check "h1 apply exit 0" "$rc" "0"
[ -d "$wt5" ] && ok "h2 dirty worktree SURVIVED --apply (dirty-guard intact)" \
               || bad "h2 dirty worktree was REAPED (dirty-guard reverted — DATA LOSS)"
echo "$out" | grep -q "KEEP.*$wt5" && ok "h3 dirty worktree flagged KEEP" \
                                    || bad "h3 dirty worktree flagged KEEP"
echo "$out" | grep -q "REAP.*$wt5" && bad "h4 dirty worktree wrongly listed REAP-able" \
                                    || ok "h4 dirty worktree NOT listed REAP-able"
grep -q 'uncommitted edit' "$wt5/base.txt" 2>/dev/null \
  && ok "h5 the uncommitted edit itself still exists on disk" \
  || bad "h5 the uncommitted edit was destroyed"

echo "== (i) DIRTY GUARD covers UNTRACKED files too =="
root6="$(mktemp -d)"; repo6="$(mk_repo)"; fleet6="$(mk_fleet "$root6")"
wt6="$root6/repo-fleet-UNTRACKED1"
git -C "$repo6" worktree add -q "$wt6" -b feat/untracked1 master >/dev/null 2>&1
printf 'scratch notes\n' > "$wt6/NOTES-not-added.txt"   # never `git add`ed
out="$(run_reaper "$repo6" "$fleet6" "$root6/repo-fleet-*" --apply 2>&1)"; rc=$?
check "i1 apply exit 0" "$rc" "0"
[ -f "$wt6/NOTES-not-added.txt" ] \
  && ok "i2 untracked file SURVIVED --apply (porcelain '??' honoured)" \
  || bad "i2 untracked file was DESTROYED (untracked changes ignored — DATA LOSS)"

echo "== (j) UNPUSHED-COMMIT GUARD: clean worktree with HEAD on no remote SURVIVES =="
root7="$(mktemp -d)"; repo7="$(mk_repo)"; fleet7="$(mk_fleet "$root7")"
wt7="$root7/repo-fleet-UNPUSHED1"
git -C "$repo7" worktree add -q "$wt7" -b feat/unpushed1 master >/dev/null 2>&1
( cd "$wt7" && printf 'real work\n' > work.txt && git add work.txt \
  && git commit -q -m "stranded work — committed, never pushed" ) >/dev/null 2>&1
# The tree is now CLEAN (status --porcelain is empty) — only the unpushed guard can save it.
clean="$(git -C "$wt7" status --porcelain 2>/dev/null)"
check "j1 fixture really is clean (isolates the unpushed guard)" "$clean" ""
out="$(run_reaper "$repo7" "$fleet7" "$root7/repo-fleet-*" --apply 2>&1)"; rc=$?
check "j2 apply exit 0" "$rc" "0"
[ -d "$wt7" ] && ok "j3 unpushed-commit worktree SURVIVED (unpushed-guard intact)" \
               || bad "j3 unpushed-commit worktree REAPED (unpushed-guard reverted — DATA LOSS)"
[ -f "$wt7/work.txt" ] && ok "j4 the stranded commit's file still on disk" \
                        || bad "j4 the stranded commit was destroyed"

echo "== (k) ANTI-OVER-BLOCK: clean + fully-pushed + unclaimed worktree IS reaped =="
root8="$(mktemp -d)"; repo8="$(mk_repo)"; fleet8="$(mk_fleet "$root8")"
wt8="$root8/repo-fleet-CLEAN1"
git -C "$repo8" worktree add -q "$wt8" -b feat/clean1 master >/dev/null 2>&1
# HEAD == master == origin/master, no local edits, no markers => nothing to preserve.
clean="$(git -C "$wt8" status --porcelain 2>/dev/null)"
check "k1 fixture is clean" "$clean" ""
unp="$(git -C "$wt8" rev-list --count HEAD --not --remotes 2>/dev/null)"
check "k2 fixture HEAD is fully pushed" "$unp" "0"
out="$(run_reaper "$repo8" "$fleet8" "$root8/repo-fleet-*" --apply 2>&1)"; rc=$?
check "k3 apply exit 0" "$rc" "0"
echo "$out" | grep -q "REAP.*$wt8" && ok "k4 clean+pushed worktree flagged REAP-able" \
                                    || bad "k4 clean+pushed worktree NOT flagged (guards over-block)"
[ -d "$wt8" ] && bad "k5 clean+pushed worktree reaped (dir still exists — reaper is inert)" \
               || ok "k5 clean+pushed worktree reaped"

echo "== (l) FAIL-CLOSED: worktree whose state cannot be determined SURVIVES =="
root9="$(mktemp -d)"; repo9="$(mk_repo)"; fleet9="$(mk_fleet "$root9")"
wt9="$root9/repo-fleet-OPAQUE1"
git -C "$repo9" worktree add -q "$wt9" -b feat/opaque1 master >/dev/null 2>&1
printf 'gitdir: /nonexistent/broken/path\n' > "$wt9/.git"   # git can no longer read this tree
printf 'irreplaceable\n' > "$wt9/precious.txt"
git -C "$wt9" status --porcelain >/dev/null 2>&1 \
  && bad "l1 fixture is NOT actually undecidable (git status still works)" \
  || ok "l1 fixture really is undecidable (git status fails there)"
out="$(run_reaper "$repo9" "$fleet9" "$root9/repo-fleet-*" --apply 2>&1)"; rc=$?
check "l2 apply exit 0" "$rc" "0"
[ -d "$wt9" ] && ok "l3 undecidable worktree SURVIVED (fail-closed)" \
               || bad "l3 undecidable worktree REAPED ('cannot check' treated as 'clean')"
[ -f "$wt9/precious.txt" ] && ok "l4 its contents still on disk" \
                            || bad "l4 its contents were destroyed"

echo "== (m) HIGH-1 CATASTROPHIC-TARGET GUARD: live checkout / a dir CONTAINING it are REFUSEd =="
# m1 — the candidate IS the live checkout. Glob '<root>/rep*' makes the repo itself a family
# member, which is exactly the "naming accident" the guard exists to survive.
rootM="$(mktmp)"; repoM="$(mk_repo)"; fleetM="$(mk_fleet "$rootM")"
repoM_root="$(dirname "$repoM")"
outM="$(run_reaper "$repoM" "$fleetM" "$repoM_root/rep*" --apply 2>&1)"; rc=$?
check "m1 apply exit 0" "$rc" "0"
echo "$outM" | grep -q "REFUSE worktree .*$repoM" \
  && ok "m2 live checkout REFUSEd by the catastrophic guard" \
  || bad "m2 live checkout NOT refused (catastrophic guard removed/bypassed)"
echo "$outM" | grep -q "that is the LIVE checkout" \
  && ok "m3 refusal names the reason (live checkout)" \
  || bad "m3 refusal reason missing (catastrophic guard removed/bypassed)"
[ -d "$repoM/.git" ] && ok "m4 the live checkout still exists" \
                      || bad "m4 the live checkout was DESTROYED"
# m2 — the candidate CONTAINS the live checkout (an ancestor directory). Deleting it would
# take the repo with it; equality checks alone would sail straight past this.
rootM2="$(mktmp)"
mkdir -p "$rootM2/fam/inner/repo"
( cd "$rootM2/fam/inner/repo" && git init -q . && printf 'x\n' > f.txt && git add f.txt \
  && git commit -q -m x ) >/dev/null 2>&1
fleetM2="$(mk_fleet "$rootM2")"
outM2="$(run_reaper "$rootM2/fam/inner/repo" "$fleetM2" "$rootM2/fam/*" --apply 2>&1)"; rc=$?
check "m5 apply exit 0" "$rc" "0"
echo "$outM2" | grep -q "CONTAINS the live checkout" \
  && ok "m6 ancestor-of-checkout REFUSEd (containment, not equality)" \
  || bad "m6 ancestor-of-checkout NOT refused (catastrophic guard removed/bypassed)"
[ -f "$rootM2/fam/inner/repo/f.txt" ] && ok "m7 the contained checkout survived" \
                                       || bad "m7 the contained checkout was DESTROYED"

echo "== (n) HIGH-2: a '*'-style glob cannot reach outside the configured family =="
# The reviewer drove REAPER_WT_GLOB='*' end-to-end and rm -rf'd an unrelated repo in cwd.
# This runs DRY-RUN only: with the guard the run aborts; without it, the victim is LISTED as
# REAP-able, which is the assertion that goes RED. No deletion is risked either way.
rootN="$(mktmp)"; repoN="$(mk_repo)"; fleetN="$(mk_fleet "$rootN")"
victim="$rootN/precious-repo"
git init -q --bare "$rootN/victim-origin.git"
git init -q "$victim"
( cd "$victim" && git checkout -q -b master && printf 'irreplaceable\n' > precious.txt \
  && git add precious.txt && git commit -q -m p \
  && git remote add origin "$rootN/victim-origin.git" && git push -q origin master ) >/dev/null 2>&1
# Precondition: the victim is clean AND fully pushed, i.e. NOTHING but the family restriction
# stands between it and deletion. Without this the test would pass for the wrong reason.
vclean="$(git -C "$victim" status --porcelain 2>/dev/null)"
check "n1 victim is clean" "$vclean" ""
vunp="$(git -C "$victim" rev-list --count HEAD --not --remotes 2>/dev/null)"
check "n2 victim is fully pushed (only the family guard can save it)" "$vunp" "0"
outN="$( cd "$rootN" && REAPER_REPO="$repoN" REAPER_FLEET_DIR="$fleetN" REAPER_WT_GLOB='*' \
         REAPER_KEYS="" REAPER_BASE=master REAPER_PROTECTED="" \
         bash "$SRC/branch-reaper.sh" 2>&1 )"; rc=$?
[ "$rc" -ne 0 ] && ok "n3 degenerate glob '*' ABORTS non-zero" \
                 || bad "n3 degenerate glob '*' was ACCEPTED (rc=$rc — family guard removed)"
echo "$outN" | grep -q "INVALID CONFIG" && ok "n4 abort names it as invalid config" \
                                         || bad "n4 no INVALID CONFIG message"
echo "$outN" | grep -q "REAP.*precious-repo" \
  && bad "n5 unrelated repo in CWD listed as REAP-able (glob escaped the family — DATA LOSS)" \
  || ok "n5 unrelated repo in CWD never listed as REAP-able"
[ -f "$victim/precious.txt" ] && ok "n6 unrelated repo untouched" \
                               || bad "n6 unrelated repo was DESTROYED"
# n7 — the weaker sibling case: no trailing '*' means prefix '<x>/xy' also admits '<x>/xyZ'.
rc=0; ( cd "$rootN" && REAPER_REPO="$repoN" REAPER_FLEET_DIR="$fleetN" REAPER_WT_GLOB="$rootN/xy" \
        REAPER_KEYS="" REAPER_BASE=master REAPER_PROTECTED="" \
        bash "$SRC/branch-reaper.sh" ) >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "n7 glob without trailing '*' ABORTS (sibling-prefix hazard)" \
                 || bad "n7 glob without trailing '*' accepted (admits sibling dirs)"

# n8..n11 — MED: the family checks are LITERAL, so a non-canonical prefix defeats them while
# expanding to the IDENTICAL candidate set. Confirmed by the reviewer against the live rig:
# '/home/stack/*' is refused as admitting a protected tree, but '/home/stack/./*',
# '//home/stack/*', '/home/stack/../*' and '/home/stack/a/../../../*' were all ACCEPTED, and an
# unrelated clean fully-pushed repo in the widened family was listed REAP.
#
# Every form below is written to RE-DESCEND into "$rootN", so it reaches exactly the set that
# "$rootN/*" reaches — the victim included. That keeps the blast radius inside the fixture even
# when the guard is neutered for a RED demonstration, while still making "victim listed REAP"
# the discriminating assertion rather than a log-string match. DRY-RUN only.
baseN="$(basename "$rootN")"
# The '..' forms only EXPAND if their intermediate components exist, and a glob that expands to
# nothing would pass the victim assertion for the wrong reason. Create them so all four forms
# genuinely reach the victim when the guard is neutered.
mkdir -p "$rootN/sub" "$rootN/a/b"
i=8
for badglob in "$rootN/./*" "/$rootN/*" "$rootN/sub/../*" "$rootN/a/b/../../../$baseN/*"; do
  outB="$( cd "$rootN" && REAPER_REPO="$repoN" REAPER_FLEET_DIR="$fleetN" REAPER_WT_GLOB="$badglob" \
           REAPER_KEYS="" REAPER_BASE=master REAPER_PROTECTED="" \
           bash "$SRC/branch-reaper.sh" 2>&1 )"; rc=$?
  [ "$rc" -ne 0 ] \
    && ok "n$i non-canonical glob '$badglob' ABORTS non-zero" \
    || bad "n$i non-canonical glob '$badglob' was ACCEPTED (rc=$rc — normalisation check removed)"
  echo "$outB" | grep -q "INVALID CONFIG" \
    && ok "n$i-r abort names it as invalid config with a reason" \
    || bad "n$i-r no INVALID CONFIG reason for '$badglob'"
  echo "$outB" | grep -q "REAP.*precious-repo" \
    && bad "n$i-v unrelated repo listed as REAP-able via '$badglob' (non-canonical bypass — DATA LOSS)" \
    || ok "n$i-v unrelated repo never listed as REAP-able via '$badglob'"
  i=$((i+1))
done
[ -f "$victim/precious.txt" ] && ok "n12 unrelated repo still untouched after the bypass forms" \
                               || bad "n12 unrelated repo was DESTROYED by a non-canonical glob"
# n13 — the canonical family head must still be ACCEPTED. A normalisation check that rejects
# legitimate globs would silently disable the reaper; this is the anti-overreach assertion.
rc=0; ( cd "$rootN" && REAPER_REPO="$repoN" REAPER_FLEET_DIR="$fleetN" REAPER_WT_GLOB="$rootN/wt-*" \
        REAPER_KEYS="" REAPER_BASE=master REAPER_PROTECTED="" \
        bash "$SRC/branch-reaper.sh" ) >/dev/null 2>&1 || rc=$?
check "n13 canonical glob still accepted (normalisation is not over-broad)" "$rc" "0"

echo "== (o) MED-2: misconfiguration exits NON-ZERO (a silent no-op is a false green) =="
rc=0; REAPER_WT_GLOB="/tmp/definitely-not-a-family-*" REAPER_KEYS="" \
      bash "$SRC/branch-reaper.sh" >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "o1 REAPER_WT_GLOB without REAPER_REPO exits non-zero" \
                 || bad "o1 REAPER_WT_GLOB without REAPER_REPO exited 0 (false green)"
rc=0; REAPER_KEYS="no-such-repo-key" bash "$SRC/branch-reaper.sh" >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "o2 unknown repo key exits non-zero" \
                 || bad "o2 unknown repo key exited 0 (false green)"
rc=0; REAPER_KEYS="" bash "$SRC/branch-reaper.sh" >/dev/null 2>&1 || rc=$?
[ "$rc" -ne 0 ] && ok "o3 no usable targets exits non-zero" \
                 || bad "o3 no usable targets exited 0 (false green)"

echo "== (p) HIGH-3: the REGISTRY / MULTI-TARGET path is actually executed =="
# Every other test sets REAPER_REPO and so takes the legacy single-target early-return; the
# registry resolution, the RPGLOBID sentinel, and the multi-target loop were never run. A stub
# repo-registry.sh beside a COPY of the real branch-reaper.sh drives them against fixtures.
rootP="$(mktmp)"
repoP1="$(mk_repo)"; rootP1="$(dirname "$repoP1")"
repoP2="$(mk_repo)"; rootP2="$(dirname "$repoP2")"
stub="$rootP/stubfleet"; mkdir -p "$stub"
cp "$SRC/branch-reaper.sh" "$SRC/leak-guard.sh" "$stub/"
cat > "$stub/repo-registry.sh" <<STUBEOF
repo_default_key(){ echo P1; }
repo_known_keys(){ echo "P1 P2"; }
repo_valid_id(){ [ -n "\${1-}" ]; }
repo_resolve(){
  case "\$1" in
    P1) RR_KEY=P1; RR_PATH="$repoP1"; RR_WT="$rootP1/wt-\$2"; RR_BASE=master; RR_GATE=true ;;
    P2) RR_KEY=P2; RR_PATH="$repoP2"; RR_WT="$rootP2/wt-\$2"; RR_BASE=master; RR_GATE=true ;;
    *)  return 1 ;;
  esac
  return 0
}
STUBEOF
mkdir -p "$stub/state/claims" "$stub/state/needs-push"
wtP1="$rootP1/wt-S1"; wtP2="$rootP2/wt-S2"
git -C "$repoP1" worktree add -q "$wtP1" -b feat/s1 master >/dev/null 2>&1
git -C "$repoP2" worktree add -q "$wtP2" -b feat/s2 master >/dev/null 2>&1
outP="$(REAPER_KEYS="P1 P2" REAPER_FLEET_DIR="$stub" REAPER_PROTECTED="" \
        bash "$stub/branch-reaper.sh" --apply 2>&1)"; rc=$?
check "p1 registry-mode apply exit 0" "$rc" "0"
echo "$outP" | grep -q "target: repo=$repoP1" && ok "p2 target 1 resolved from the registry" \
                                               || bad "p2 target 1 NOT resolved (registry path never ran)"
echo "$outP" | grep -q "target: repo=$repoP2" && ok "p3 target 2 resolved (multi-target loop ran)" \
                                               || bad "p3 target 2 NOT resolved (multi-target loop never ran)"
[ -d "$wtP1" ] && bad "p4 target 1's stale worktree reaped" || ok "p4 target 1's stale worktree reaped"
[ -d "$wtP2" ] && bad "p5 target 2's stale worktree reaped" || ok "p5 target 2's stale worktree reaped"

echo "== (q) MED-1: worktree-marked branches are parsed cleanly and honour the protected list =="
# `git branch --merged` prints '+ ' before a branch checked out in ANOTHER worktree. Scraping
# that produced the literal name "+ main", which matched no protected entry and no ref.
rootQ="$(mktmp)"; repoQ="$(mk_repo)"; rootQ1="$(dirname "$repoQ")"; fleetQ="$(mk_fleet "$rootQ")"
git -C "$repoQ" branch -q main master                       # merged AND protected
git -C "$repoQ" worktree add -q "$rootQ1/wt-main" main    >/dev/null 2>&1   # => '+ main'
git -C "$repoQ" worktree add -q "$rootQ1/wt-tw" throwaway-merged >/dev/null 2>&1 # => '+ throwaway-merged'
# Sanity: git really does mark them (if git ever stops, this test stops being meaningful).
git -C "$repoQ" branch --merged master | grep -q '^+ ' \
  && ok "q1 git really does '+'-mark worktree-held branches" \
  || bad "q1 fixture does not reproduce the '+' marker"
outQ="$(REAPER_REPO="$repoQ" REAPER_FLEET_DIR="$fleetQ" REAPER_WT_GLOB="$rootQ/none-*" \
        REAPER_KEYS="" REAPER_BASE=master REAPER_PROTECTED="main" \
        bash "$SRC/branch-reaper.sh" 2>&1)"; rc=$?
check "q2 dry-run exit 0" "$rc" "0"
echo "$outQ" | grep -qF 'branch + ' \
  && bad "q3 a branch was reported with git's '+' marker still attached (name not parsed)" \
  || ok "q3 no branch reported with a '+' marker"
echo "$outQ" | grep -q "KEEP   branch main (protected)" \
  && ok "q4 worktree-held PROTECTED branch still recognised as protected" \
  || bad "q4 worktree-held protected branch BYPASSED the protected list"
echo "$outQ" | grep -qE "REAP.*branch (\+ )?main" \
  && bad "q5 protected branch 'main' listed as REAP-able" \
  || ok "q5 protected branch 'main' never listed as REAP-able"
echo "$outQ" | grep -q "KEEP   branch throwaway-merged (checked out in worktree" \
  && ok "q6 in-use branch kept, not falsely counted as reaped" \
  || bad "q6 in-use branch not kept (would be reported deleted without being deleted)"
git -C "$repoQ" show-ref --verify --quiet refs/heads/main \
  && ok "q7 protected branch still exists" || bad "q7 protected branch was deleted"

echo "== (r) MED-3: a worktree whose 'git status' ERRORS survives (fail-closed exit-code probe) =="
rootR="$(mktmp)"; repoR="$(mk_repo)"; rootR1="$(dirname "$repoR")"; fleetR="$(mk_fleet "$rootR")"
wtR="$rootR1/repo-fleet-IDX1"
git -C "$repoR" worktree add -q "$wtR" -b feat/idx1 master >/dev/null 2>&1
printf 'irreplaceable\n' > "$wtR/precious.txt"
git -C "$wtR" add precious.txt >/dev/null 2>&1
git -C "$wtR" commit -q -m precious >/dev/null 2>&1
git -C "$wtR" push -q origin HEAD:refs/heads/feat-idx1 >/dev/null 2>&1   # fully pushed
printf 'not-a-valid-index' > "$repoR/.git/worktrees/repo-fleet-IDX1/index"
# The fixture must reach branch-reaper's OWN probe: rev-parse must SUCCEED (so the
# "not a readable git working tree" check at the line above does not short-circuit it)
# while `git status` FAILS. Test (l) never got this far — it broke .git outright.
git -C "$wtR" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  && ok "r1 fixture is still a readable work tree (rev-parse succeeds)" \
  || bad "r1 fixture short-circuits at rev-parse — it does not reach the status probe"
git -C "$wtR" status --porcelain >/dev/null 2>&1 \
  && bad "r2 fixture's git status still works — nothing to fail closed on" \
  || ok "r2 fixture's git status ERRORS (corrupt index)"
runp="$(git -C "$wtR" rev-list --count HEAD --not --remotes 2>/dev/null)"
check "r3 fixture is fully pushed (only the status probe can save it)" "$runp" "0"
outR="$(run_reaper "$repoR" "$fleetR" "$rootR1/repo-fleet-*" --apply 2>&1)"; rc=$?
check "r4 apply exit 0" "$rc" "0"
echo "$outR" | grep -q "'git status' failed" \
  && ok "r5 KEEP reason is the failed status probe" \
  || bad "r5 status-probe reason absent (probe removed — the tree read as 'clean')"
[ -d "$wtR" ] && ok "r6 unreadable-status worktree SURVIVED --apply" \
               || bad "r6 unreadable-status worktree REAPED (errored probe read as 'clean')"
[ -f "$wtR/precious.txt" ] && ok "r7 its contents still on disk" \
                            || bad "r7 its contents were destroyed"

echo "== (s) FINDING-1 LEAK-GUARD BYPASS: refusal is TERMINAL — no 'rm -rf' fallback =="
# The removal line used to be `worktree remove --force ... 2>/dev/null || rm -rf "$wt_dir"`:
# the guard REFUSING was the TRIGGER for the unguarded delete. The fixture below is the exact
# shape that turns that into data loss — a directory inside the reaped family that is a clean,
# fully-pushed git repo but is NOT a registered worktree of the target repo (and not any
# ticket's canonical path). `git worktree remove` cannot remove it, so the old code fell
# through to `rm -rf` on a repo it had no claim to. safe_worktree_remove refuses and STOPS.
rootS="$(mktmp)"; repoS="$(mk_repo)"; fleetS="$(mk_fleet "$rootS")"
wtS="$rootS/repo-fleet-ORPHAN1"
git init -q --bare "$rootS/orphan-origin.git"
git init -q "$wtS"
( cd "$wtS"
  git checkout -q -b master
  printf 'irreplaceable\n' > precious.txt; git add precious.txt; git commit -q -m orphan
  git remote add origin "$rootS/orphan-origin.git"; git push -q origin master ) >/dev/null 2>&1
# Fixture must be indistinguishable from a reap candidate on every EXISTING guard, so that only
# the removal-path fix can save it.
check "s1 orphan is clean" "$(git -C "$wtS" status --porcelain 2>/dev/null)" ""
check "s2 orphan HEAD is fully pushed" "$(git -C "$wtS" rev-list --count HEAD --not --remotes 2>/dev/null)" "0"
git -C "$repoS" worktree list --porcelain 2>/dev/null | grep -qF "$wtS" \
  && bad "s3 fixture IS a registered worktree — safe_worktree_remove would legitimately remove it" \
  || ok "s3 orphan is NOT a registered worktree of the target repo"
outS="$(run_reaper "$repoS" "$fleetS" "$rootS/repo-fleet-*" --apply 2>&1)"; rc=$?
check "s4 apply exit 0" "$rc" "0"
echo "$outS" | grep -q "REAP.*$wtS" \
  && ok "s5 orphan WAS selected for reaping (so only the removal path can save it)" \
  || bad "s5 orphan never selected — this fixture no longer exercises the removal path"
echo "$outS" | grep -q "NOT running 'rm -rf'" \
  && ok "s6 leak-guard's refusal reason is VISIBLE (not swallowed by 2>/dev/null)" \
  || bad "s6 refusal reason absent — stderr swallowed, or safe_worktree_remove bypassed"
echo "$outS" | grep -q "FAILED worktree $wtS" \
  && ok "s7 refusal is reported as FAILED, not counted as a reap" \
  || bad "s7 refusal not reported — the run claims a deletion that did not happen"
[ -d "$wtS" ] && ok "s8 ON DISK: orphan repo SURVIVED --apply" \
               || bad "s8 ON DISK: orphan repo DESTROYED (the '|| rm -rf' fallback is back)"
[ -f "$wtS/precious.txt" ] && ok "s9 ON DISK: its contents intact" \
                            || bad "s9 ON DISK: its contents destroyed"
git -C "$wtS" show-ref --verify --quiet refs/heads/master \
  && ok "s10 ON DISK: its git history intact" || bad "s10 ON DISK: its git history destroyed"

echo "== (t) FINDING-2 LOW-2: 'fully pushed' on an UNVOUCHABLE remote-tracking ref => KEEP =="
# refs/remotes/* is a CACHE of a remote we are not talking to. After a force-push or an upstream
# branch deletion it asserts commits exist upstream when they do not — and this is a destruction
# path. The fix does NOT fetch (that would make deletion depend on the network, and would make
# the reaper MORE willing to delete); it ages the evidence and fails toward preservation.
rootT="$(mktmp)"; repoT="$(mk_repo)"; fleetT="$(mk_fleet "$rootT")"
wtT="$rootT/repo-fleet-STALE1"
git -C "$repoT" worktree add -q "$wtT" -b feat/stale1 master >/dev/null 2>&1
printf 'irreplaceable\n' > "$wtT/precious.txt"
git -C "$wtT" add precious.txt >/dev/null 2>&1
git -C "$wtT" commit -q -m stale-work >/dev/null 2>&1
git -C "$wtT" push -q origin HEAD:refs/heads/feat-stale1 >/dev/null 2>&1
check "t1 fixture is clean" "$(git -C "$wtT" status --porcelain 2>/dev/null)" ""
check "t2 fixture reads as fully pushed (per the local ref cache)" \
      "$(git -C "$wtT" rev-list --count HEAD --not --remotes 2>/dev/null)" "0"
# Age EVERY piece of on-disk sync evidence past the default 24h window. Nothing else changes:
# the tree is still clean, still unclaimed, and still "fully pushed" by the cache's account.
_age_evidence(){
  local gc; gc="$(git -C "$1" rev-parse --git-common-dir 2>/dev/null)"
  gc="$(cd "$1" && cd "$gc" && pwd -P)"
  while IFS= read -r f; do [ -e "$f" ] && touch -d '30 days ago' "$f" 2>/dev/null; done < <(
    printf '%s\n' "$gc/FETCH_HEAD" "$gc/packed-refs" "$(git -C "$1" rev-parse --git-path FETCH_HEAD 2>/dev/null)"
    find "$gc/logs/refs/remotes" "$gc/refs/remotes" -type f 2>/dev/null )
}
_age_evidence "$wtT"
outT="$(run_reaper "$repoT" "$fleetT" "$rootT/repo-fleet-*" --apply 2>&1)"; rc=$?
check "t3 apply exit 0" "$rc" "0"
echo "$outT" | grep -q "last reconciled with the remote" \
  && ok "t4 staleness is VISIBLE in the report (age + limit stated)" \
  || bad "t4 staleness never surfaced — the freshness probe is gone or inert"
[ -d "$wtT" ] && ok "t5 ON DISK: stale-ref worktree SURVIVED --apply" \
               || bad "t5 ON DISK: REAPED on the strength of a ref it cannot vouch for"
[ -f "$wtT/precious.txt" ] && ok "t6 ON DISK: its contents intact" \
                            || bad "t6 ON DISK: its contents destroyed"
git -C "$repoT" show-ref --verify --quiet refs/heads/feat/stale1 \
  && ok "t7 ON DISK: its branch ref still exists" || bad "t7 ON DISK: its branch ref is gone"
# ANTI-OVER-BLOCK for this guard specifically: with the window widened past the fixture's age,
# the SAME tree is reaped. Proves the AGE decided it, not a blanket keep-everything.
outT2="$(REAPER_REMOTE_MAX_AGE=999999999 run_reaper "$repoT" "$fleetT" "$rootT/repo-fleet-*" --apply 2>&1)"
echo "$outT2" | grep -q "REAP.*$wtT" \
  && ok "t8 with the window widened, the SAME tree is REAP-able (age was the deciding input)" \
  || bad "t8 still kept with an unbounded window — the guard blocks unconditionally"
[ -d "$wtT" ] && bad "t9 ON DISK: not removed even with an unbounded window (reaper inert)" \
               || ok "t9 ON DISK: removed once the ref freshness was in-window"
# (u) SECOND EVIDENCE SOURCE: the same guard must hold when the ONLY surviving sync artefact is
# packed-refs (the (t) fixture aged loose refs + reflogs). A probe that reads one artefact and
# ignores another silently reverts to "no evidence found => looks fine".
# NOTE the fixture is COMMITTED and pushed, deliberately: an uncommitted file would be held by
# the dirty guard instead, and this block would prove nothing about freshness (it did, at first).
rootU="$(mktmp)"; repoU="$(mk_repo)"; fleetU="$(mk_fleet "$rootU")"
wtU="$rootU/repo-fleet-PACKED1"
git -C "$repoU" worktree add -q "$wtU" -b feat/packed1 master >/dev/null 2>&1
printf 'irreplaceable\n' > "$wtU/precious.txt"
git -C "$wtU" add precious.txt >/dev/null 2>&1
git -C "$wtU" commit -q -m packed-work >/dev/null 2>&1
git -C "$wtU" push -q origin HEAD:refs/heads/feat-packed1 >/dev/null 2>&1
gcU="$(cd "$repoU" && cd "$(git -C "$repoU" rev-parse --git-common-dir)" && pwd -P)"
git -C "$repoU" pack-refs --all >/dev/null 2>&1     # ref CONTENT survives in packed-refs
rm -rf "$gcU/logs/refs/remotes" "$gcU/refs/remotes" "$gcU/FETCH_HEAD"
rm -f "$(git -C "$wtU" rev-parse --git-path FETCH_HEAD 2>/dev/null)"
touch -d '30 days ago' "$gcU/packed-refs" 2>/dev/null
check "u1 fixture is clean (so only the freshness guard can save it)" \
      "$(git -C "$wtU" status --porcelain 2>/dev/null)" ""
check "u2 fixture still reads as fully pushed (via packed-refs)" \
      "$(git -C "$wtU" rev-list --count HEAD --not --remotes 2>/dev/null)" "0"
outU="$(run_reaper "$repoU" "$fleetU" "$rootU/repo-fleet-*" --apply 2>&1)"; rc=$?
check "u3 apply exit 0" "$rc" "0"
echo "$outU" | grep -q "last reconciled with the remote" \
  && ok "u4 packed-refs is honoured as freshness evidence (age reported)" \
  || bad "u4 packed-refs ignored — the probe missed the only artefact present"
[ -d "$wtU" ] && ok "u5 ON DISK: worktree with only-stale packed-refs SURVIVED --apply" \
               || bad "u5 ON DISK: REAPED on the strength of a ref it cannot vouch for"
[ -f "$wtU/precious.txt" ] && ok "u6 ON DISK: its contents intact" \
                            || bad "u6 ON DISK: its contents destroyed"

# cleanup
rm -rf "$root" "$root2" "$root3" "$root4" "$root5" "$root6" "$root7" "$root8" "$root9"
[ "${#TMPDIRS[@]}" -eq 0 ] || rm -rf "${TMPDIRS[@]}"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL BRANCH-REAPER TESTS PASS"
