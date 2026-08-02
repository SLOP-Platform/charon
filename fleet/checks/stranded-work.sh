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
# SQUASH-MERGE AWARENESS (the day-one false-positive class)
#   This repo merges via SQUASH. A squash merge creates a NEW commit sha, so the original branch
#   commits are permanently unreachable from every remote ref even though the CONTENT is fully
#   landed on base. "Unreachable" therefore does NOT mean "stranded". Measured on the live rig
#   2026-07-19, the naive reachability test reported FIVE branches (PRs #121/#123/#124/#125/#126)
#   that were all already merged — findings that could never clear, on the detector's first real
#   run.
#   A detector that cries wolf on day one gets switched off, which is the exact
#   [[gates-must-actually-run]] failure this file exists to end.
#
#   THE TEST USED: net-diff PATCH-ID. A branch's content is landed when the patch-id of its net
#   diff (merge-base..branch) equals the patch-id of some commit already on base — which is
#   precisely what a squash commit is. `git cherry` was REJECTED: it compares per-commit
#   patch-ids, so it only ever recognises a squash of a SINGLE-commit branch; three of the five
#   real false positives carry 2-4 commits. Base patch-ids are collected in ONE
#   `git log -p | git patch-id` pass per repo, computed LAZILY (only if some branch is unreachable)
#   and cached, so the common clean case costs nothing. Nothing is written to the object store —
#   the `git commit-tree` variant of this recipe was rejected for that reason alone (report-only).
#
#   DIRECTION THAT MUST NOT WEAKEN: a branch whose content is genuinely NOT on base is STILL
#   reported. The patch-id test can only ever SUPPRESS on positive proof of landing; every
#   inconclusive path reports, annotated UNVERIFIED. See SW_SQUASH_SCAN below.
#
# THE EIGHT SHAPES (each one was REAL on this rig; each has a fail-on-revert test)
#   Shapes 6-8 were added after the detector's FIRST REAL MISS: a 96-commit backlog that the
#   original five shapes could not see. Shape 6 was being detected and MISNAMED; shapes 7-8 were
#   not represented at all. Narrow coverage, not a broken check, is what let the backlog build.
#   1 unpushed-branch    local branch with commits reachable from no remote ref AND whose content
#                        is not provably landed on base (see SQUASH-MERGE AWARENESS).
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
#   6 ahead-of-remote    branch that TRACKS a remote but is ahead of it. Already detected by the
#                        shape-1 walk; it was reported AS shape 1, which is the wrong triage
#                        instruction (see scan_unpushed_branches). Relabelled, not re-scanned.
#   7 stash              refs/stash entries: content on no branch and no remote, invisible to
#                        every branch/worktree audit, destroyed silently by `stash clear`/prune.
#                        PER-REPO (one stash list per common git dir), never per-worktree.
#   8 detached-head      worktree on an anonymous HEAD carrying commits reachable from no branch
#                        and no remote. Emitted BEFORE the dirty check: a CLEAN detached checkout
#                        is still stranded, and `git status` has nothing to say about it.
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
#   SW_SQUASH_SCAN how many commits back along base to collect patch-ids for squash detection
#                  (default 300). A branch whose merge-base is OLDER than this window cannot be
#                  decided locally: it is reported as UNVERIFIED, never silently cleared.
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

# ── squash-merge awareness ────────────────────────────────────────────────────────────────────
# PER-REPO PR TSV, fetched ONCE by the main loop and shared by every scan below. Two globals
# rather than a second _pr_tsv call: the "is this branch's PR merged?" question is answered from
# the SAME rows shapes 3/4/5 already read, so squash-awareness costs ZERO extra gh calls and adds
# ZERO new fixture surface (SW_PR_FIXTURE covers it, exactly as before).
# WHY NOT fleet/gh-cache.sh's branch_merged_pr: it is a genuinely separate seam — its own cache
# file, its own TTL, its own GH_MERGED_FIXTURE hook. Sourcing it here would put TWO GitHub seams
# in one script that must agree about merge state, and two seams that must agree will drift. The
# reuse that actually applies is of this file's existing, already-paid-for query.
REPO_TSV=""; REPO_TSV_OK=0

# Base-side patch-ids, ONE `git log -p | git patch-id` pass per repo, built lazily on first need.
declare -A _BASE_PIDS=()      # "<repo>|<baseref>" -> newline-joined patch-ids
_base_pids(){
  local repo="$1" baseref="$2" key="$1|$2"
  if [ -z "${_BASE_PIDS[$key]+set}" ]; then
    _BASE_PIDS[$key]="$(git -C "$repo" log -p --no-merges --max-count="${SW_SQUASH_SCAN:-300}" \
                          "$baseref" 2>/dev/null | git -C "$repo" patch-id --stable 2>/dev/null \
                          | cut -d' ' -f1)"
  fi
  printf '%s' "${_BASE_PIDS[$key]}"
}

# _merge_verdict <repo> <branch> <base> -> prints "landed" | "unlanded" | "unverified: <why>"
# ONLY "landed" suppresses a finding, and only on positive proof. Every other path reports.
_merge_verdict(){
  local repo="$1" b="$2" base="$3" baseref="" mb bpid gap
  if git -C "$repo" rev-parse --verify -q "origin/$base" >/dev/null 2>&1; then baseref="origin/$base"
  elif git -C "$repo" rev-parse --verify -q "$base" >/dev/null 2>&1; then baseref="$base"
  else printf 'unverified: no %s ref to compare against' "$base"; return 0; fi

  # Plain (non-squash) merge or already contained: reachable from base. Cheapest test, first.
  git -C "$repo" merge-base --is-ancestor "$b" "$baseref" 2>/dev/null && { printf landed; return 0; }

  mb="$(git -C "$repo" merge-base "$b" "$baseref" 2>/dev/null)"
  [ -n "$mb" ] || { printf 'unverified: no merge-base with %s' "$baseref"; return 0; }

  # Net diff of the branch since it forked. Empty => the branch adds no content at all.
  bpid="$(git -C "$repo" diff "$mb" "$b" 2>/dev/null | git -C "$repo" patch-id --stable 2>/dev/null | cut -d' ' -f1)"
  [ -n "$bpid" ] || { printf landed; return 0; }

  # THE squash test: does some commit already on base carry this exact net diff?
  if printf '%s\n' "$(_base_pids "$repo" "$baseref")" | grep -qxF "$bpid"; then printf landed; return 0; fi

  # No match. Was the window even wide enough to contain the merge point? If the branch forked
  # further back than SW_SQUASH_SCAN, "no match" proves nothing — fall back to PR state (from the
  # TSV already fetched), and if that is unreadable too, say UNVERIFIED rather than guessing.
  gap="$(git -C "$repo" rev-list --count "$mb..$baseref" 2>/dev/null || echo 0)"
  if [ "${gap:-0}" -gt "${SW_SQUASH_SCAN:-300}" ] 2>/dev/null; then
    if [ "$REPO_TSV_OK" -eq 1 ]; then
      if printf '%s\n' "$REPO_TSV" | awk -F'\t' -v b="$b" '$2=="MERGED" && $3==b{f=1} END{exit !f}'; then
        printf landed; return 0
      fi
      printf 'unverified: forked %s commits before base tip (beyond SW_SQUASH_SCAN) and no MERGED PR found' "$gap"
      return 0
    fi
    printf 'unverified: forked %s commits before base tip (beyond SW_SQUASH_SCAN) and PR state unreadable' "$gap"
    return 0
  fi
  printf unlanded
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

# SHAPES 1 + 6: local branch with commits on no remote ref.
#
# WHY THIS SPLITS INTO TWO SHAPES [[fix-root-cause-never-workaround]]
#   `--not --remotes` already CAUGHT the ahead-of-upstream case — a branch that was pushed once
#   and then grew 5 more local commits has those 5 commits on no remote ref, so n>0 and it was
#   reported. It was reported under the WRONG NAME: "unpushed-branch". That mislabel is not
#   cosmetic. It is why the 96-commit backlog read as noise: an operator scanning a wall of
#   "unpushed-branch" lines reads them as "branches I never pushed", triages the ones with no
#   remote, and skips the rest — while the ahead-of-remote rows are the ones with a LIVE PR
#   whose head is silently missing commits, i.e. the higher-severity half.
#   So this is a RELABEL of an existing detection (via @{upstream}), NOT a new scan. Same walk,
#   same cost, same suppression rules; only the shape name and the message differ.
scan_unpushed_branches(){
  local repo="$1" base="$2" b n up ahead shape
  while IFS= read -r b; do
    [ -n "$b" ] || continue
    [ "$b" = "$base" ] && continue
    n="$(git -C "$repo" rev-list --count "$b" --not --remotes 2>/dev/null || echo 0)"
    [ "${n:-0}" -gt 0 ] 2>/dev/null || continue
    # Does this branch have a remote counterpart OF ITS OWN NAME? Only then are its commits
    # "ahead of a remote" rather than "never pushed".
    # PRECISION THAT MATTERS: `git checkout -b foo origin/master` sets foo's upstream to
    # origin/MASTER. A naive @{upstream} test therefore calls every freshly-branched, never-pushed
    # branch "ahead-of-remote" — which is the mislabel this shape exists to FIX, just inverted.
    # So the upstream's branch component must equal $b AND that ref must actually exist.
    local rem merge upb
    rem="$(git -C "$repo" config --get "branch.$b.remote" 2>/dev/null || true)"
    merge="$(git -C "$repo" config --get "branch.$b.merge" 2>/dev/null || true)"
    upb="${merge#refs/heads/}"
    up=""
    if [ -n "$rem" ] && [ "$upb" = "$b" ] \
       && git -C "$repo" rev-parse --verify -q "$rem/$b" >/dev/null 2>&1; then
      up="$rem/$b"
    fi
    if [ -n "$up" ]; then
      shape=ahead-of-remote
      ahead="$(git -C "$repo" rev-list --count "$up..$b" 2>/dev/null || echo "$n")"
    else
      shape=unpushed-branch; ahead="$n"
    fi
    # Unreachable != stranded under SQUASH merge. Suppress ONLY on positive proof that the
    # content is already on base; report everything else, annotating what could not be decided.
    local v; v="$(_merge_verdict "$repo" "$b" "$base")"
    local where; if [ -n "$up" ]; then where="AHEAD of its upstream '$up' by $ahead commit(s)"; else where="$n commit(s) on NO remote ref"; fi
    case "$v" in
      landed) continue ;;
      unlanded) finding "$shape" "$repo: branch '$b' is $where and its content is NOT on $base" ;;
      *)        finding "$shape" "$repo: branch '$b' is $where — merge status UNVERIFIED (${v#unverified: })" ;;
    esac
  done < <(git -C "$repo" for-each-ref --format='%(refname:short)' refs/heads/ 2>/dev/null)
}

# SHAPE 7: STASHES. Wholly absent before — and a stash is the purest form of stranded work:
# content that exists in the object store, is reachable from NO branch and NO remote, survives
# every branch/worktree audit this file already did, and is destroyed silently by `git stash
# clear` or a `.git` prune. It is PER-REPO, not per-worktree: refs/stash lives in the common
# git dir, so every linked worktree shares ONE stash list. Scanning it per-worktree would report
# the same entries N times (the "unreadable report gets skimmed past" failure) and would be wrong
# about which checkout the work belongs to.
# Report-only, like everything else here: this NEVER runs `stash drop`/`clear`.
scan_stashes(){
  local repo="$1" n first
  n="$(git -C "$repo" stash list 2>/dev/null | grep -c . || true)"
  [ "${n:-0}" -gt 0 ] 2>/dev/null || return 0
  first="$(git -C "$repo" stash list 2>/dev/null | head -1)"
  finding stash "$repo: $n stash entr(ies) on NO branch/remote (newest: ${first:-?}) — inspect with: git -C $repo stash list"
}

# SHAPES 2 + 8: per-worktree scans.
#
# WHY THE PORCELAIN IS NOW PARSED AS RECORDS
#   `git worktree list --porcelain` emits a RECORD per worktree — `worktree <path>`, `HEAD <sha>`,
#   then either `branch <ref>` or the bare word `detached`. The previous `sed -n 's/^worktree //p'`
#   threw the `detached` line on the floor, so shape 8 was unreachable by construction: the one
#   field that identifies it was discarded before any test could look at it.
#
# SHAPE 8: DETACHED HEAD. Emitted BEFORE the dirty-check `continue`, because a detached HEAD is
#   stranded whether or not the worktree is dirty — a CLEAN detached checkout carrying commits on
#   no ref is exactly the silent case (nothing to `git status`, nothing to push, no branch name to
#   show up in any branch audit; the commits vanish on the next `git gc`).
#   PRECISION GUARD (kept deliberately, [[gates-must-actually-run]]): a detached HEAD parked on a
#   commit that IS reachable from some branch/remote is a PINNED CHECKOUT (this rig keeps two:
#   a baseline and a verify-master worktree), not lost work — it is recoverable by name and is NOT
#   reported. Only commits reachable from HEAD and from NO branch and NO remote count. That is the
#   same "unreachable content" test shape 1 uses, applied to an anonymous head.
scan_worktrees(){
  local repo="$1" wt det id st orphan
  while IFS=$'\t' read -r wt det; do
    [ -n "$wt" ] || continue
    [ -d "$wt" ] || continue

    # --- SHAPE 8 first: applies to EVERY worktree including the primary checkout, and does not
    # depend on dirtiness. A detached primary checkout is the most dangerous instance of all.
    if [ "${det:-0}" = "1" ]; then
      orphan="$(git -C "$wt" rev-list --count HEAD --not --branches --remotes 2>/dev/null || echo 0)"
      if [ "${orphan:-0}" -gt 0 ] 2>/dev/null; then
        finding detached-head "$wt: DETACHED HEAD at $(git -C "$wt" rev-parse --short HEAD 2>/dev/null) carrying $orphan commit(s) on NO branch and NO remote"
      fi
    fi

    # --- SHAPE 2: uncommitted work, no live claim. Primary checkout excluded (it is the scan
    # root, always "dirty" with the operator's in-progress session).
    [ "$(cd "$wt" 2>/dev/null && pwd -P)" = "$(cd "$repo" 2>/dev/null && pwd -P)" ] && continue
    id="$(_wt_id "$wt")"
    _claimed "$id" && continue
    st="$(git -C "$wt" status --porcelain 2>/dev/null)"
    [ -n "$st" ] || continue
    finding dirty-worktree "$wt: $(printf '%s\n' "$st" | grep -c .) uncommitted/untracked path(s), no live claim for '$id'"
  done < <(git -C "$repo" worktree list --porcelain 2>/dev/null | awk '
      /^worktree /{ if (p != "") printf "%s\t%d\n", p, d; p=substr($0,10); d=0; next }
      /^detached$/{ d=1; next }
      END{ if (p != "") printf "%s\t%d\n", p, d }')
}

# SHAPES 3/4/5: everything that needs PR state. One TSV read, three passes.
scan_pr_shapes(){
  local repo="$1" base="$2" tsv pr state head checks
  tsv="$REPO_TSV"
  if [ "$REPO_TSV_OK" -ne 1 ]; then
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
  # ONE PR query per repo, hoisted so shape 1's squash fallback and shapes 3/4/5 share it.
  REPO_TSV=""; REPO_TSV_OK=0
  if REPO_TSV="$(_pr_tsv "$repo")"; then REPO_TSV_OK=1; else REPO_TSV=""; fi
  scan_unpushed_branches "$repo" "$base"
  scan_stashes "$repo"
  scan_worktrees "$repo"
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
