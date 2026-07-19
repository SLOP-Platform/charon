#!/usr/bin/env bash
# leak-guard-salvage.test.sh — FAIL-ON-REVERT tests for LEAK-GUARD-VACUITY (FIX 3).
#
# THE BUG (2026-07-18): leak_worktree_setup ran
#     git -C "$charon" branch -D "$branch" 2>/dev/null || true
#     git -C "$charon" worktree add "$wt" -b "$branch" "$base_ref"
# UNCONDITIONALLY. Its only guard was "a state/needs-push/<id> marker exists" — and
# state/needs-push/ is EMPTY (verified in-tree: `ls fleet/state/needs-push/` returns nothing but
# . and ..), so the guard was VACUOUS for EVERY branch and the delete always ran. It orphaned
# reviewed commit 32254b3, and `branch -D` also erases .git/logs/refs/heads/<branch>, destroying
# the ATTRIBUTION (why that rewrite initially looked actorless).
#
# THE RULE: commits on the branch are the ground truth, not a bookkeeping marker. If
# `rev-list --count <base>..<branch>` > 0 -> salvage-tag it and REFUSE (rc 3). Archive the reflog
# before ANY deletion. Prefer -d over -D.
#
# NON-FIXTURE: sources the REAL fleet/leak-guard.sh and drives leak_worktree_setup against REAL
# git objects in a real repo with real worktrees.
#
# ── FAIL-ON-REVERT ──────────────────────────────────────────────────────────────────────────
#   S1 — leak-guard.sh: delete the whole `if [ "${ahead:-0}" -gt 0 ]` block in
#        leak_worktree_setup (restore the unconditional delete). RED: assertions 1, 2, 3.
#   S2 — leak-guard.sh: delete the `_lg_archive_reflog "$charon" "$branch" || true` line that
#        precedes the branch delete.                              RED: assertion 5.
#   S3 — leak-guard.sh: make _lg_unlanded_count always `echo 0`.  RED: assertions 1, 2, 3.
#   S4 — leak-guard.sh: in _lg_unlanded_count, restore the fail-open tails
#        `... 2>/dev/null || echo 0` on BOTH the rev-parse base check and the rev-list.
#                                                              RED: assertions 7, 8, 9, 10.
#   S5 — leak-guard.sh: in leak_worktree_setup restore `if [ "${ahead:-0}" -gt 0 ] 2>/dev/null`
#        in place of the ahead_rc / non-numeric test.          RED: assertions 7, 8, 9, 11.
#        (NOT 10 — that one drives the helper directly in its own repo and is independent.)
#   S6 — leak-guard.sh: in safe_worktree_remove restore the single line
#        `git -C "$charon" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"`.
#                                                              RED: assertions 12, 14, 15.
set -uo pipefail
FLEET_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
ok(){ printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
export FLEET="$D/fleetstate"; mkdir -p "$FLEET/state"
# shellcheck source=/dev/null
source "$FLEET_SRC/leak-guard.sh"

# ── VACUITY OF THE OLD GUARD, asserted in the shipped tree ──────────────────────────────────
# The only pre-fix guard keys on a live needs-push marker. If that directory is empty, the guard
# could never fire for any branch. (Informational assertion — it documents WHY the fix is needed.)
np_count="$(find "$FLEET_SRC/state/needs-push" -maxdepth 1 -type f 2>/dev/null | wc -l)"
if [ "$np_count" -eq 0 ]; then
  ok "0 confirmed: fleet/state/needs-push/ is EMPTY -> the pre-fix marker guard was VACUOUS for every branch"
else
  ok "0 fleet/state/needs-push/ now has $np_count marker(s) (guard non-vacuous for those ids only)"
fi

# ── a REAL repo with a branch carrying UNLANDED work ─────────────────────────────────────────
R="$D/repo"; git init -q -b master "$R"
git -C "$R" config user.email t@t; git -C "$R" config user.name t
echo base > "$R/f"; git -C "$R" add f; git -C "$R" commit -qm base
git -C "$R" update-ref refs/remotes/origin/master master
git -C "$R" checkout -q -b work/unlanded
echo reviewed > "$R/f"; git -C "$R" commit -qam "reviewed work that must not be orphaned"
UNLANDED_SHA="$(git -C "$R" rev-parse HEAD)"
git -C "$R" checkout -q master

rc=0; leak_worktree_setup "$R" "$D/wt1" "work/unlanded" "" "origin/master" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 3 ] \
  && ok "1 leak_worktree_setup REFUSES (rc=3) a branch with unlanded commits" \
  || bad "1 leak_worktree_setup returned rc=$rc (want 3) for a branch with unlanded commits"

# NOTE: mere existence of the ref is NOT enough — the pre-fix path deletes the branch and then
# `worktree add -b` RECREATES the same name at base, so an existence check passes while the work
# is orphaned. Assert the ref still points AT THE UNLANDED COMMIT.
now_sha="$(git -C "$R" rev-parse --verify --quiet refs/heads/work/unlanded 2>/dev/null)"
if [ "$now_sha" = "$UNLANDED_SHA" ]; then
  ok "2 the branch still points at the unlanded commit (the work was not destroyed)"
else
  bad "2 branch now ${now_sha:-<deleted>} not $UNLANDED_SHA — reviewed work orphaned (the 32254b3 bug)"
fi

tag="$(git -C "$R" tag -l 'salvage/work/unlanded-*' | head -1)"
if [ -n "$tag" ] && [ "$(git -C "$R" rev-parse "$tag^{commit}")" = "$UNLANDED_SHA" ]; then
  ok "3 a salvage tag ($tag) points at the unlanded commit"
else
  bad "3 no salvage tag pointing at $UNLANDED_SHA (tags: $(git -C "$R" tag -l | tr '\n' ' '))"
fi

# ── 4/5. a branch with NO unlanded commits: the setup proceeds, and the reflog is archived
# BEFORE the delete so attribution survives.
git -C "$R" branch stale-empty master
rc=0; leak_worktree_setup "$R" "$D/wt2" "stale-empty" "" "origin/master" >/dev/null 2>&1 || rc=$?
if [ "$rc" -eq 0 ] && [ -d "$D/wt2" ]; then
  ok "4 a branch with 0 unlanded commits is still recycled normally (no over-fixing)"
else
  bad "4 leak_worktree_setup rc=$rc for a 0-commit branch (want 0, worktree created)"
fi
if find "$FLEET/state/refloghist" -name 'stale-empty-*.reflog' 2>/dev/null | grep -q .; then
  ok "5 the branch reflog was archived to state/refloghist/ before deletion (attribution preserved)"
else
  bad "5 no reflog archive for 'stale-empty' — branch -D erased attribution unrecorded"
fi

# ── 6. the needs-push marker guard still wins (rc 2, unchanged pre-existing contract) ────────
: > "$D/npmark"
rc=0; leak_worktree_setup "$R" "$D/wt3" "stale-empty" "$D/npmark" "origin/master" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] \
  && ok "6 a live needs-push marker still REFUSES with rc=2 (pre-existing contract intact)" \
  || bad "6 needs-push marker path returned rc=$rc (want 2)"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# BLOCKER-1 — THE FAIL-OPEN THE EXISTING TESTS ABOVE COULD NEVER CATCH.
# Every assertion above hands leak_worktree_setup a REAL, resolvable origin/master (created at
# line ~51 by `update-ref refs/remotes/origin/master`). That is exactly why the fail-open
# survived them: `rev-list --count <unresolvable>..<branch>` FAILS, the old `|| echo 0` turned
# that failure into "0 unlanded commits", the salvage guard was skipped, and control reached
# `branch -d || branch -D || true` — where -d fails on an unmerged branch so -D ALWAYS fires.
# Reproduced live before the fix: a branch holding "PRECIOUS WORK" was deleted with no ref left
# pointing at it. Same mechanism as rig #103 and the 32254b3 orphaning, INSIDE the guard.
# These assertions drive REAL git objects with a BOGUS base — no fixtures, no stubs.
# ══════════════════════════════════════════════════════════════════════════════════════════════
mk_precious(){   # <repo-dir> -> echoes the sha of a commit that must survive
  local r="$1"
  git init -q -b master "$r"
  git -C "$r" config user.email t@t; git -C "$r" config user.name t
  echo base > "$r/f"; git -C "$r" add f; git -C "$r" commit -qm base
  git -C "$r" checkout -q -b work/precious
  echo precious > "$r/f"; git -C "$r" commit -qam "PRECIOUS WORK"
  git -C "$r" rev-parse HEAD
  git -C "$r" checkout -q master
}

# ── 7/8/9. an UNRESOLVABLE base ref (no origin/* at all — offline, or no `origin` remote, or a
# main-based repo hitting the origin/master default). The count is UNKNOWABLE, so the only
# correct behaviour is REFUSE — never "0, safe to delete".
RB="$D/repo-bogus"; PRECIOUS="$(mk_precious "$RB")"
rc=0; leak_worktree_setup "$RB" "$D/wtb" "work/precious" "" "origin/does-not-exist" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 3 ]   && ok "7 an UNRESOLVABLE base ref REFUSES with rc=3 (not a fail-open 0-count delete)"   || bad "7 leak_worktree_setup rc=$rc (want 3) with an unresolvable base — this is the #103 fail-open"

# The decisive one. Existence of the ref is NOT enough: the pre-fix path deletes the branch and
# `worktree add -b` recreates the SAME NAME at base, so a naive existence check passes while the
# work is orphaned. Assert the ref still resolves to the PRECIOUS COMMIT ITSELF.
now="$(git -C "$RB" rev-parse --verify --quiet refs/heads/work/precious 2>/dev/null)"
[ "$now" = "$PRECIOUS" ]   && ok "8 the branch still points at the PRECIOUS commit (not deleted, not recreated at base)"   || bad "8 branch is ${now:-<deleted>} not $PRECIOUS — work orphaned by the unresolvable-base fail-open"

# Reachable forever even if a later run does delete the branch.
tag7="$(git -C "$RB" tag -l 'salvage/work/precious-*' | head -1)"
if [ -n "$tag7" ] && [ "$(git -C "$RB" rev-parse "$tag7^{commit}" 2>/dev/null)" = "$PRECIOUS" ]; then
  ok "9 the unresolvable-base refusal still salvage-tagged the commit ($tag7)"
else
  bad "9 no salvage tag pointing at $PRECIOUS (tags: $(git -C "$RB" tag -l | tr '\n' ' '))"
fi

# ── 10. the helper's CONTRACT: on an unresolvable base it must NOT print a number. A numeric
# answer here is what the caller's `-gt 0` test consumes; a wrong number is a silent delete.
# INDEPENDENT REPO on purpose. Reusing $RB made this assertion cascade: under the S5 revert the
# branch above is already DELETED, so the helper takes its legitimate "branch does not exist -> 0"
# path and this went RED for the WRONG reason (a knock-on of assertion 8, not its own detection).
RH="$D/repo-helper"; mk_precious "$RH" >/dev/null
out10="$(_lg_unlanded_count "$RH" "work/precious" "origin/does-not-exist")"; rc10=$?
if [ "$rc10" -ne 0 ] && [ "$out10" != "0" ]; then
  ok "10 _lg_unlanded_count fails closed on an unresolvable base (rc=$rc10, out='$out10', not '0')"
else
  bad "10 _lg_unlanded_count returned rc=$rc10 out='$out10' — a fail-open 0 count"
fi

# ── 11. NON-NUMERIC COUNT. The old caller test `[ "${ahead:-0}" -gt 0 ] 2>/dev/null` returns 2 on
# a non-numeric value, which bash reads as FALSE — falling straight through to the delete. Drive
# the REAL leak_worktree_setup with a helper that yields garbage and assert it REFUSES.
RN="$D/repo-nonnum"; PRECIOUS_N="$(mk_precious "$RN")"
git -C "$RN" update-ref refs/remotes/origin/master master   # base IS resolvable here
_lg_orig_count="$(declare -f _lg_unlanded_count)"
_lg_unlanded_count(){ echo "not-a-number"; return 0; }      # rc 0 + garbage: the nastiest case
rc=0; leak_worktree_setup "$RN" "$D/wtn" "work/precious" "" "origin/master" >/dev/null 2>&1 || rc=$?
now_n="$(git -C "$RN" rev-parse --verify --quiet refs/heads/work/precious 2>/dev/null)"
eval "$_lg_orig_count"                                      # restore the real helper
if [ "$rc" -eq 3 ] && [ "$now_n" = "$PRECIOUS_N" ]; then
  ok "11 a NON-NUMERIC count REFUSES (rc=3) and the branch is untouched"
else
  bad "11 non-numeric count gave rc=$rc, branch=${now_n:-<deleted>} (want rc 3, branch $PRECIOUS_N)"
fi

# ══════════════════════════════════════════════════════════════════════════════════════════════
# MED-2 — safe_worktree_remove must not `rm -rf` a path that is not a registered worktree.
# Before W0 no rig ticket reached this (the path was hardcoded to the product checkout); now
# every `repo: charon-private` ticket does, against /home/stack/charon-private-wt/<id>.
# ══════════════════════════════════════════════════════════════════════════════════════════════
RW="$D/repo-wt"; git init -q -b master "$RW"
git -C "$RW" config user.email t@t; git -C "$RW" config user.name t
echo a > "$RW/f"; git -C "$RW" add f; git -C "$RW" commit -qm base
git -C "$RW" update-ref refs/remotes/origin/master master
npd="$D/np-empty"; mkdir -p "$npd"

# ── 12. an UNREGISTERED directory (not a worktree of $RW) holding a real file: must survive.
STRAY="$D/stray-not-a-worktree"; mkdir -p "$STRAY"; echo "DO NOT DELETE ME" > "$STRAY/keep"
rc=0; safe_worktree_remove "$RW" "$STRAY" "someid" "$npd" >/dev/null 2>&1 || rc=$?
if [ -f "$STRAY/keep" ]; then
  ok "12 an UNREGISTERED path is NOT rm -rf'd by safe_worktree_remove (rc=$rc, contents intact)"
else
  bad "12 safe_worktree_remove DELETED unregistered $STRAY — newly-reachable rm -rf on any path"
fi

# ── 13. no over-fixing: a genuinely registered, clean worktree is still removed.
git -C "$RW" worktree add -q "$D/wt-real" -b tmp/real master 2>/dev/null
rc=0; safe_worktree_remove "$RW" "$D/wt-real" "someid" "$npd" >/dev/null 2>&1 || rc=$?
if [ "$rc" -eq 0 ] && [ ! -e "$D/wt-real" ]; then
  ok "13 a registered clean worktree is still removed normally (no over-fixing)"
else
  bad "13 registered worktree removal rc=$rc, still present=$([ -e "$D/wt-real" ] && echo yes || echo no)"
fi

# ── 14. the LIVE checkout itself is never a legal removal target, whatever else is true.
rc=0; safe_worktree_remove "$RW" "$RW" "someid" "$npd" >/dev/null 2>&1 || rc=$?
if [ "$rc" -ne 0 ] && [ -f "$RW/f" ]; then
  ok "14 the repo's own LIVE checkout is REFUSED as a removal target (rc=$rc, intact)"
else
  bad "14 safe_worktree_remove accepted the LIVE checkout $RW (rc=$rc)"
fi

# ── 15. a registered worktree holding UNCOMMITTED work is refused (worktree remove --force would
# have destroyed it just as thoroughly as rm -rf).
git -C "$RW" worktree add -q "$D/wt-dirty" -b tmp/dirty master 2>/dev/null
echo "unsaved work" > "$D/wt-dirty/scratch"; git -C "$D/wt-dirty" add scratch
rc=0; safe_worktree_remove "$RW" "$D/wt-dirty" "someid" "$npd" >/dev/null 2>&1 || rc=$?
if [ "$rc" -ne 0 ] && [ -f "$D/wt-dirty/scratch" ]; then
  ok "15 a worktree with uncommitted work is REFUSED, not force-removed (rc=$rc)"
else
  bad "15 uncommitted work in $D/wt-dirty was destroyed (rc=$rc)"
fi

# ════════════════════════════════════════════════════════════════════════════════════════════
# REVIEW #2 — the CANONICAL ALLOW-ROUTE (HIGH-1/HIGH-2/HIGH-3).
#
# HIGH-3 was that assertions 12-15 above all exercise REFUSAL paths, so the one NET-NEW hole in
# the delta — the `|| _lg_wt_canonical "$charon" "$wt" "$id"` clause that AUTHORIZES `rm -rf` —
# had ZERO coverage: deleting that clause outright left this suite at 15/15 green. Nothing
# pinned that the route succeeds for a legitimate target, and nothing pinned that it is BOUNDED.
#
# Each assertion below builds its OWN temp repo (mkrepo) so a RED here is never a cascade from a
# sibling's leftover state — assertion 10 above already had to be split out for that reason.
#
# ── FAIL-ON-REVERT (all VERIFIED by actually performing the revert) ─────────────────────────
#   S7  — leak-guard.sh: delete `|| _lg_wt_canonical "$charon" "$wt" "$id"` from the
#         `if _lg_wt_registered ...` line in safe_worktree_remove.        RED: assertion 16.
#   S8  — repo-registry.sh: delete the `if [ -n "$id" ] && ! repo_valid_id "$id"` block from
#         repo_resolve AND the `repo_valid_id "$id" || return 1` pair from _lg_wt_canonical.
#                                                                        RED: assertions 18, 19.
#   S9  — leak-guard.sh: in _lg_wt_catastrophic/_lg_wt_target_ok, restore the equality-only test
#         (`[ "$real" = "$repo_real" ]`) in place of _lg_path_contains + _lg_protected_paths.
#                                                                        RED: assertions 20, 21.
#   S10 — repo-registry.sh: restore `repo_is_public(){ case "${1:-}" in ...` (drop the
#         repo_default_key defaulting).                                   RED: assertion 22.
mkrepo(){ # mkrepo <dir> — an independent real repo with one commit on master
  local r="$1"; git init -q -b master "$r"
  git -C "$r" config user.email t@t; git -C "$r" config user.name t
  echo base > "$r/f"; git -C "$r" add f; git -C "$r" commit -qm base
  git -C "$r" update-ref refs/remotes/origin/master master
}
# stub_registry <repo> <family> — a repo_resolve/repo_known_keys pair with the SAME contract as
# fleet/repo-registry.sh but pointing at temp paths, so the canonical route can be driven against
# real git objects. It delegates the id check to the REAL repo_valid_id (sourced below), so these
# assertions pin the real validator, not a reimplementation of it.
source "$FLEET_SRC/repo-registry.sh"
REAL_VALID_ID=repo_valid_id
stub_registry(){
  local sr="$1" sf="$2"
  eval "repo_known_keys(){ echo tkey; }
        repo_resolve(){ local k=\"\${1:-tkey}\" id=\"\${2:-}\"
          [ \"\$k\" = tkey ] || return 1
          if [ -n \"\$id\" ] && ! $REAL_VALID_ID \"\$id\"; then return 2; fi
          RR_KEY=tkey; RR_PATH='$sr'; RR_WT='$sf'/\"\$id\"; RR_BASE=master; RR_GATE=true
          [ -n \"\$id\" ] || RR_WT=''
          return 0; }"
}

# ── 16. THE SUCCESS PATH (this is the assertion whose absence made the route invisible).
# A worktree git has ALREADY PRUNED leaves an inert directory at the canonical RR_WT path: not
# "registered" any more, but unambiguously this ticket's to sweep. That case is WHY the route
# exists (retire-done-repo-aware assertion 1 depends on it), so it must actually authorize.
( D16="$(mktemp -d)"; trap 'rm -rf "$D16"' EXIT
  R16="$D16/repo"; FAM16="$D16/fam"; mkrepo "$R16"; mkdir -p "$FAM16"
  stub_registry "$R16" "$FAM16"
  git -C "$R16" worktree add -q "$FAM16/TICKET-16" -b tmp/t16 master 2>/dev/null
  rm -rf "$R16/.git/worktrees"                     # simulate a prune: dir stays, registration gone
  npd16="$D16/np"; mkdir -p "$npd16"
  rc=0; safe_worktree_remove "$R16" "$FAM16/TICKET-16" "TICKET-16" "$npd16" >/dev/null 2>&1 || rc=$?
  [ "$rc" -eq 0 ] && [ ! -e "$FAM16/TICKET-16" ] ) \
  && ok "16 the canonical route AUTHORIZES sweeping an already-pruned worktree at the exact RR_WT" \
  || bad "16 the canonical allow-route did NOT sweep a legitimate pruned worktree (route is dead/unpinned)"

# ── 17. …and it is BOUNDED: a sibling in the SAME family that is not this id's RR_WT is refused.
( D17="$(mktemp -d)"; trap 'rm -rf "$D17"' EXIT
  R17="$D17/repo"; FAM17="$D17/fam"; mkrepo "$R17"; mkdir -p "$FAM17/OTHER-TICKET"
  echo "SOMEONE ELSE'S WORK" > "$FAM17/OTHER-TICKET/keep"
  stub_registry "$R17" "$FAM17"
  npd17="$D17/np"; mkdir -p "$npd17"
  safe_worktree_remove "$R17" "$FAM17/OTHER-TICKET" "TICKET-17" "$npd17" >/dev/null 2>&1
  [ -f "$FAM17/OTHER-TICKET/keep" ] ) \
  && ok "17 the canonical route authorizes ONLY this id's exact RR_WT, not a sibling in the family" \
  || bad "17 the canonical route swept a DIFFERENT ticket's directory — the route is unbounded"

# ── 18. HIGH-1: the traversal ids that reached `rm -rf /home/stack` are ALL refused by the route.
# Driven against the REAL registry (read-only — _lg_wt_canonical only compares strings), which is
# the exact pre-fix repro: _lg_wt_canonical /home/stack/charon-private /home/stack ".." -> AUTHORIZED.
bad18=""
for badid in ".." "../.." "" "a/b" "." "*" "a b" 'x$(rm -rf /)' "..%2f" $'a\nb'; do
  if _lg_wt_canonical /home/stack/charon-private /home/stack "$badid" 2>/dev/null; then
    bad18="$bad18 '$badid'"
  fi
done
[ -z "$bad18" ] \
  && ok "18 _lg_wt_canonical REFUSES every traversal/glob/space/empty id (the rm -rf /home/stack route)" \
  || bad "18 _lg_wt_canonical still AUTHORIZES unsafe id(s):$bad18 — unbounded destruction reachable"

# ── 19. HIGH-1 at the SSOT: repo_resolve itself refuses the unsafe id, so EVERY consumer inherits
# the check — not just leak-guard. rc 2 (not 1) so an unsafe id is distinguishable from a bad key.
bad19=""
for badid in ".." "../.." "a/b" "." "*" "a b"; do
  ( repo_resolve charon-private "$badid" >/dev/null 2>&1 ) && bad19="$bad19 '$badid'"
done
rc19=0; ( repo_resolve charon-private ".." >/dev/null 2>&1 ) || rc19=$?
if [ -z "$bad19" ] && [ "$rc19" -eq 2 ]; then
  ok "19 repo_resolve REFUSES an unsafe id at the SSOT (rc=$rc19) — every consumer inherits it"
else
  bad "19 repo_resolve accepted unsafe id(s):$bad19 (rc for '..' = $rc19, want 2)"
fi

# ── 19b. …and refuses NO legitimate id: every real ticket id on the board must still resolve.
n19=0; bad19b=""
while IFS= read -r bid; do
  [ -n "$bid" ] || continue
  n19=$((n19+1))
  repo_valid_id "$bid" || bad19b="$bad19b '$bid'"
done < <(ls "$FLEET_SRC/board" "$FLEET_SRC/board/retired" "$FLEET_SRC/board/archive" 2>/dev/null \
         | sed -E 's/\.(md|parked|decomposed)$//;s/\.md$//' | grep -vE '^$|:$|^(archive|briefs|retired)$')
if [ -z "$bad19b" ] && [ "$n19" -gt 0 ]; then
  ok "19b all $n19 real board ticket ids still pass repo_valid_id (no legitimate id rejected)"
else
  bad "19b repo_valid_id REJECTS legitimate board id(s):$bad19b (checked $n19)"
fi

# ── 20. HIGH-2: a parent of the LIVE tree is refused. Pre-fix this returned OK:
#   _lg_wt_target_ok /home/stack/code/charon /home/stack/code  -> OK
# Read-only: _lg_wt_target_ok only inspects and prints; nothing is removed against a real path.
( D20="$(mktemp -d)"; trap 'rm -rf "$D20"' EXIT
  R20="$D20/deep/nest/repo"; mkdir -p "$(dirname "$R20")"; mkrepo "$R20"
  ! _lg_wt_target_ok "$R20" "$D20/deep/nest" >/dev/null 2>&1 \
  && ! _lg_wt_target_ok "$R20" "$D20/deep"    >/dev/null 2>&1 \
  && ! _lg_wt_target_ok "$R20" "$D20"         >/dev/null 2>&1 ) \
  && ok "20 every ANCESTOR of the live checkout is REFUSED as a removal target (not just equality)" \
  || bad "20 a directory CONTAINING the live checkout was accepted — rm -rf of the parent reachable"

# ── 21. HIGH-2: $HOME and the worktree-family roots are refused outright. Read-only check
# against the REAL paths — asserted via the guard's own verdict, never by attempting a removal.
bad21=""
for prot in "$HOME" /home/stack/charon-private-wt /home/stack/code; do
  _lg_wt_target_ok /home/stack/code/charon "$prot" >/dev/null 2>&1 && bad21="$bad21 '$prot'"
done
[ -z "$bad21" ] \
  && ok "21 \$HOME, the worktree-family root and the repo parent are all REFUSED removal targets" \
  || bad "21 catastrophic target(s) still accepted:$bad21"

# ── 21b. the inline recycle guard in leak_worktree_setup has the SAME protection (it also ends in
# `rm -rf "$wt"`). Reverting only _lg_wt_target_ok must not leave this second site open.
( D21="$(mktemp -d)"; trap 'rm -rf "$D21"' EXIT
  R21="$D21/deep/repo"; mkdir -p "$(dirname "$R21")"; mkrepo "$R21"
  echo "MUST SURVIVE" > "$D21/deep/canary"
  rc=0; leak_worktree_setup "$R21" "$D21/deep" "tmp/t21" "" "origin/master" >/dev/null 2>&1 || rc=$?
  [ "$rc" -ne 0 ] && [ -f "$D21/deep/canary" ] && [ -d "$R21/.git" ] ) \
  && ok "21b leak_worktree_setup's inline recycle guard also REFUSES a parent of the live checkout" \
  || bad "21b the inline recycle guard destroyed/accepted a directory containing the live checkout"

# ── 22. MED-4: the DEFAULT key must land on the PUBLIC side. repo_resolve maps "" -> charon (the
# public product), so repo_is_public "" answering "not public" would stamp the rig's
# `frontier-<pid> <...@fleet.local>` taxonomy onto a PUBLIC commit. keystone stays non-public.
if repo_is_public "" && repo_is_public charon && ! repo_is_public keystone; then
  pubname="$( . "$FLEET_SRC/droid-identity.sh"; droid_identity_for_repo "" "frontier-25379" >/dev/null
              printf '%s' "$GIT_COMMITTER_NAME" )"
  case "$pubname" in
    *frontier*|*25379*) bad "22 the empty/default repo key stamped rig taxonomy '$pubname' on a PUBLIC commit" ;;
    "")                 bad "22 droid_identity_for_repo '' produced no committer name" ;;
    *)                  ok  "22 the default/empty repo key is PUBLIC -> neutral stamp '$pubname' (no rig leakage)" ;;
  esac
else
  bad "22 repo_is_public defaults wrong: ''=$(repo_is_public "" && echo pub || echo priv), keystone must stay priv"
fi

echo "leak-guard-salvage: $fails failure(s)"
[ "$fails" -eq 0 ]
