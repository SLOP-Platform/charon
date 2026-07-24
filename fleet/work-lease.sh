#!/usr/bin/env bash
# work-lease.sh — Universal work-lease gate.
#
# Every session (manager subagent, off-Claude droid, or CG tab) must hold an atomic lease
# bound to an isolated worktree to touch a ticket; the main checkout is land/gate-only.
#
# ONE STORE, ONE LOCK (do NOT fork a second): the lease IS claim.sh's atomic claim —
# state/claims/<ticket>, guarded by the SAME flock on state/lock. A `claim.sh claim` and a
# `work-lease acquire` write the SAME file, so the two paths are mutually exclusive by
# construction: a ticket claimed by an off-Claude droid (claim.sh) makes a manager
# `work-lease acquire` REFUSE, and a ticket a manager holds a lease on is skipped by claim.sh
# (it is already in state/claims). This is the dispatch-time double-claim closure.
#
# Enforcement is at TWO boundaries:
#   1. DISPATCH — `acquire`/`dispatch` refuse to hand a ticket to a second builder. fleet-droid.sh
#      already acquires via claim.sh before launch; the manager ad-hoc path uses `dispatch`.
#   2. COMMIT   — pre-commit / commit-msg hooks refuse an un-leased worktree commit and refuse
#      work-commits in the main checkout. Auto-wired via `ensure` (fired by session-start.sh and
#      fleet-droid.sh), so a fresh checkout is NOT inert.
#
# Reuses claim.sh's flock + _lib.sh's ticket_for_branch resolver. Builds no second lock/store.
set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$FLEET/state"
CLAIMS="$STATE/claims"          # SINGLE store — same dir claim.sh writes (state/claims/<ticket>)
LOCK="$STATE/lock"              # SINGLE lock — same flock file claim.sh uses (state/lock)
STALE_S="${WORK_LEASE_STALE_S:-900}"

mkdir -p "$CLAIMS"
: >>"$LOCK" 2>/dev/null || true

# _lib.sh gives us the canonical branch->ticket resolver (ticket_for_branch, via each ticket's
# `branch:` field). REUSE it — do not hand-roll a second mapping. FLEET is set above as required.
# shellcheck source=/dev/null
[ -f "$FLEET/_lib.sh" ] && source "$FLEET/_lib.sh" 2>/dev/null || true

# ------------------------------------------------------------------ helpers
is_worktree() {
  local gd; gd="$(git rev-parse --git-dir 2>/dev/null)" || return 1
  case "$gd" in */worktrees/*) return 0;; esac; return 1
}
current_wt() { git rev-parse --show-toplevel 2>/dev/null || echo "$PWD"; }

# branch_to_ticket -> the ticket id this worktree's branch owns, or non-zero if UNMAPPED.
# Resolution order (adopt-first): _lib.sh's ticket_for_branch (matches the ticket `branch:` field,
# the canonical fleet mapping) -> a board/<branch>.md whose basename IS the branch. An UNMAPPED
# branch returns non-zero: the caller FAILS CLOSED (a worktree with no resolvable ticket is not a
# sanctioned work surface), never silently passes.
branch_to_ticket() {
  local br; br="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || return 1
  [ -n "$br" ] || return 1
  if declare -F ticket_for_branch >/dev/null 2>&1; then
    local tid; tid="$(ticket_for_branch "$br" 2>/dev/null)" || true
    [ -n "$tid" ] && { printf '%s' "$tid"; return 0; }
  fi
  [ -f "$FLEET/board/$br.md" ] && { printf '%s' "$br"; return 0; }
  return 1
}
lf() { echo "$CLAIMS/$1"; }

# claim_epoch <file> -> the freshest timestamp we can read for a claim/lease, as unix epoch.
#   1. a structured `heartbeat: <epoch>` line (work-lease format)
#   2. claim.sh's line-1 `<droid> <ISO8601Z>` — parse field 2
#   3. the file mtime (last resort)
# Used ONLY for STALE-reclaim decisions (acquire), never to refuse a holder's own commit.
claim_epoch() {
  local f="$1" hb ts
  hb="$(grep -m1 '^heartbeat:' "$f" 2>/dev/null | awk '{print $2}')" || hb=""
  if [ -n "$hb" ] && [ "$hb" -eq "$hb" ] 2>/dev/null; then echo "$hb"; return 0; fi
  ts="$(awk 'NR==1{print $2; exit}' "$f" 2>/dev/null)" || ts=""
  if [ -n "$ts" ]; then hb="$(date -d "$ts" +%s 2>/dev/null || echo "")"; [ -n "$hb" ] && { echo "$hb"; return 0; }; fi
  stat -c %Y "$f" 2>/dev/null || echo 0
}
lease_wt() { grep -m1 '^worktree:' "$1" 2>/dev/null | cut -d' ' -f2- || echo ""; }
lease_session() {
  local s; s="$(grep -m1 '^session:' "$1" 2>/dev/null | cut -d' ' -f2-)" || s=""
  [ -n "$s" ] && { echo "$s"; return 0; }
  awk 'NR==1{print $1; exit}' "$1" 2>/dev/null || echo "?"   # claim.sh line-1 droid fallback
}
write_lease() {   # write_lease <file> <ticket> <session> <worktree>
  cat > "$1" <<EOL
ticket: $2
session: $3
worktree: $4
heartbeat: $(date +%s)
claimed: $(date +%s)
EOL
}

# ---------------------------------------------------------- lease lifecycle
# acquire <ticket> [session] [worktree] — the DISPATCH gate. REFUSES if the ticket is already
# held by a LIVE lease in a DIFFERENT worktree (a second builder). Idempotent for the holder
# (same worktree re-acquires + heartbeats). A STALE lease (dead session) is reclaimable, so a
# crashed builder never permanently blocks the ticket.
cmd_acquire() {
  local ticket="${1:?acquire needs a ticket id}"
  local wt; wt="${3:-$(current_wt)}"
  local session="${2:-$(basename "$wt" 2>/dev/null || echo "session-$$")}"
  exec 9>"$LOCK"; flock 9
  local f; f="$(lf "$ticket")"
  if [ -f "$f" ]; then
    local ewt; ewt="$(lease_wt "$f")"
    if [ -n "$ewt" ] && [ "$ewt" = "$wt" ]; then
      sed -i "s/^heartbeat:.*/heartbeat: $(date +%s)/" "$f" 2>/dev/null || write_lease "$f" "$ticket" "$session" "$wt"
      echo "re-acquired $ticket ($session @ $wt)"; return 0
    fi
    local now age; now="$(date +%s)"; age=$(( now - $(claim_epoch "$f") ))
    if [ "$age" -lt "$STALE_S" ]; then
      local h; h="$(lease_session "$f")"
      echo "CONFLICT: '$ticket' already leased by '${h:-?}' @ '${ewt:-?}' (age ${age}s < ${STALE_S}s)" >&2
      return 1
    fi
    echo "reclaiming STALE lease on '$ticket' (age ${age}s >= ${STALE_S}s, prior holder presumed dead)" >&2
  fi
  write_lease "$f" "$ticket" "$session" "$wt"
  echo "leased $ticket ($session @ $wt)"
}

# check <ticket> — HOLDER-side validity: the claim exists AND (no worktree bound, OR it is bound
# to THIS worktree). Deliberately does NOT enforce staleness: a long-running holder must still be
# able to commit. Staleness gates RECLAIM (acquire), not the holder's own writes.
cmd_check() {
  local ticket="${1:?check needs a ticket id}"; local f; f="$(lf "$ticket")"
  [ -f "$f" ] || { echo "NO-LEASE: $ticket" >&2; return 1; }
  local wt; wt="$(lease_wt "$f")"
  local cwt; cwt="$(current_wt)"
  if [ -n "$wt" ] && [ "$cwt" != "$wt" ]; then
    echo "MISMATCH: $ticket bound to '$wt', cwd='$cwt'" >&2; return 1
  fi
  echo "VALID: $ticket ($(lease_session "$f"))"
}

# holds <ticket> — quiet predicate (exit 0 = this worktree holds a valid lease, 1 = not).
# The clean, callable interface CLAIM-LEASE-EXACTLY-ONCE composes with. No stdout on success.
cmd_holds() { cmd_check "$1" >/dev/null 2>&1; }

# bind <ticket> [worktree] [session] — enrich an EXISTING claim (e.g. one written by claim.sh as
# `<droid> <ISO-ts>`) with the worktree binding + a fresh heartbeat, so the commit-time worktree
# match has something to check against. Called by fleet-droid.sh right after it creates the
# worktree. Requires the claim to already exist (the claim IS the lease).
cmd_bind() {
  local ticket="${1:?bind needs a ticket id}"
  local wt; wt="${2:-$(current_wt)}"
  exec 9>"$LOCK"; flock 9
  local f; f="$(lf "$ticket")"
  [ -f "$f" ] || { echo "NO-CLAIM: $ticket (bind requires an existing claim; claim it first)" >&2; return 1; }
  local session="${3:-$(lease_session "$f")}"
  write_lease "$f" "$ticket" "$session" "$wt"
  echo "bound $ticket -> $wt ($session)"
}

# dispatch <ticket> [session] [worktree] [-- cmd ...] — the ONE command a manager uses to hand a
# ticket to an ad-hoc build subagent: acquire-or-REFUSE, then (optionally) exec the launch command
# after `--`. A launch for an already-leased ticket never runs.
cmd_dispatch() {
  local ticket="${1:?dispatch needs a ticket id}"; shift
  local session="" wt=""
  # optional positional session/worktree before the `--` launch separator
  if [ "${1:-}" != "--" ] && [ "$#" -gt 0 ]; then session="$1"; shift; fi
  if [ "${1:-}" != "--" ] && [ "$#" -gt 0 ]; then wt="$1"; shift; fi
  if ! cmd_acquire "$ticket" "$session" "$wt"; then
    echo "DISPATCH REFUSED: '$ticket' — a builder already holds this ticket; not launching a second." >&2
    return 1
  fi
  if [ "${1:-}" = "--" ]; then
    shift
    [ "$#" -gt 0 ] && exec "$@"
  fi
  echo "dispatch-ok: lease acquired for '$ticket' — safe to launch the builder."
}

cmd_release() {
  local ticket="${1:?release needs a ticket id}"
  exec 9>"$LOCK"; flock 9; rm -f "$(lf "$ticket")"
  echo "released $ticket"
}

cmd_heartbeat() {
  local ticket="${1:?heartbeat needs a ticket id}"
  exec 9>"$LOCK"; flock 9
  local f; f="$(lf "$ticket")"
  [ -f "$f" ] || { echo "NO-LEASE: $ticket" >&2; return 1; }
  if grep -q '^heartbeat:' "$f" 2>/dev/null; then
    sed -i "s/^heartbeat:.*/heartbeat: $(date +%s)/" "$f"
  else
    printf 'heartbeat: %s\n' "$(date +%s)" >> "$f"
  fi
  echo "heartbeat $ticket"
}

# -------------------------------------------------------- commit-boundary checks
is_sanctioned_msg() {
  local msgf="$1"; [ -f "$msgf" ] || return 1
  local l; l="$(head -1 "$msgf" 2>/dev/null || true)"
  case "$l" in land:*|*board-hygiene*) return 0;; esac; return 1
}

# pre-commit — in a WORKTREE, refuse a commit unless this session holds a valid lease on the
# worktree's ticket. FAIL CLOSED: if the branch maps to NO ticket, the worktree is not a
# sanctioned work surface -> REFUSE loudly (the old `|| return 0` passed unmapped branches
# SILENTLY, exactly the escape this gate exists to close).
cmd_pre_commit() {
  [ -z "${WORK_LEASE_BYPASS:-}" ] || return 0
  git rev-parse --git-dir >/dev/null 2>&1 || return 0
  is_worktree || return 0
  local ticket=""
  if ! ticket="$(branch_to_ticket 2>/dev/null)" || [ -z "$ticket" ]; then
    cat >&2 <<EOM
WORK-LEASE REFUSED: worktree branch '$(git rev-parse --abbrev-ref HEAD 2>/dev/null)' maps to NO board ticket.
  A worktree with no resolvable ticket is not a sanctioned work surface (fail-closed).
  Fix: give the ticket a 'branch:' field for this branch, or work under a mapped branch.
  Bypass (deliberate exception only): WORK_LEASE_BYPASS=1 git commit ...
EOM
    return 1
  fi
  if cmd_holds "$ticket"; then return 0; fi
  cat >&2 <<EOM
WORK-LEASE REFUSED: no valid lease for '$ticket' held by this worktree.
  Acquire: bash $FLEET/work-lease.sh acquire $ticket
  Bypass:  WORK_LEASE_BYPASS=1 git commit ...
EOM
  return 1
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
    return 1
  fi
  return 0
}

# -------------------------------------------------------- installation
_hook_targets() {
  # Hooks live in the COMMON git dir (git-common-dir), so ONE install covers the main checkout
  # AND every linked worktree. Resolve it for both the rig repo and the product repo when present.
  local targets=() gcd
  gcd="$(git -C "$FLEET" rev-parse --git-common-dir 2>/dev/null)" || gcd=""
  [ -n "$gcd" ] && { case "$gcd" in /*) :;; *) gcd="$FLEET/$gcd";; esac; targets+=("$gcd/hooks"); }
  if [ -d /home/stack/code/charon/.git ]; then
    local pgcd; pgcd="$(git -C /home/stack/code/charon rev-parse --git-common-dir 2>/dev/null)" || pgcd=""
    [ -n "$pgcd" ] && { case "$pgcd" in /*) :;; *) pgcd="/home/stack/code/charon/$pgcd";; esac; targets+=("$pgcd/hooks"); }
  fi
  printf '%s\n' "${targets[@]}"
}

cmd_install() {
  local hd
  while IFS= read -r hd; do
    [ -n "$hd" ] || continue
    mkdir -p "$hd"
    for hook in pre-commit commit-msg; do
      ln -sf "$FLEET/hooks/$hook" "$hd/$hook"
      echo "  $hd/$hook -> $FLEET/hooks/$hook"
    done
  done < <(_hook_targets)
  echo "work-lease hooks installed"
}

# ensure — idempotent auto-wire: install the hooks ONLY if not already the correct symlink.
# Fired automatically by session-start.sh (every session) and fleet-droid.sh (every droid),
# so the gate is NEVER inert on a fresh checkout — with no manual install step. Never fails a
# session boot: any error is swallowed (the caller invokes it with `|| true`).
cmd_ensure() {
  local hd changed=0
  while IFS= read -r hd; do
    [ -n "$hd" ] || continue
    mkdir -p "$hd" 2>/dev/null || continue
    for hook in pre-commit commit-msg; do
      if [ "$(readlink "$hd/$hook" 2>/dev/null)" != "$FLEET/hooks/$hook" ]; then
        ln -sf "$FLEET/hooks/$hook" "$hd/$hook" 2>/dev/null && changed=1
      fi
    done
  done < <(_hook_targets)
  [ "$changed" -eq 1 ] && echo "work-lease: hooks wired" || true
  return 0
}

cmd_uninstall() {
  local hd
  while IFS= read -r hd; do
    [ -n "$hd" ] || continue
    for hook in pre-commit commit-msg; do
      local t="$hd/$hook"
      if [ -L "$t" ] && [ "$(readlink "$t")" = "$FLEET/hooks/$hook" ]; then
        rm -f "$t"; echo "  removed $t"
      fi
    done
  done < <(_hook_targets)
  echo "work-lease hooks removed"
}

# ------------------------------------------------------------------ dispatch
cmd="${1:-}"; shift 2>/dev/null || true
case "$cmd" in
  acquire)       cmd_acquire "$@" ;;
  check)         cmd_check "$@" ;;
  holds)         cmd_holds "$@" ;;
  bind)          cmd_bind "$@" ;;
  dispatch)      cmd_dispatch "$@" ;;
  release)       cmd_release "$@" ;;
  heartbeat)     cmd_heartbeat "$@" ;;
  pre-commit)    cmd_pre_commit "$@" ;;
  commit-msg)    cmd_commit_msg "$@" ;;
  install)       cmd_install "$@" ;;
  ensure)        cmd_ensure "$@" ;;
  uninstall)     cmd_uninstall "$@" ;;
  *)             echo "Usage: $(basename "$0") {acquire|check|holds|bind|dispatch|release|heartbeat|pre-commit|commit-msg|install|ensure|uninstall}" >&2; exit 2 ;;
esac
