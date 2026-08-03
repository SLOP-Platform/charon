#!/usr/bin/env bash
# force-push-safety.test.sh — FAIL-ON-REVERT tests for FORCE-PUSH-SAFETY-GATE.
#
# THE RULE: `--force` must PROVE it destroys nothing before pushing.
#   count = git rev-list <local>..<remote>   (commits on the remote NOT reachable from local)
#   count == 0  -> nothing unique on the remote; force is safe; proceed.
#   count > 0   -> REFUSE by default; print sha + subject + diffstat of every commit this push
#                  would erase, so the operator sees exactly what is at stake.
#   --force-with-destroy=<reason> -> the SEPARATE, louder override for "I truly mean to discard
#                  that"; it names what is being discarded in its own invocation.
#
# The incident this gates against (measured, 2026-08-01): a manager used `land-push.sh --force`
# 19 times to rescue stranded branches; each was justified by reasoning and each was correct. On
# the 20th the reasoning was wrong: `fix/shared-namespace-contention` had LOCAL on 24 master-side
# commits and REMOTE holding the ONLY copy of a +905-line fix. `--force` would have destroyed it;
# it was stopped only because git happened to refuse the non-fast-forward. The safety must come
# from a CHECK, not from an accident of history shape — a fast-forward-shaped overwrite of real
# work would have gone straight through.
#
# The gate functions (fps_gate_check / fps_destroy_override / fps_push) are embedded in this file
# so the test IS the reference gate — no shared-script coupling. The files that would host the
# production gate (fleet/land-push.sh, fleet/rescue-push.sh) belong to other board tickets, so
# this suite is the EXTERNAL SPEC the production gate must satisfy: revert any one behavior below
# and the suite goes RED (fail-on-revert).
#
# NON-FIXTURE: REAL git objects, a REAL bare file:// remote, two repos sharing the remote.
#
# ── FAIL-ON-REVERT ───────────────────────────────────────────────────────────────────────────
#   R1 — make fps_gate_check always return 0 (delete the count>0 refusal).
#                                                                        RED: assertions 3, 3b, 4, 4b
#   R2 — delete the per-commit sha+subject+diffstat printing block.      RED: assertions 4, 4b
#   R3 — make --force-with-destroy route through fps_gate_check.         RED: assertions 5, 5b
#   R4 — make the non-force path call fps_gate_check.                    RED: assertion 10
#
#   Live dogfood (2026-08-01): the reference gate was run against the REAL
#   `fix/shared-namespace-contention` branch on the charon-private origin, which still diverges
#   from master (1 unique fix commit vs 91 master commits). It REFUSED and named the fix. That
#   run is captured in docs/review-log/FORCE-PUSH-SAFETY-GATE.md — it is intentionally not baked
#   into this file so the suite stays hermetic and offline.

set -uo pipefail

passes=0; fails=0
ok(){ passes=$((passes+1)); printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT

# ── REFERENCE GATE FUNCTIONS (self-contained, no external deps) ─────────────────────────────

# fps_gate_check <repo> <remote> <local_ref> <dst_branch>
#   Returns 0 (safe to force) or 1 (refused: the remote holds commits this push would erase).
fps_gate_check(){
  local repo="$1" remote="$2" local_ref="$3" dst="$4"
  local remote_sha local_sha orphans count
  remote_sha="$(git -C "$repo" ls-remote "$remote" "refs/heads/$dst" 2>/dev/null | awk 'NR==1{print $1}')"
  [ -z "$remote_sha" ] && return 0                    # branch does not exist on the remote
  local_sha="$(git -C "$repo" rev-parse --verify "$local_ref" 2>/dev/null)" || return 0
  git -C "$repo" fetch -q "$remote" "refs/heads/$dst" 2>/dev/null || true
  orphans="$(git -C "$repo" rev-list "$local_sha".."$remote_sha" 2>/dev/null)" || orphans=""
  # grep -c . -> 0 for empty output (wc -l would count a blank line as 1 and FALSELY refuse)
  count="$(printf '%s' "$orphans" | grep -c . || true)"
  if [ "$count" -gt 0 ]; then
    printf 'fps: REFUSING --force — %s/%s holds %s commit(s) this push would destroy:\n' "$remote" "$dst" "$count"
    printf '%s\n' "$orphans" | while read -r sha; do
      [ -n "$sha" ] || continue
      local subj statline
      subj="$(git -C "$repo" log -1 --format='%s' "$sha" 2>/dev/null || echo 'unknown')"
      statline="$(git -C "$repo" show --stat --format='' "$sha" 2>/dev/null | tail -1)"
      printf 'fps:   %s  %s\n' "$sha" "$subj"
      [ -n "$statline" ] && printf 'fps:     %s\n' "$statline"
    done
    printf 'fps: Use --force-with-destroy=<reason> to override (it names what is discarded).\n'
    return 1
  fi
  return 0
}

# fps_destroy_override <repo> <remote> <local_ref> <dst> <reason>
#   The SEPARATE, louder flag: proceeds and names exactly what it discards.
fps_destroy_override(){
  local repo="$1" remote="$2" local_ref="$3" dst="$4" reason="$5"
  local local_sha remote_sha orphans count
  local_sha="$(git -C "$repo" rev-parse --verify "$local_ref" 2>/dev/null)" || {
    printf 'fps: --force-with-destroy: cannot resolve %s\n' "$local_ref"; return 1; }
  remote_sha="$(git -C "$repo" ls-remote "$remote" "refs/heads/$dst" 2>/dev/null | awk 'NR==1{print $1}')"
  if [ -n "$remote_sha" ]; then
    git -C "$repo" fetch -q "$remote" "refs/heads/$dst" 2>/dev/null || true
    orphans="$(git -C "$repo" rev-list "$local_sha".."$remote_sha" 2>/dev/null)" || orphans=""
    count="$(printf '%s' "$orphans" | grep -c . || true)"
    printf 'fps: --force-with-destroy (%s): discarding %s commit(s) from %s/%s:\n' "$reason" "$count" "$remote" "$dst"
    printf '%s\n' "$orphans" | while read -r sha; do
      [ -n "$sha" ] || continue
      local subj
      subj="$(git -C "$repo" log -1 --format='%s' "$sha" 2>/dev/null || echo 'unknown')"
      printf 'fps:   %s  %s\n' "$sha" "$subj"
    done
  else
    printf 'fps: --force-with-destroy (%s): %s/%s has no ref; nothing to discard\n' "$reason" "$remote" "$dst"
  fi
}

# fps_push <repo> <remote> <local_ref> <dst> [--force|--force-with-destroy=<reason>]
fps_push(){
  local repo="$1" remote="$2" local_ref="$3" dst="$4"; shift 4
  local force="" destroy_reason=""
  while [ $# -gt 0 ]; do case "$1" in
    --force)                 force=1; shift;;
    --force-with-destroy=*)  destroy_reason="${1#*=}"; force=1; shift;;
    *)                       shift;;
  esac; done
  if [ -n "$force" ]; then
    if [ -n "$destroy_reason" ]; then
      fps_destroy_override "$repo" "$remote" "$local_ref" "$dst" "$destroy_reason"
      git -C "$repo" push --force "$remote" "${local_ref}:refs/heads/${dst}" 2>/dev/null
    else
      fps_gate_check "$repo" "$remote" "$local_ref" "$dst" || return 1
      git -C "$repo" push --force "$remote" "${local_ref}:refs/heads/${dst}" 2>/dev/null
    fi
  else
    # non-force path never consults the gate — a normal push is untouched (R4 protects this)
    git -C "$repo" push "$remote" "${local_ref}:refs/heads/${dst}" 2>/dev/null
  fi
}

remote_sha(){ git -C "$1" ls-remote "$2" "refs/heads/$3" 2>/dev/null | awk 'NR==1{print $1}'; }

# ── TEST SCENARIO A: remote holds NOTHING unique (the 19 legitimate rescues) ────────────────

REMOTE="$D/remote.git"; git init -q --bare -b master "$REMOTE"
R="$D/repo"; git init -q -b master "$R"
git -C "$R" config user.email t@t; git -C "$R" config user.name t
git -C "$R" remote add origin "$REMOTE"
echo base > "$R/f"; git -C "$R" add f; git -C "$R" commit -qm "base commit"
git -C "$R" push -q origin master
git -C "$R" checkout -q -b feature
echo feat >> "$R/f"; git -C "$R" commit -qam "add feature work"
FEAT_SHA="$(git -C "$R" rev-parse HEAD)"

# ── 1. --force to a branch the remote does not have -> PROCEEDS ───────────────────────────
fps_push "$R" origin HEAD feature --force >/dev/null 2>&1; rc=$?
rs="$(remote_sha "$R" origin feature)"
if [ "$rc" -eq 0 ] && [ "$rs" = "$FEAT_SHA" ]; then
  ok "1 --force to a new branch: proceeds (nothing to destroy)"
else
  bad "1 --force rc=$rc remote=${rs:0:7} want=${FEAT_SHA:0:7}"
fi

# ── 2. --force-with-destroy when the remote is clean -> proceeds ──────────────────────────
git -C "$R" push -q origin HEAD:refs/heads/clean-test 2>/dev/null || true
git -C "$R" checkout -q -b more-work
echo more >> "$R/f"; git -C "$R" commit -qam "more work"
NEW_SHA="$(git -C "$R" rev-parse HEAD)"
fps_push "$R" origin HEAD clean-test --force-with-destroy="clean override" >"$D/override2" 2>&1; rc=$?
rs="$(remote_sha "$R" origin clean-test)"
if [ "$rc" -eq 0 ] && [ "$rs" = "$NEW_SHA" ]; then
  ok "2 --force-with-destroy when remote clean: proceeds"
else
  bad "2 override rc=$rc remote=${rs:0:7} want=${NEW_SHA:0:7}"
fi

# ── 9. ANTI-OVER-BLOCK: remote branch EXISTS but holds NOTHING unique (fast-forward-shaped) ─
#      This is the shape the incident warned about — a fast-forward-shaped overwrite — when it is
#      GENUINELY harmless. count==0 must proceed or the 19 legitimate rescues die. Exercises the
#      count==0-with-existing-remote path (the count computation must not treat empty as 1).
git -C "$R" push -q origin HEAD:refs/heads/ff-test 2>/dev/null || true   # remote ff-test = NEW_SHA
fps_push "$R" origin HEAD ff-test --force >/dev/null 2>&1; rc=$?
rs="$(remote_sha "$R" origin ff-test)"
if [ "$rc" -eq 0 ] && [ "$rs" = "$NEW_SHA" ]; then
  ok "9 --force when remote holds NOTHING unique: proceeds (anti-over-block)"
else
  bad "9 anti-over-block rc=$rc remote=${rs:0:7} want=${NEW_SHA:0:7}"
fi

# ── TEST SCENARIO B: remote has REAL WORK absent from local (the near-miss) ────────────────
# Reproduces fix/shared-namespace-contention: remote holds 1 unique fix commit (+905 real lines
# across claim-jedi-name.sh, spawn-worker.sh, two test suites), local holds 24 board-hygiene
# commits. --force would destroy the only copy of the real fix.

REMOTE2="$D/remote2.git"; git init -q --bare -b master "$REMOTE2"
R_REMOTE="$D/remote-owner"; git init -q -b master "$R_REMOTE"
git -C "$R_REMOTE" config user.email t@t; git -C "$R_REMOTE" config user.name t
git -C "$R_REMOTE" remote add origin "$REMOTE2"
echo "fix for the contention bug" > "$R_REMOTE/claim-jedi-name.sh"
echo "# real fix line 2" >> "$R_REMOTE/claim-jedi-name.sh"
echo "# real fix line 3" >> "$R_REMOTE/spawn-worker.sh"
git -C "$R_REMOTE" add .; git -C "$R_REMOTE" commit -qm "the real fix: shared namespace contention (+905 lines)"
REMOTE_REAL_SHA="$(git -C "$R_REMOTE" rev-parse HEAD)"
git -C "$R_REMOTE" push -q origin master

R_LOCAL="$D/local-pusher"; git init -q -b master "$R_LOCAL"
git -C "$R_LOCAL" config user.email t@t; git -C "$R_LOCAL" config user.name t
git -C "$R_LOCAL" remote add origin "$REMOTE2"
for i in $(seq 1 24); do
  echo "master hygiene commit $i" >> "$R_LOCAL/f"
  git -C "$R_LOCAL" add f; git -C "$R_LOCAL" commit -qm "chore: board hygiene commit $i"
done
LOCAL_SHA="$(git -C "$R_LOCAL" rev-parse HEAD)"
git -C "$R_LOCAL" push -q origin master 2>/dev/null || true   # non-ff, git refuses, remote untouched
git -C "$R_LOCAL" fetch -q origin master 2>/dev/null || true

# ── 3. THE NEAR-MISS: --force is REFUSED ─────────────────────────────────────────────────
fps_push "$R_LOCAL" origin HEAD master --force >"$D/refusal3" 2>&1; rc=$?
rs="$(remote_sha "$R_LOCAL" origin master)"
if [ "$rc" -ne 0 ]; then
  ok "3 --force when remote holds unique work: REFUSED (rc=$rc)"
else
  bad "3 --force ALLOWED when remote holds unique work (rc=$rc)"
fi
if [ "$rs" = "$REMOTE_REAL_SHA" ]; then
  ok "3b remote UNCHANGED after refused push"
else
  bad "3b remote moved to ${rs:0:7} (should be $REMOTE_REAL_SHA)"
fi

# ── 4. Refusal names the at-risk commit (sha + subject) ──────────────────────────────────
REFUSAL_OUT="$(cat "$D/refusal3")"
if printf '%s\n' "$REFUSAL_OUT" | grep -q 'shared namespace contention'; then
  ok "4 refusal names the at-risk commit subject"
else
  bad "4 refusal missing subject: $REFUSAL_OUT"
fi

# ── 4b. Refusal shows the diffstat of every at-risk commit (decide without digging) ───────
if printf '%s\n' "$REFUSAL_OUT" | grep -qE 'file changed|files changed'; then
  ok "4b refusal shows a diffstat line"
else
  bad "4b refusal missing diffstat: $REFUSAL_OUT"
fi

# ── 10. Non-force push to a diverged branch: GIT's own refusal, gate SILENT ───────────────
fps_push "$R_LOCAL" origin HEAD master >"$D/nonforce10" 2>&1; rc=$?
if [ "$rc" -ne 0 ] && ! grep -q 'fps: REFUSING' "$D/nonforce10"; then
  ok "10 non-force diverged push: git refuses, fps gate silent"
else
  bad "10 non-force rc=$rc fps-printed=$(grep -c 'fps:' "$D/nonforce10" || true)"
fi

# ── 5. --force-with-destroy DOES proceed and names what was discarded ─────────────────────
fps_push "$R_LOCAL" origin HEAD master --force-with-destroy="I mean to discard intentionally" >"$D/override5" 2>&1; rc=$?
rs="$(remote_sha "$R_LOCAL" origin master)"
if [ "$rc" -eq 0 ] && [ "$rs" = "$LOCAL_SHA" ]; then
  ok "5 --force-with-destroy override proceeds (rc=$rc)"
else
  bad "5 override rc=$rc remote=${rs:0:7} want=${LOCAL_SHA:0:7}"
fi
OVERRIDE_OUT="$(cat "$D/override5")"
if printf '%s\n' "$OVERRIDE_OUT" | grep -q 'discarding' \
   && printf '%s\n' "$OVERRIDE_OUT" | grep -q "$REMOTE_REAL_SHA"; then
  ok "5b override message names the discarded sha"
else
  bad "5b override missing discard-list: $OVERRIDE_OUT"
fi

# ── 6. Second --force (now safe) proceeds ────────────────────────────────────────────────
git -C "$R_LOCAL" checkout -q -b fix-it
echo fix >> "$R_LOCAL/f"; git -C "$R_LOCAL" commit -qam "actually fix"
FIX_SHA="$(git -C "$R_LOCAL" rev-parse HEAD)"
fps_push "$R_LOCAL" origin HEAD fix-it --force >/dev/null 2>&1; rc=$?
rs="$(remote_sha "$R_LOCAL" origin fix-it)"
if [ "$rc" -eq 0 ] && [ "$rs" = "$FIX_SHA" ]; then
  ok "6 second --force (now safe): proceeds"
else
  bad "6 second --force rc=$rc remote=${rs:0:7} want=${FIX_SHA:0:7}"
fi

# ── TEST SCENARIO C: a normal non-force push is unaffected ───────────────────────────────

# ── 7. Non-force push to a new branch works ──────────────────────────────────────────────
REMOTE3="$D/remote3.git"; git init -q --bare -b master "$REMOTE3"
R3="$D/repo3"; git init -q -b master "$R3"
git -C "$R3" config user.email t@t; git -C "$R3" config user.name t
git -C "$R3" remote add origin "$REMOTE3"
echo base > "$R3/f"; git -C "$R3" add f; git -C "$R3" commit -qm "base"
git -C "$R3" push -q origin master
git -C "$R3" checkout -q -b feat
echo work >> "$R3/f"; git -C "$R3" commit -qam "add work"
WORK3="$(git -C "$R3" rev-parse HEAD)"
fps_push "$R3" origin HEAD feat >/dev/null 2>&1; rc=$?
rs3="$(remote_sha "$R3" origin feat)"
if [ "$rc" -eq 0 ] && [ "$rs3" = "$WORK3" ]; then
  ok "7 non-force push to new branch: works"
else
  bad "7 non-force new-branch rc=$rc remote=${rs3:0:7} want=${WORK3:0:7}"
fi

# ── 8. Non-force push to an existing fast-forward target works ───────────────────────────
git -C "$R3" push -q origin master
echo more >> "$R3/f"; git -C "$R3" commit -qam "more work"
MORE3="$(git -C "$R3" rev-parse HEAD)"
fps_push "$R3" origin HEAD master >/dev/null 2>&1; rc=$?
rs3="$(remote_sha "$R3" origin master)"
if [ "$rc" -eq 0 ] && [ "$rs3" = "$MORE3" ]; then
  ok "8 non-force fast-forward push to existing branch: works"
else
  bad "8 non-force ff rc=$rc remote=${rs3:0:7} want=${MORE3:0:7}"
fi

echo "force-push-safety: $passes pass ($fails failure(s))"
[ "$fails" -eq 0 ]
