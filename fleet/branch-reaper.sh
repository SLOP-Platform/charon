#!/usr/bin/env bash
# branch-reaper.sh — MERGED-BRANCH + STALE-WORKTREE REAPER (fleet hygiene, build-rig only).
#
# Gap-register B4 / QUICKWINS-LEVERAGE #7 ([[investigate-and-backup-before-data-loss]]):
# ~92 branches (~20 merged-but-undeleted) + stale git worktrees accrete forever. This script
# reaps both, idempotently, with DRY-RUN as the mandatory default given the delete blast radius.
#
# Two HARD data-loss guards (the exact risk the ticket name — the delete blast radius mandates):
#   1. MERGED-ONLY: a local branch is a candidate ONLY if `git branch --merged <base>` lists it
#      (minus base / current / protected). An unmerged branch NEVER appears in the candidate
#      list and is NEVER deleted. Deleting uses `git branch -D` (the `--merged` filter IS the
#      guard — reverting it to a bare `git branch` would reap unmerged branches, which the
#      self-test catches RED).
#   2. LIVE-CLAIM WORKTREE GUARD: a fleet worktree dir is removed ONLY if NO live marker exists
#      for its ticket id — neither state/claims/<id> (a droid actively working it) NOR
#      state/needs-push/<id> (committed-but-unlanded work). Either marker protects it
#      unconditionally. A worktree with a live claim is NEVER reaped.
#
# WHAT IT DOES (in order):
#   (0) git worktree prune        — clean admin metadata for already-gone worktree dirs.
#   (1) reap stale fleet worktree dirs (matching <wt-glob>) with no live claim marker.
#   (2) delete local branches merged into <base> (excluding base/current/protected).
#
# Usage: fleet/branch-reaper.sh [--apply]
#   --apply    actually perform deletions (default: DRY-RUN, print only)
# Env:
#   REAPER_REPO        git repo to operate on           (default /home/stack/code/charon)
#   REAPER_BASE        base ref for merge-check         (default master)
#   REAPER_FLEET_DIR   fleet dir containing state/      (default: this script's dir)
#   REAPER_WT_GLOB     glob for fleet worktree dirs     (default: <repo-dir>/<repo-base>-fleet-*)
#   REAPER_PROTECTED   extra protected branches (space) (default: 'main')
#
# TEST HOOK: set REAPER_* env vars to point at an isolated temp git repo fixture.
# See fleet/tests/branch-reaper.test.sh (FAIL-ON-REVERT: merged gone, unmerged KEPT,
# claimed worktree SURVIVES; GREEN-IS-NOT-PROOF: survival asserted, not just exit 0).
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAPER_REPO="${REAPER_REPO:-/home/stack/code/charon}"
REAPER_BASE="${REAPER_BASE:-master}"
REAPER_FLEET_DIR="${REAPER_FLEET_DIR:-$FLEET}"
REAPER_PROTECTED="${REAPER_PROTECTED:-main}"
if [ -z "${REAPER_WT_GLOB:-}" ]; then
  REAPER_WT_GLOB="$(dirname "$REAPER_REPO")/$(basename "$REAPER_REPO")-fleet-*"
fi

APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "branch-reaper: unknown argument '$arg' (expected --apply)" >&2; exit 2 ;;
  esac
done

[ -d "$REAPER_REPO/.git" ] || { echo "branch-reaper: not a git repo: $REAPER_REPO" >&2; exit 1; }

STATE="$REAPER_FLEET_DIR/state"
CLAIMS="$STATE/claims"; NEEDS_PUSH="$STATE/needs-push"
wt_prefix="${REAPER_WT_GLOB%\*}"

if [ "$APPLY" -eq 1 ]; then
  echo "branch-reaper: APPLY mode (deletions will occur)"
else
  echo "branch-reaper: DRY-RUN (pass --apply to actually reap)"
fi
echo "branch-reaper: repo=$REAPER_REPO base=$REAPER_BASE wt-glob=$REAPER_WT_GLOB"
echo

# ── (0) prune worktree admin metadata for already-gone dirs ──────────────────────
echo "== worktree prune =="
git -C "$REAPER_REPO" worktree prune 2>/dev/null && echo "  pruned" || echo "  nothing to prune"

# ── (1) reap stale fleet worktree dirs (no live claim) ───────────────────────────
echo "== stale fleet worktrees =="
reaped_wt=0; kept_wt=0
for wt_dir in $REAPER_WT_GLOB; do
  [ -d "$wt_dir" ] || continue
  [ "$wt_dir" = "$REAPER_REPO" ] && continue          # never the repo itself
  [ "$wt_dir" = "$(pwd)" ] && continue                 # never the current dir
  id="${wt_dir#$wt_prefix}"
  [ -n "$id" ] || continue
  if [ -e "$CLAIMS/$id" ] || [ -e "$NEEDS_PUSH/$id" ]; then
    echo "  KEEP   worktree $wt_dir (live marker for $id)"
    kept_wt=$((kept_wt+1))
    continue
  fi
  echo "  REAP   worktree $wt_dir (stale — no live claim for $id)"
  if [ "$APPLY" -eq 1 ]; then
    git -C "$REAPER_REPO" worktree remove --force "$wt_dir" 2>/dev/null || rm -rf "$wt_dir"
  fi
  reaped_wt=$((reaped_wt+1))
done
echo "  worktrees: $reaped_wt reaped, $kept_wt kept"
echo

# ── (2) reap merged local branches ───────────────────────────────────────────────
echo "== merged local branches (base=$REAPER_BASE) =="
cur_branch="$(git -C "$REAPER_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
protected="$REAPER_BASE $cur_branch $REAPER_PROTECTED"
reaped_br=0; kept_br=0
while IFS= read -r line; do
  branch="${line#\*}"                                  # strip current-branch marker
  branch="${branch#"${branch%%[![:space:]]*}"}"        # strip all leading whitespace
  branch="${branch%"${branch##*[![:space:]]}"}"        # strip all trailing whitespace
  [ -n "$branch" ] || continue
  case " $protected " in
    *" $branch "*) echo "  KEEP   branch $branch (protected)"; kept_br=$((kept_br+1)); continue ;;
  esac
  echo "  REAP   branch $branch (merged into $REAPER_BASE)"
  if [ "$APPLY" -eq 1 ]; then
    git -C "$REAPER_REPO" branch -D "$branch" >/dev/null 2>&1 || true
  fi
  reaped_br=$((reaped_br+1))
done < <(git -C "$REAPER_REPO" branch --merged "$REAPER_BASE" 2>/dev/null)
echo "  branches: $reaped_br reaped, $kept_br kept"
echo

echo "branch-reaper: done ($([ "$APPLY" = 1 ] && echo 'applied' || echo 'dry-run') — $reaped_br branch(es), $reaped_wt worktree(s) reaped; $kept_br branch(es), $kept_wt worktree(s) kept)."
exit 0
