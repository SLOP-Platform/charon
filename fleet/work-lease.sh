#!/usr/bin/env bash
# work-lease.sh — Universal work-lease gate.
#
# Every session (manager subagent or CG tab) must hold an atomic lease bound to an
# isolated worktree to touch a ticket; the main checkout is land/gate-only.
# Enforced at commit time via pre-commit + commit-msg hooks.
# Reuses claim.sh's flock + stale-check.sh's liveness. Does NOT build a second lock.
set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$FLEET/state"
LEASES="$STATE/leases"
LOCK="$STATE/lock"
STALE_S="${WORK_LEASE_STALE_S:-900}"

mkdir -p "$LEASES"

# ------------------------------------------------------------------ helpers
is_worktree() {
  local gd; gd="$(git rev-parse --git-dir 2>/dev/null)" || return 1
  case "$gd" in */worktrees/*) return 0;; esac; return 1
}
current_wt() { git rev-parse --show-toplevel 2>/dev/null || echo "$PWD"; }
branch_to_ticket() {
  local br; br="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || return 1
  if command -v ticket_for_branch >/dev/null 2>&1; then
    local tid; tid="$(ticket_for_branch "$br" 2>/dev/null)" || true
    [ -n "$tid" ] && { echo "$tid"; return 0; }
  fi
  [ -f "$FLEET/board/$br.md" ] && { echo "$br"; return 0; }
  return 1
}
lf() { echo "$LEASES/$1"; }

# ---------------------------------------------------------- lease lifecycle
cmd_acquire() {
  local ticket="$1"
  local session="${2:-$(basename "$(current_wt)" 2>/dev/null || echo "session-$$")}"
  local wt; wt="$(current_wt)"
  exec 9>"$LOCK"; flock 9
  local f; f="$(lf "$ticket")"
  if [ -f "$f" ]; then
    local h; h="$(grep -m1 '^session:' "$f" 2>/dev/null | cut -d' ' -f2)"
    echo "CONFLICT: '$ticket' already leased by '${h:-?}'" >&2; exit 1
  fi
  cat > "$f" <<EOL
ticket: $ticket
session: $session
worktree: $wt
heartbeat: $(date +%s)
claimed: $(date +%s)
EOL
  echo "leased $ticket ($session @ $wt)"
}

cmd_check() {
  local ticket="$1"; local f; f="$(lf "$ticket")"
  [ -f "$f" ] || { echo "NO-LEASE: $ticket" >&2; exit 1; }
  local hb; hb="$(grep -m1 '^heartbeat:' "$f" 2>/dev/null | cut -d' ' -f2-)" || hb=0
  local now; now="$(date +%s)"; local age=$((now - hb))
  [ "$age" -lt "$STALE_S" ] || { echo "STALE: $ticket (${age}s > ${STALE_S}s)" >&2; exit 1; }
  local wt; wt="$(grep -m1 '^worktree:' "$f" 2>/dev/null | cut -d' ' -f2-)" || wt=""
  local cwt; cwt="$(current_wt)"
  [ -z "$wt" ] || [ "$cwt" = "$wt" ] || { echo "MISMATCH: $ticket bound to '$wt', cwd='$cwt'" >&2; exit 1; }
  local sid; sid="$(grep -m1 '^session:' "$f" 2>/dev/null | cut -d' ' -f2-)" || sid="?"
  echo "VALID: $ticket ($sid, age=${age}s)"
}

cmd_release() {
  local ticket="$1"
  exec 9>"$LOCK"; flock 9; rm -f "$(lf "$ticket")"
  echo "released $ticket"
}

cmd_heartbeat() {
  local ticket="$1"
  exec 9>"$LOCK"; flock 9
  local f; f="$(lf "$ticket")"
  [ -f "$f" ] || { echo "NO-LEASE: $ticket" >&2; exit 1; }
  sed -i "s/^heartbeat:.*/heartbeat: $(date +%s)/" "$f"
  echo "heartbeat $ticket"
}

# -------------------------------------------------------- commit-boundary checks
is_sanctioned_msg() {
  local msgf="$1"; [ -f "$msgf" ] || return 1
  local l; l="$(head -1 "$msgf" 2>/dev/null || true)"
  case "$l" in land:*|*board-hygiene*) return 0;; esac; return 1
}

cmd_pre_commit() {
  [ -z "${WORK_LEASE_BYPASS:-}" ] || return 0
  git rev-parse --git-dir >/dev/null 2>&1 || return 0
  if is_worktree; then
    local ticket=""
    ticket="$(branch_to_ticket 2>/dev/null)" || return 0
    if cmd_check "$ticket" >/dev/null 2>&1; then return 0; fi
    cat >&2 <<EOM
WORK-LEASE REFUSED: no valid lease for '$ticket'
  Acquire: bash $FLEET/work-lease.sh acquire $ticket
  Bypass:  WORK_LEASE_BYPASS=1 git commit ...
EOM
    exit 1
  fi
  return 0
}

cmd_commit_msg() {
  [ -z "${WORK_LEASE_BYPASS:-}" ] || return 0
  git rev-parse --git-dir >/dev/null 2>&1 || return 0
  if ! is_worktree; then
    local msgf="${1:?commit-msg needs message file}"
    if is_sanctioned_msg "$msgf"; then return 0; fi
    cat >&2 <<EOM
WORK-LEASE REFUSED: main checkout not a work surface
  Commit message must start with 'land:' or include 'board-hygiene'.
  Work in a leased worktree.
  Bypass:  WORK_LEASE_BYPASS=1 git commit ...
EOM
    exit 1
  fi
  return 0
}

# -------------------------------------------------------- installation
cmd_install() {
  local targets=("$FLEET")
  [ -d /home/stack/code/charon/.git/hooks ] && targets+=("/home/stack/code/charon")
  for repo in "${targets[@]}"; do
    local hd="$repo/.git/hooks"
    for hook in pre-commit commit-msg; do
      ln -sf "$FLEET/hooks/$hook" "$hd/$hook"
      echo "  $hd/$hook -> $FLEET/hooks/$hook"
    done
  done
  echo "work-lease hooks installed"
}

cmd_uninstall() {
  local targets=("$FLEET")
  [ -d /home/stack/code/charon/.git/hooks ] && targets+=("/home/stack/code/charon")
  for repo in "${targets[@]}"; do
    local hd="$repo/.git/hooks"
    for hook in pre-commit commit-msg; do
      local t="$hd/$hook"
      if [ -L "$t" ] && [ "$(readlink "$t")" = "$FLEET/hooks/$hook" ]; then
        rm -f "$t"; echo "  removed $t"
      fi
    done
  done
  echo "work-lease hooks removed"
}

# ------------------------------------------------------------------ dispatch
cmd="${1:-}"; shift 2>/dev/null || true
case "$cmd" in
  acquire)       cmd_acquire "$@" ;;
  check)         cmd_check "$@" ;;
  release)       cmd_release "$@" ;;
  heartbeat)     cmd_heartbeat "$@" ;;
  pre-commit)    cmd_pre_commit "$@" ;;
  commit-msg)    cmd_commit_msg "$@" ;;
  install)       cmd_install "$@" ;;
  uninstall)     cmd_uninstall "$@" ;;
  *)             echo "Usage: $(basename "$0") {acquire|check|release|heartbeat|pre-commit|commit-msg|install|uninstall}" >&2; exit 2 ;;
esac
