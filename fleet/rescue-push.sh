#!/usr/bin/env bash
# rescue-push.sh — push every local-only branch to its remote so no commit exists on one disk only.
#
# WHY THIS EXISTS (PRIORITY-TODO.md §L): 47 branches carrying 96 commits existed ONLY on this box.
# The class recurs every session because the sweep is hand-typed in the moment and the narrow
# "ahead of upstream" query MISSES branches that have no upstream at all. This is the mechanized
# sweep — run it, do not retype it.
#
# SAFETY: read-only by default. It NEVER deletes, forces, prunes or rewrites. The only mutation is
# `git push -u origin <branch>` for branches that carry commits absent from origin/master, and only
# when --push is passed. Setting upstream is deliberate: it keeps the no-upstream class detectable.
#
# Detection-only companion: fleet/checks/stranded-work.sh (unpushed / dirty-worktree / pushed-no-PR).
# This tool is the RESCUE half — it acts on the unpushed class rather than reporting it.
#
# usage:
#   bash fleet/rescue-push.sh            # dry run — list what would be pushed
#   bash fleet/rescue-push.sh --push     # actually push
set -uo pipefail

# The repos to sweep. Overridable via RESCUE_PUSH_REPOS (space-separated) for ONE reason: the
# safety properties below (never force a diverged branch, dry-run mutates nothing) are only worth
# anything if they are TESTED, and they cannot be tested against the live boxes. The default is
# unchanged, so live behaviour is identical whether or not the variable is set.
# shellcheck disable=SC2206
REPOS=(${RESCUE_PUSH_REPOS:-/home/stack/charon-private /home/stack/code/charon})
DO_PUSH=0
case "${1:-}" in
  --push) DO_PUSH=1 ;;
  ""|--dry-run) ;;
  *) echo "usage: rescue-push.sh [--push|--dry-run]" >&2; exit 2 ;;
esac

total=0; pushed=0; failed=0

for repo in "${REPOS[@]}"; do
  [ -d "$repo/.git" ] || { echo "SKIP $repo (not a git repo)"; continue; }
  echo "=== $repo"
  base="origin/master"
  git -C "$repo" rev-parse --verify --quiet "$base" >/dev/null || {
    echo "  UNDETERMINED: no $base ref — skipping repo"; continue; }

  while read -r br up; do
    case "$br" in backup/*) continue ;; esac
    if [ -n "$up" ]; then
      # HAS an upstream: at risk only for commits AHEAD of that upstream. This class was MISSED by
      # the first cut of this tool (it looked at no-upstream branches only) — the exact narrow-scan
      # mistake PRIORITY-TODO §L3 calls out. fix/shared-namespace-contention sat 25 commits ahead.
      n=$(git -C "$repo" rev-list --count "$up..$br" 2>/dev/null) || continue
    else
      n=$(git -C "$repo" rev-list --count "$base..$br" 2>/dev/null) || continue
    fi
    [ "${n:-0}" -gt 0 ] || continue          # nothing at risk on this branch
    total=$((total + 1))
    if [ "$DO_PUSH" -eq 1 ]; then
      # Capture stderr: a silent FAILED is useless — a rescue that cannot say WHY it failed sends
      # you back to raw `git push`, which is deny-listed for manager sessions.
      if err="$(git -C "$repo" push -u origin "$br" 2>&1)"; then
        echo "  PUSHED  $n commit(s)  $br"; pushed=$((pushed + 1))
      else
        # DIVERGED (non-fast-forward): local carries commits the remote lacks AND the remote carries
        # commits local lacks. A force-push here would DESTROY the remote side — never do that from a
        # rescue. Instead push the local tip to a PARALLEL rescue/* ref: purely additive, loses
        # nothing on either side, and leaves the merge decision to a human at leisure. Rescue first,
        # triage later (PRIORITY-TODO §L2).
        # git names this rejection THREE ways and they are not interchangeable:
        #   (non-fast-forward)  local is behind a remote-tracking ref that is UP TO DATE
        #   (fetch first)       the remote moved and our remote-tracking ref is STALE
        #   (stale info)        a --force-with-lease-shaped stale-ref rejection
        # Matching only 'non-fast-forward' — which is what the hand-typed sweep did — silently
        # drops the STALE-tracking case into the FAILED bucket with no rescue ref, and stale
        # tracking is the NORMAL state of a branch nobody has fetched in days: precisely the
        # branches this tool exists for. Caught by fleet/tests/rescue-push.test.sh case (c).
        if printf '%s\n' "$err" | grep -qE 'non-fast-forward|fetch first|stale info'; then
          if git -C "$repo" push origin "$br:refs/heads/rescue/$br" >/dev/null 2>&1; then
            echo "  DIVERGED -> rescued to 'rescue/$br'  ($n local-only commit(s))  $br"
            echo "            remote also has commits local lacks — MERGE BY HAND, do not force."
            pushed=$((pushed + 1))
          else
            echo "  FAILED  $n commit(s)  $br  (diverged AND rescue ref push failed)"; failed=$((failed + 1))
          fi
        else
          echo "  FAILED  $n commit(s)  $br"; failed=$((failed + 1))
          printf '%s\n' "$err" | grep -Ei 'reject|error|denied|hook|refus|\!' | sed 's/^/            /' | head -3
        fi
      fi
    else
      echo "  WOULD PUSH  $n commit(s)  $br"
    fi
  done < <(git -C "$repo" for-each-ref --format='%(refname:short) %(upstream)' refs/heads)
done

echo
if [ "$DO_PUSH" -eq 1 ]; then
  echo "rescue-push: $pushed pushed, $failed failed, of $total at-risk branch(es)."
  [ "$failed" -eq 0 ] || exit 1
else
  echo "rescue-push: $total local-only branch(es) carry commits that exist ONLY on this box."
  echo "rescue-push: re-run with --push to rescue them."
fi
