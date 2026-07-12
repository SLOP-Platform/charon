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
leak_worktree_setup(){
  local charon="$1" wt="$2" branch="$3" npmarker="${4:-}" base_ref="${5:-origin/master}"
  if [ -n "$npmarker" ] && [ -e "$npmarker" ]; then
    echo "leak-guard: REFUSING to (re)create $wt — $npmarker exists (committed-but-unlanded work); land it first." >&2
    return 2
  fi
  git -C "$charon" fetch origin --quiet 2>/dev/null || true
  # Clear any stale leftover worktree/branch (retry path) — but ONLY reachable here because the
  # needs-push guard above already passed, so nothing committed-and-unlanded is at risk.
  if [ -e "$wt" ]; then
    git -C "$charon" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  fi
  git -C "$charon" worktree prune 2>/dev/null || true
  git -C "$charon" branch -D "$branch" 2>/dev/null || true
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
  git -C "$charon" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  return 0
}
