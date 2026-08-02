#!/usr/bin/env bash
# preserve-unpushed.sh — PUBLISH a droid's committed-but-unpushed work BEFORE the worktree is
# torn down, so a tab that ends early can never leave commits on one disk only.
#
# THE DEFECT THIS CLOSES (measured 2026-08-01, five frontier tabs). The launcher's gate ran under
# `set -euo pipefail`; a RED gate unwound the tab mid-ticket (fixed separately — see
# fleet/tests/launcher-gate-sete-kill.test.sh). The EXIT trap `cleanup()` then reached
# `safe_worktree_remove`, which correctly REFUSED:
#     leak-guard: REFUSING to remove <wt> — 1 commit(s) on HEAD are not on any remote (unpushed
#     work). Nothing removed; resolve by hand.
# The refusal is right and must never be weakened — it is the last thing standing between a real
# commit and an `rm -rf`. But it is a SYMPTOM report, not a remedy: the droid had already
# committed, the tab was already going away, and nobody had published the branch. The manager had
# to rescue those commits by hand. The launcher was MANUFACTURING stranded work.
#
# The remedy is ordering, not tolerance: publish FIRST, then let the guard evaluate a branch that
# is genuinely safe to drop. After a successful push the "not on any remote" condition is FALSE by
# construction, so leak-guard stops refusing for the right reason instead of being talked out of it.
#
# EXISTING MECHANISM ONLY — nothing new is invented here:
#   * the durable record is `state/needs-push/<id>`, the marker convention `cleanup()` already
#     writes for its auto-commit path and that `safe_worktree_remove` already refuses on;
#   * the publish call is the same `git push -u origin <branch>` the launcher's happy path uses
#     (fleet-droid.sh, submit path) and that fleet/rescue-push.sh uses to rescue at-risk branches;
#   * the operator's recovery path when the push cannot happen is the existing
#     `fleet/land-needs-push.sh <id>`, which is exactly what the marker is for.
#
# The marker is written BEFORE the push is attempted, never after: if this process is killed
# mid-push the durable record already exists. It is removed only once the commits are provably on
# a remote, because the marker's whole job is to say "work exists that only this disk has".
#
# A feature branch is the ONLY push target. This never touches master and never force-pushes:
# publishing a droid's own branch is purely additive and cannot destroy anything on the remote.
#
# Usage:  preserve-unpushed.sh <repo> <worktree> <branch> <id> <needs_push_dir>
# Exit:   0  nothing was unpushed, or the work is now published — safe to tear the worktree down
#         1  unpushed commits remain; the needs-push marker is live — DO NOT tear the worktree down
#         2  bad usage
#
# Run:    bash fleet/tests/preserve-unpushed.test.sh
set -uo pipefail

[ "$#" -eq 5 ] || { echo "usage: preserve-unpushed.sh <repo> <worktree> <branch> <id> <needs_push_dir>" >&2; exit 2; }
repo="$1"; wt="$2"; branch="$3"; id="$4"; npdir="$5"

[ -d "$wt" ] || { echo "preserve-unpushed: worktree '$wt' is gone — nothing to preserve." >&2; exit 0; }

# SAME PREDICATE leak-guard's _lg_wt_target_ok refuses on ("N commit(s) on HEAD are not on any
# remote"), so this step and the guard can never disagree about what counts as unpushed work.
# FAIL CLOSED: a count we cannot read is treated as "there IS unpushed work" — the expensive
# mistake is deciding there is nothing to save when there is.
unpushed="$(git -C "$wt" rev-list --count HEAD --not --remotes 2>/dev/null)"
case "$unpushed" in ''|*[!0-9]*) unpushed=1 ;; esac
if [ "$unpushed" -eq 0 ]; then
  echo "preserve-unpushed: $id — every commit on '$branch' is already on a remote; nothing to publish."
  exit 0
fi

# Durable record FIRST — a kill between here and the push must still leave the manager a marker.
mkdir -p "$npdir" 2>/dev/null || true
printf 'branch=%s\nworktree=%s\nrepo=%s\nreason=%s commit(s) committed but not on any remote at stand-down\nflagged=%s\n' \
  "$branch" "$wt" "$repo" "$unpushed" "$(date -u +%FT%TZ)" > "$npdir/$id" 2>/dev/null || true

echo "preserve-unpushed: $id — $unpushed commit(s) on '$branch' exist only on this disk; publishing before cleanup."
if git -C "$wt" push -u origin "$branch" >/dev/null 2>&1; then
  # Re-ASK, do not assume: `push` can exit 0 having published nothing the guard cares about
  # (wrong refspec, a hook that swallowed it). The marker is cleared only against a re-read count.
  after="$(git -C "$wt" rev-list --count HEAD --not --remotes 2>/dev/null)"
  case "$after" in ''|*[!0-9]*) after=1 ;; esac
  if [ "$after" -eq 0 ]; then
    rm -f "$npdir/$id" 2>/dev/null || true
    echo "preserve-unpushed: $id — published '$branch'; work is on the remote. Cleanup may proceed."
    exit 0
  fi
  echo "preserve-unpushed: $id — push exited 0 but $after commit(s) are STILL on no remote; keeping the needs-push marker." >&2
else
  echo "preserve-unpushed: $id — push of '$branch' FAILED; work stays on disk and the needs-push marker is live." >&2
fi
echo "preserve-unpushed: recover with:  bash fleet/land-needs-push.sh $id" >&2
exit 1
