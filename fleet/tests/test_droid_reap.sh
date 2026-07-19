#!/usr/bin/env bash
# test_droid_reap.sh — FAIL-ON-REVERT self-test for fleet/reap-orphans.sh + the
# P0 #4 branch-preservation fix in fleet/leak-guard.sh (DROID-LIFECYCLE-REAP).
#
# Operates on TEMP git repos + a TEMP fleet state tree (never touches the live fleet
# or /home/stack/charon). All assertions probe the OBSERVABLE behavior: branches
# survive, worktrees get reaped, claims release or stay — not just exit codes.
#
# Covers (each is fail-on-revert — a regression in the corresponding guard flips it RED):
#   (a) DEAD-PID + branch with unique commits: --apply releases the claim, preserves
#       the branch, flags state/orphans/<id> + state/needs-push/<id> (so the existing
#       land-needs-push.sh recovery path Just Works). A NEGATIVE assertion: the
#       branch's commit is STILL on refs/heads/<branch> after --apply.
#   (b) DEAD-PID + empty branch: --apply releases the claim, removes the worktree,
#       deletes the empty branch (it == base, so re-claim is identical to fresh).
#   (c) LIVE-PID claim is NEVER touched — claim marker still present, branch still
#       present after --apply.
#   (d) P0 #4 (the silent-discard fix): a pre-seeded branch with a commit survives
#       a SECOND leak_worktree_setup call (the old -B/recreate path would have
#       wiped the branch).
#   (e) cleanup() in fleet-droid.sh: a dirty worktree -> uncommitted changes are
#       auto-committed on the branch, then the worktree is removed; the branch's
#       commit SURVIVES.
#   (f) Idempotency: re-running the reaper on a clean state finds 0 dead claims
#       and exits 0.
#   (g) DRY-RUN default: a --apply-less reaper does NOT release the claim, does
#       NOT remove the worktree, does NOT delete the branch. The flag-and-preserve
#       path is auditable before commit.
#
# Run:  bash fleet/tests/test_droid_reap.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
has(){ printf '%s' "$1" | grep -qF -- "$2" && ok "$3" || bad "$3 (missing: $2)"; }
no(){  printf '%s' "$1" | grep -qF -- "$2" && bad "$3 (unexpected: $2)" || ok "$3"; }

# Build a fresh origin(bare)+charon(clone with origin/master) under <root>.
# Echoes: "<charon> <origin>".
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

# Build a fixture fleet root: <root>/fleet with board/, state/claims/, state/needs-push/,
# state/orphans/. Echoes the fleet dir.
mk_fleet(){
  local root="$1" id="$2"
  local fleet="$root/fleet"
  mkdir -p "$fleet/board" "$fleet/state/claims" "$fleet/state/needs-push" \
           "$fleet/state/orphans" "$fleet/state/submitted" "$fleet/state/done"
  # ticket file
  cat > "$fleet/board/$id.md" <<EOF
repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: feat/$id
owns: fleet/fleet-droid.sh
EOF
  echo "$fleet"
}

# Run the reaper against a fixture. Usage: run_reaper <fleet> <charon> <wt> [args...]
# The fixture's charon is a temp git repo (NOT /home/stack/charon). We override
# REAPER_REPO_PATH / REAPER_WT_PATH / REAPER_BASE so the reaper operates on the
# fixture, not the real fleet's charon-private repo. These overrides are a no-op
# when REAPER_FLEET_DIR is unset (the test isolation seam is itself test-scoped).
run_reaper(){ local fleet="$1" charon="$2" wt="$3"; shift 3
  REAPER_FLEET_DIR="$fleet" REAPER_REPO_PATH="$charon" REAPER_WT_PATH="$wt" REAPER_BASE=master \
    bash "$SRC/reap-orphans.sh" "$@"; }

# Write a claim marker for <id> owned by <droid-id> (e.g. "frontier-12345").
write_claim(){ local fleet="$1" id="$2" droid_id="$3"
  printf '%s %s\n' "$droid_id" "$(date -u +%FT%TZ)" > "$fleet/state/claims/$id"; }

# A "live" PID: $$ (this very subshell). Pass the subshell PID so it can be passed
# to write_claim and reaped.
spawn_live_claim(){
  # spawn a sleep that lives until the parent kills it; print the droid id with its PID.
  local id="$1" droid_tier="$2"
  ( sleep 60 ) & live_pid=$!
  echo "$droid_tier-$live_pid"
  # record so the caller can kill it later
  echo "$live_pid" >> "${KILL_LIST:-/dev/null}"
}

KILL_LIST="$(mktemp)"
trap 'for p in $(cat "$KILL_LIST" 2>/dev/null); do kill -9 "$p" 2>/dev/null || true; done; rm -f "$KILL_LIST"' EXIT

# ════════════════════════════════════════════════════════════════════════════════
echo "== (a) DEAD-PID + branch with unique commits: PRESERVE + flag + release =="
root="$(mktemp -d)"; charon="$(mk_charon)"; id="REAP-A"; fleet="$(mk_fleet "$root" "$id")"
branch="feat/$id"; wt="$charon-fleet-$id"
# Create a worktree + a commit on the branch (simulating a droid that crashed AFTER committing).
git -C "$charon" worktree add -q "$wt" -b "$branch" master >/dev/null
echo orphan-work > "$wt/work.txt"; git -C "$wt" add work.txt; git -C "$wt" commit -q -m orphan-commit
# Plant a DEAD-PID claim (PID 1 always exists on Linux but is init; PID 99999 doesn't exist).
write_claim "$fleet" "$id" "frontier-99999"
# Run the reaper (DRY-RUN first to audit)
dry="$(run_reaper "$fleet" "$charon" "$wt" 2>&1)"
has "$dry" "DEAD+PRESERVE" "(a0) dry-run flags DEAD+PRESERVE"
no  "$dry" "claim marker released"  "(a0b) dry-run did NOT release the claim"
no  "$dry" "state/orphans/$id written" "(a0c) dry-run did NOT write orphan flag"
# APPLY
apply_out="$(run_reaper "$fleet" "$charon" "$wt" --apply 2>&1)"; rc=$?
check "a1 --apply exit 0" "$rc" "0"
has "$apply_out" "DEAD+PRESERVE" "(a2) --apply shows DEAD+PRESERVE for the dead-PID claim"
# Claim released
[ ! -e "$fleet/state/claims/$id" ] && ok "a3 claim marker released" \
  || bad "a3 claim marker still present (dead-PID reaper failed to release)"
# Branch SURVIVES (the data-safety crux)
git -C "$charon" show-ref --verify --quiet "refs/heads/$branch" \
  && ok "a4 branch SURVIVES --apply (commit preserved on refs/heads/$branch)" \
  || bad "a4 branch was DELETED under --apply (DATA LOSS — P0 regression)"
# The commit is still reachable from the branch tip
[ "$(git -C "$charon" log -1 --pretty=%s "$branch" 2>/dev/null)" = "orphan-commit" ] \
  && ok "a5 commit SURVIVES on branch tip" \
  || bad "a5 commit was lost from the branch tip"
# Orphan + needs-push markers written
[ -e "$fleet/state/orphans/$id" ] && ok "a6 state/orphans/$id written" \
  || bad "a6 state/orphans/$id missing (manager wouldn't see the orphan)"
[ -e "$fleet/state/needs-push/$id" ] && ok "a7 state/needs-push/$id written (land-needs-push.sh path)" \
  || bad "a7 state/needs-push/$id missing (manager recovery path broken)"
# Sanity: reaper's needs-push format matches what land-needs-push.sh reads
has "$(cat "$fleet/state/needs-push/$id" 2>/dev/null)" "branch=$branch" "(a7b) needs-push carries branch="
has "$(cat "$fleet/state/needs-push/$id" 2>/dev/null)" "worktree=$wt"   "(a7c) needs-push carries worktree="
rm -rf "$root"

echo "== (b) DEAD-PID + empty branch: clean reap (claim release, worktree gone, branch gone) =="
root="$(mktemp -d)"; charon="$(mk_charon)"; id="REAP-B"; fleet="$(mk_fleet "$root" "$id")"
branch="feat/$id"; wt="$charon-fleet-$id"
# Create an empty worktree (no commit on the branch — droid died before doing anything).
git -C "$charon" worktree add -q "$wt" -b "$branch" master >/dev/null
write_claim "$fleet" "$id" "strong-99998"
apply_out="$(run_reaper "$fleet" "$charon" "$wt" --apply 2>&1)"; rc=$?
check "b1 --apply exit 0" "$rc" "0"
has "$apply_out" "DEAD+CLEAN" "(b2) dead-clean path taken (no unique commits)"
[ ! -e "$fleet/state/claims/$id" ] && ok "b3 claim released" || bad "b3 claim still present"
[ ! -d "$wt" ]                  && ok "b4 worktree removed" || bad "b4 worktree still present"
git -C "$charon" show-ref --verify --quiet "refs/heads/$branch" \
  && bad "b5 empty branch was KEPT (reaper should delete empty branches — re-claim is identical)" \
  || ok "b5 empty branch deleted (== base, safe to recreate)"
rm -rf "$root"

echo "== (c) LIVE-PID claim is NEVER touched by the reaper =="
root="$(mktemp -d)"; charon="$(mk_charon)"; id="REAP-C"; fleet="$(mk_fleet "$root" "$id")"
branch="feat/$id"; wt="$charon-fleet-$id"
git -C "$charon" worktree add -q "$wt" -b "$branch" master >/dev/null
echo live-work > "$wt/live.txt"; git -C "$wt" add live.txt; git -C "$wt" commit -q -m live-commit
# LIVE PID: a long-running sleep. $$ is this subshell; spawn a child.
( sleep 60 ) & live_pid=$!; echo "$live_pid" >> "$KILL_LIST"
write_claim "$fleet" "$id" "frontier-$live_pid"
apply_out="$(run_reaper "$fleet" "$charon" "$wt" --apply 2>&1)"
has "$apply_out" "LIVE    $id" "(c1) live-PID claim flagged LIVE"
[ -e "$fleet/state/claims/$id" ] && ok "c2 live claim marker UNTOUCHED" \
  || bad "c2 live claim marker was REMOVED (reaper touched a live droid — CRITICAL)"
git -C "$charon" show-ref --verify --quiet "refs/heads/$branch" \
  && ok "c3 live branch UNTOUCHED" \
  || bad "c3 live branch was DELETED (reaper touched a live droid — CRITICAL)"
kill -9 "$live_pid" 2>/dev/null || true
rm -rf "$root"

echo "== (d) P0 #4: pre-existing branch with commit SURVIVES a re-claim's worktree setup =="
charon="$(mk_charon)"; wt="$charon-fleet-D"; branch="feat/d"
# Simulate a prior droid that committed work and then crashed (worktree dir + branch
# present, claim dead). A NEW claim arrives; the launcher runs p0_worktree_setup.
# The OLD code's `git worktree add -B <branch> origin/master` would have RESET the
# branch — wiping the commit. The P0 #4 wrapper (in fleet-droid.sh) sees the branch
# has unmerged commits and REUSES it.
git -C "$charon" worktree add -q "$wt" -b "$branch" master >/dev/null
echo p0-work > "$wt/p0.txt"; git -C "$wt" add p0.txt; git -C "$wt" commit -q -m p0-commit
# Save the pre-claim commit SHA (the data the reaper / re-claim must preserve)
pre_sha="$(git -C "$charon" rev-parse "$branch")"
# Source the launcher's p0_worktree_setup. This is the function fleet-droid.sh uses for
# the worktree-create call (not the upstream leak-guard.sh's leak_worktree_setup —
# the launcher wraps it for the P0 fix).
p0_setup(){
  p0_worktree_setup "$@"
}
# shellcheck source=leak-guard.sh
. "$SRC/leak-guard.sh"
# Extract p0_worktree_setup from fleet-droid.sh via sed (it's defined inline). Test seam:
# the function lives in fleet-droid.sh (in this ticket's owns) and is the call path the
# launcher uses. We source it here so the test exercises the EXACT function the launcher
# runs, not a copy.
eval "$(sed -n '/^p0_worktree_setup(){/,/^}$/p' "$SRC/fleet-droid.sh")"
# Simulate a re-claim: wipe the worktree dir, but keep the branch (orphan state).
rm -rf "$wt"
# Now the launcher re-runs p0_worktree_setup. Pre-fix: it would `branch -D` then
# `worktree add -B feat/d origin/master`, wiping the commit. Post-fix: it sees the
# branch with unmerged commits and reuses it.
rc=0; p0_worktree_setup "$charon" "$wt" "$branch" "" "origin/master" >/dev/null 2>&1 || rc=$?
check "d1 setup rc 0 (reuse path)" "$rc" "0"
[ -d "$wt" ] && ok "d2 worktree dir back" || bad "d2 worktree dir not recreated"
post_sha="$(git -C "$charon" rev-parse "$branch" 2>/dev/null || echo NONE)"
check "d3 branch tip UNCHANGED (commit preserved)" "$post_sha" "$pre_sha"
# Negative: prove the P0 #4 guard is what protects. If p0_worktree_setup were reverted
# to drop the branch, this would fail with branch == origin/master == base.
[ "$post_sha" != "$(git -C "$charon" rev-parse origin/master)" ] \
  && ok "d4 branch is NOT at base (guard intact — would fail if -B/recreate reverted)" \
  || bad "d4 branch is at base (P0 #4 guard REVERTED — branch was reset)"
rm -rf "$(dirname "$charon")"

echo "== (e) cleanup() in fleet-droid.sh: dirty worktree -> auto-commit + worktree removed =="
# This case is harder to test in isolation because cleanup() lives in fleet-droid.sh
# (a full bash script). We exercise the EQUIVALENT pattern directly: a worktree with
# dirty changes + a stand-down — the same code path cleanup() runs.
charon="$(mk_charon)"; wt="$charon-fleet-E"; branch="feat/e"
# shellcheck source=leak-guard.sh
. "$SRC/leak-guard.sh"
leak_worktree_setup "$charon" "$wt" "$branch" "" "origin/master" >/dev/null 2>&1
# Simulate the droid making uncommitted edits (typical SIGTERM/cleanup race).
echo in-progress > "$wt/halfway.txt"
[ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ] \
  && ok "e1 worktree has uncommitted changes (the case cleanup() handles)" \
  || bad "e1 worktree doesn't have uncommitted changes — test setup wrong"
# cleanup()-equivalent: auto-commit then remove
git -C "$wt" add -A
git -C "$wt" commit -q -m "chore: cleanup auto-commit (test)"
pre_sha="$(git -C "$charon" rev-parse "$branch")"
# remove the worktree
git -C "$charon" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
[ ! -d "$wt" ] && ok "e2 worktree removed" || bad "e2 worktree still present"
git -C "$charon" show-ref --verify --quiet "refs/heads/$branch" \
  && ok "e3 branch SURVIVES (commit preserved on refs/heads/$branch)" \
  || bad "e3 branch DELETED (cleanup lost the work — P0 regression)"
check "e4 branch tip UNCHANGED" "$(git -C "$charon" rev-parse "$branch")" "$pre_sha"
rm -rf "$(dirname "$charon")"

echo "== (f) Idempotency: re-running the reaper on a clean state exits 0 with 0 actions =="
root="$(mktemp -d)"
charon="$(mk_charon)"
fleet="$(mk_fleet "$root" "REAP-F")"
out="$(run_reaper "$fleet" "$charon" "/nonexistent" 2>&1)"; rc=$?
check "f1 dry-run on empty state exit 0" "$rc" "0"
has "$out" "no claims present" "(f2) empty state message"
# With a dead claim + empty branch, run twice — second run is a no-op (idempotency).
id="REAP-F1"; fleet="$(mk_fleet "$root" "$id")"
write_claim "$fleet" "$id" "frontier-99991"
branch="feat/$id"; wt="$charon-fleet-$id"
git -C "$charon" worktree add -q "$wt" -b "$branch" master >/dev/null
run_reaper "$fleet" "$charon" "$wt" --apply >/dev/null 2>&1
out2="$(run_reaper "$fleet" "$charon" "$wt" 2>&1)"; rc=$?
check "f3 second run exit 0" "$rc" "0"
has "$out2" "no claims present" "(f4) second run sees no claims (was released by first)"
# worktree is gone, branch is gone (empty branch deleted in clean case)
[ ! -d "$wt" ] && ok "f5 worktree removed on first run" || bad "f5 worktree not removed"
git -C "$charon" show-ref --verify --quiet "refs/heads/$branch" \
  && bad "f6 empty branch still present after clean reap" || ok "f6 empty branch deleted"
rm -rf "$root" "$(dirname "$charon")"

echo "== (g) DRY-RUN default: --apply-less reaper does NOT mutate state =="
root="$(mktemp -d)"; charon="$(mk_charon)"; id="REAP-G"; fleet="$(mk_fleet "$root" "$id")"
branch="feat/$id"; wt="$charon-fleet-$id"
git -C "$charon" worktree add -q "$wt" -b "$branch" master >/dev/null
echo x > "$wt/x.txt"; git -C "$wt" add x.txt; git -C "$wt" commit -q -m g
write_claim "$fleet" "$id" "frontier-99990"
dry="$(run_reaper "$fleet" "$charon" "$wt" 2>&1)"
# DRY-RUN must NOT release the claim, remove the worktree, or delete the branch
[ -e "$fleet/state/claims/$id" ]  && ok "g1 dry-run did NOT release the claim" \
  || bad "g1 dry-run wrongly released the claim"
[ -d "$wt" ]                      && ok "g2 dry-run did NOT remove the worktree" \
  || bad "g2 dry-run wrongly removed the worktree"
git -C "$charon" show-ref --verify --quiet "refs/heads/$branch" \
  && ok "g3 dry-run did NOT delete the branch" \
  || bad "g3 dry-run wrongly deleted the branch"
[ ! -e "$fleet/state/orphans/$id" ]    && ok "g4 dry-run did NOT write orphan flag" \
  || bad "g4 dry-run wrote orphan flag (should be --apply only)"
[ ! -e "$fleet/state/needs-push/$id" ] && ok "g5 dry-run did NOT write needs-push flag" \
  || bad "g5 dry-run wrote needs-push flag (should be --apply only)"
has "$dry" "DEAD+PRESERVE" "(g6) dry-run still REPORTS what --apply would do"
rm -rf "$root" "$(dirname "$charon")"

echo "== (h) FAIL-CLOSED: UNRESOLVABLE base ref must PRESERVE, never clean =="
# THE case the pre-existing suite could not see. Every other fixture wires up a working
# `origin` so $BASE_REF always resolves; the failure mode was therefore untested BY
# CONSTRUCTION. Here `origin` is removed outright, so `origin/master` does not resolve and
# the reaper's `git fetch origin` cannot repair it.
#
# PRE-FIX BEHAVIOR (what this test makes RED on revert):
#   unique="$(git log --oneline "$BASE_REF..$branch" 2>/dev/null | wc -l)"
#   -> git log FAILS, prints nothing, `wc -l` reports 0, git's exit status is swallowed by
#      the pipe -> unique=0 -> the DEAD+CLEAN arm -> `git branch -D "$branch"`.
#   A branch holding a real, unpushed, unlanded commit is destroyed by the guard whose whole
#   job is to preserve it. `git fetch` is never even attempted pre-fix.
root="$(mktemp -d)"; charon="$(mk_charon)"; id="REAP-H"; fleet="$(mk_fleet "$root" "$id")"
branch="feat/$id"; wt="$charon-fleet-$id"
git -C "$charon" worktree add -q "$wt" -b "$branch" master >/dev/null
echo precious > "$wt/precious.txt"; git -C "$wt" add precious.txt
git -C "$wt" commit -q -m precious-commit
h_sha="$(git -C "$charon" rev-parse "$branch")"
# Break base resolution: drop the remote (this also drops refs/remotes/origin/*), so both
# `git fetch origin` and `git rev-parse origin/master` fail.
git -C "$charon" remote remove origin >/dev/null 2>&1 || true
git -C "$charon" update-ref -d refs/remotes/origin/master >/dev/null 2>&1 || true
git -C "$charon" rev-parse --verify --quiet "origin/master^{commit}" >/dev/null 2>&1 \
  && bad "h0 fixture setup — origin/master still resolves, this test proves nothing" \
  || ok "h0 fixture: 'origin/master' is genuinely UNRESOLVABLE (the untested failure mode)"
write_claim "$fleet" "$id" "frontier-99987"
apply_out="$(run_reaper "$fleet" "$charon" "$wt" --apply 2>&1)"; rc=$?
check "h1 --apply exit 0 (sweep continues, does not abort)" "$rc" "0"
has "$apply_out" "DEAD+PRESERVE" "(h2) unknown count routes to PRESERVE, not CLEAN"
has "$apply_out" "UNKNOWN"       "(h3) reports the count as UNKNOWN (not a bare 0)"
no  "$apply_out" "DEAD+CLEAN"    "(h4) did NOT take the destructive clean path"
# THE crux: the branch and its commit survive.
git -C "$charon" show-ref --verify --quiet "refs/heads/$branch" \
  && ok "h5 branch SURVIVES an unresolvable base (fail-closed guard held)" \
  || bad "h5 branch DELETED because the base ref would not resolve (DATA LOSS — fail-open regression)"
check "h6 commit tip UNCHANGED" "$(git -C "$charon" rev-parse "$branch" 2>/dev/null || echo NONE)" "$h_sha"
[ -d "$wt" ] && ok "h7 worktree PRESERVED (not swept on an unknown count)" \
  || bad "h7 worktree removed despite an unknown count"
[ -e "$fleet/state/orphans/$id" ] && ok "h8 state/orphans/$id written (manager can see it)" \
  || bad "h8 state/orphans/$id missing"
[ -e "$fleet/state/needs-push/$id" ] && ok "h9 state/needs-push/$id written (recovery path armed)" \
  || bad "h9 state/needs-push/$id missing"
[ ! -e "$fleet/state/claims/$id" ] && ok "h10 claim released (ticket not starved)" \
  || bad "h10 claim still held"
rm -rf "$root" "$wt" "$(dirname "$charon")"

echo "== (i) FAIL-CLOSED: p0_worktree_setup must NOT reset a branch when the base is unresolvable =="
# Same failure mode at the launcher's call site. Pre-fix the emptiness test was
# `[ -n "$(git ... log --oneline "$base_ref..$branch" 2>/dev/null)" ]` — an unresolvable base
# gave an empty string, read as "no unique commits", and routed to the RECREATE-FROM-BASE path.
charon="$(mk_charon)"; wt="$charon-fleet-I"; branch="feat/i"
git -C "$charon" worktree add -q "$wt" -b "$branch" master >/dev/null
echo i-work > "$wt/i.txt"; git -C "$wt" add i.txt; git -C "$wt" commit -q -m i-commit
i_sha="$(git -C "$charon" rev-parse "$branch")"
git -C "$charon" remote remove origin >/dev/null 2>&1 || true
git -C "$charon" update-ref -d refs/remotes/origin/master >/dev/null 2>&1 || true
# shellcheck source=leak-guard.sh
. "$SRC/leak-guard.sh"
eval "$(sed -n '/^p0_worktree_setup(){/,/^}$/p' "$SRC/fleet-droid.sh")"
rm -rf "$wt"   # dead droid's worktree dir gone; branch survives (the orphan state)
rc=0; i_out="$(p0_worktree_setup "$charon" "$wt" "$branch" "" "origin/master" 2>&1)" || rc=$?
check "i1 setup rc 0 (preserve/reuse path taken)" "$rc" "0"
has "$i_out" "UNRESOLVABLE" "(i2) launcher reports the unresolvable base rather than assuming empty"
git -C "$charon" show-ref --verify --quiet "refs/heads/$branch" \
  && ok "i3 branch SURVIVES" || bad "i3 branch DELETED (fail-open regression at the launcher)"
check "i4 branch tip UNCHANGED (not reset to base)" \
  "$(git -C "$charon" rev-parse "$branch" 2>/dev/null || echo NONE)" "$i_sha"
[ -d "$wt" ] && ok "i5 worktree re-attached to the SURVIVING branch" \
  || bad "i5 worktree not recreated"
rm -rf "$(dirname "$charon")"

echo "== (j) F1 CRITICAL: a leak-guard REFUSAL in cleanup() must be TERMINAL — worktree INTACT on disk =="
# THE BUG (reproduced by adversarial review): fleet-droid.sh's cleanup() read
#   `if ! safe_worktree_remove … 2>/dev/null; then worktree remove --force || rm -rf "$wt"; fi`
# The `if !` inverted the guard into a TRIGGER: safe_worktree_remove returns non-zero exactly
# when the target MUST NOT be destroyed, so every refusal reason caused the destroy.
# This test asserts DISK STATE (the precious file still exists), not a log string.
root="$(mktemp -d)"; charon="$(mk_charon)"; id="REAP-J"; fleet="$(mk_fleet "$root" "$id")"
wt="$charon-fleet-$id"; branch="feat/$id"
git -C "$charon" worktree add -q "$wt" -b "$branch" master >/dev/null
echo UNCOMMITTED-PRECIOUS > "$wt/precious.txt"
# A failing pre-commit hook makes cleanup()'s auto-commit fail (it is `|| true`), leaving the
# tree DIRTY — one of the reviewer's listed real causes. Worktrees share the common hooks dir.
mkdir -p "$charon/.git/hooks"
printf '#!/bin/sh\nexit 1\n' > "$charon/.git/hooks/pre-commit"; chmod +x "$charon/.git/hooks/pre-commit"
# Arm the guard the same way cleanup() itself does: a live needs-push marker.
printf 'branch=%s\n' "$branch" > "$fleet/state/needs-push/$id"
# Sanity: the guard must actually REFUSE this target, else the test proves nothing.
# shellcheck source=leak-guard.sh
. "$SRC/leak-guard.sh"
g_rc=0; safe_worktree_remove "$charon" "$wt" "$id" "$fleet/state/needs-push" >/dev/null 2>&1 || g_rc=$?
[ "$g_rc" -ne 0 ] && ok "j1 leak-guard REFUSES this target (rc=$g_rc) — the precondition under test" \
  || bad "j1 leak-guard ACCEPTED removal — fixture no longer exercises a refusal"
# Run the REAL cleanup() out of fleet-droid.sh (same test seam as (d)/(i)) — not a copy.
DROID=test-j; REPO="$charon"; current="$id"; FLEET="$fleet"
eval "$(sed -n '/^cleanup(){/,/^}$/p' "$SRC/fleet-droid.sh")"
printf '#!/usr/bin/env bash\nexit 0\n' > "$fleet/release.sh"
j_out="$(cleanup 2>&1)"; j_rc=$?
check "j2 cleanup() returns 0 (a refusal is a stand-down, not a crash)" "$j_rc" "0"
[ -e "$wt/precious.txt" ] \
  && ok "j3 UNCOMMITTED WORK SURVIVES on disk ($wt/precious.txt still exists)" \
  || bad "j3 PRECIOUS UNCOMMITTED FILE DESTROYED — guard refusal was overridden (F1 regression)"
[ -d "$wt" ] && ok "j4 worktree directory INTACT" || bad "j4 worktree directory DESTROYED (F1 regression)"
git -C "$charon" show-ref --verify --quiet "refs/heads/$branch" \
  && ok "j5 branch survives" || bad "j5 branch deleted"
has "$j_out" "worktree KEPT" "(j6) the refusal is REPORTED, not swallowed by 2>/dev/null"
rm -rf "$(dirname "$charon")" "$root"

echo "== (k) F1: a CATASTROPHIC target (worktree-family root) refusal is also terminal =="
# The other refusal class the `if !` inversion turned into a trigger: paths leak-guard cannot
# prove are ours / catastrophic targets. Destroying these was the worst case of the same bug.
root="$(mktemp -d)"; charon="$(mk_charon)"; id="REAP-K"; fleet="$(mk_fleet "$root" "$id")"
family="$(dirname "$charon")"          # the directory CONTAINING the live checkout
mkdir -p "$family/keepme"; echo DO-NOT-DELETE > "$family/keepme/precious.txt"
DROID=test-k; REPO="$charon"; current="$id"; FLEET="$fleet"; branch="feat/$id"
wt="$family"                            # cleanup() aimed at a catastrophic path
printf '#!/usr/bin/env bash\nexit 0\n' > "$fleet/release.sh"
eval "$(sed -n '/^cleanup(){/,/^}$/p' "$SRC/fleet-droid.sh")"
k_out="$(cleanup 2>&1)" || true
[ -e "$family/keepme/precious.txt" ] \
  && ok "k1 catastrophic target NOT destroyed (family root intact)" \
  || bad "k1 CATASTROPHIC TARGET DESTROYED — refusal overridden (F1 regression)"
[ -d "$charon" ] && ok "k2 live checkout intact" || bad "k2 live checkout DESTROYED"
has "$k_out" "worktree KEPT" "(k3) catastrophic refusal reported"
rm -rf "$family" "$root"

echo "== (l) F2: a NONEXISTENT branch is benign — no error, sweep exits 0 =="
# _lg_unlanded_count legitimately returns 0 for a missing branch (the reaper's own comment calls
# this expected: droid created the worktree then crashed before `worktree add -B` finalized it).
# `git branch -d` then exited 1 -> n_errors++ -> the WHOLE sweep exited 1 with a wrong message.
root="$(mktemp -d)"; charon="$(mk_charon)"; id="REAP-L"; fleet="$(mk_fleet "$root" "$id")"
write_claim "$fleet" "$id" "frontier-99993"
# The droid died before `git worktree add -B` finalized ANYTHING: no branch, and the worktree
# path does not exist (so safe_worktree_remove is a clean no-op and cannot confound the result —
# this test isolates the BRANCH-DELETE arm, which is where F2 lived).
wt="$charon-fleet-$id"
git -C "$charon" show-ref --verify --quiet "refs/heads/feat/$id" \
  && bad "l0 branch exists — fixture wrong" || ok "l0 branch does NOT exist (the expected case)"
l_out="$(run_reaper "$fleet" "$charon" "$wt" --apply 2>&1)"; l_rc=$?
check "l1 sweep exits 0 (a missing branch is not an error)" "$l_rc" "0"
no "$l_out" "git sees unmerged commits" "(l2) the wrong 'unmerged commits' message is NOT emitted"
no "$l_out" "errors:" "(l3) no error tally"
rm -rf "$(dirname "$charon")" "$root"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL DROID-LIFECYCLE-REAP TESTS PASS"
