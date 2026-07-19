#!/usr/bin/env bash
# leak-guard.sh — WORKTREE-LEAK GUARD library (fleet build-rig only).
#
# MECHANIZES the #1 fragility (confirmed work-loss 2x, state/MODEL-SELF-REPORT-RELIABILITY.md):
# a droid that ignores JOIN-PROMPT's "cd into your worktree" step writes into the MAIN checkout
# /home/stack/code/charon; the launcher inspects the EMPTY charon-fleet-<id>, sees no commits,
# releases, and the work is stranded in main where a later re-claim wipes it.
#
# Three defences, all pure/deterministic so they are unit-testable (see
# fleet/tests/worktree-leak-guard.test.sh — every function FAILS ON REVERT):
#   leak_worktree_setup  — the LAUNCHER pre-creates the worktree off origin/master BEFORE the
#                          model runs, so the create/cd step is out of the model's hands. Fails
#                          LOUDLY (never silently falls back to the main checkout). REFUSES to
#                          touch a worktree that still has a live needs-push marker (would
#                          destroy stranded committed work — the #3 hazard).
#   leak_detect          — after the session: zero new commits AND clean worktree AND the main
#                          checkout is NEWLY dirty  ==>  the droid leaked into main. Deterministic
#                          diff of before/after `git status --porcelain`.
#   leak_capture         — snapshot the stray main-checkout diff to a durable file so the work is
#                          preserved (quarantined) instead of wiped.
#   safe_worktree_remove — the ONE sanctioned worktree-removal path: REFUSES when a needs-push
#                          marker for that id still exists (protects committed-but-unlanded work).
#
# This file is a LIBRARY: `source` it. It runs nothing on its own.
# Requires: git. No other deps.

# leak_worktree_setup <repo> <worktree_dir> <branch> <needs_push_marker> [base_ref]
#   Creates <worktree_dir> as a fresh worktree of <branch> off <base_ref>.
#   base_ref defaults to origin/master (charon back-compat); pass origin/main for keystone etc.
#   Return: 0 = created OK.  1 = FATAL (could not create — caller must NOT launch into main).
#           2 = REFUSED (needs-push marker present — stranded work; do not destroy).
#           3 = REFUSED (branch carries UNLANDED commits — salvage-tagged; do not destroy).
#
# LEAK-GUARD-VACUITY FIX (2026-07-18). The needs-push guard above was the ONLY thing standing
# between this function and an unconditional `branch -D`, and state/needs-push/ is EMPTY — so the
# guard was VACUOUS for EVERY branch and the delete ran unconditionally. It orphaned reviewed
# commit 32254b3, and because `git branch -D` also erases .git/logs/refs/heads/<branch>, it
# destroyed the ATTRIBUTION with it (which is why that rewrite initially looked actorless).
# A needs-push marker is a bookkeeping artifact; COMMITS ON THE BRANCH are the ground truth.
#
# _lg_unlanded_count <repo> <branch> <base_ref> -> commits on <branch> not in <base_ref> (0 when
# the branch does not exist). Ground truth for "is there work here that would be destroyed".
#
# FAIL-CLOSED (BLOCKER-1 fix, 2026-07-18): this used to end in `… || echo 0`, which turned EVERY
# failure of rev-list into "0 unlanded commits" — the same fail-open shape as rig #103. An
# UNRESOLVABLE <base> (no local origin/master because the `fetch … || true` at the call site
# silently failed offline; no `origin` remote at all; a main-based repo hitting the origin/master
# DEFAULT) made the count 0, skipped the salvage guard, and fell through to `branch -d || -D` —
# where -d fails on an unmerged branch so -D ALWAYS fired. Reproduced live: a branch holding
# "PRECIOUS WORK" was deleted with no ref left pointing at it, INSIDE the guard meant to stop it.
# The base is now resolved FIRST and any failure yields UNRESOLVABLE + rc 1, which the caller must
# treat as REFUSE — never as 0.
_lg_unlanded_count(){
  local repo="$1" branch="$2" base="$3"
  # A branch that does not exist has nothing to destroy — 0 is the honest answer here.
  git -C "$repo" rev-parse --verify --quiet "refs/heads/$branch" >/dev/null 2>&1 || { echo 0; return 0; }
  # The branch DOES exist: from here on, not knowing the count must never read as "nothing to lose".
  git -C "$repo" rev-parse --verify --quiet "$base^{commit}" >/dev/null 2>&1 \
    || { echo UNRESOLVABLE; return 1; }
  git -C "$repo" rev-list --count "$base..refs/heads/$branch" 2>/dev/null \
    || { echo UNRESOLVABLE; return 1; }
}
# _lg_archive_reflog <repo> <branch> [outdir] — copy .git/logs/refs/heads/<branch> somewhere durable
# BEFORE any deletion, so attribution survives the branch. Uses the COMMON git dir (worktrees have
# their own $GIT_DIR). Slashes in the branch name are flattened into the archive filename.
_lg_archive_reflog(){
  local repo="$1" branch="$2" outdir="${3:-}" gd src flat
  [ -n "$outdir" ] || outdir="${FLEET:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}/state/refloghist"
  gd="$(git -C "$repo" rev-parse --git-common-dir 2>/dev/null)" || return 1
  case "$gd" in /*) ;; *) gd="$repo/$gd" ;; esac
  src="$gd/logs/refs/heads/$branch"
  [ -f "$src" ] || return 1
  mkdir -p "$outdir" || return 1
  flat="${branch//\//__}"
  # LOW-4: 1-second granularity let two runs on one branch inside the same second silently
  # OVERWRITE each other's archive — the second copy destroying the attribution the first saved.
  # pid + $RANDOM make the name unique even within a tick.
  cp "$src" "$outdir/${flat}-$(date -u +%Y%m%dT%H%M%S)-$$-$RANDOM.reflog" 2>/dev/null || return 1
  return 0
}
# ── MED-2: destructive-target gating for worktree removal ────────────────────────────────────
# Before W0 no rig ticket ever reached safe_worktree_remove (the path was hardcoded to the
# PRODUCT checkout); now every `repo: charon-private` ticket does, and the rig's RR_WT is
# /home/stack/charon-private-wt/<id> — the same tree family the rig's own work lives in. Nothing
# verified that the target was even a worktree of <repo>, so `rm -rf "$wt"` was reachable against
# an arbitrary path. These two helpers make the fallback earn its blast radius.
#
# _lg_wt_registered <repo> <wt> — 0 only when <wt> is a NON-PRIMARY worktree registered to <repo>.
# The primary checkout is listed first by `worktree list --porcelain`; it is the LIVE tree and is
# never a legal removal target.
_lg_wt_registered(){
  local repo="$1" wt="$2" real primary="" p rp
  [ -n "$wt" ] || return 1
  real="$(cd "$wt" 2>/dev/null && pwd -P)" || return 1
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    rp="$(cd "$p" 2>/dev/null && pwd -P)" || rp="$p"
    [ -n "$primary" ] || { primary="$rp"; continue; }   # first entry = primary/live checkout
    [ "$rp" = "$real" ] && return 0
  done < <(git -C "$repo" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p')
  return 1
}
# _lg_wt_canonical <repo> <wt> <id> — 0 when <wt> is EXACTLY the per-ticket worktree path the repo
# registry assigns to <id> for the repo checked out at <repo>. A worktree that git already pruned
# leaves an inert directory at that path which is no longer "registered" but is still unambiguously
# ours to sweep. Needs repo_resolve sourced; without it this is simply never true (fail closed).
_lg_wt_canonical(){
  local repo="$1" wt="$2" id="$3" real repo_real k rp wp
  [ -n "$wt" ] && [ -n "$id" ] || return 1
  declare -F repo_resolve >/dev/null 2>&1 || return 1
  # HIGH-1: this is the route that AUTHORIZES `rm -rf`, so it re-checks the id itself rather than
  # inferring safety from repo_resolve's rc. repo_resolve now refuses an unsafe id (rc 2) and the
  # `|| continue` below would already fail closed; this makes the refusal explicit and survives
  # anyone loosening the registry later. Fail closed when the validator is absent entirely.
  declare -F repo_valid_id >/dev/null 2>&1 || return 1
  repo_valid_id "$id" || return 1
  real="$(cd "$wt" 2>/dev/null && pwd -P)" || real="$wt"
  repo_real="$(cd "$repo" 2>/dev/null && pwd -P)" || repo_real="$repo"
  for k in $(repo_known_keys 2>/dev/null); do
    local RR_KEY RR_PATH RR_WT RR_BASE RR_GATE
    repo_resolve "$k" "$id" >/dev/null 2>&1 || continue
    rp="$(cd "$RR_PATH" 2>/dev/null && pwd -P)" || rp="$RR_PATH"
    wp="$(cd "$RR_WT"   2>/dev/null && pwd -P)" || wp="$RR_WT"
    [ "$rp" = "$repo_real" ] && [ "$wp" = "$real" ] && return 0
  done
  return 1
}
# ── HIGH-2: ancestry-based catastrophic-target guard ────────────────────────────────────────
# The old guard compared for EQUALITY only (empty, "/", real = repo_real). It therefore said OK
# to any directory CONTAINING the live checkout. Confirmed before this fix:
#   _lg_wt_target_ok /home/stack/code/charon /home/stack/code   -> OK
# $HOME, /home/stack/code, and the /home/stack/charon-private-wt family parent were all legal
# `rm -rf` targets. Equality is the wrong relation: what makes a target catastrophic is that it
# CONTAINS something that must survive.
#
# _lg_path_contains <a> <b> — 0 when <a> is an ancestor OF, or equal to, <b>.
# Both sides arrive realpath-normalised (pwd -P: symlinks resolved, no trailing slash except
# "/"), and the comparison appends "/" to BOTH sides so a trailing slash cannot defeat it and
# "/home/stack/code2" is not read as a child of "/home/stack/code". The "$a/" pattern is QUOTED,
# so a glob character in a path is matched literally rather than as a wildcard.
_lg_path_contains(){
  local a="${1-}" b="${2-}"
  [ -n "$a" ] && [ -n "$b" ] || return 1
  [ "$a" = "/" ] && return 0                       # root contains everything
  case "$b/" in "$a/"*) return 0 ;; esac
  return 1
}
# _lg_protected_paths — every tree that must never be inside a removal target: $HOME, and for
# each key the registry knows, that repo's live checkout AND the parent directory of its
# per-ticket worktree family (the family parent is what `id=".."` collapsed onto). Emits
# realpath-normalised absolute paths, one per line. Degrades to $HOME alone when the registry is
# not sourced — fewer protections, never fewer than the most important one.
_lg_protected_paths(){
  local k rp wp
  [ -n "${HOME:-}" ] && { rp="$(cd "$HOME" 2>/dev/null && pwd -P)" && printf '%s\n' "$rp"; }
  declare -F repo_resolve >/dev/null 2>&1 || return 0
  for k in $(repo_known_keys 2>/dev/null); do
    local RR_KEY RR_PATH RR_WT RR_BASE RR_GATE
    # A syntactically valid probe id: we want the FAMILY path, and repo_valid_id now rejects "".
    repo_resolve "$k" "__lg_probe__" >/dev/null 2>&1 || continue
    rp="$(cd "$RR_PATH" 2>/dev/null && pwd -P)" || rp="$RR_PATH"
    [ -n "$rp" ] && printf '%s\n' "$rp"
    wp="${RR_WT%/*}"                                # family parent, e.g. /home/stack/charon-private-wt
    [ -n "$wp" ] && { rp="$(cd "$wp" 2>/dev/null && pwd -P)" && printf '%s\n' "$rp"; }
  done
}
# _lg_wt_catastrophic <real> <repo_real> — 0 when <real> must NEVER be removed, whatever else is
# true of it. Prints the reason. THE shared refusal used by both destructive sites.
_lg_wt_catastrophic(){
  local real="${1-}" repo_real="${2-}" p
  if [ -z "$real" ]; then echo "empty path"; return 0; fi
  case "$real" in /) echo "refusing filesystem root"; return 0 ;; esac
  if [ -n "$repo_real" ] && _lg_path_contains "$real" "$repo_real"; then
    if [ "$real" = "$repo_real" ]; then
      echo "that is the LIVE checkout ($repo_real), not a per-ticket worktree"; return 0
    fi
    echo "'$real' CONTAINS the live checkout ($repo_real)"; return 0
  fi
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    if _lg_path_contains "$real" "$p"; then
      if [ "$real" = "$p" ]; then echo "'$real' is a protected tree (\$HOME, a live checkout, or a worktree family root)"
      else echo "'$real' CONTAINS the protected tree '$p'"; fi
      return 0
    fi
  done < <(_lg_protected_paths)
  return 1
}
# _lg_wt_target_ok <repo> <wt> — 0 when <wt> is a defensible removal target. REFUSES: empty, /,
# a non-directory, the repo's own live checkout, and — for paths that really ARE git working trees
# — any tree still holding uncommitted or unpushed work. Prints the reason on refusal.
# NOTE the dirty/unpushed probes apply only when `git status` actually succeeds there. An inert
# leftover directory is not a working tree; judging it by a failed git command would refuse every
# already-pruned worktree (which is exactly what the retire sweep exists to clean up).
_lg_wt_target_ok(){
  local repo="$1" wt="$2" real repo_real dirty unpushed
  if [ -z "$wt" ]; then echo "empty path"; return 1; fi
  real="$(cd "$wt" 2>/dev/null && pwd -P)" || { echo "not a directory: $wt"; return 1; }
  repo_real="$(cd "$repo" 2>/dev/null && pwd -P)" || repo_real=""
  # HIGH-2: ancestry, not equality. Covers /, the live checkout, anything CONTAINING it, $HOME,
  # and every worktree-family root.
  local why
  if why="$(_lg_wt_catastrophic "$real" "$repo_real")"; then echo "$why"; return 1; fi
  if git -C "$real" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    dirty="$(git -C "$real" status --porcelain 2>/dev/null)"
    if [ -n "$dirty" ]; then
      echo "$(printf '%s\n' "$dirty" | wc -l) uncommitted change(s) present"; return 1
    fi
    unpushed="$(git -C "$real" rev-list --count HEAD --not --remotes 2>/dev/null)"
    case "$unpushed" in ''|*[!0-9]*) unpushed=1 ;; esac   # a working tree we cannot read => fail closed
    if [ "$unpushed" -gt 0 ]; then
      echo "$unpushed commit(s) on HEAD are not on any remote (unpushed work)"; return 1
    fi
  fi
  return 0
}
leak_worktree_setup(){
  local charon="$1" wt="$2" branch="$3" npmarker="${4:-}" base_ref="${5:-origin/master}"
  if [ -n "$npmarker" ] && [ -e "$npmarker" ]; then
    echo "leak-guard: REFUSING to (re)create $wt — $npmarker exists (committed-but-unlanded work); land it first." >&2
    return 2
  fi
  git -C "$charon" fetch origin --quiet 2>/dev/null || true
  # UNLANDED-WORK GUARD (fail closed, loud): count the branch's own commits BEFORE touching
  # anything. >0 means a delete here would orphan real work — tag it salvage/… so it is
  # reachable forever, then REFUSE. The caller must not proceed. Note this deliberately uses the
  # caller's <base_ref>, not a hardcoded origin/master, so multi-repo (base main) is covered too.
  # A non-numeric value or a non-zero rc means WE DO NOT KNOW — and not knowing must REFUSE.
  # The old test `[ "${ahead:-0}" -gt 0 ] 2>/dev/null` returned 2 on a non-numeric value, which
  # reads as FALSE and fell straight through to the delete. Both are now hard REFUSE (rc 3).
  local ahead ahead_rc=0
  ahead="$(_lg_unlanded_count "$charon" "$branch" "$base_ref")" || ahead_rc=$?
  case "$ahead" in ''|*[!0-9]*) ahead_rc=1 ;; esac
  if [ "$ahead_rc" -ne 0 ] || [ "$ahead" -gt 0 ]; then
    local why="has $ahead commit(s) not in $base_ref"
    [ "$ahead_rc" -eq 0 ] || why="has an UNKNOWN number of commits ('$base_ref' is unresolvable in $charon)"
    local tag="salvage/${branch}-$(date -u +%Y%m%dT%H%M%S)-$$-$RANDOM"
    git -C "$charon" tag -f "$tag" "refs/heads/$branch" >/dev/null 2>&1 \
      && echo "leak-guard: SALVAGE TAG $tag -> $(git -C "$charon" rev-parse --short "refs/heads/$branch" 2>/dev/null)" >&2 \
      || echo "leak-guard: WARNING could not create salvage tag $tag — still REFUSING (nothing deleted)" >&2
    _lg_archive_reflog "$charon" "$branch" && echo "leak-guard: archived reflog for '$branch' (attribution preserved)" >&2
    echo "leak-guard: REFUSING to (re)create $wt — branch '$branch' $why." >&2
    echo "leak-guard:   Deleting it would ORPHAN that work (this is how 32254b3 was orphaned)." >&2
    echo "leak-guard:   Recover from $tag, land the branch, or delete it by hand once it is truly landed." >&2
    return 3
  fi
  # Clear any stale leftover worktree/branch (retry path) — reachable ONLY when the branch has NO
  # commits of its own beyond base, so nothing recoverable is at risk.
  if [ -e "$wt" ]; then
    # Catastrophic-target guard only (NOT the full _lg_wt_target_ok): a stale leftover here is
    # legitimately an UNregistered, possibly dirty directory, and refusing those would deadlock
    # every retry. But '/' and the live checkout are never recyclable, whatever the state.
    # HIGH-2: this site had the SAME equality-only gap as _lg_wt_target_ok and is just as
    # destructive (it ends in `rm -rf "$wt"`). Both now share _lg_wt_catastrophic.
    local wt_real charon_real cat_why
    wt_real="$(cd "$wt" 2>/dev/null && pwd -P)" || wt_real=""
    charon_real="$(cd "$charon" 2>/dev/null && pwd -P)" || charon_real=""
    if cat_why="$(_lg_wt_catastrophic "$wt_real" "$charon_real")"; then
      echo "leak-guard: REFUSING to recycle '$wt' — $cat_why." >&2
      return 1
    fi
    git -C "$charon" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  fi
  git -C "$charon" worktree prune 2>/dev/null || true
  # Archive the reflog BEFORE the delete erases it — `branch -D/-d` removes
  # .git/logs/refs/heads/<branch>, taking the who/when/what-sha attribution with it.
  _lg_archive_reflog "$charon" "$branch" || true
  # Prefer -d (safe delete) — the guard above already proved 0 unlanded commits, so -D is only a
  # fallback for git's stricter "merged into HEAD/upstream" bookkeeping, never a work-destroyer.
  git -C "$charon" branch -d "$branch" 2>/dev/null || git -C "$charon" branch -D "$branch" 2>/dev/null || true
  git -C "$charon" worktree add "$wt" -b "$branch" "$base_ref" >/dev/null 2>&1 || return 1
  return 0
}

# leak_detect <repo> <worktree_dir> <branch> <main_before_porcelain> [base_ref]
#   Echoes "LEAK" + returns 0 when the droid leaked into the main checkout; echoes "CLEAN" +
#   returns 1 otherwise. LEAK == worktree produced NO commits AND is clean AND the main checkout
#   gained NEW porcelain entries versus the pre-session snapshot.
#   base_ref defaults to origin/master (charon back-compat); pass origin/main for keystone etc.
leak_detect(){
  local charon="$1" wt="$2" branch="$3" main_before="$4" base_ref="${5:-origin/master}"
  local commits wtdirty main_after newmain
  commits="$(git -C "$wt" log --oneline "$base_ref..$branch" 2>/dev/null)"
  wtdirty="$(git -C "$wt" status --porcelain 2>/dev/null)"
  main_after="$(git -C "$charon" status --porcelain 2>/dev/null)"
  # lines present in main_after but NOT in the pre-session snapshot = new stray work in main.
  newmain="$(comm -13 \
      <(printf '%s\n' "$main_before" | sort) \
      <(printf '%s\n' "$main_after"  | sort) | grep -v '^[[:space:]]*$' || true)"
  if [ -z "$commits" ] && [ -z "$wtdirty" ] && [ -n "$newmain" ]; then
    echo "LEAK"; return 0
  fi
  echo "CLEAN"; return 1
}

# leak_capture <charon_repo> <id> <out_dir>
#   Snapshots the stray main-checkout diff (tracked + untracked) to a durable file so the leaked
#   work is preserved. Echoes the capture-file path.
leak_capture(){
  local charon="$1" id="$2" outdir="$3"
  mkdir -p "$outdir"
  local lf="$outdir/${id}-$(date -u +%Y%m%dT%H%M%SZ).leak"
  {
    echo "# LEAK CAPTURE — $id — $(date -u +%FT%TZ)"
    echo "# stray work written into the MAIN checkout: $charon"
    echo "# RECOVER: apply into the ticket's worktree, or cherry-pick; do NOT discard blindly."
    echo "## git status --porcelain:"
    git -C "$charon" status --porcelain 2>/dev/null
    echo "## tracked diff (git diff HEAD):"
    git -C "$charon" diff HEAD 2>/dev/null
    echo "## untracked files:"
    git -C "$charon" ls-files --others --exclude-standard 2>/dev/null
  } > "$lf"
  echo "$lf"
}

# safe_worktree_remove <charon_repo> <worktree_dir> <id> <needs_push_dir>
#   The ONLY sanctioned worktree removal. REFUSES (returns 2, loud) when a live needs-push marker
#   for <id> still exists — committed-but-unlanded work must never be force-removed (CI-WORKFLOW-
#   POLICY-GATE was stranded exactly this way). Returns 0 on removal / nothing-to-do.
safe_worktree_remove(){
  local charon="$1" wt="$2" id="$3" npdir="$4"
  if [ -e "$npdir/$id" ]; then
    echo "leak-guard: REFUSING to remove $wt — state/needs-push/$id is live (committed-but-unlanded work). Land it first." >&2
    return 2
  fi
  [ -e "$wt" ] || return 0
  # MED-2: prove the target is a defensible one BEFORE any destructive call. `worktree remove
  # --force` destroys uncommitted work just as thoroughly as `rm -rf`, so the check gates both.
  local why
  if ! why="$(_lg_wt_target_ok "$charon" "$wt")"; then
    echo "leak-guard: REFUSING to remove $wt — $why. Nothing removed; resolve by hand." >&2
    return 2
  fi
  git -C "$charon" worktree remove --force "$wt" 2>/dev/null && return 0
  # FALLBACK. `rm -rf` is only defensible on a path that is provably OURS: either git itself
  # confirms it is a registered non-primary worktree of THIS repo, or the repo registry says it is
  # this ticket's canonical worktree path (the already-pruned case). Anything else is left on disk
  # with a WARNING — an orphaned directory is recoverable, an `rm -rf` of the wrong tree is not.
  if _lg_wt_registered "$charon" "$wt" || _lg_wt_canonical "$charon" "$wt" "$id"; then
    rm -rf "$wt"
    return 0
  fi
  echo "leak-guard: WARNING — '$wt' is neither a registered worktree of $charon nor $id's canonical worktree path; NOT running 'rm -rf' on it. Left in place for inspection." >&2
  return 2
}
