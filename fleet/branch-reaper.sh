#!/usr/bin/env bash
# branch-reaper.sh — MERGED-BRANCH + STALE-WORKTREE REAPER (fleet hygiene, build-rig only).
#
# Gap-register B4 / QUICKWINS-LEVERAGE #7 ([[investigate-and-backup-before-data-loss]]):
# ~92 branches (~20 merged-but-undeleted) + stale git worktrees accrete forever. This script
# reaps both, idempotently, with DRY-RUN as the mandatory default given the delete blast radius.
#
# FOUR HARD data-loss guards (in the order they are applied to a worktree):
#   0. FAMILY-GLOB GUARD (_rp_glob_ok), added 2026-07-19: the worktree glob BOUNDS every guard
#      below it, and was previously taken on faith. It must be absolute, end in '*', have a
#      non-empty literal prefix at least two directories below '/', and contain no protected
#      tree. REAPER_WT_GLOB='*' yielded an EMPTY prefix, which made the family restriction
#      match every path and the glob expand against the CURRENT DIRECTORY — a reviewer used
#      exactly that to rm -rf an unrelated repo. Validated BEFORE any iteration; on failure the
#      run ABORTS non-zero having touched nothing.
#   1. CATASTROPHIC-TARGET GUARD: _lg_wt_catastrophic (shared with leak-guard) refuses /,
#      $HOME, the live checkout, any worktree-family root, and any path CONTAINING them.
#   2. LIVE-CLAIM GUARD: a worktree is a candidate ONLY if NO live marker exists for its
#      ticket id — neither state/claims/<id> NOR state/needs-push/<id>.
#   3. REAL WORK GUARD (fail-closed), added 2026-07-19: guards 1+2 are rig BOOKKEEPING. A
#      released claim marker was being treated as PROOF the tree held no work — it is not.
#      The tree itself is now inspected: `git status --porcelain` non-empty (uncommitted or
#      untracked changes) => KEEP, and HEAD not reachable from any remote ref
#      (`git rev-list --count HEAD --not --remotes` > 0) => KEEP. Both probes live in the
#      SHARED _lg_wt_target_ok (leak-guard.sh) — do NOT write a second copy here.
#   4. FAIL-CLOSED UNDECIDABILITY: if the path cannot be resolved, is not a readable git
#      working tree, or any probe errors, the answer is KEEP. "Could not check" is NEVER
#      treated as "clean". Consequence, accepted deliberately: an inert non-git leftover
#      directory inside the worktree glob is now KEPT rather than reaped. Under-reaping is
#      recoverable; over-reaping is not.
#   5. MERGED-ONLY (branches): a local branch is a candidate ONLY if `git branch --merged
#      <base>` lists it (minus base / current / protected).
#
# WHAT IT DOES, per target (repo, base, worktree-glob):
#   (0) git worktree prune        — clean admin metadata for already-gone worktree dirs.
#   (1) reap stale fleet worktree dirs with no live claim AND no real work.
#   (2) delete local branches merged into <base> (excluding base/current/protected).
#
# TARGETS (rig-awareness, 2026-07-19). The reaper used to see ONLY the product repo, so the
# rig's own worktrees under charon-private-wt were invisible to it. Targets are now a LIST,
# resolved through fleet/repo-registry.sh (the path SSOT) — no absolute path is hardcoded here.
#
# Usage: fleet/branch-reaper.sh [--apply]
#   --apply    actually perform deletions (default: DRY-RUN, print only)
# Exit codes: 0 ok · 2 bad argument · 3 INVALID CONFIGURATION (nothing was touched).
#   rc 3 matters: a misconfigured run used to exit 0, so every caller gating on rc read a
#   silent no-op as success.
# Env:
#   REAPER_KEYS        space-separated repo-registry keys (default 'charon charon-private')
#   REAPER_REPO        single-target override: git repo to operate on
#   REAPER_WT_GLOB     single-target override: glob for that repo's worktree dirs
#   REAPER_BASE        base ref for merge-check         (default: the registry's base)
#   REAPER_FLEET_DIR   fleet dir containing state/      (default: this script's dir)
#   REAPER_PROTECTED   extra protected branches (space) (default: 'main')
# Setting REAPER_REPO or REAPER_WT_GLOB selects LEGACY SINGLE-TARGET mode (REAPER_KEYS ignored).
#
# TEST HOOK: set REAPER_* env vars to point at an isolated temp git repo fixture.
# See fleet/tests/branch-reaper.test.sh (FAIL-ON-REVERT: merged gone, unmerged KEPT,
# claimed worktree SURVIVES, dirty/untracked/unpushed/undecidable worktrees SURVIVE, a
# genuinely clean+pushed+unclaimed worktree IS reaped; GREEN-IS-NOT-PROOF throughout).
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$FLEET/repo-registry.sh"
# shellcheck source=/dev/null
source "$FLEET/leak-guard.sh"
# SOURCE ORDER IS NOT SIGNIFICANT: _lg_protected_paths tests `declare -F repo_resolve` at CALL
# time (leak-guard.sh:156). Do NOT introduce a real ordering dependency.

REAPER_BASE_OVERRIDE="${REAPER_BASE:-}"
REAPER_FLEET_DIR="${REAPER_FLEET_DIR:-$FLEET}"
REAPER_PROTECTED="${REAPER_PROTECTED:-main}"
# NOTE the `-` (not `:-`): an EXPLICIT empty REAPER_KEYS must stay empty. The test suite sets
# REAPER_KEYS="" defensively so that if the legacy single-target early-return in _rp_targets is
# ever broken, the suite's nine `--apply` runs resolve to NO targets and abort loudly, rather
# than silently retargeting the live rig checkouts. `:-` would have handed back the default.
REAPER_KEYS="${REAPER_KEYS-charon charon-private}"

APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "branch-reaper: unknown argument '$arg' (expected --apply)" >&2; exit 2 ;;
  esac
done

STATE="$REAPER_FLEET_DIR/state"
CLAIMS="$STATE/claims"; NEEDS_PUSH="$STATE/needs-push"

# ── target table: "repo<TAB>base<TAB>wt_glob" lines ──────────────────────────────
# Derived from repo-registry.sh so the paths have exactly ONE definition in the rig.
# The registry hands back a per-ticket worktree path; substituting a sentinel id yields
# the family glob without this file ever naming a directory.

# _rp_glob_ok <glob> — 0 when <glob> is a SAFE worktree-family pattern. Prints the reason on
# refusal. THIS RUNS BEFORE ANY ITERATION: an invalid family is a configuration abort, never a
# narrowed sweep (see the abort at the `TARGETS=` assignment below).
#
# HIGH-2 (2026-07-19 adversarial review). The family prefix used to be taken on faith:
# `wt_prefix="${glob%\*}"`. With REAPER_WT_GLOB='*' the prefix is the EMPTY STRING, at which
# point (i) `grep -F -- ""` matches every registered worktree, (ii) the family restriction
# `case "$wt_dir" in "$wt_prefix"?*` matches every non-empty path, and (iii) the unquoted glob
# expands against the CURRENT WORKING DIRECTORY. The reviewer drove that end-to-end and
# `rm -rf`'d a clean, fully-pushed, entirely unrelated repo sitting in cwd. The catastrophic
# guard could not help: an unrelated repo is not a protected path.
#
# The weaker sibling case is the same defect: a glob with no trailing '*' (e.g. '/a/b') yields
# prefix '/a/b', and prefix matching then admits the SIBLING '/a/bX'. Hence the trailing-'*'
# requirement — the prefix is only meaningful as the literal head of a family.
_rp_glob_ok(){
  local glob="${1-}" prefix probe dir p
  [ -n "$glob" ] || { echo "worktree glob is empty"; return 1; }
  case "$glob" in
    *'*') ;;
    *) echo "worktree glob '$glob' does not end in '*' — prefix matching would admit siblings (e.g. '${glob}X')"; return 1 ;;
  esac
  prefix="${glob%\*}"
  [ -n "$prefix" ] || { echo "worktree glob '$glob' has an EMPTY family prefix — it would match EVERY path and expand against the current directory"; return 1; }
  case "$prefix" in
    /*) ;;
    *) echo "worktree glob '$glob' is not absolute — it would expand against the current directory"; return 1 ;;
  esac
  case "$prefix" in
    *'*'*|*'?'*|*'['*) echo "worktree glob '$glob' contains a wildcard before its final '*' — the family head must be literal"; return 1 ;;
  esac
  # MED (2026-07-19 adversarial review). Every check below — the depth check and, critically,
  # the protected-tree check — is LITERAL. A single '.', '..' or empty ('//') component makes
  # each protected tree invisible to `case "$p" in "$prefix"?*` while the glob still expands to
  # the IDENTICAL candidate set. Confirmed by execution: '/home/stack/*' is refused as admitting
  # a protected tree, but '/home/stack/./*' — the same set — was ACCEPTED, as were '//home/stack/*',
  # '/home/stack/../*' (escapes to /home/*) and '/home/stack/a/../../../*' (root-equivalent). A
  # clean, fully-pushed, unrelated repo inside the widened family was listed REAP: the same victim
  # class as the real deletion that prompted this guard.
  #
  # REJECT rather than canonicalise. An operator writing '/home/stack/./*' has made a mistake
  # worth surfacing, and refusing is the fail-closed choice in a destruction path. The check is
  # PURELY LEXICAL by necessity: a family head may legitimately name a directory that does not
  # exist yet, so `realpath -e`/`readlink -f` semantics (which fail on missing paths) are wrong
  # here. `${prefix%/}/` normalises to exactly one trailing slash, so every component is bounded
  # by slashes on both sides and a single `case` per offending form suffices.
  probe="${prefix%/}/"
  case "$probe" in
    *//*)   echo "worktree glob '$glob' has an EMPTY path component ('//') in its family prefix — the protected-tree check is literal and would not see any protected tree; use the canonical path"; return 1 ;;
    */./*)  echo "worktree glob '$glob' has a '.' component in its family prefix — the protected-tree check is literal and would not see any protected tree; use the canonical path"; return 1 ;;
    */../*) echo "worktree glob '$glob' has a '..' component in its family prefix — it silently escapes to a parent family and the protected-tree check would not see any protected tree; use the canonical path"; return 1 ;;
  esac
  # Depth: the family must live at least two directories below the filesystem root, so that a
  # truncated/degenerate value ('/', '/*', '/home/*') can never become the family head.
  dir="${prefix%/*}"
  case "$dir" in
    ''|/) echo "worktree glob '$glob' is rooted directly at '/' — far too broad"; return 1 ;;
  esac
  case "${dir%/*}" in
    '') echo "worktree glob '$glob' is only one directory below '/' — far too broad"; return 1 ;;
  esac
  # No protected tree may sit INSIDE the family. If one does, some candidate under this prefix
  # is either a protected path or an ancestor of one, and the family itself is misconfigured —
  # refuse the whole target rather than rely on the per-candidate guard to catch it later.
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    case "$p" in
      "$prefix"?*) echo "worktree glob '$glob' would admit the protected tree '$p'"; return 1 ;;
    esac
  done < <(_lg_protected_paths)
  return 0
}

_rp_targets(){
  local bad=0 emitted=0 why repo glob key sentinel=RPGLOBID
  if [ -n "${REAPER_REPO:-}" ] || [ -n "${REAPER_WT_GLOB:-}" ]; then
    repo="${REAPER_REPO:-}"; glob="${REAPER_WT_GLOB:-}"
    [ -n "$repo" ] || { echo "branch-reaper: REAPER_WT_GLOB set without REAPER_REPO" >&2; return 1; }
    [ -n "$glob" ] || glob="$(dirname "$repo")/$(basename "$repo")-fleet-*"
    if ! why="$(_rp_glob_ok "$glob")"; then
      echo "branch-reaper: INVALID CONFIG — $why" >&2; return 1
    fi
    printf '%s\t%s\t%s\n' "$repo" "${REAPER_BASE_OVERRIDE:-master}" "$glob"
    return 0
  fi
  for key in ${REAPER_KEYS-}; do
    if ! repo_resolve "$key" "$sentinel" >/dev/null 2>&1; then
      echo "branch-reaper: unknown repo key '$key'" >&2; bad=1; continue
    fi
    case "$RR_WT" in
      *"$sentinel") glob="${RR_WT%$sentinel}*" ;;
      *) echo "branch-reaper: cannot derive worktree glob for key '$key'" >&2; bad=1; continue ;;
    esac
    if ! why="$(_rp_glob_ok "$glob")"; then
      echo "branch-reaper: INVALID CONFIG for key '$key' — $why" >&2; bad=1; continue
    fi
    printf '%s\t%s\t%s\n' "$RR_PATH" "${REAPER_BASE_OVERRIDE:-$RR_BASE}" "$glob"
    emitted=$((emitted+1))
  done
  # MED-2: a reaper that silently no-ops on bad configuration is a FALSE GREEN for every caller
  # that gates on rc. No usable target, an unknown key, or an unsafe family is a hard failure.
  if [ "$emitted" -eq 0 ]; then
    echo "branch-reaper: no usable targets (REAPER_KEYS='${REAPER_KEYS-}')" >&2; return 1
  fi
  [ "$bad" -eq 0 ] || return 1
  return 0
}

# LOW-2 (2026-07-19 adversarial review) — STALE REMOTE-TRACKING REFS READ AS "PUSHED".
# _lg_wt_target_ok proves "fully pushed" with `rev-list --count HEAD --not --remotes`, i.e. it
# trusts local refs/remotes/*. Those are a CACHE of a remote we are not talking to. A force-push
# or an upstream branch deletion leaves that cache asserting commits exist upstream when they no
# longer do — and this is a DESTRUCTION path, so believing it reaps the only copy.
#
# WHY NOT `fetch --prune` HERE: a network call inside a delete path makes deletion depend on
# network state, and — worse — it makes the reaper MORE willing to delete right after it runs.
# The sound direction is the opposite one: make the staleness VISIBLE and fail toward KEEPING.
#
# _rp_remote_freshness <dir> — prints, in SECONDS, the age of the most recent LOCAL evidence
# that this repo's remote-tracking refs were reconciled with the network. Returns 1 (silent)
# when no such evidence exists at all. Zero network calls; reads mtimes only.
# Evidence = any event that required actually contacting the remote:
#   FETCH_HEAD (per-worktree and common dir)  — last fetch
#   logs/refs/remotes/**                      — reflog of every remote-tracking ref update
#   refs/remotes/**, packed-refs              — the ref cache itself
# A push counts: it proves the remote accepted those objects at that time. Neither a push nor a
# fetch proves anything about what happened AFTERWARDS — which is precisely why this is an AGE
# and not a boolean.
_rp_remote_freshness(){
  local dir="$1" gd cd_ newest=0 f t
  gd="$(git -C "$dir" rev-parse --git-path FETCH_HEAD 2>/dev/null)" || gd=""
  cd_="$(git -C "$dir" rev-parse --git-common-dir 2>/dev/null)" || cd_=""
  [ -n "$cd_" ] && cd_="$(cd "$dir" 2>/dev/null && cd "$cd_" 2>/dev/null && pwd -P)"
  while IFS= read -r f; do
    [ -n "$f" ] && [ -e "$f" ] || continue
    t="$(stat -c %Y "$f" 2>/dev/null)" || continue
    case "$t" in ''|*[!0-9]*) continue ;; esac
    [ "$t" -gt "$newest" ] && newest="$t"
  done < <(
    printf '%s\n' "$gd"
    [ -n "$cd_" ] && {
      printf '%s\n' "$cd_/FETCH_HEAD" "$cd_/packed-refs"
      find "$cd_/logs/refs/remotes" "$cd_/refs/remotes" -type f 2>/dev/null
    }
  )
  [ "$newest" -gt 0 ] || return 1
  local now; now="$(date +%s 2>/dev/null)" || return 1
  local age=$(( now - newest ))
  [ "$age" -ge 0 ] || age=0      # clock skew / future mtime => treat as fresh-now, not negative
  printf '%s\n' "$age"
  return 0
}

# _rp_keep_reason <repo> <wt_dir> — prints WHY the worktree must be kept and returns 0.
# Returns 1 (silent) only when the tree is provably safe to remove. FAIL-CLOSED: every
# error path, unreadable path, and undecidable probe returns 0 (KEEP).
_rp_keep_reason(){
  local repo="$1" wt="$2" real why
  [ -n "$wt" ] && [ -e "$wt" ] || { echo "path does not exist or is empty (fail-closed)"; return 0; }
  real="$(cd "$wt" 2>/dev/null && pwd -P)" || real=""
  [ -n "$real" ] || { echo "path could not be resolved (fail-closed)"; return 0; }
  [ -d "$real" ] || { echo "not a directory (fail-closed)"; return 0; }
  # Not a readable git working tree => its state is UNDECIDABLE. leak-guard's shared probe
  # deliberately skips its dirty/unpushed checks in this case; for a destructive sweep that
  # leniency is the wrong direction, so refuse here BEFORE delegating.
  git -C "$real" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
    || { echo "not a readable git working tree — state undecidable (fail-closed)"; return 0; }
  # EXIT-CODE probe. NOT a duplicate of the shared dirty check: _lg_wt_target_ok captures
  # `status --porcelain` output but DISCARDS its exit code, so a status that ERRORS (corrupt
  # index, unreadable object store, permissions) yields an empty string there and reads as
  # "clean". For a destructive sweep the failure of the probe is itself decisive: if we cannot
  # ask the tree what it holds, we do not delete it.
  if ! git -C "$real" status --porcelain >/dev/null 2>&1; then
    echo "'git status' failed — working-tree state undecidable (fail-closed)"; return 0
  fi
  # SHARED dirty + unpushed + catastrophic-target probe (leak-guard.sh:_lg_wt_target_ok).
  if ! why="$(_lg_wt_target_ok "$repo" "$real" 2>/dev/null)"; then
    [ -n "$why" ] || why="refused by leak-guard (no reason given — fail-closed)"
    echo "$why"; return 0
  fi
  # LOW-2: _lg_wt_target_ok just said "fully pushed" ON THE STRENGTH OF THE LOCAL REF CACHE.
  # Refuse to destroy on the strength of a ref whose freshness we cannot vouch for. Both arms
  # KEEP — this guard can only ever preserve a tree, never authorise one for deletion.
  local age max="${REAPER_REMOTE_MAX_AGE:-86400}"
  case "$max" in ''|*[!0-9]*) max=86400 ;; esac
  if ! age="$(_rp_remote_freshness "$real")"; then
    echo "'fully pushed' rests on remote-tracking refs whose freshness CANNOT be established (no fetch/push evidence on disk) — fail-closed"
    return 0
  fi
  if [ "$age" -gt "$max" ]; then
    echo "'fully pushed' rests on remote-tracking refs last reconciled with the remote ${age}s ago (limit ${max}s) — a force-push or an upstream branch deletion since then would make that claim FALSE; fail-closed (raise REAPER_REMOTE_MAX_AGE or fetch --prune BY HAND, never from this script)"
    return 0
  fi
  _RP_FRESH_AGE="$age"     # reported on the REAP line so the basis of the decision is visible
  return 1
}

# MED-2 + HIGH-2: resolve and VALIDATE every target BEFORE the first mutation. This used to be
# `done < <(_rp_targets)`, where _rp_targets' `return 1` was swallowed by the process
# substitution and the script fell through to `exit 0` — a misconfigured run reported success.
# Materialising the table here means an invalid family aborts non-zero with nothing touched.
if ! TARGETS="$(_rp_targets)"; then
  echo "branch-reaper: ABORTING — target resolution failed; NOTHING was touched." >&2
  exit 3
fi

if [ "$APPLY" -eq 1 ]; then
  echo "branch-reaper: APPLY mode (deletions will occur)"
else
  echo "branch-reaper: DRY-RUN (pass --apply to actually reap)"
fi

total_reaped_wt=0; total_kept_wt=0; total_reaped_br=0; total_kept_br=0

while IFS=$'\t' read -r REAPER_REPO_T REAPER_BASE_T REAPER_WT_GLOB_T; do
  [ -n "$REAPER_REPO_T" ] || continue
  echo
  echo "######## target: repo=$REAPER_REPO_T base=$REAPER_BASE_T wt-glob=$REAPER_WT_GLOB_T"
  if [ ! -d "$REAPER_REPO_T/.git" ] && [ ! -f "$REAPER_REPO_T/.git" ]; then
    echo "  SKIP — not a git repo: $REAPER_REPO_T"
    continue
  fi
  # Safe by construction: _rp_glob_ok already refused every degenerate family (empty prefix,
  # relative, root-adjacent, no trailing '*', or one containing a protected tree). Re-assert it
  # here anyway — this is the single value that bounds the blast radius of everything below.
  if ! _rp_why="$(_rp_glob_ok "$REAPER_WT_GLOB_T")"; then
    echo "  ABORT — unsafe worktree glob reached the sweep loop: $_rp_why" >&2
    exit 3
  fi
  wt_prefix="${REAPER_WT_GLOB_T%\*}"

  # ── (0) prune worktree admin metadata for already-gone dirs ────────────────────
  # DRY-RUN MUST BE READ-ONLY. `worktree prune` mutates git admin metadata, so it is gated on
  # --apply like every other mutation — a dry run (what the SessionStart hook invokes) now
  # touches nothing at all in any repo.
  echo "== worktree prune =="
  if [ "$APPLY" -eq 1 ]; then
    git -C "$REAPER_REPO_T" worktree prune 2>/dev/null && echo "  pruned" || echo "  nothing to prune"
  else
    echo "  (dry-run: skipped — prune is a mutation)"
  fi

  # ── (1) reap stale fleet worktree dirs ─────────────────────────────────────────
  echo "== stale fleet worktrees =="
  reaped_wt=0; kept_wt=0
  # Candidates = git's OWN registry (authoritative; catches worktrees a glob would miss)
  # UNION the glob (catches orphan dirs git has already pruned), restricted to the family
  # prefix so widening the registry can never widen the blast radius.
  candidates="$(
    {
      git -C "$REAPER_REPO_T" worktree list --porcelain 2>/dev/null \
        | sed -n 's/^worktree //p' \
        | grep -F -- "$wt_prefix" || true
      for g in $REAPER_WT_GLOB_T; do [ -e "$g" ] && printf '%s\n' "$g"; done
    } | sort -u
  )"
  while IFS= read -r wt_dir; do
    [ -n "$wt_dir" ] || continue
    case "$wt_dir" in "$wt_prefix"?*) ;; *) continue ;; esac   # inside the family only
    # CATASTROPHIC-TARGET GUARD — FIRST, ahead of every equality/label check. A guard a
    # naming accident can jump over is not a guard.
    _rp_real="$(cd "$wt_dir" 2>/dev/null && pwd -P)" || _rp_real=""
    _rp_repo="$(cd "$REAPER_REPO_T" 2>/dev/null && pwd -P)" || _rp_repo=""
    if _rp_why="$(_lg_wt_catastrophic "$_rp_real" "$_rp_repo")"; then
      echo "  REFUSE worktree $wt_dir — $_rp_why"
      kept_wt=$((kept_wt+1)); continue
    fi
    [ "$wt_dir" = "$REAPER_REPO_T" ] && continue          # never the repo itself
    # LOW-1: compare RESOLVED paths (every other comparison in this file uses `pwd -P`), and
    # LOG the skip — a silent `continue` dropped the current worktree out of the report entirely.
    if [ -n "$_rp_real" ] && [ "$_rp_real" = "$(pwd -P)" ]; then
      echo "  KEEP   worktree $wt_dir (this is the current working directory)"
      kept_wt=$((kept_wt+1)); continue
    fi
    id="${wt_dir#$wt_prefix}"
    [ -n "$id" ] || continue
    if [ -e "$CLAIMS/$id" ] || [ -e "$NEEDS_PUSH/$id" ]; then
      echo "  KEEP   worktree $wt_dir (live marker for $id)"
      kept_wt=$((kept_wt+1)); continue
    fi
    # REAL WORK GUARD — the marker files above are bookkeeping, not evidence about the tree.
    if _rp_why="$(_rp_keep_reason "$REAPER_REPO_T" "$wt_dir")"; then
      echo "  KEEP   worktree $wt_dir (unreaped work: $_rp_why)"
      kept_wt=$((kept_wt+1)); continue
    fi
    echo "  REAP   worktree $wt_dir (stale — no live claim for $id, clean, fully pushed; remote refs verified ${_RP_FRESH_AGE:-?}s ago)"
    if [ "$APPLY" -eq 1 ]; then
      # LEAK-GUARD BYPASS (2026-07-19 adversarial review, FINDING 1). This line used to be
      #     git ... worktree remove --force "$wt_dir" 2>/dev/null || rm -rf "$wt_dir"
      # which is the exact guard-inversion shape: `worktree remove` REFUSING (rc!=0) TRIGGERED
      # an unconditional `rm -rf`, and 2>/dev/null threw away the reason. It also skipped
      # safe_worktree_remove entirely — the ONE sanctioned removal path — so the needs-push
      # re-check, the _lg_wt_target_ok re-probe, and the registered/canonical proof that
      # AUTHORIZES `rm -rf` were all absent. A second, weaker guard beside the shared one is
      # the drift seam that costs committed work.
      # A REFUSAL HERE IS TERMINAL: no fallback, no `|| rm -rf`, no swallowed stderr. The tree
      # is counted KEPT and left on disk for inspection. Shape mirrors fleet/retire-done.sh:74-77.
      if safe_worktree_remove "$REAPER_REPO_T" "$wt_dir" "$id" "$NEEDS_PUSH"; then
        reaped_wt=$((reaped_wt+1))
      else
        echo "  FAILED worktree $wt_dir — leak-guard REFUSED removal (reason above); NOT deleted"
        kept_wt=$((kept_wt+1))
      fi
    else
      reaped_wt=$((reaped_wt+1))
    fi
  done <<< "$candidates"
  echo "  worktrees: $reaped_wt reaped, $kept_wt kept"

  # ── (2) reap merged local branches ───────────────────────────────────────────────
  echo "== merged local branches (base=$REAPER_BASE_T) =="
  cur_branch="$(git -C "$REAPER_REPO_T" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  protected="$REAPER_BASE_T $cur_branch $REAPER_PROTECTED"
  reaped_br=0; kept_br=0
  # MED-1: NEVER scrape `git branch`. Its output is a HUMAN TABLE: it prefixes the current
  # branch with '* ' and — since git 2.23 — any branch checked out in ANOTHER worktree with
  # '+ '. Only '*' was stripped, so on the live rig 30+ branches became the literal name
  # "+ feat/...". Three consequences, all bad: the protected-list check at the bottom of this
  # loop could never match a '+'-marked branch (so `main`/base BYPASSED the protected list
  # whenever they were checked out in a worktree); `git branch -D "+ main"` failed with rc 1,
  # swallowed by `|| true`; and reaped_br was incremented regardless, so the tool REPORTED
  # deletions that never happened. for-each-ref emits the bare refname with no decoration,
  # plus the worktree holding it (empty when none) — which lets us keep in-use branches
  # deliberately instead of relying on `branch -D` to fail.
  while IFS=$'\t' read -r branch wtpath; do
    [ -n "$branch" ] || continue
    case " $protected " in
      *" $branch "*) echo "  KEEP   branch $branch (protected)"; kept_br=$((kept_br+1)); continue ;;
    esac
    if [ -n "$wtpath" ]; then
      echo "  KEEP   branch $branch (checked out in worktree $wtpath)"
      kept_br=$((kept_br+1)); continue
    fi
    echo "  REAP   branch $branch (merged into $REAPER_BASE_T)"
    if [ "$APPLY" -eq 1 ]; then
      # Count what ACTUALLY happened, not what was attempted.
      if git -C "$REAPER_REPO_T" branch -D "$branch" >/dev/null 2>&1; then
        reaped_br=$((reaped_br+1))
      else
        echo "  FAILED branch $branch — 'git branch -D' refused it; NOT deleted"
        kept_br=$((kept_br+1))
      fi
    else
      reaped_br=$((reaped_br+1))
    fi
  done < <(git -C "$REAPER_REPO_T" for-each-ref --format='%(refname:short)%09%(worktreepath)' \
             --merged "$REAPER_BASE_T" refs/heads/ 2>/dev/null)
  echo "  branches: $reaped_br reaped, $kept_br kept"

  total_reaped_wt=$((total_reaped_wt+reaped_wt)); total_kept_wt=$((total_kept_wt+kept_wt))
  total_reaped_br=$((total_reaped_br+reaped_br)); total_kept_br=$((total_kept_br+kept_br))
done <<< "$TARGETS"

echo
echo "  worktrees: $total_reaped_wt reaped, $total_kept_wt kept (all targets)"
echo "  branches: $total_reaped_br reaped, $total_kept_br kept (all targets)"
echo "branch-reaper: done ($([ "$APPLY" = 1 ] && echo 'applied' || echo 'dry-run') — $total_reaped_br branch(es), $total_reaped_wt worktree(s) reaped; $total_kept_br branch(es), $total_kept_wt worktree(s) kept)."
exit 0
