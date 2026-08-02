#!/usr/bin/env bash
# Release a CLAIM so another droid can retry the ticket (abandon / blocker).
# Does NOT clear a `submitted` marker — for a rejected/closed PR use reject.sh.
#
# RELEASE-PRESERVES-WORK (2026-08-01): releasing must never discard finished work.
# Before dropping the claim, this checks the ticket's branch/worktree for unlanded
# commits or a dirty tree. If any exist it KEEPS the claim, writes
# state/needs-push/<id> (the marker fleet-droid.sh already honours), and prints the
# recovery command loudly. When the branch/worktree cannot be resolved it FAILS
# SAFE and refuses to release — losing a claim is cheap, losing finished work is not.
# A ticket with genuinely nothing to lose releases exactly as before (anti-over-block).
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$FLEET/state"; BOARD="$FLEET/board"
canon(){ local w="$1" f b; for f in "$BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  echo "release.sh: no board ticket matching '$w'" >&2; return 1; }
id="$(canon "${1:?usage: release.sh <id>}")" || exit 2

# ── RESOLVE the ticket's branch/repo/worktree (SSOT readers + test hooks) ──
# RELEASE_BRANCH / RELEASE_REPO / RELEASE_WT force resolution so the guard is fully
# exercisable hermetically (offline fixture) without touching real repos.
[ -f "$FLEET/_lib.sh" ] && source "$FLEET/_lib.sh" || true
branch="${RELEASE_BRANCH:-}"
[ -n "$branch" ] || branch="$(_vm_meta branch "$BOARD/$id.md" 2>/dev/null || true)"
repo="${RELEASE_REPO:-}"
[ -n "$repo" ] || repo="$(ticket_repo_path "$id" 2>/dev/null || true)"
wt="${RELEASE_WT:-}"
[ -n "$wt" ] || wt="$(ticket_worktree_path "$id" 2>/dev/null || true)"

# A ticket with no branch declares nothing to check -> release as today.
if [ -z "$branch" ] || [ "$branch" = "n/a" ]; then
  rm -f "$S/claims/$id"
  echo "released $id (claim cleared, re-claimable)"
  exit 0
fi

# _release_block <repo> <wt> <branch> — returns 0 (block release) with a reason on
# stdout when releasing <id> would discard work OR when it cannot be proven safe.
# Returns 1 only when there is genuinely nothing to lose.
_release_block(){
  local r="$1" w="$2" b="$3" dirty n
  # Unresolvable repo -> FAIL SAFE: cannot prove the branch is empty of work.
  if [ -z "$r" ] || ! { [ -d "$r/.git" ] || [ -f "$r/.git" ]; }; then
    echo "cannot resolve a git repo for $id (repo=${r:-<unset>}) — treating as work-in-progress"
    return 0
  fi
  # A live worktree holds the droid's state directly: dirty tree OR commits not on
  # any remote ref are both work that must not be stranded by a release.
  if [ -n "$w" ] && { [ -d "$w/.git" ] || [ -f "$w/.git" ]; }; then
    dirty="$(git -C "$w" status --porcelain 2>/dev/null || echo UNREADABLE)"
    if [ "$dirty" = "UNREADABLE" ]; then
      echo "cannot read worktree $w — treating as work-in-progress"
      return 0
    fi
    if [ -n "$dirty" ]; then
      echo "uncommitted changes in worktree $w"
      return 0
    fi
    n="$(git -C "$w" rev-list --count HEAD --not --remotes 2>/dev/null || echo ERROR)"
    if [ "$n" = "ERROR" ]; then
      echo "cannot count unlanded commits in worktree $w — treating as work-in-progress"
      return 0
    fi
    if [ "$n" -gt 0 ] 2>/dev/null; then
      echo "$n unlanded commit(s) on $b in $w"
      return 0
    fi
    return 1
  fi
  # No worktree: the branch may still exist in the main repo with commits.
  if [ -n "$(git -C "$r" rev-parse --verify --quiet "refs/heads/$b" 2>/dev/null)" ]; then
    n="$(git -C "$r" rev-list --count "refs/heads/$b" --not --remotes 2>/dev/null || echo ERROR)"
    if [ "$n" = "ERROR" ]; then
      echo "cannot count unlanded commits for $b in $r — treating as work-in-progress"
      return 0
    fi
    if [ "$n" -gt 0 ] 2>/dev/null; then
      echo "$n unlanded commit(s) on $b in $r"
      return 0
    fi
  fi
  # No worktree and no branch anywhere -> genuinely nothing to lose.
  return 1
}

block=0
reason="$(_release_block "$repo" "$wt" "$branch")" || block=$?
if [ "$block" -eq 0 ]; then
  mkdir -p "$S/needs-push"
  printf 'branch=%s\nworktree=%s\nrepo=%s\nreason=release.sh refused: %s\nflagged=%s\n' \
    "$branch" "${wt:-n/a}" "${repo:-n/a}" "$reason" "$(date -u +%FT%TZ)" \
    > "$S/needs-push/$id"
  echo "release.sh: REFUSING to release $id — $reason" >&2
  echo "release.sh:   claim RETAINED; state/needs-push/$id written — no other droid will redo this work." >&2
  echo "release.sh:   RECOVERY: land the branch, then re-release:" >&2
  echo "release.sh:     bash $FLEET/land-needs-push.sh $id" >&2
  echo "release.sh:     bash $FLEET/release.sh $id" >&2
  exit 3
fi

rm -f "$S/claims/$id"
echo "released $id (claim cleared, re-claimable)"
