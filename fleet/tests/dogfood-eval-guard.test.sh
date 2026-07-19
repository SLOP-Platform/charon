#!/usr/bin/env bash
# dogfood-eval-guard.test.sh — fail-on-revert coverage for the destruction paths in
# fleet/benchmark/dogfood-eval.sh.
#
# WHY THESE ASSERT ON-DISK STATE AND NEVER ON LOG STRINGS
# ------------------------------------------------------
# A sibling suite on this rig stayed 38/38 green while three separate guards were gutted,
# because every assertion matched a REFUSING/WARNING line that the script printed on its way
# to destroying the target anyway. A guard's only observable contract is what survives on
# disk. So every check below is `[ -e ]`, `git rev-parse`, or a file's byte content — there is
# not one grep of stderr in this file, deliberately. If you add one, it proves nothing.
#
# ISOLATION
# ---------
# Every fixture is a throwaway repo under `mktemp -d`. This suite NEVER points
# DOGFOOD_PRODUCT_REPO, DOGFOOD_WORKTREE_PARENT or DOGFOOD_RESULTS_DIR at a real checkout,
# and charon-run.sh is replaced by a stub, so no model is ever invoked and nothing touches
# the network. Do not "verify" any of this against the live product checkout.
#
# ISOLATION IS TOTAL, INCLUDING WRITES (corrected after adversarial review F6 — the earlier
# version of this comment overstated it). Two paths used to resolve to the REAL tree:
#   * the needs-push marker dir, which run_one derived from $FLEET_DIR — so every needs-push
#     refusal in this file was VACUOUS against the live (empty) state/needs-push. It is now
#     DOGFOOD_NEEDS_PUSH_DIR, pointed at a per-fixture temp dir that tests actually populate.
#   * _lg_archive_reflog's output, which defaults under $FLEET — so running this suite deposited
#     .reflog files in the real fleet/state/refloghist/. FLEET is now exported to a temp dir.
# Consequence: outcomes here no longer depend on live rig state, and the suite writes nothing
# outside $TMPROOT. If you add a fixture, keep it that way.
#
# DOGFOOD_EVAL_SH overrides the script under test — that seam exists so a guard can be
# neutered on a SCRATCHPAD COPY to prove each test goes RED. No neutering ever lands in
# committed code.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# NOT named FLEET: leak-guard.sh reads $FLEET as the reflog-archive root, and this suite sources
# it directly (test 3b). Colliding on that name is what sent archives into the real state dir.
FLEETDIR="$(cd "$HERE/.." && pwd)"
SCRIPT="${DOGFOOD_EVAL_SH:-$FLEETDIR/benchmark/dogfood-eval.sh}"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); printf 'ok   %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1"; }
check(){ if [ "$1" = 0 ]; then ok "$2"; else bad "$2"; fi; }

# ---- fixture constants: these reproduce run_one's path arithmetic exactly -------------
TICKET=GUARDTEST
MODEL=testmodel
STAMP=TESTSTAMP
LABEL="dogfood-${TICKET}-${MODEL}-${STAMP}"
BRANCH="dogfood-eval/${TICKET}/${MODEL}-${STAMP}"

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT
case "$TMPROOT" in /tmp/*|/var/*) ;; *) echo "refusing: mktemp gave a non-temp root: $TMPROOT" >&2; exit 2 ;; esac

# F6: redirect _lg_archive_reflog's default output ($FLEET/state/refloghist) into the throwaway
# root, for BOTH the sourced-in-process case and every `env`-launched subprocess.
export FLEET="$TMPROOT/fleethome"
mkdir -p "$FLEET/state"

# mkfix <name> -> populates FIX_REPO / FIX_WTP / FIX_RESULTS / FIX_WT for a fresh fixture.
# A bare remote + a clone, so `origin/master` really resolves and "not on any remote" is a
# meaningful distinction rather than an artefact of there being no remote at all.
mkfix(){
  local n="$1" d="$TMPROOT/$1"
  mkdir -p "$d"
  git init --quiet --bare "$d/remote.git"
  git init --quiet -b master "$d/repo"
  git -C "$d/repo" config user.email t@t; git -C "$d/repo" config user.name t
  echo base > "$d/repo/README"
  git -C "$d/repo" add README && git -C "$d/repo" commit --quiet -m base
  git -C "$d/repo" remote add origin "$d/remote.git"
  git -C "$d/repo" push --quiet -u origin master
  mkdir -p "$d/wtp" "$d/results" "$d/needs-push"
  FIX_REPO="$d/repo"; FIX_WTP="$d/wtp"; FIX_RESULTS="$d/results"; FIX_NPDIR="$d/needs-push"
  FIX_WT="$FIX_WTP/charon-fleet-$LABEL"
  FIX_BRIEF="$d/brief.md"; echo "do nothing" > "$FIX_BRIEF"
  # Stub charon-run.sh. Touches a marker so a test can tell "the run happened" from "the
  # candidate was blocked before the run", without reading a log line.
  FIX_RAN="$d/RAN"
  FIX_RUN="$d/charon-run.sh"
  cat > "$FIX_RUN" <<STUB
#!/usr/bin/env bash
echo ran > "$FIX_RAN"
exit 0
STUB
  chmod +x "$FIX_RUN"
}

# run_eval [extra env assignments...] — invokes the script under test against the fixture.
run_eval(){
  env \
    DOGFOOD_TEST_MODE=1 DOGFOOD_TS="$STAMP" \
    DOGFOOD_PRODUCT_REPO="${OVERRIDE_REPO:-$FIX_REPO}" \
    DOGFOOD_WORKTREE_PARENT="$FIX_WTP" \
    DOGFOOD_RESULTS_DIR="$FIX_RESULTS" \
    DOGFOOD_NEEDS_PUSH_DIR="$FIX_NPDIR" \
    DOGFOOD_CHARON_RUN="$FIX_RUN" \
    DOGFOOD_GATE_CMD=true \
    DOGFOOD_BASE_REF="${OVERRIDE_BASE:-origin/master}" \
    DOGFOOD_KEEP_WORKTREE="${OVERRIDE_KEEP:-1}" \
    DOGFOOD_LATENCY_BUDGET_S=60 \
    bash "$SCRIPT" "$TICKET" "$FIX_BRIEF" "$MODEL" >/dev/null 2>&1
}

# =====================================================================================
# 1. Pre-existing worktree holding UNCOMMITTED changes must be KEPT, file intact.
#    RED when the stale-worktree removal is reverted to
#    `worktree remove --force ... || rm -rf` — that destroys SENTINEL unconditionally.
# =====================================================================================
t_dirty_worktree_kept(){
  local t=dirty; OVERRIDE_REPO=; OVERRIDE_BASE=; OVERRIDE_KEEP=
  mkfix "$t"
  git -C "$FIX_REPO" worktree add --quiet "$FIX_WT" -b "$BRANCH" master 2>/dev/null
  printf 'PRECIOUS\n' > "$FIX_WT/SENTINEL"
  run_eval
  [ -e "$FIX_WT/SENTINEL" ] && [ "$(cat "$FIX_WT/SENTINEL" 2>/dev/null)" = PRECIOUS ]
  check $? "dirty pre-existing worktree KEPT (SENTINEL still on disk, contents intact)"
  # And the candidate must have been blocked, not run into a tree we refused to prepare.
  [ ! -e "$FIX_RAN" ]
  check $? "dirty pre-existing worktree: candidate BLOCKED (model never invoked)"
}

# =====================================================================================
# 2. A branch whose commits exist on NO remote must not be deleted.
#    RED when `git branch -D "$branch" 2>/dev/null || true` is restored — -D deletes an
#    unmerged branch outright and rev-parse then stops resolving.
# =====================================================================================
t_unpushed_branch_kept(){
  local t=unpushed; OVERRIDE_REPO=; OVERRIDE_BASE=; OVERRIDE_KEEP=
  mkfix "$t"
  git -C "$FIX_REPO" branch "$BRANCH" master
  local scratch="$TMPROOT/$t/scratch"
  git -C "$FIX_REPO" worktree add --quiet "$scratch" "$BRANCH"
  echo unlanded > "$scratch/WORK"
  git -C "$scratch" add WORK && git -C "$scratch" commit --quiet -m "unlanded work"
  local before; before="$(git -C "$FIX_REPO" rev-parse "refs/heads/$BRANCH")"
  git -C "$FIX_REPO" worktree remove --force "$scratch"
  run_eval
  local after; after="$(git -C "$FIX_REPO" rev-parse --verify --quiet "refs/heads/$BRANCH" 2>/dev/null)"
  [ -n "$after" ] && [ "$after" = "$before" ]
  check $? "branch with commits on no remote NOT deleted (rev-parse still resolves, same SHA)"
  # The commit itself must remain reachable even if the ref were touched.
  git -C "$FIX_REPO" cat-file -e "$before^{commit}" 2>/dev/null
  check $? "unlanded commit object still present in the object store"
}

# =====================================================================================
# 3. END-TO-END: pointing a whole run at the LIVE checkout destroys nothing.
#
#    HEADER CORRECTED (adversarial review F1). This test previously claimed to prove that
#    _lg_wt_catastrophic is load-bearing. IT DOES NOT, and stubbing that helper to
#    `return 1` leaves this test GREEN — the live checkout survives here for an unrelated
#    reason: `git worktree remove` refuses a PRIMARY tree, then neither _lg_wt_registered
#    nor _lg_wt_canonical can vouch for the path, so safe_worktree_remove bails at the
#    `rm -rf` fallback (leak-guard.sh:344) no matter what the catastrophic check said.
#    A test whose header asserts fail-on-revert while surviving the revert is worse than
#    no test — it is exactly the "38/38 green while three guards were gutted" pattern.
#    So this now claims only the end-to-end property it really proves: run_one's layered
#    refusals leave a live checkout intact. The catastrophic guard's OWN fail-on-revert
#    coverage is t_catastrophic_isolated below, which does go RED.
# =====================================================================================
t_catastrophic_refused(){
  local t=catastrophic; OVERRIDE_BASE=; OVERRIDE_KEEP=
  mkfix "$t"
  # Clone the fixture repo to EXACTLY the path run_one will target, and declare that clone
  # to be the product checkout. dg_real == dg_repo -> "that is the LIVE checkout".
  git clone --quiet "$TMPROOT/$t/remote.git" "$FIX_WT"
  echo LIVE > "$FIX_WT/LIVE-CHECKOUT-MARKER"
  git -C "$FIX_WT" config user.email t@t; git -C "$FIX_WT" config user.name t
  OVERRIDE_REPO="$FIX_WT"
  run_eval
  OVERRIDE_REPO=
  [ -e "$FIX_WT/LIVE-CHECKOUT-MARKER" ] && [ -e "$FIX_WT/README" ] && [ -d "$FIX_WT/.git" ]
  check $? "end-to-end: a run aimed at the live checkout leaves it intact (marker + .git)"
}

# =====================================================================================
# 3b. THE CATASTROPHIC GUARD, IN ISOLATION — this is the one that goes RED. (review F1)
#
#     leak_worktree_setup's stale-leftover recycle block ends in
#         git worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
#     — an UNCONDITIONAL `rm -rf` with no registered/canonical vouching in front of it,
#     unlike safe_worktree_remove's fallback. _lg_wt_catastrophic is the ONLY thing
#     standing between that line and the target, which is what makes it observable here.
#
#     The branch name is one that does not exist, so _lg_unlanded_count measures 0 and the
#     unlanded-work guard falls straight through: nothing UPSTREAM of the catastrophic
#     check can refuse for an unrelated reason, and the refusal we observe is that check's.
#     Stub _lg_wt_catastrophic to `return 1` and the fixture repo is rm -rf'd -> RED.
# =====================================================================================
t_catastrophic_isolated(){
  local t=catiso
  mkfix "$t"
  local rc=0
  ( source "$FLEETDIR/leak-guard.sh"
    leak_worktree_setup "$FIX_REPO" "$FIX_REPO" "branch-that-does-not-exist" "" "origin/master"
  ) >/dev/null 2>&1 || rc=$?
  [ -e "$FIX_REPO/README" ] && [ "$(cat "$FIX_REPO/README" 2>/dev/null)" = base ] && [ -d "$FIX_REPO/.git" ]
  check $? "catastrophic guard ISOLATED: recycle path did NOT rm -rf the live checkout"
  [ "$rc" -ne 0 ]
  check $? "catastrophic guard ISOLATED: refusal is terminal (non-zero rc, no worktree created)"
}

# =====================================================================================
# 4. UNDETERMINABLE state must resolve to KEEP, never to delete.
#    Base ref is unresolvable, so "how many commits would this delete orphan?" cannot be
#    answered. leak-guard returns UNRESOLVABLE/rc1 and the setup must REFUSE.
#    RED on any fail-open revert (`|| echo 0`, `2>/dev/null | wc -l`, dropping the rc check).
# =====================================================================================
t_undeterminable_kept(){
  local t=unknown; OVERRIDE_REPO=; OVERRIDE_KEEP=
  mkfix "$t"
  git -C "$FIX_REPO" branch "$BRANCH" master
  local scratch="$TMPROOT/$t/scratch"
  git -C "$FIX_REPO" worktree add --quiet "$scratch" "$BRANCH"
  echo work > "$scratch/WORK"
  git -C "$scratch" add WORK && git -C "$scratch" commit --quiet -m work
  local before; before="$(git -C "$FIX_REPO" rev-parse "refs/heads/$BRANCH")"
  git -C "$FIX_REPO" worktree remove --force "$scratch"
  OVERRIDE_BASE=origin/this-ref-does-not-exist
  run_eval
  OVERRIDE_BASE=
  local after; after="$(git -C "$FIX_REPO" rev-parse --verify --quiet "refs/heads/$BRANCH" 2>/dev/null)"
  [ -n "$after" ] && [ "$after" = "$before" ]
  check $? "undeterminable base ref -> branch KEPT (fail-closed, rev-parse unchanged)"
}

# =====================================================================================
# 5. ANTI-OVER-BLOCK: a genuinely clean, fully-pushed, provably-ours worktree IS removed.
#    A guard that keeps everything is as useless as one that keeps nothing. This is the
#    early-ditch case: the model produced no diff, so there is nothing to protect.
#    RED if the removal is replaced by an unconditional keep/no-op.
# =====================================================================================
t_clean_is_removed(){
  local t=clean; OVERRIDE_REPO=; OVERRIDE_BASE=
  mkfix "$t"
  OVERRIDE_KEEP=0
  run_eval
  OVERRIDE_KEEP=
  [ -e "$FIX_RAN" ]
  check $? "clean case: the run actually executed (fixture is exercising the real path)"
  [ ! -e "$FIX_WT" ]
  check $? "clean + fully-pushed worktree IS removed (path gone from disk)"
}

# =====================================================================================
# 6. END-OF-RUN cleanup must not destroy the CANDIDATE'S OWN work.
#    Nothing in dogfood-eval ever commits the model's output — it lives in the worktree as
#    uncommitted changes, and the saved .diff only captures TRACKED files, so an untracked
#    new file had no copy anywhere. `worktree remove --force` deletes it as thoroughly as
#    `rm -rf`. Here the stub writes BOTH a modified tracked file and a new untracked one.
#    RED when the end-of-run removal is reverted to `worktree remove --force ... || true`.
# =====================================================================================
t_candidate_work_not_destroyed(){
  local t=candidatework; OVERRIDE_REPO=; OVERRIDE_BASE=
  mkfix "$t"
  cat > "$FIX_RUN" <<STUB
#!/usr/bin/env bash
echo ran > "$FIX_RAN"
printf 'MODEL EDIT\n' >> "\$1/README"
printf 'BRAND NEW FILE\n' > "\$1/NEW-UNTRACKED.txt"
exit 0
STUB
  chmod +x "$FIX_RUN"
  OVERRIDE_KEEP=0
  run_eval
  OVERRIDE_KEEP=
  [ -e "$FIX_WT/NEW-UNTRACKED.txt" ] && [ "$(cat "$FIX_WT/NEW-UNTRACKED.txt" 2>/dev/null)" = "BRAND NEW FILE" ]
  check $? "end-of-run: candidate's UNTRACKED new file survives cleanup"
  grep -q 'MODEL EDIT' "$FIX_WT/README" 2>/dev/null
  check $? "end-of-run: candidate's uncommitted edit to a tracked file survives cleanup"
}

# =====================================================================================
# 7. (review F3) A worktree that is CLEAN but holds UNPUSHED COMMITS must be KEPT.
#    _lg_wt_target_ok's `rev-list --count HEAD --not --remotes` check had NO fixture: every
#    tree in this file was either dirty or fully pushed, so forcing `unpushed=0` left the
#    suite 10/10 green. The commit's premise — "nothing in this script ever commits the
#    candidate's work" — is an assumption about MODEL BEHAVIOUR, not an invariant: agents
#    driven through `opencode run` do commit unprompted. In that exact case this check is
#    the only thing between committed candidate work and removal.
#    RED when the unpushed count is forced to 0: the tree is removed and the files vanish.
# =====================================================================================
t_clean_but_unpushed_kept(){
  local t=unpushedwt; OVERRIDE_REPO=; OVERRIDE_BASE=; OVERRIDE_KEEP=
  mkfix "$t"
  git -C "$FIX_REPO" worktree add --quiet "$FIX_WT" -b "$BRANCH" master
  printf 'COMMITTED BY THE CANDIDATE\n' > "$FIX_WT/AGENT-WORK"
  git -C "$FIX_WT" add AGENT-WORK && git -C "$FIX_WT" commit --quiet -m "candidate committed unprompted"
  # The tree is now CLEAN (status --porcelain is empty) — only the unpushed-commit probe can
  # refuse. HEAD is one commit past origin/master and on no remote.
  [ -z "$(git -C "$FIX_WT" status --porcelain)" ] || { bad "fixture broken: tree not clean"; return; }
  run_eval
  [ -e "$FIX_WT/AGENT-WORK" ] && [ "$(cat "$FIX_WT/AGENT-WORK" 2>/dev/null)" = "COMMITTED BY THE CANDIDATE" ]
  check $? "clean worktree with UNPUSHED COMMITS kept (committed candidate work still on disk)"
  [ ! -e "$FIX_RAN" ]
  check $? "unpushed-commit worktree: candidate BLOCKED (model never invoked)"
}

# =====================================================================================
# 8. (review F5) The needs-push refusal in safe_worktree_remove must actually fire.
#    Every test above passed the REAL $FLEET_DIR/state/needs-push, which is empty — so
#    `[ -e "$npdir/$id" ]` could never be true and gutting the refusal changed nothing.
#    That is the identical vacuity leak-guard.sh:34-38 records as having orphaned 32254b3.
#    This fixture plants a REAL marker in a temp dir (DOGFOOD_NEEDS_PUSH_DIR).
#    The tree is deliberately CLEAN, fully pushed and a registered worktree of the fixture
#    repo — every other check in _lg_wt_target_ok passes — so the marker is the ONLY thing
#    refusing, and removing the marker check removes the tree. RED.
# =====================================================================================
t_needs_push_marker_kept(){
  local t=needspush; OVERRIDE_REPO=; OVERRIDE_BASE=; OVERRIDE_KEEP=
  mkfix "$t"
  git -C "$FIX_REPO" worktree add --quiet "$FIX_WT" -b "$BRANCH" master
  printf 'UNLANDED\n' > "$FIX_WT/LANDED-NOTHING"
  git -C "$FIX_WT" add LANDED-NOTHING && git -C "$FIX_WT" commit --quiet -m "committed but unlanded"
  git -C "$FIX_WT" push --quiet origin "HEAD:refs/heads/$BRANCH"   # pushed => the unpushed probe CANNOT refuse
  printf 'live marker\n' > "$FIX_NPDIR/$LABEL"
  run_eval
  [ -e "$FIX_WT/LANDED-NOTHING" ]
  check $? "live needs-push marker -> pre-existing worktree KEPT (marker refusal fired)"
  [ ! -e "$FIX_RAN" ]
  check $? "live needs-push marker: candidate BLOCKED (model never invoked)"
}

# =====================================================================================
# 9. (review F2) run_one's INTERPRETATION of leak_worktree_setup's rc.
#    The BLOCKED card / summary row / `return` block this commit added had zero coverage:
#    tests 2 and 4 stay green because leak_worktree_setup itself refuses the delete, so the
#    caller's `if [ "$lws_rc" -ne 0 ]` contributed nothing observable and weakening it to
#    never fire left the suite 10/10 green.
#    Here NO worktree pre-exists, so safe_worktree_remove is skipped entirely and
#    leak_worktree_setup's own rc 2 (needs-push marker) is the only signal. If the caller
#    ignores it, run_one falls through to `cp`-ing the brief into a directory that was never
#    created and LAUNCHES THE CANDIDATE anyway. RED on $FIX_RAN.
# =====================================================================================
t_setup_rc_blocks_candidate(){
  local t=lwsrc; OVERRIDE_REPO=; OVERRIDE_BASE=; OVERRIDE_KEEP=
  mkfix "$t"
  [ -e "$FIX_WT" ] && { bad "fixture broken: worktree must not pre-exist"; return; }
  printf 'live marker\n' > "$FIX_NPDIR/$LABEL"
  run_eval
  [ ! -e "$FIX_RAN" ]
  check $? "leak_worktree_setup rc!=0 -> candidate BLOCKED (model never invoked)"
  [ ! -e "$FIX_WT" ]
  check $? "leak_worktree_setup rc!=0 -> no worktree materialised"
  grep -rlq 'BLOCKED' "$FIX_RESULTS" 2>/dev/null
  check $? "leak_worktree_setup rc!=0 -> a BLOCKED result card was written to disk"
}

# =====================================================================================
# 10. (review F4) The end-of-run brief cleanup must not delete CANDIDATE WORK.
#     `rm -f "$wt/DOGFOOD-TICKET-BRIEF.md"` deleted by NAME with no content check. That file
#     is UNTRACKED, so $diff_file (`git diff`, tracked only) holds no copy — a model that
#     wrote its plan, notes or answer into the brief it was handed lost them silently, which
#     is the exact failure class this commit exists to close. The removal is now gated on
#     `cmp -s` against the pristine copy the script planted.
#     RED when the removal goes back to unconditional: the answer is gone AND the tree then
#     reads as clean, so the worktree is removed too.
# =====================================================================================
t_modified_brief_preserved(){
  local t=briefedit; OVERRIDE_REPO=; OVERRIDE_BASE=
  mkfix "$t"
  cat > "$FIX_RUN" <<STUB
#!/usr/bin/env bash
echo ran > "$FIX_RAN"
printf 'CANDIDATE ANSWER LINE\n' >> "\$1/DOGFOOD-TICKET-BRIEF.md"
exit 0
STUB
  chmod +x "$FIX_RUN"
  OVERRIDE_KEEP=0
  run_eval
  OVERRIDE_KEEP=
  [ -e "$FIX_WT/DOGFOOD-TICKET-BRIEF.md" ] \
    && grep -q 'CANDIDATE ANSWER LINE' "$FIX_WT/DOGFOOD-TICKET-BRIEF.md" 2>/dev/null
  check $? "brief the candidate WROTE INTO is preserved (removal is by content, not by name)"
  [ -e "$FIX_WT" ]
  check $? "...and the worktree holding that work is kept (dirty guard refuses removal)"
}

t_dirty_worktree_kept
t_unpushed_branch_kept
t_catastrophic_refused
t_catastrophic_isolated
t_undeterminable_kept
t_clean_is_removed
t_candidate_work_not_destroyed
t_clean_but_unpushed_kept
t_needs_push_marker_kept
t_setup_rc_blocks_candidate
t_modified_brief_preserved

printf '\ndogfood-eval-guard: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
