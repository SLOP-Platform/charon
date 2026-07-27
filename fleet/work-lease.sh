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
# Enforcement is at THREE boundaries (earliest first — late enforcement IS the defect):
#   0. CREATION — `guard-branch <branch>` refuses a worktree/branch that maps to NO board ticket,
#      BEFORE the worktree exists. Wired into fleet-droid.sh's dispatch loop. Without it the same
#      requirement was only discovered at (2), after the whole build was already done.
#   1. DISPATCH — `acquire`/`dispatch` refuse to hand a ticket to a second builder. fleet-droid.sh
#      already acquires via claim.sh before launch; the manager ad-hoc path uses `dispatch`.
#   2. COMMIT   — pre-commit / commit-msg hooks refuse an un-leased worktree commit and refuse
#      work-commits in the main checkout. Auto-wired via `ensure` (fired by session-start.sh and
#      fleet-droid.sh), so a fresh checkout is NOT inert.
#
# Reuses claim.sh's flock + _lib.sh's ticket_for_branch resolver. Builds no second lock/store.
set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ONE STORE ACROSS WORKTREES (WORK-LEASE-WORKTREE-RESOLVE accept-1).
# `fleet/state/*` is .gitignored, so every linked worktree starts with its OWN empty
# state/claims/. Deriving the store from $FLEET therefore SPLIT it: an `acquire` run from a
# worktree's copy of this script wrote <worktree>/fleet/state/claims/<t>, while the pre-commit
# hook (a symlink resolving to the MAIN checkout's fleet/hooks/*) read <main>/fleet/state/claims/
# — so a lease could be acquired successfully and the very next commit still REFUSED.
# Resolve the store from `git rev-parse --git-common-dir`, which is IDENTICAL for the main
# checkout and every linked worktree, so both agree on one store and one lock.
# Falls back to $FLEET when $FLEET is not inside a git repo (hermetic tests) or the common dir's
# parent holds no fleet/ — never silently points at a directory that is not a fleet root.
_state_root() {
  if [ -n "${WORK_LEASE_STATE_ROOT:-}" ]; then printf '%s' "$WORK_LEASE_STATE_ROOT"; return 0; fi
  local gcd root
  gcd="$(git -C "$FLEET" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" \
    || gcd="$(git -C "$FLEET" rev-parse --git-common-dir 2>/dev/null)" || gcd=""
  if [ -n "$gcd" ]; then
    case "$gcd" in /*) :;; *) gcd="$(cd "$FLEET" && cd "$gcd" 2>/dev/null && pwd)" || gcd="";; esac
  fi
  if [ -n "$gcd" ]; then
    root="$(cd "$gcd/.." 2>/dev/null && pwd)" || root=""
    if [ -n "$root" ] && [ -f "$root/fleet/work-lease.sh" ]; then printf '%s' "$root/fleet"; return 0; fi
  fi
  printf '%s' "$FLEET"
}
STATE_ROOT="$(_state_root)"
STATE="$STATE_ROOT/state"
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
#
# branch_to_ticket [branch] — with no argument it resolves the CURRENT HEAD's branch (the
# commit-boundary use); with an argument it resolves an ARBITRARY branch name, which is what the
# creation-time guard needs (the branch does not exist yet when we must decide).
# Both this worktree's board/ AND the shared (git-common-dir) board/ are searched: the shared one
# is the current master board (a worktree cut days ago has a STALE board and would otherwise fail
# to see a ticket that exists), while the local one still resolves a ticket a sub has authored on
# its own branch but not yet landed.
branch_to_ticket() {
  local br="${1:-}"
  if [ -z "$br" ]; then br="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || return 1; fi
  [ -n "$br" ] || return 1
  local root tid saved="${FLEET_LIB_BOARD:-}"
  local roots="$FLEET"
  [ "$STATE_ROOT" != "$FLEET" ] && roots="$FLEET $STATE_ROOT"
  for root in $roots; do
    [ -d "$root/board" ] || continue
    if declare -F ticket_for_branch >/dev/null 2>&1; then
      FLEET_LIB_BOARD="$root/board"
      tid="$(ticket_for_branch "$br" 2>/dev/null)" || tid=""
      FLEET_LIB_BOARD="$saved"
      if [ -n "$tid" ]; then printf '%s' "$tid"; return 0; fi
    fi
    if [ -f "$root/board/$br.md" ]; then printf '%s' "$br"; return 0; fi
  done
  return 1
}

# board_reachable — fail-CLOSED precondition: at least one board/ directory holding at least one
# ticket must be visible. No board == the mapping machinery is missing, and a gate that cannot
# read its own inputs must REFUSE, never wave the branch through.
board_reachable() {
  local root roots="$FLEET"
  [ "$STATE_ROOT" != "$FLEET" ] && roots="$FLEET $STATE_ROOT"
  for root in $roots; do
    [ -d "$root/board" ] || continue
    if compgen -G "$root/board/*.md" >/dev/null 2>&1; then return 0; fi
  done
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

# guard-branch <branch> [context] — the CREATION-TIME gate (TICKET-MAP-GATE).
#
# THE CLASS THIS CLOSES: cmd_pre_commit already refuses a worktree branch that maps to no board
# ticket — but it fires at COMMIT, i.e. after the whole build is finished. Four separate agents
# paid that cost in one day: complete, tested, green work that could not be committed. The
# mapping requirement is identical; only the MOMENT is wrong. This runs the SAME resolver at
# worktree/branch-creation time, so an unmapped branch is refused before any work happens.
#
# FAIL CLOSED, LOUD, non-zero: an empty branch name, an unreachable board, or an unresolvable
# branch all REFUSE (rc 1). WORK_LEASE_BYPASS is deliberately NOT honoured here — the answer to
# "my branch maps to no ticket" is a ticket, never a softer gate; bypassing at creation would
# just re-create the late-refusal it exists to prevent.
cmd_guard_branch() {
  local br="${1:-}" ctx="${2:-}"
  if [ -z "$br" ]; then
    echo "WORK-LEASE CREATION REFUSED: no branch name given (fail-closed)." >&2
    return 1
  fi
  if ! board_reachable; then
    echo "WORK-LEASE CREATION REFUSED: no readable board/ under '$FLEET' or '$STATE_ROOT'" >&2
    echo "  The branch->ticket mapping machinery is MISSING; a gate that cannot read its inputs refuses." >&2
    return 1
  fi
  local tid=""
  if tid="$(branch_to_ticket "$br" 2>/dev/null)" && [ -n "$tid" ]; then
    echo "work-lease: branch '$br' -> ticket '$tid'${ctx:+ ($ctx)}"
    return 0
  fi
  cat >&2 <<EOM
WORK-LEASE CREATION REFUSED: branch '$br'${ctx:+ ($ctx)} maps to NO board ticket.
  Refusing to create a worktree/branch that could not be committed from later — this is the
  SAME check pre-commit runs, moved to creation time so no work is wasted.
  Fix FIRST, then retry: add a board ticket whose 'branch:' field is exactly '$br'
  (or point this work at an existing ticket's branch).
EOM
  return 1
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
# repo_guard <hook> [args...] — run the REPO'S OWN tracked hook (tools/hooks/<hook>) FIRST and
# abort the commit on any non-zero exit.
#
# WHY (do not "simplify" this away): only ONE hook per name can be active in .git/hooks, so
# installing the work-lease symlink there DISPLACES whatever the repo shipped. The product repo
# (/home/stack/code/charon) is PUBLIC and ships its own public-clean guard at
# tools/hooks/pre-commit which blocks internal IPs / home paths / rig names / hex secrets from
# entering a commit. Chain, never replace.
#
# ORDERING IS A SECURITY PROPERTY: the repo guard runs FIRST and its non-zero returns
# immediately, so a later leg (the lease check) can never mask a leak by returning 0. It is also
# placed BEFORE the WORK_LEASE_BYPASS early-return on purpose — bypassing the LEASE must not
# bypass the repo's own guard.
repo_guard() {
  local hook="$1"; shift
  local top; top="$(git rev-parse --show-toplevel 2>/dev/null)" || return 0
  [ -n "$top" ] || return 0
  local h="$top/tools/hooks/$hook"
  [ -x "$h" ] || return 0
  # Re-entrancy guard: if a repo ever points its tracked hook back at this gate, do not recurse.
  [ "$(readlink -f "$h" 2>/dev/null)" != "$(readlink -f "$FLEET/hooks/$hook" 2>/dev/null)" ] || return 0
  ( cd "$top" && "$h" "$@" ) || return $?
  return 0
}

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
  repo_guard pre-commit "$@" || return $?   # public-clean & friends — FIRST, and not bypassable
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
  repo_guard commit-msg "$@" || return $?   # repo's own commit-msg guard, if it ships one
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
# _link_src — the fleet/ dir the installed hook symlinks must RESOLVE TO: always the rig's MAIN
# checkout, NEVER a linked worktree.
#
# WHY: .git/hooks is shared by the main checkout AND every linked worktree, but `ensure` is fired
# from whatever checkout booted (session-start.sh and fleet-droid.sh both derive FLEET from their
# own location). Linking to "$FLEET/hooks/..." therefore pointed BOTH repos' hooks into whichever
# WORKTREE happened to run ensure last — and the shim resolves its FLEET from the symlink target,
# so the gate then consulted that worktree's fleet/ (its board, its state/claims). Two failures
# followed: false NO-LEASE refusals, and reaping that worktree silently breaks commits in EVERY
# repo (a dangling hook symlink is not executable, so git skips it without a word — which would
# also silently disable the product's public-clean guard).
# `git rev-parse --git-common-dir` always names the MAIN checkout's .git, so its parent is the
# main worktree root: a stable target that outlives any worktree.
_link_src() {
  local gcd root
  gcd="$(git -C "$FLEET" rev-parse --git-common-dir 2>/dev/null)" || { printf '%s' "$FLEET"; return 0; }
  [ -n "$gcd" ] || { printf '%s' "$FLEET"; return 0; }
  case "$gcd" in /*) :;; *) gcd="$FLEET/$gcd";; esac
  root="$(cd "$gcd/.." 2>/dev/null && pwd)" || { printf '%s' "$FLEET"; return 0; }
  if [ -d "$root/fleet/hooks" ]; then printf '%s' "$root/fleet"; else printf '%s' "$FLEET"; fi
}

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
  local hd src; src="$(_link_src)"
  while IFS= read -r hd; do
    [ -n "$hd" ] || continue
    mkdir -p "$hd"
    for hook in pre-commit commit-msg; do
      ln -sf "$src/hooks/$hook" "$hd/$hook"
      echo "  $hd/$hook -> $src/hooks/$hook"
    done
  done < <(_hook_targets)
  echo "work-lease hooks installed"
}

# ensure — idempotent auto-wire: install the hooks ONLY if not already the correct symlink.
# Fired automatically by session-start.sh (every session) and fleet-droid.sh (every droid),
# so the gate is NEVER inert on a fresh checkout — with no manual install step. Never fails a
# session boot: any error is swallowed (the caller invokes it with `|| true`).
cmd_ensure() {
  local hd changed=0 src; src="$(_link_src)"
  while IFS= read -r hd; do
    [ -n "$hd" ] || continue
    mkdir -p "$hd" 2>/dev/null || continue
    for hook in pre-commit commit-msg; do
      if [ "$(readlink "$hd/$hook" 2>/dev/null)" != "$src/hooks/$hook" ]; then
        ln -sf "$src/hooks/$hook" "$hd/$hook" 2>/dev/null && changed=1
      fi
    done
  done < <(_hook_targets)
  [ "$changed" -eq 1 ] && echo "work-lease: hooks wired" || true
  return 0
}

cmd_uninstall() {
  local hd src; src="$(_link_src)"
  while IFS= read -r hd; do
    [ -n "$hd" ] || continue
    for hook in pre-commit commit-msg; do
      local t="$hd/$hook"
      if [ -L "$t" ] && [ "$(readlink "$t")" = "$src/hooks/$hook" ]; then
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
  guard-branch)  cmd_guard_branch "$@" ;;
  release)       cmd_release "$@" ;;
  heartbeat)     cmd_heartbeat "$@" ;;
  pre-commit)    cmd_pre_commit "$@" ;;
  commit-msg)    cmd_commit_msg "$@" ;;
  install)       cmd_install "$@" ;;
  ensure)        cmd_ensure "$@" ;;
  uninstall)     cmd_uninstall "$@" ;;
  *)             echo "Usage: $(basename "$0") {acquire|check|holds|bind|dispatch|guard-branch|release|heartbeat|pre-commit|commit-msg|install|ensure|uninstall}" >&2; exit 2 ;;
esac
