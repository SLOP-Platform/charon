#!/usr/bin/env bash
# stranded-work.sh — RECURRING STRANDED-WORK DETECTOR (build-rig only; report-only).
#
# WHY THIS EXISTS
#   The rig's most persistent failure mode is work that is FINISHED-ISH BUT STRANDED: committed
#   and never merged, uncommitted in an abandoned worktree, or parked behind a CLOSED-but-unlanded
#   PR. Every session has been re-discovering the same backlog BY HAND (see the one-shot audit
#   fleet/state/STRANDED-WORK-AUDIT.md, hand-run 2026-07-14). A hand-run discovery is not a
#   control: the standing directive [[dynamic-tools-never-on-demand]] says a dynamic-data tool
#   must run on a CADENCE + TRIGGERS or it does not count. This file is the recurring half.
#   Discovery-by-hand is DONE and is NOT rebuilt here.
#
# WHAT IT IS NOT
#   It NEVER deletes, prunes, pushes, closes, or mutates anything. No `rm`, no `branch -D`, no
#   `worktree remove`, no `gh pr` mutation. It REPORTS; the operator (or fleet/branch-reaper.sh,
#   which carries its own data-loss guards) acts. Read-only is the whole safety argument — do not
#   add an --apply mode to this file.
#
# THE FIVE SHAPES (each one was REAL on this rig; each has a fail-on-revert test)
#   1 unpushed-branch    local branch with commits reachable from no remote ref.
#   2 dirty-worktree     worktree with uncommitted/untracked changes and NO live claim marker.
#                        (A live claim means someone is working in it — that is not stranded.)
#   3 pushed-no-pr       branch on the remote, not merged into base, with no PR at all.
#   4 closed-pr-unlanded CLOSED (not merged) PR whose head branch still carries commits absent
#                        from base. "Closed" does NOT mean "abandoned" — rig #81/#57/#56/#104
#                        were all closed with real unlanded work in them.
#   5 pr-no-checks       OPEN PR with ZERO CI checks. checks=0 renders as mergeable in the UI,
#                        which is the same FALSE-RECEIPT class as a proofless done-marker: it
#                        looks green because nothing ever ran. Every rig PR predated the rig CI
#                        workflow, so this was the normal case, not an edge case.
#
# NEVER-FALSE-GREEN CONTRACT
#   Shapes 3-5 need PR state. If `gh` is missing, rate-limited, offline, or the repo has no
#   github remote, this reports UNDETERMINED for that repo and exits 3 — it does NOT report
#   clean. "Could not determine" resolving to green is the vacuous-receipt defect this rig keeps
#   re-learning; it is refused here by construction. Shapes 1-2 are pure local git and are never
#   undetermined.
#
# FRESH-CHECKOUT / EMPTY-STATE SAFETY
#   fleet/state/ is gitignored, so in CI it is ABSENT. A missing claims dir must not turn every
#   worktree into a finding, and a repo key whose checkout does not exist on this box is SKIPPED,
#   not flagged. A detector that reds spuriously gets disabled [[gates-must-actually-run]].
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]
#   This script must NEVER invoke preflight.sh, validate_board.sh, land*.sh, branch-reaper.sh,
#   or any gate that could re-invoke it. It is local git + ONE cached gh list per repo.
#   STRANDED_WORK_ACTIVE additionally short-circuits any accidental nesting.
#
# Usage: fleet/checks/stranded-work.sh [--quiet]
# Exit:  0 fully determined, nothing stranded
#        1 stranded work FOUND (advisory — callers may treat as informational)
#        2 usage error
#        3 UNDETERMINED (PR state unreadable for at least one repo; nothing else found)
# Env:
#   SW_KEYS        repo-registry keys to scan  (default: "charon charon-private")
#   SW_REPO        single-target override: a repo path (ignores SW_KEYS)
#   SW_BASE        base ref for the single-target override (default: master)
#   SW_WT_GLOB     single-target override: glob for that repo's worktree dirs
#   SW_FLEET_DIR   fleet dir holding state/claims + state/needs-push (default: this script's ../)
#   SW_PR_FIXTURE  offline/test hook: TSV "<pr#>\t<state>\t<headRefName>\t<check-count>"
#                  replacing the gh call entirely (state: OPEN|CLOSED|MERGED)
#   SW_LIMIT       max DETAIL lines printed per shape (default 5; 0 = print all). Counts and the
#                  exit status are never capped — only the printed detail.
#   SW_NO_GH=1     do not call gh at all (forces UNDETERMINED unless SW_PR_FIXTURE is set)
#   SW_CACHE_TTL   seconds to reuse a cached gh PR list (default 300)
set -uo pipefail

[ -n "${STRANDED_WORK_ACTIVE:-}" ] && { echo "stranded-work: already running (reentrancy guard) — skipping"; exit 0; }
export STRANDED_WORK_ACTIVE=1

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET="${SW_FLEET_DIR:-$(cd "$HERE/.." && pwd)}"
QUIET=0
case "${1:-}" in
  --quiet) QUIET=1 ;;
  "") ;;
  *) echo "usage: stranded-work.sh [--quiet]" >&2; exit 2 ;;
esac

FOUND=0
UNDET=0
# PER-SHAPE OUTPUT CAP. The first live run emitted 100+ dirty-worktree lines (ephemeral dogfood
# eval sandboxes), which is the same failure as being switched off: an unreadable report gets
# skimmed past. Findings are COUNTED in full and exit status is unaffected — only the printed
# detail is capped, exactly like preflight.sh's report_hits. SW_LIMIT=0 prints everything.
LIMIT="${SW_LIMIT:-5}"
declare -A SHAPE_N=()
say(){ [ "$QUIET" -eq 1 ] || echo "$*"; }
finding(){
  FOUND=$((FOUND+1))
  local n=$(( ${SHAPE_N[$1]:-0} + 1 )); SHAPE_N[$1]=$n
  if [ "$LIMIT" -eq 0 ] || [ "$n" -le "$LIMIT" ]; then echo "STRANDED[$1] $2"
  elif [ "$n" -eq $((LIMIT+1)) ]; then echo "STRANDED[$1] ... more of this shape suppressed (SW_LIMIT=0 for the full list)"; fi
}
undetermined(){ UNDET=1; echo "UNDETERMINED $*"; }

# ── PR state, batched + cached ────────────────────────────────────────────────────────────────
# ONE gh call per repo per TTL, mirroring fleet/gh-cache.sh's contract (that file batches MERGED
# PRs only and exposes no state/checks columns, so it cannot answer shapes 4/5; the caching
# discipline is copied deliberately rather than the file being widened, which would change a
# primitive four other callers depend on).
# Prints TSV "<pr#>\t<state>\t<headRefName>\t<check-count>"; returns non-zero when unreadable.
_pr_tsv(){
  local repo="$1" slug cf dir ttl now age=999999
  if [ -n "${SW_PR_FIXTURE:-}" ]; then cat "$SW_PR_FIXTURE" 2>/dev/null; return 0; fi
  [ -n "${SW_NO_GH:-}" ] && return 1
  command -v gh >/dev/null 2>&1 || return 1
  slug="$(git -C "$repo" remote get-url origin 2>/dev/null \
          | sed -E 's#^.*github\.com[:/]##; s/\.git$//')" || return 1
  case "$slug" in */*) ;; *) return 1 ;; esac   # not a github remote: unreadable, not clean
  dir="${GH_CACHE_DIR:-$FLEET/state/cache}"; mkdir -p "$dir" 2>/dev/null
  ttl="${SW_CACHE_TTL:-300}"; cf="$dir/stranded-prs-${slug//\//_}.tsv"
  now="$(date +%s 2>/dev/null || echo 0)"
  [ -f "$cf" ] && age=$(( now - $(stat -c %Y "$cf" 2>/dev/null || echo 0) ))
  if [ ! -f "$cf" ] || [ "$age" -gt "$ttl" ]; then
    if gh pr list --repo "$slug" --state all --limit 300 \
         --json number,state,headRefName,statusCheckRollup \
         -q '.[] | [(.number|tostring), .state, .headRefName, ((.statusCheckRollup // []) | length | tostring)] | @tsv' \
         > "$cf.tmp" 2>/dev/null; then mv "$cf.tmp" "$cf"; else rm -f "$cf.tmp"; fi
  fi
  # A STALE cache is still usable (same call as gh-cache.sh). NO cache at all => cannot verify.
  [ -f "$cf" ] || return 1
  cat "$cf" 2>/dev/null
}

# ── claim awareness ───────────────────────────────────────────────────────────────────────────
# A worktree whose ticket is CLAIMED (or holds a needs-push marker) is in-flight, not stranded.
# Missing state dirs (fresh checkout) simply mean "no claims" — never a reason to flag more.
_claimed(){
  local id="$1"
  [ -n "$id" ] || return 1
  [ -e "$FLEET/state/claims/$id" ] && return 0
  [ -e "$FLEET/state/needs-push/$id" ] && return 0
  return 1
}

# worktree dir -> ticket id. Product worktrees are "<...>/charon-fleet-<id>"; rig worktrees are
# "<...>/<id>". Both reduce to the basename minus the product prefix.
_wt_id(){ local b; b="$(basename "$1")"; printf '%s' "${b#charon-fleet-}"; }

# ── the four scans ────────────────────────────────────────────────────────────────────────────

# SHAPE 1: local branch with commits on no remote ref.
scan_unpushed_branches(){
  local repo="$1" base="$2" b n
  while IFS= read -r b; do
    [ -n "$b" ] || continue
    [ "$b" = "$base" ] && continue
    n="$(git -C "$repo" rev-list --count "$b" --not --remotes 2>/dev/null || echo 0)"
    [ "${n:-0}" -gt 0 ] 2>/dev/null || continue
    finding unpushed-branch "$repo: branch '$b' has $n commit(s) on NO remote ref"
  done < <(git -C "$repo" for-each-ref --format='%(refname:short)' refs/heads/ 2>/dev/null)
}

# SHAPE 2: worktree with real uncommitted work and no live claim.
scan_dirty_worktrees(){
  local repo="$1" wt id st
  while IFS= read -r wt; do
    [ -n "$wt" ] || continue
    [ "$(cd "$wt" 2>/dev/null && pwd -P)" = "$(cd "$repo" 2>/dev/null && pwd -P)" ] && continue
    [ -d "$wt" ] || continue
    id="$(_wt_id "$wt")"
    _claimed "$id" && continue
    st="$(git -C "$wt" status --porcelain 2>/dev/null)"
    [ -n "$st" ] || continue
    finding dirty-worktree "$wt: $(printf '%s\n' "$st" | grep -c .) uncommitted/untracked path(s), no live claim for '$id'"
  done < <(git -C "$repo" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p')
}

# SHAPES 3/4/5: everything that needs PR state. One TSV read, three passes.
scan_pr_shapes(){
  local repo="$1" base="$2" tsv pr state head checks
  if ! tsv="$(_pr_tsv "$repo")"; then
    undetermined "$repo: PR state unreadable (gh missing/offline/rate-limited or no github remote)"
    echo "          shapes pushed-no-pr / closed-pr-unlanded / pr-no-checks NOT checked here."
    return 0
  fi

  # 3: remote branch, unmerged into base, with NO PR of any state.
  local rb short
  while IFS= read -r rb; do
    short="${rb#origin/}"
    [ -n "$short" ] || continue
    [ "$short" = "$base" ] && continue
    [ "$short" = HEAD ] && continue
    printf '%s\n' "$tsv" | cut -f3 | grep -qxF "$short" && continue
    # unmerged into base?
    git -C "$repo" merge-base --is-ancestor "$rb" "origin/$base" 2>/dev/null && continue
    finding pushed-no-pr "$repo: remote branch '$short' is unmerged into $base and has NO PR"
  done < <(git -C "$repo" for-each-ref --format='%(refname:short)' refs/remotes/origin/ 2>/dev/null)

  while IFS=$'\t' read -r pr state head checks; do
    [ -n "${pr:-}" ] || continue
    case "$state" in
      CLOSED)
        # 4: closed-but-unlanded. Commits still absent from base => real work was closed away.
        local ref="" n
        if git -C "$repo" rev-parse --verify -q "origin/$head" >/dev/null 2>&1; then ref="origin/$head"
        elif git -C "$repo" rev-parse --verify -q "$head" >/dev/null 2>&1; then ref="$head"; fi
        [ -n "$ref" ] || continue   # branch genuinely gone: nothing left to strand
        n="$(git -C "$repo" rev-list --count "$ref" --not "origin/$base" 2>/dev/null || echo 0)"
        [ "${n:-0}" -gt 0 ] 2>/dev/null || continue
        finding closed-pr-unlanded "$repo: PR #$pr is CLOSED but '$head' still carries $n commit(s) not on $base"
        ;;
      OPEN)
        # 5: zero checks. Not "checks failed" — checks NEVER RAN, and the UI calls that mergeable.
        [ "${checks:-0}" = "0" ] || continue
        finding pr-no-checks "$repo: PR #$pr ('$head') is OPEN with ZERO CI checks — mergeable-looking with nothing verified"
        ;;
    esac
  done <<< "$tsv"
}

# ── target resolution ─────────────────────────────────────────────────────────────────────────
# "path<TAB>base" lines. Single-target override exists for hermetic fixtures; otherwise paths come
# from fleet/repo-registry.sh, the rig's path SSOT — no checkout path is spelled out in this file.
targets(){
  if [ -n "${SW_REPO:-}" ]; then
    printf '%s\t%s\n' "$SW_REPO" "${SW_BASE:-master}"
    return 0
  fi
  # shellcheck source=/dev/null
  source "$FLEET/repo-registry.sh" 2>/dev/null || return 0
  local k
  for k in ${SW_KEYS:-charon charon-private}; do
    repo_resolve "$k" "" >/dev/null 2>&1 || continue
    printf '%s\t%s\n' "$RR_PATH" "$RR_BASE"
  done
}

echo "--- stranded-work: recurring detector (REPORT ONLY — deletes nothing) ---"
while IFS=$'\t' read -r repo base; do
  [ -n "${repo:-}" ] || continue
  if [ ! -d "$repo/.git" ] && [ ! -f "$repo/.git" ]; then
    say "skip: $repo (no checkout on this box)"
    continue
  fi
  say "scan: $repo (base $base)"
  scan_unpushed_branches "$repo" "$base"
  scan_dirty_worktrees "$repo"
  scan_pr_shapes "$repo" "$base"
done < <(targets)

if [ "$FOUND" -gt 0 ]; then
  for s in "${!SHAPE_N[@]}"; do echo "stranded-work: ${SHAPE_N[$s]} x $s"; done
  echo "stranded-work: $FOUND finding(s) — REPORT ONLY. Recover with fleet/land.sh <branch> <repo>; never reap by hand."
  exit 1
fi
if [ "$UNDET" -eq 1 ]; then
  echo "stranded-work: 0 findings but PR state was UNREADABLE — this is NOT a clean receipt."
  exit 3
fi
echo "clean: stranded-work (0 findings, all shapes determined)"
exit 0
