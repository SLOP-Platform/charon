#!/usr/bin/env bash
# session-start.sh — SessionStart hook (SYNC-SCHEDULE): mechanized anti-clobber gate.
#
# WHY: a session's bootstrap can read a STALE handoff when (a) the local checkout has
# drifted behind origin (the real handoff arrived via a merged PR the local master never
# pulled) and (b) the staleness check compares against a hardcoded ref that doesn't exist
# on this repo (see check_push_status.sh fix — origin/main on a master-default repo),
# so the false-green "up to date" banner hides the drift. This hook is the primary
# clobber-prevention: it FF-syncs local master to origin FIRST (dirty-safe, via
# sync-checkouts.sh), then reports freshness against the REAL resolved upstream — never a
# hardcoded branch name. If a repo is behind AND could not be fast-forwarded (dirty or
# diverged), it prints a loud STALE banner instead of a quiet checkmark.
#
# Wired into /home/stack/.claude/settings.json SessionStart hooks (added alongside the
# existing three entries — see check_push_status.sh, update_tasklist.py, update_wavemap.py).
#
# Usage: bash /home/stack/charon-private/fleet/hooks/session-start.sh
#
# Test hooks (used only by fleet/tests/session-start-hook.test.sh; never in normal operation):
#   SESSION_START_PRODUCT=<repo>   override the "product" repo path (default /home/stack/code/charon)
#   SESSION_START_PRIV=<repo>      override the "rig" repo path (default /home/stack/charon-private)
#   SESSION_START_SYNC_SH=<path>   override the sync script invoked first (default fleet/sync-checkouts.sh)
set -uo pipefail

FLEET="${SESSION_START_FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PRODUCT="${SESSION_START_PRODUCT:-/home/stack/code/charon}"
PRIV="${SESSION_START_PRIV:-/home/stack/charon-private}"
SYNC_SH="${SESSION_START_SYNC_SH:-$FLEET/sync-checkouts.sh}"

# WORK-LEASE auto-wire (gates-must-actually-run): install the commit-boundary hooks idempotently
# on every session boot, so the work-lease gate is never inert on a fresh checkout and needs no
# manual `work-lease.sh install`. Never blocks boot (swallow all errors).
bash "$FLEET/work-lease.sh" ensure 2>/dev/null || true

echo "== session-start: syncing local checkouts (FF-only, dirty-safe) =="
if [ -f "$SYNC_SH" ]; then
  bash "$SYNC_SH" 2>&1
else
  echo "session-start: WARN — sync script not found ($SYNC_SH), skipping sync"
fi

# Resolve the REAL upstream — never a hardcoded branch name (see check_push_status.sh's
# origin/main false-pass on master-default repos, which is the root cause this hook exists
# to prevent). Prefer the branch's own tracking ref; fall back to origin/HEAD's default branch.
resolve_upstream() {
  local repo="$1" u
  u=$(git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null) || u=""
  if [ -z "$u" ]; then
    u=$(git -C "$repo" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/@@')
  fi
  printf '%s' "$u"
}

any_stale=0

report_one() {
  local repo="$1" name="$2"
  if ! git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
    echo "[$name] not a git repo ($repo)"
    return
  fi
  git -C "$repo" fetch --quiet origin 2>/dev/null || true
  local upstream; upstream="$(resolve_upstream "$repo")"
  if [ -z "$upstream" ]; then
    echo "[$name] WARN: could not resolve upstream (no @{u}, no origin/HEAD) — cannot verify freshness"
    any_stale=1
    return
  fi
  local behind ahead dirty
  behind=$(git -C "$repo" rev-list --count "HEAD..$upstream" 2>/dev/null || echo 0)
  ahead=$(git -C "$repo" rev-list --count "$upstream..HEAD" 2>/dev/null || echo 0)
  dirty=$(git -C "$repo" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')
  if [ "${behind:-0}" -gt 0 ]; then
    any_stale=1
    echo ""
    echo "######################################################################"
    echo "# STALE — [$name] $repo is $behind commit(s) behind $upstream"
    if [ "${dirty:-0}" -gt 0 ]; then
      echo "#   ...and has $dirty uncommitted tracked change(s) — sync-checkouts.sh could NOT fast-forward"
    else
      echo "#   sync-checkouts.sh could not fast-forward this (diverged, or fetch failed) — reconcile manually"
    fi
    echo "#   RECONCILE BEFORE TRUSTING ANY HANDOFF: git -C $repo log HEAD..$upstream --oneline"
    echo "######################################################################"
    echo ""
  else
    local aheadmsg=""
    [ "${ahead:-0}" -gt 0 ] && aheadmsg=", $ahead ahead (unpushed)"
    echo "[$name] OK — current with $upstream ($(git -C "$repo" rev-parse --short HEAD 2>/dev/null)${aheadmsg})"
  fi
}

report_one "$PRODUCT" "product"
report_one "$PRIV" "rig"

if [ "$any_stale" -eq 0 ]; then
  echo "session-start: all repos current — safe to trust the latest committed handoff."
else
  echo "session-start: >>> STALE repo(s) detected above — do NOT trust a handoff until reconciled. <<<"
fi

# SessionStart graphify refresh: keep the code map fresh on every session boot.
# Mechanized auto-refresh — a stale map is a reinvention risk (WIRE-GRAPHIFY-FRESHNESS
# contract, checks/graphify-freshness.sh).
GRAPHIFY_FRESHNESS_SH="$FLEET/checks/graphify-freshness.sh"
if [ -f "$GRAPHIFY_FRESHNESS_SH" ]; then
  echo "session-start: refreshing graphify code maps..."
  bash "$GRAPHIFY_FRESHNESS_SH" update 2>&1 || true
fi

# This is a SessionStart hook: never block session boot on repo drift. The banner above is
# the signal; the operator/session reconciles. (settings.json also wraps the call in `|| true`.)
exit 0
