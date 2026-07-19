#!/usr/bin/env bash
# push-verify.sh — PROVE-THE-PUSH library (fleet build-rig only; `source` it, runs nothing).
#
# WHY (LAND-SAFETY-FIX, 2026-07-18): THREE push paths reported SUCCESS while doing the wrong
# thing, and one silently merged the WRONG COMMIT (522c147):
#   * land-push.sh pushed the LOCAL REF matching the NAME it was given, not HEAD. With HEAD on a
#     feature branch, `land-push.sh master` printed "pushing 'master'" + success while pushing
#     NOTHING (local master was stale).
#   * land.sh ran `git branch -f <branch> HEAD` and IGNORED its rc. `git branch -f` FAILS with
#     "fatal: cannot force update the branch ... used by worktree at ..." whenever any live
#     worktree holds that branch — with 63 worktrees in play that is the COMMON case, not an edge
#     case. land.sh fell through and pushed the STALE same-named local ref (be41ece).
#
# THE RULE these functions enforce: a tool's own success message is NEVER the only evidence.
# Every push must (1) check the rc of every ref-manipulating command and fail CLOSED, (2) resolve
# EXACTLY which sha it intends to publish, and (3) PROVE with `git ls-remote` afterwards that the
# remote ref now equals that sha — refusing loudly when it does not.
#
# Requires: git. No other deps. Used by land-push.sh and land.sh.

# pv_resolve_sha <repo> <ref> -> full commit sha on stdout. rc 1 = unresolvable (FAIL CLOSED).
pv_resolve_sha(){
  local repo="$1" ref="$2" sha
  sha="$(git -C "$repo" rev-parse --verify --quiet "${ref}^{commit}" 2>/dev/null)" || return 1
  [ -n "$sha" ] || return 1
  printf '%s' "$sha"
}

# pv_branch_holder <repo> <branch> -> path of a DIFFERENT worktree that currently has <branch>
# checked out (empty + rc 1 when nobody else holds it). This is the condition that makes
# `git branch -f <branch>` fail; detecting it up-front turns a silent wrong push into an
# actionable message. The repo's OWN checkout is excluded: being on the branch you are landing is
# normal and harmless (`branch -f` is then skipped entirely).
pv_branch_holder(){
  local repo="$1" branch="$2" self wt="" line held=""
  self="$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null)" || self="$repo"
  while IFS= read -r line; do
    case "$line" in
      worktree\ *) wt="${line#worktree }" ;;
      branch\ refs/heads/*)
        held="${line#branch refs/heads/}"
        if [ "$held" = "$branch" ] && [ "$wt" != "$self" ]; then printf '%s' "$wt"; return 0; fi
        ;;
    esac
  done < <(git -C "$repo" worktree list --porcelain 2>/dev/null)
  return 1
}

# pv_remote_sha <repo> <remote> <branch> -> the sha the REMOTE currently has for refs/heads/<branch>
# ("" when the branch does not exist there). rc 1 only when the remote could not be queried.
pv_remote_sha(){
  local repo="$1" remote="$2" branch="$3" out
  out="$(git -C "$repo" ls-remote "$remote" "refs/heads/$branch" 2>/dev/null)" || return 1
  printf '%s' "$(printf '%s\n' "$out" | awk 'NR==1{print $1}')"
}

# pv_push_verified <repo> <remote> <intended_sha> <dst_branch> [--force]
#   Pushes EXACTLY <intended_sha> to refs/heads/<dst_branch>, then PROVES with ls-remote that the
#   remote ref equals it. rc 0 ONLY on proven success.
#   rc 1 = push command failed. rc 2 = push "succeeded" but the remote sha is NOT the intended sha
#   (the false-success class this library exists to catch).
pv_push_verified(){
  local repo="$1" remote="$2" sha="$3" dst="$4" force="${5:-}"
  local args=(push "$remote" "$sha:refs/heads/$dst")
  [ "$force" = "--force" ] && args=(push --force "$remote" "$sha:refs/heads/$dst")
  echo "push-verify: pushing $sha -> $remote/$dst"
  if ! git -C "$repo" "${args[@]}"; then
    echo "push-verify: PUSH FAILED — $sha -> $remote/$dst (nothing published)" >&2
    return 1
  fi
  local now; now="$(pv_remote_sha "$repo" "$remote" "$dst")" || {
    echo "push-verify: UNPROVEN — could not ls-remote $remote refs/heads/$dst; refusing to report success" >&2
    return 2; }
  if [ "$now" != "$sha" ]; then
    echo "push-verify: REMOTE MISMATCH — intended $sha but $remote/$dst is ${now:-<absent>}; the push did NOT publish the intended commit" >&2
    return 2
  fi
  echo "push-verify: PROVEN — $remote/$dst == $sha (ls-remote verified)"
  return 0
}
