#!/usr/bin/env bash
# release-preserves-work.test.sh — FAIL-ON-REVERT self-test for fleet/release.sh.
#
# THE DEFECT (2026-08-01): release.sh dropped a claim UNCONDITIONALLY. A droid that
# committed work and then hit a blocker ran release.sh per the brief; the commits
# stayed on an unpushed branch, the ticket returned to READY, and ANOTHER droid
# claimed and REDID the work (observed: 3 tabs on one ticket, 4 tickets finished
# with green gates, none pushed). release.sh never learned about the existing
# state/needs-push mechanism.
#
# THE FIX: before dropping a claim, release.sh checks the ticket's branch/worktree
# for unlanded commits or a dirty tree. If any exist it KEEPS the claim, writes
# state/needs-push/<id>, and prints the recovery command. Unresolvable branch/
# worktree FAILS SAFE (refuse). Nothing to lose -> release as before.
#
# GUARD PROPERTIES (each revert -> RED):
#   (a) >=1 unlanded commit  -> claim RETAINED, needs-push written, recovery printed.
#   (b) DIRTY worktree, no commits -> claim RETAINED too (uncommitted work is work).
#   (c) genuinely nothing to lose -> claim dropped exactly as before (anti-over-block).
#   (d) unresolvable branch/worktree -> fail SAFE, refuse to release, say why.
#   (e) a ticket left in needs-push (claim retained) is NOT re-offered by claim.sh —
#       the assertion that closes the duplicate-work loop.
#
# Hermetic: isolated git fixture repos + temp fleet state. Never touches the live
# fleet/state or any real repo. Models fleet/tests/reconcile-stale-claims.test.sh.
#
# Run:  bash fleet/tests/release-preserves-work.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
has(){ printf '%s' "$1" | grep -qF -- "$2" && ok "$3" || bad "$3 (missing: $2)"; }
no(){  printf '%s' "$1" | grep -qF -- "$2" && bad "$3 (unexpected: $2)" || ok "$3"; }

TMPDIRS=()
mktmp(){ local d; d="$(mktemp -d)"; TMPDIRS+=("$d"); echo "$d"; }
trap 'for d in "${TMPDIRS[@]:-}"; do rm -rf "$d"; done' EXIT

# ── isolated product repo with origin/master ────────────────────────────────
mk_repo(){
  local root; root="$(mktmp)"
  git init -q --bare "$root/origin.git"
  git init -q "$root/repo"
  ( cd "$root/repo"
    git checkout -q -b master
    printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
    git remote add origin "$root/origin.git"
    git push -q origin master
  ) >/dev/null 2>&1
  echo "$root/repo"
}

# ── fixture fleet: ONLY release.sh + empty board/state (self-contained) ─────
mk_fleet(){
  local d; d="$(mktmp)"
  cp "$SRC/release.sh" "$d/"
  mkdir -p "$d/board" "$d/state/claims" "$d/state/submitted" "$d/state/done" \
           "$d/state/loop-guard"
  echo "$d"
}

add_ticket(){ local d="$1" id="$2" branch="$3"; printf 'tier: strong\nrepo: charon\nbranch: %s\n' "$branch" > "$d/board/$id.md"; }

# run_release <fleet> <id> [env-kv...] — runs the real release.sh against the
# fixture with env overrides so it NEVER touches a real repo.
run_release(){
  local d="$1" id="$2"; shift 2
  env "$@" bash "$d/release.sh" "$id"
}

echo "═══ release-preserves-work.test.sh ═══"
echo "== (a) ticket with >=1 unlanded commit -> claim RETAINED + needs-push =="
P="$(mk_repo)"
d_a="$(mk_fleet)"
WT_A="$(mktmp)"
( cd "$WT_A"
  git init -q; git checkout -q -b feat/a-unlanded
  git remote add origin "$(dirname "$P")/origin.git"
  printf 'work\n' > work.txt; git add work.txt; git commit -q -m "completed work"
  # NOT pushed: the commit exists only locally -> unlanded.
) >/dev/null 2>&1
add_ticket "$d_a" "A-UNLANDED" "feat/a-unlanded"
printf 'holder\n' > "$d_a/state/claims/A-UNLANDED"
run_a(){ run_release "$d_a" "A-UNLANDED" RELEASE_BRANCH="feat/a-unlanded" RELEASE_REPO="$P" RELEASE_WT="$WT_A"; }
out_a="$(run_a 2>&1)"
rc_a=0; run_a >/dev/null 2>&1 || rc_a=$?
check "a0 refused release exits non-zero" "$rc_a" "3"
has "$out_a" "REFUSING to release A-UNLANDED" "(a1) refusal printed loudly"
has "$out_a" "unlanded commit"                "(a2) reason names the unlanded commits"
has "$out_a" "land-needs-push.sh A-UNLANDED"  "(a3) exact recovery command printed"
[ -e "$d_a/state/claims/A-UNLANDED" ]         && ok "(a4) claim RETAINED"                || bad "(a4) claim RETAINED — release discarded finished work (RED)"
[ -e "$d_a/state/needs-push/A-UNLANDED" ]     && ok "(a5) needs-push marker written"     || bad "(a5) needs-push marker written"
has "$(cat "$d_a/state/needs-push/A-UNLANDED")" "branch=feat/a-unlanded" "(a6) marker carries branch"

rm -rf "$d_a" "$WT_A"

echo "== (b) DIRTY worktree, no commits -> claim RETAINED + needs-push =="
d_b="$(mk_fleet)"
WT_B="$(mktmp)"
( cd "$WT_B"
  git init -q; git checkout -q -b feat/b-dirty
  git remote add origin "$(dirname "$P")/origin.git"
  printf 'base\n' > base.txt; git add base.txt; git commit -q -m base
  git push -q origin feat/b-dirty 2>/dev/null || true
  printf 'uncommitted edit\n' >> base.txt   # NOW dirty, but no commits beyond base
) >/dev/null 2>&1
add_ticket "$d_b" "B-DIRTY" "feat/b-dirty"
printf 'holder\n' > "$d_b/state/claims/B-DIRTY"
out_b="$(run_release "$d_b" "B-DIRTY" RELEASE_BRANCH="feat/b-dirty" RELEASE_REPO="$P" RELEASE_WT="$WT_B" 2>&1)"
has "$out_b" "REFUSING to release B-DIRTY" "(b1) refusal printed loudly"
has "$out_b" "uncommitted changes"          "(b2) reason names the dirty tree"
[ -e "$d_b/state/claims/B-DIRTY" ]          && ok "(b3) claim RETAINED for dirty worktree" || bad "(b3) claim RETAINED for dirty worktree (RED)"
[ -e "$d_b/state/needs-push/B-DIRTY" ]      && ok "(b4) needs-push marker written"         || bad "(b4) needs-push marker written"

rm -rf "$d_b" "$WT_B"

echo "== (c) genuinely nothing to lose -> claim dropped exactly as before =="
# (c1) no branch declared at all -> release as today.
d_c1="$(mk_fleet)"
printf 'tier: strong\nrepo: charon\n' > "$d_c1/board/C-NOBRANCH.md"
printf 'holder\n' > "$d_c1/state/claims/C-NOBRANCH"
out_c1="$(run_release "$d_c1" "C-NOBRANCH" 2>&1)"
has "$out_c1" "released C-NOBRANCH (claim cleared, re-claimable)" "(c1) no-branch ticket released as today"
[ ! -e "$d_c1/state/claims/C-NOBRANCH" ]        && ok "(c2) claim REMOVED"                      || bad "(c2) claim REMOVED"
[ ! -e "$d_c1/state/needs-push/C-NOBRANCH" ]    && ok "(c3) NO needs-push marker (anti-over-block)" || bad "(c3) NO needs-push marker (anti-over-block)"
rm -rf "$d_c1"

# (c2) branch declared but provably absent in a valid repo + no worktree -> release.
d_c2="$(mk_fleet)"
add_ticket "$d_c2" "C-EMPTY" "feat/c-never-started"
printf 'holder\n' > "$d_c2/state/claims/C-EMPTY"
out_c2="$(run_release "$d_c2" "C-EMPTY" RELEASE_REPO="$P" 2>&1)"
has "$out_c2" "released C-EMPTY (claim cleared, re-claimable)" "(c4) branch-absent ticket released as today"
[ ! -e "$d_c2/state/claims/C-EMPTY" ]        && ok "(c5) claim REMOVED"                   || bad "(c5) claim REMOVED"
[ ! -e "$d_c2/state/needs-push/C-EMPTY" ]    && ok "(c6) NO needs-push marker"            || bad "(c6) NO needs-push marker"
rm -rf "$d_c2"

echo "== (d) unresolvable branch/worktree -> fail SAFE, refuse, say why =="
d_d="$(mk_fleet)"
add_ticket "$d_d" "D-UNRESOLVABLE" "feat/d-resolve"
printf 'holder\n' > "$d_d/state/claims/D-UNRESOLVABLE"
out_d="$(run_release "$d_d" "D-UNRESOLVABLE" RELEASE_BRANCH="feat/d-resolve" RELEASE_REPO="/nonexistent/no/repo" RELEASE_WT="/nonexistent/no/wt" 2>&1)"
has "$out_d" "REFUSING to release D-UNRESOLVABLE" "(d1) refused loudly"
has "$out_d" "cannot resolve a git repo"          "(d2) refusal says WHY (fail-safe reason)"
[ -e "$d_d/state/claims/D-UNRESOLVABLE" ]      && ok "(d3) claim RETAINED (fail-safe)"      || bad "(d3) claim RETAINED (fail-safe — RED)"
[ -e "$d_d/state/needs-push/D-UNRESOLVABLE" ]  && ok "(d4) needs-push marker written"       || bad "(d4) needs-push marker written"

rm -rf "$d_d" "$P"

echo "== (e) ticket left in needs-push is NOT re-offered by claim.sh =="
# Uses claim.sh + _lib.sh + loop-guard.sh copied into the fixture (mirrors
# claim-loop-guard.test.sh) so the loop-closure assertion runs the REAL claimer.
d_e="$(mktmp)"
cp "$SRC/release.sh" "$SRC/claim.sh" "$SRC/_lib.sh" "$SRC/loop-guard.sh" "$d_e/"
mkdir -p "$d_e/board" "$d_e/state/claims" "$d_e/state/submitted" "$d_e/state/done" "$d_e/state/loop-guard"
PE="$(mk_repo)"
WTE="$(mktmp)"
( cd "$WTE"
  git init -q; git checkout -q -b feat/e-stranded
  git remote add origin "$(dirname "$PE")/origin.git"
  printf 'work\n' > work.txt; git add work.txt; git commit -q -m "stranded finished work"
) >/dev/null 2>&1
# Stranded ticket + one clean ready ticket so the pool can still feed.
printf 'tier: strong\nrepo: charon\nbranch: feat/e-stranded\n' > "$d_e/board/E-STRANDED.md"
printf 'tier: strong\nrepo: charon\nbranch: feat/e-ready\n'    > "$d_e/board/E-READY.md"
printf 'holder\n' > "$d_e/state/claims/E-STRANDED"

# release refuses (unlanded work) -> claim retained + needs-push written.
out_e="$(env RELEASE_REPO="$PE" RELEASE_WT="$WTE" bash "$d_e/release.sh" E-STRANDED 2>&1)"
has "$out_e" "REFUSING to release E-STRANDED" "(e1) stranded ticket release refused"
[ -e "$d_e/state/claims/E-STRANDED" ]       && ok "(e2) claim retained after refused release" || bad "(e2) claim retained after refused release"
[ -e "$d_e/state/needs-push/E-STRANDED" ]   && ok "(e3) needs-push marker written"            || bad "(e3) needs-push marker written"

# claim.sh must NOT offer the stranded ticket — the claim (kept) closes the loop.
out_c1e="$(bash "$d_e/claim.sh" strong droidX own-only 2>/dev/null || true)"
no "$out_c1e" "E-STRANDED" "(e4) claim.sh does NOT re-offer the stranded ticket"
has "$out_c1e" "CLAIMED E-READY" "(e5) claim.sh feeds the pool with the OTHER ticket instead"

rm -rf "$d_e" "$PE" "$WTE"

echo
echo "════════════════════════════════════════════════"
echo "release-preserves-work.test.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL GREEN"
