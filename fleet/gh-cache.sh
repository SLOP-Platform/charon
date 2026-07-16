#!/usr/bin/env bash
# gh-cache.sh — batch the fleet's merged-PR lookups into ONE gh call per repo (cached, short TTL),
# so a fleet loop costs O(repos) API calls instead of O(tickets). Root cause of the GitHub API
# rate-limit exhaustion: foreman.sh did `gh pr list --head <branch>` per blocked ticket (x2 repos),
# done.sh/retire-done did per-ticket gh calls — hundreds per sweep. This makes it a handful.
#
# Sourced by callers; provides:
#   branch_merged_pr <repo-slug> <branch>   -> prints the MERGED PR number for <branch> (or empty),
#                                              from a cached list; NO per-branch gh call.
# Offline/CI/test hook: GH_MERGED_FIXTURE=<file> (TSV "<branch>\t<pr#>") bypasses gh entirely.
# Tunables: GH_CACHE_DIR (default <fleet>/state/cache), GH_CACHE_TTL seconds (default 120).

# resolve fleet dir for a default cache location (callers usually set FLEET already)
_ghc_fleet(){ if [ -n "${FLEET:-}" ]; then printf '%s' "$FLEET"; else (cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); fi; }

# _gh_merged_tsv <repo-slug> -> "<branch>\t<pr#>" lines. Fetches ONCE per TTL, caches to disk.
_gh_merged_tsv(){
  local slug="$1"
  if [ -n "${GH_MERGED_FIXTURE:-}" ]; then cat "$GH_MERGED_FIXTURE" 2>/dev/null; return 0; fi
  local dir="${GH_CACHE_DIR:-$(_ghc_fleet)/state/cache}"; mkdir -p "$dir" 2>/dev/null
  local ttl="${GH_CACHE_TTL:-120}" cf="$dir/merged-${slug//\//_}.tsv" now age=999999
  now="$(date +%s 2>/dev/null || echo 0)"
  [ -f "$cf" ] && age=$(( now - $(stat -c %Y "$cf" 2>/dev/null || echo 0) ))
  if [ ! -f "$cf" ] || [ "$age" -gt "$ttl" ]; then
    # ONE gh call for the whole repo's merged PRs (batched). On failure keep any stale cache.
    if gh pr list --repo "$slug" --state merged --limit 800 --json number,headRefName \
         -q '.[] | .headRefName + "\t" + (.number|tostring)' > "$cf.tmp" 2>/dev/null; then mv "$cf.tmp" "$cf"
    else rm -f "$cf.tmp"; fi
  fi
  cat "$cf" 2>/dev/null
}

# branch_merged_pr <repo-slug> <branch> -> merged PR number or empty. No per-branch API call.
branch_merged_pr(){
  local slug="$1" br="$2"; [ -n "$br" ] || return 0
  _gh_merged_tsv "$slug" | awk -F'\t' -v b="$br" '$1==b{print $2; exit}'
}
