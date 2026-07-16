#!/usr/bin/env bash
# reconcile-held-markers.sh — RESOLVE state/done/* HELD markers, repo-aware, batched.
#
# BACKSTORY (2026-07-15): retire-done.sh refused to archive 33 state/done/* markers because
# verify_merged could not PROVE they were merge-verified. Most carry `merged:#<pr>` (PR-number
# proof) and fall to a `gh` network check; if gh is missing/slow/rate-limited, that fallback
# can't confirm the merge and the marker stays HELD, cluttering the active board forever (the
# board<->GitHub done-marker drift class of bug). Done-marker write PROOF must be the LOCAL,
# deterministic form — a `merged:<sha>` that the offline ancestor check in verify_merged can
# resolve. This script backfills that proof.
#
# For each state/done/* marker that LACKS `merged:<sha>`, ONCE:
#   1. Read the ticket's `branch:` (board or board/archive) and `repo:` (defaults to "charon"
#      when the field is absent, matching the pre-schema majority of the 33 HELD backlog).
#   2. Map repo -> owner/slug (charon -> SLOP-Platform/charon, charon-private ->
#      Nnyan/charon-private). The two repos the rig has ever emitted tickets into; new repos
#      must be added here AND surfaced so the rig doesn't grow an invisible "I don't know
#      where this lives" bucket.
#   3. BATCH (the perf trap): ONE `gh pr list --state merged --limit 200` per distinct repo,
#      NOT per marker. Pre-group markers by repo, fan out one query per repo, then map each
#      marker's branch to the merged-PR row in memory. This is the same class of fix as
#      done.sh / reconcile-merged perf bugs (O(markers * network) -> O(repos)).
#   4. If the branch has a MERGED PR with a mergeCommit oid -> rewrite the marker line to
#      carry `merged:<sha>` (the local ancestor check now resolves the marker OFFLINE from
#      that point on; verify_merged's fast path returns 0 before any network call). Leave
#      everything else on the line intact (date, branch:). Then retire-done will archive
#      the marker on its next pass.
#   5. If the branch has NO merged PR (still open, never opened, or wrong repo) -> leave
#      HELD and EMIT it to a needs-action list (do NOT silently archive unmerged work — that
#      violates retire-done's G3c guard, which is the whole point of this class of gate).
#   6. If a marker was already proven (carries `merged:<sha>` or an `override:`) -> skip
#      (idempotent; safe to re-run on every preflight).
#
# Network-tolerant: gh missing/offline -> warn once, leave markers HELD (no destructive act),
# exit 0 (never blocks preflight). Same offline posture as retire-done / reconcile-merged.
#
# TEST HOOK: RECONCILE_HELD_SRC=<file>, TSV "repo\tbranch\tsha" (one row per (repo,branch) that
# HAS a merged PR; sha = the mergeCommit oid). Distinct from RECONCILE_MERGED_SRC by name so
# both hooks can coexist. RECONCILE_HELD_REPO=<path> overrides the rig repo (for the
# board/<id>.md lookup); RECONCILE_HELD_DRY_RUN=1 prints what would change but writes nothing.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAB=$'\t'

# --- repo -> owner/slug map. The two repos the rig has ever emitted tickets into; adding
# a new repo is a deliberate, visible act (justification logged below). ---
repo_to_slug(){
  case "$1" in
    charon)         printf '%s' "SLOP-Platform/charon" ;;
    charon-private) printf '%s' "Nnyan/charon-private" ;;
    *)              printf '' ;;
  esac
}

meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2" 2>/dev/null || true; }

# locate a board file for <id> (active first, then archive) -> echoes the path. Empty = no file.
board_file_for(){
  local id="$1" f
  for f in "$BOARD_USE/$id.md" "$BOARD_USE/archive/$id.md"; do
    [ -f "$f" ] && { printf '%s' "$f"; return 0; }
  done
  return 1
}

# merged PRs as TSV "repo\tbranch\tsha" from a fixture (one row per known merged head-branch)
# OR a single gh query per distinct repo. Empty sha means "not merged". Network-tolerant.
gather_merged(){
  if [ -n "${RECONCILE_HELD_SRC:-}" ]; then
    [ -f "$RECONCILE_HELD_SRC" ] && grep -v '^[[:space:]]*$' "$RECONCILE_HELD_SRC" || true
    return 0
  fi
  command -v gh >/dev/null 2>&1 || return 0
  local r slug out
  for r in $(printf '%s\n' "${REPOS_TO_QUERY[@]}" | sort -u); do
    [ -n "$r" ] || continue
    slug="$(repo_to_slug "$r")"; [ -n "$slug" ] || continue
    out="$(gh pr list --repo "$slug" --state merged --limit 200 \
            --json headRefName,mergeCommit \
            -q ".[] | [\"$r\", .headRefName, (.mergeCommit.oid // \"\")] | @tsv" \
            2>/dev/null || true)"
    printf '%s\n' "$out"
  done
}

# HELD test: a marker is HELD iff it has NO `merged:<sha>` proof. `merged:#<pr>` is still
# HELD (falls to network check in verify_merged; we want to UPGRADE it to a local sha proof).
# `override:` and `merged:<sha>` markers are NOT held and are skipped.
is_held_marker(){
  local mk="$1" proof val
  grep -q 'override:' "$mk" 2>/dev/null && return 1
  proof="$(grep -oE 'merged:#?[0-9a-fA-F]+' "$mk" 2>/dev/null | head -1)"
  val="${proof#merged:}"; val="${val#\#}"
  if printf '%s' "$val" | grep -qiE '^[0-9a-f]{7,40}$'; then return 1; fi
  return 0
}

# PHASE 1: enumerate HELD markers, extract (id, repo, branch) tuples. Group repos.
# RECONCILE_HELD_DONE_DIR overrides DONE so isolated tests can use a fresh dir without
# shipping the live fleet/state.
DONE="${RECONCILE_HELD_DONE_DIR:-$FLEET/state/done}"
BOARD_USE="${RECONCILE_HELD_BOARD_DIR:-$FLEET/board}"
declare -A MARKER_REPO=()  # id -> repo
declare -A MARKER_BRANCH=() # id -> branch
declare -a REPOS_TO_QUERY=()
declare -a HELD_IDS=()
[ -d "$DONE" ] || { echo "reconcile-held: no state/done dir — nothing to do"; exit 0; }
for m in "$DONE"/*; do
  [ -f "$m" ] || continue
  id="$(basename "$m")"
  is_held_marker "$m" || continue
  HELD_IDS+=("$id")
  bfile="$(board_file_for "$id" 2>/dev/null || true)"
  repo=""; branch=""
  if [ -n "$bfile" ]; then
    repo="$(meta repo "$bfile")"; branch="$(meta branch "$bfile")"
  fi
  # pre-`repo:`-schema tickets (the majority of the 33 HELD backlog): default to the product.
  [ -n "$repo" ] || repo="charon"
  [ -n "$branch" ] || branch="n/a"
  MARKER_REPO["$id"]="$repo"
  MARKER_BRANCH["$id"]="$branch"
  REPOS_TO_QUERY+=("$repo")
done

if [ "${#HELD_IDS[@]}" -eq 0 ]; then
  echo "reconcile-held: clean (0 HELD markers; nothing to backfill)."
  exit 0
fi
echo "reconcile-held: found ${#HELD_IDS[@]} HELD marker(s); querying ${#REPOS_TO_QUERY[@]} repo(s) (batched)."

# PHASE 2: build an in-memory map. key = "<repo>|<branch>", value = merge sha. Empty/missing
#           means "not merged in that repo". Skipped repos (unknown slug) stay empty.
declare -A MERGE_SHA=()
while IFS="$TAB" read -r r b s; do
  [ -n "$r" ] || continue
  [ -n "$b" ] || continue
  MERGE_SHA["$r|$b"]="$s"
done < <(gather_merged)

# PHASE 3: for each HELD marker, look up (repo, branch) -> sha. If found, rewrite the marker
#           to add `merged:<sha>` (preserving the rest of the line). Otherwise, list it.
backfilled=0; needs_action=0; needs_action_list=""
skipped_repo=0
for id in "${HELD_IDS[@]}"; do
  repo="${MARKER_REPO[$id]}"; branch="${MARKER_BRANCH[$id]}"
  slug="$(repo_to_slug "$repo")"
  if [ -z "$slug" ]; then
    needs_action=$((needs_action+1))
    needs_action_list="${needs_action_list}${needs_action_list:+$'\n'}  - $id (repo=$repo UNKNOWN; no slug map)"
    skipped_repo=$((skipped_repo+1))
    continue
  fi
  sha="${MERGE_SHA[$repo|$branch]:-}"
  if [ -z "$sha" ]; then
    needs_action=$((needs_action+1))
    needs_action_list="${needs_action_list}${needs_action_list:+$'\n'}  - $id (repo=$repo branch=$branch; no merged PR found)"
    continue
  fi
  # rewrite the marker line. Preserve the date + add merged:<sha>; keep any branch: hint.
  m="$DONE/$id"
  cur="$(cat "$m" 2>/dev/null || true)"
  iso="$(printf '%s' "$cur" | awk -F'\t' '{print $1}')"
  [ -n "$iso" ] || iso="$(date -u +%FT%TZ)"
  new_line="${iso}"$'\t'"merged:${sha}"$'\t'"branch:${branch}"
  if [ "${RECONCILE_HELD_DRY_RUN:-}" = "1" ]; then
    echo "reconcile-held: DRY-RUN would rewrite $id: $cur -> $new_line"
  else
    printf '%s\n' "$new_line" > "$m"
    echo "reconcile-held: backfilled $id with merged:${sha} (repo=$repo branch=$branch) -> retire-done will now archive."
  fi
  backfilled=$((backfilled+1))
done

echo
echo "reconcile-held: backfilled $backfilled, needs-action $needs_action (of ${#HELD_IDS[@]} HELD)."
if [ "$needs_action" -gt 0 ]; then
  echo "reconcile-held: NEEDS-ACTION (genuinely unmerged / unknown repo — NOT archived, in line with retire-done G3c):"
  printf '%s\n' "$needs_action_list"
fi
exit 0
