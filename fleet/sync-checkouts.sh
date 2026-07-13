#!/usr/bin/env bash
# sync-checkouts.sh — keep the fleet's LOCAL main checkouts' master current with origin,
# FF-only and DIRTY-SAFE (never reset/clean/merge; skips loudly if tracked changes exist).
# Recurring problem: local master drifts stale (builders branch off origin, but the manager's
# board work + the rig's runtime invocation of the product engine use the LOCAL checkout).
# Run on a sensible schedule (SessionStart hook + before firing a build wave).
set -uo pipefail

sync_one() {
  local repo="$1" name="$2"
  git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 || { echo "sync[$name]: not a repo ($repo)"; return 0; }
  git -C "$repo" fetch origin --quiet 2>/dev/null || { echo "sync[$name]: fetch FAILED"; return 0; }
  local behind; behind=$(git -C "$repo" rev-list --count master..origin/master 2>/dev/null || echo 0)
  if [ "${behind:-0}" = "0" ]; then echo "sync[$name]: master current"; return 0; fi
  # DIRTY GUARD (tracked only): never FF over uncommitted tracked work
  if [ -n "$(git -C "$repo" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    echo "sync[$name]: $behind behind, but TRACKED changes present — SKIP (commit/land first)"; return 0
  fi
  # DIVERGENCE GUARD: only FF when local master is an ancestor of origin/master
  if ! git -C "$repo" merge-base --is-ancestor master origin/master 2>/dev/null; then
    echo "sync[$name]: master DIVERGED from origin — SKIP (manual reconcile)"; return 0
  fi
  # FF via detach + ref-fetch (no merge/reset/clean); untracked files survive
  local cur; cur=$(git -C "$repo" symbolic-ref --short HEAD 2>/dev/null || echo master)
  git -C "$repo" checkout --quiet --detach 2>/dev/null || { echo "sync[$name]: detach failed"; return 0; }
  if git -C "$repo" fetch origin master:master --quiet 2>/dev/null; then
    git -C "$repo" checkout --quiet master 2>/dev/null
    echo "sync[$name]: master FF'd +$behind → $(git -C "$repo" rev-parse --short master)"
  else
    git -C "$repo" checkout --quiet "$cur" 2>/dev/null; echo "sync[$name]: FF fetch failed — manual"
  fi
}

# Env overrides exist ONLY so tests (fleet/tests/session-start-hook.test.sh) can point this
# at throwaway repos instead of the real checkouts. Defaults are unchanged in normal operation.
sync_one "${SYNC_CHECKOUTS_PRODUCT:-/home/stack/code/charon}"    product
sync_one "${SYNC_CHECKOUTS_PRIV:-/home/stack/charon-private}"    rig
