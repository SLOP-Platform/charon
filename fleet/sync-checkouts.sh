#!/usr/bin/env bash
# sync-checkouts.sh — keep the fleet's LOCAL main checkouts' master current with origin,
# FF-only and DIRTY-SAFE (never reset/clean/merge; skips loudly if tracked changes exist).
# Recurring problem: local master drifts stale (builders branch off origin, but the manager's
# board work + the rig's runtime invocation of the product engine use the LOCAL checkout).
# Run on a sensible schedule (SessionStart hook + before firing a build wave).
#
# THIS RUNS ON THE SESSION-START CRITICAL PATH (fleet/hooks/session-start.sh AND
# fleet/preflight.sh's `scan` dispatch). Three properties are load-bearing and each has a
# fail-on-revert test in fleet/tests/sync-checkouts.test.sh:
#
#   (1) NEVER MOVES HEAD. The old success path ran `checkout master` unconditionally, so a
#       checkout sitting on a feature branch was silently flipped onto master while logging
#       "master FF'd" as though it had succeeded — mid-session, against main checkouts shared
#       by every concurrent worktree. A `master:master` refspec fetch does not need master to
#       be checked out, so when HEAD is NOT on master we now do NO checkout at all. When HEAD
#       IS on master we detach, fetch, and restore master — and if the restore fails we say so
#       LOUDLY rather than leaving the operator silently on a different HEAD.
#   (2) NEVER BLOCKS. Both fetches are wrapped in `timeout`, run with GIT_TERMINAL_PROMPT=0 and
#       a non-interactive BatchMode ssh, and carry http.lowSpeedLimit so a half-open HTTPS
#       connection cannot stall forever. A session-start command that HANGS with no output is
#       strictly worse than one that fails; every bounded failure prints its reason. The fetch
#       output is redirected to a temp file rather than captured with `$( )`, so a transport
#       grandchild that survives the timeout's SIGTERM cannot hold the call open past its
#       budget while printing a "TIMED OUT" receipt that was not true — see _git_fetch.
#   (3) NEVER SILENTLY EXITS NON-ZERO. Every branch returns 0 — callers chain this in a `;`
#       list and it must not abort the dispatch.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- NON-INTERACTIVE + BOUNDED NETWORK (property 2) ----------------------------------------
# GIT_TERMINAL_PROMPT=0 turns a credential prompt (private repo / revoked anon read) into an
# immediate error instead of an indefinite read on /dev/tty — which `2>/dev/null` does NOT
# suppress. BatchMode=yes does the same for a passphrase-protected key or a changed host key.
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=5}"
SYNC_FETCH_TIMEOUT="${SYNC_CHECKOUTS_FETCH_TIMEOUT:-20}"
SYNC_LOCK_WAIT="${SYNC_CHECKOUTS_LOCK_WAIT:-10}"
SYNC_LOCK_DIR="${SYNC_CHECKOUTS_LOCK_DIR:-${TMPDIR:-/tmp}}"
TIMEOUT_BIN="$(command -v timeout || true)"
FLOCK_BIN="$(command -v flock || true)"

# _git_fetch <repo> <name> <label> [fetch args...] -> 0 on success; 1 on ANY bounded failure,
# always with a printed reason (never silent).
_git_fetch(){
  local repo="$1" name="$2" label="$3"; shift 3
  local rc=0 err="" tmp t0 el
  # R1 — DO NOT capture with $( ). `timeout` signals only its direct child (git), not the whole
  # process group, so a transport grandchild that ignores SIGTERM survives. Command substitution
  # blocks until EVERY writer to that pipe closes it, inherited grandchildren included, so such a
  # survivor held this call ~46s past a 3s budget WHILE PRINTING "TIMED OUT after 3s" — hung and
  # reporting the bound worked. Redirecting to a temp file ties our return to the direct child
  # only, so the bound we print is the bound we actually enforced. Fail-on-revert test: (B4).
  tmp="$(mktemp "${TMPDIR:-/tmp}/sync-fetch.XXXXXX" 2>/dev/null)" || tmp=""
  t0=$SECONDS
  # GIT_ASKPASS/SSH_ASKPASS blanked and core.askpass emptied: defence in depth beside
  # GIT_TERMINAL_PROMPT=0 — an inherited askpass helper is a second way to reach an
  # indefinite interactive read, and one that may block signals.
  if [ -n "$TIMEOUT_BIN" ]; then
    GIT_ASKPASS= SSH_ASKPASS= "$TIMEOUT_BIN" -k 5 "$SYNC_FETCH_TIMEOUT" \
      git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=10 -c core.askpass= \
          -C "$repo" fetch --quiet "$@" >"${tmp:-/dev/null}" 2>&1 || rc=$?
  else
    # No coreutils timeout: the git-level low-speed guard is all we have. Say so — a missing
    # bound is exactly the condition this script must not hide.
    echo "sync[$name]: WARN — 'timeout' not on PATH, $label is only guarded by http.lowSpeedTime"
    GIT_ASKPASS= SSH_ASKPASS= \
      git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=10 -c core.askpass= \
          -C "$repo" fetch --quiet "$@" >"${tmp:-/dev/null}" 2>&1 || rc=$?
  fi
  el=$(( SECONDS - t0 ))
  [ -n "$tmp" ] && { err="$(cat "$tmp" 2>/dev/null)"; rm -f "$tmp"; }
  case "$rc" in
    0) return 0 ;;
    124|137)
      # Elapsed is printed, not assumed: if the bound is ever escaped again the receipt says so.
      echo "sync[$name]: $label TIMED OUT after ${SYNC_FETCH_TIMEOUT}s (elapsed ${el}s; remote unreachable, or auth would have prompted) — SKIP"
      return 1 ;;
    *)
      echo "sync[$name]: $label FAILED rc=$rc${err:+ — ${err%%$'\n'*}}"
      return 1 ;;
  esac
}

sync_one() {
  local repo="$1" name="$2"
  git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 || { echo "sync[$name]: not a repo ($repo)"; return 0; }
  _git_fetch "$repo" "$name" "fetch" origin || return 0
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

  # FF via ref-fetch (no merge/reset/clean); untracked files survive.
  local cur; cur=$(git -C "$repo" symbolic-ref --short HEAD 2>/dev/null || echo "")
  if [ "$cur" != "master" ]; then
    # HEAD is on a FEATURE BRANCH (or already detached): master is not checked out, so the
    # refspec fetch updates it with HEAD untouched. NO checkout — nothing can be flipped.
    if _git_fetch "$repo" "$name" "FF fetch" origin master:master; then
      echo "sync[$name]: master FF'd +$behind → $(git -C "$repo" rev-parse --short master 2>/dev/null) (HEAD left on ${cur:-detached HEAD})"
    else
      echo "sync[$name]: FF fetch failed — manual (HEAD left on ${cur:-detached HEAD})"
    fi
    return 0
  fi

  # HEAD IS on master: git refuses to fetch into the checked-out branch, so detach first —
  # then ALWAYS restore master, on both the success and the failure path.
  git -C "$repo" checkout --quiet --detach 2>/dev/null || { echo "sync[$name]: detach failed"; return 0; }
  local frc=0
  _git_fetch "$repo" "$name" "FF fetch" origin master:master || frc=1
  if git -C "$repo" checkout --quiet master 2>/dev/null; then
    if [ "$frc" = 0 ]; then
      echo "sync[$name]: master FF'd +$behind → $(git -C "$repo" rev-parse --short master 2>/dev/null)"
    else
      echo "sync[$name]: FF fetch failed — manual (HEAD restored to master)"
    fi
  else
    # Loud, on stderr, with the exact recovery command. Never report success for a state
    # change the caller did not ask for.
    echo "sync[$name]: !! COULD NOT RESTORE HEAD — $repo is left DETACHED at $(git -C "$repo" rev-parse --short HEAD 2>/dev/null). Recover with: git -C $repo checkout master" >&2
  fi
  return 0
}

# sync_guarded — sync_one under a per-repo flock. ~70 live worktrees share these two main
# checkouts and `preflight.sh scan` runs from any of them, so two concurrent scans could
# otherwise interleave detach/fetch/checkout on the same repo (index.lock contention, and a
# window where another process reads a detached HEAD). Degrades to an unlocked run — with a
# printed reason — when flock or the lock dir is unavailable.
sync_guarded(){
  local repo="$1" name="$2" key lf
  if [ -z "$FLOCK_BIN" ]; then
    echo "sync[$name]: WARN — 'flock' not on PATH, running UNLOCKED (concurrent scans may race)"
    sync_one "$repo" "$name"; return 0
  fi
  key="$(printf '%s' "$repo" | tr -c 'A-Za-z0-9' '-')"
  lf="$SYNC_LOCK_DIR/sync-checkouts$key.lock"
  if ! : >>"$lf" 2>/dev/null; then
    echo "sync[$name]: WARN — cannot open lock $lf, running UNLOCKED"
    sync_one "$repo" "$name"; return 0
  fi
  (
    if "$FLOCK_BIN" -w "$SYNC_LOCK_WAIT" 9; then
      sync_one "$repo" "$name"
    else
      echo "sync[$name]: another sync holds the lock (>${SYNC_LOCK_WAIT}s) — SKIP this pass"
    fi
  ) 9>>"$lf"
  return 0
}

# PATHS: derived from fleet/repo-registry.sh, the rig's path SSOT — never re-hardcoded here
# (standing no-hardcoded-cross-boundary-paths rule). Env overrides exist so tests
# (fleet/tests/sync-checkouts.test.sh, fleet/tests/session-start-hook.test.sh) can point this
# at throwaway repos. Defaults are unchanged in normal operation.
_registry_path(){
  ( # subshell: keep the registry's RR_* globals out of this script's namespace
    # shellcheck source=/dev/null
    source "$HERE/repo-registry.sh" 2>/dev/null || exit 0
    repo_resolve "$1" "" >/dev/null 2>&1 || exit 0
    printf '%s' "${RR_PATH:-}"
  )
}
PRODUCT="${SYNC_CHECKOUTS_PRODUCT:-$(_registry_path charon)}"
PRIV="${SYNC_CHECKOUTS_PRIV:-$(_registry_path rig)}"

if [ -n "$PRODUCT" ]; then sync_guarded "$PRODUCT" product
else echo "sync[product]: WARN — no path from repo-registry.sh and no SYNC_CHECKOUTS_PRODUCT override — SKIP"; fi
if [ -n "$PRIV" ]; then sync_guarded "$PRIV" rig
else echo "sync[rig]: WARN — no path from repo-registry.sh and no SYNC_CHECKOUTS_PRIV override — SKIP"; fi
exit 0
