#!/usr/bin/env bash
# gh-cache.sh — batch the fleet's merged-PR lookups into ONE gh call per repo (cached, short TTL),
# so a fleet loop costs O(repos) API calls instead of O(tickets). Root cause of the GitHub API
# rate-limit exhaustion: foreman.sh did `gh pr list --head <branch>` per blocked ticket (x2 repos),
# done.sh/retire-done did per-ticket gh calls — hundreds per sweep. This makes it a handful.
#
# Sourced by callers; provides:
#   branch_merged_pr <repo-slug> <branch>            -> prints the MERGED PR number for <branch> (or empty),
#                                                     from a cached list; NO per-branch gh call.
#   merged_prs_touching_file <repo-slug> <path>      -> prints the MERGED PR number that touched <path>
#                                                     (or empty), from its own TTL-cached index; NO --search call.
#                                                     GitHub's SEARCH API is 30 req/MIN (10x tighter than core
#                                                     REST) — `gh ... --search "$path"` was the next-to-burn
#                                                     limit. One batched LIST call per repo per TTL caches
#                                                     `files[]` for every merged PR, so each subsequent
#                                                     owns-match is a local grep: ZERO search calls.
#
# NOTE: the two caches are TWO separate batched gh calls (branch list; files index), NOT one.
# That is intentional — see _gh_merged_tsv. Both are O(repos) per TTL, which is the rate-limit
# property that matters; the previous code was O(tickets) search calls.
# Offline/CI/test hooks:
#   GH_MERGED_FIXTURE=<file> (TSV "<branch>\t<pr#>")        — branch_merged_pr bypass, no files.
#   GH_MERGED_FILES_FIXTURE=<file> (TSV "<pr#>\t<path>")    — merged_prs_touching_file bypass.
#   The two fixtures are independent so a test can stub either path separately, mirroring the
#   two independent production caches. A test exercising the real gh path must set NEITHER
#   (see test_github_limits.sh T5 — the no-fixture production-path test).
# Tunables: GH_CACHE_DIR (default <fleet>/state/cache), GH_CACHE_TTL seconds (default 120).

# resolve fleet dir for a default cache location (callers usually set FLEET already)
_ghc_fleet(){ if [ -n "${FLEET:-}" ]; then printf '%s' "$FLEET"; else (cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); fi; }

# _gh_merged_tsv <repo-slug> -> "<branch>\t<pr#>" lines. Fetches ONCE per TTL, caches to disk.
# Backs branch_merged_pr() — the PRIMARY merge-proof path, so it stays deliberately lean:
# branch+number ONLY. It does NOT request `files[]`. Asking for files here costs ~4x wall time
# (measured 0.97s -> 4.23s over 800 merged PRs) on the hot path for a payload this function
# discards, and a slower call is a wider window to time out and fall through to REFUSED.
# The owns-match index is a SEPARATE TTL-cached call (_gh_merged_files_tsv), paid only by the
# owns-match fallback that actually needs it.
_gh_merged_tsv(){
  local slug="$1"
  if [ -n "${GH_MERGED_FIXTURE:-}" ]; then cat "$GH_MERGED_FIXTURE" 2>/dev/null; return 0; fi
  local dir="${GH_CACHE_DIR:-$(_ghc_fleet)/state/cache}"; mkdir -p "$dir" 2>/dev/null
  local ttl="${GH_CACHE_TTL:-120}" cf="$dir/merged-${slug//\//_}.tsv" now age=999999
  now="$(date +%s 2>/dev/null || echo 0)"
  [ -f "$cf" ] && age=$(( now - $(stat -c %Y "$cf" 2>/dev/null || echo 0) ))
  if [ ! -f "$cf" ] || [ "$age" -gt "$ttl" ]; then
    # ONE gh call for the whole repo's merged PRs (batched), branch+number only — see the note
    # above on why `files[]` is deliberately NOT requested here. On failure keep any stale cache.
    if gh pr list --repo "$slug" --state merged --limit 800 \
         --json number,headRefName \
         -q '.[] | .headRefName + "\t" + (.number|tostring)' > "$cf.tmp" 2>/dev/null; then mv "$cf.tmp" "$cf"
    else rm -f "$cf.tmp"; fi
  fi
  cat "$cf" 2>/dev/null
}

# hold_prs_tsv <repo-slug> -> "<pr#>\t<0|1 has a HOLD: comment>" lines, one per OPEN PR carrying
# the `hold` LABEL. Same batching/caching contract as _gh_merged_tsv: ONE gh call per repo per TTL.
# WHY this lives here and not in a new file: it is the identical problem (an O(PRs) gh sweep that
# must survive rate-limits and offline runs), so it reuses this file's cache dir, TTL and fixture
# discipline rather than growing a second gh-shaped module.
# CONVENTION: draft state is the LAUNCHER DEFAULT and carries NO information — a real hold is the
# `hold` label PLUS a `HOLD: <reason>` comment. This query therefore keys on the LABEL only; draft
# PRs are never selected, so a normal draft can never be flagged.
# Offline/CI/test hook: GH_HOLD_FIXTURE=<file> (TSV "<pr#>\t<0|1>") bypasses gh entirely.
hold_prs_tsv(){
  local slug="$1"
  if [ -n "${GH_HOLD_FIXTURE:-}" ]; then cat "$GH_HOLD_FIXTURE" 2>/dev/null; return 0; fi
  local dir="${GH_CACHE_DIR:-$(_ghc_fleet)/state/cache}"; mkdir -p "$dir" 2>/dev/null
  local ttl="${GH_CACHE_TTL:-120}" cf="$dir/hold-${slug//\//_}.tsv" now age=999999
  now="$(date +%s 2>/dev/null || echo 0)"
  [ -f "$cf" ] && age=$(( now - $(stat -c %Y "$cf" 2>/dev/null || echo 0) ))
  if [ ! -f "$cf" ] || [ "$age" -gt "$ttl" ]; then
    # ONE gh call for every open hold-labelled PR (number + its comment bodies), batched.
    if gh pr list --repo "$slug" --state open --label hold --limit 200 --json number,comments \
         -q '.[] | (.number|tostring) + "\t" + (if ([.comments[].body] | map(test("^\\s*HOLD:")) | any) then "1" else "0" end)' \
         > "$cf.tmp" 2>/dev/null; then mv "$cf.tmp" "$cf"
    else rm -f "$cf.tmp"; fi
  fi
  # THE degrade guard (deliberately the ONLY one, so a revert of it is observable): gh absent or
  # rate-limited AND no cache to fall back on -> return NON-ZERO = "cannot verify". Returning 0
  # here would report "no holds" — a silent false green. A STALE cache is still usable (same
  # contract as _gh_merged_tsv).
  [ -f "$cf" ] || return 1
  cat "$cf" 2>/dev/null
  return 0   # explicit: rc is the VERIFIED/UNVERIFIABLE contract, never an incidental cat exit code
}

# _gh_merged_files_tsv <repo-slug> -> "<pr#>\t<path>" lines (one row per touched file, per merged PR).
# Its OWN batched, TTL-cached LIST call (one per repo per TTL) — deliberately separate from the
# branch cache so the hot branch path does not pay for the `files[]` payload. Once cached, an
# owns-match is a local grep with ZERO search-API calls.
# Independent fixture: GH_MERGED_FILES_FIXTURE — "<pr#>\t<path>" rows, pr# as a TAB-prefix key
# so a test can stub the owns-match path without restaging the branch list.
_gh_merged_files_tsv(){
  local slug="$1"
  if [ -n "${GH_MERGED_FILES_FIXTURE:-}" ]; then cat "$GH_MERGED_FILES_FIXTURE" 2>/dev/null; return 0; fi
  if [ -n "${GH_MERGED_FIXTURE:-}" ]; then
    # Branch-only fixture has no files; an owns-match must NOT be allowed to spuriously hit
    # the SEARCH API on its behalf. Caller (done.sh) is responsible for treating GH_MERGED_FIXTURE
    # alone as "files not available, skip owns-match". Return empty so local grep finds nothing.
    return 0
  fi
  local dir="${GH_CACHE_DIR:-$(_ghc_fleet)/state/cache}"; mkdir -p "$dir" 2>/dev/null
  local ttl="${GH_CACHE_TTL:-120}" cf="$dir/merged-files-${slug//\//_}.tsv" now age=999999
  now="$(date +%s 2>/dev/null || echo 0)"
  [ -f "$cf" ] && age=$(( now - $(stat -c %Y "$cf" 2>/dev/null || echo 0) ))
  if [ ! -f "$cf" ] || [ "$age" -gt "$ttl" ]; then
    # jq flattens: each (pr, file) pair becomes "<pr#>\t<path>". `-q/--jq` is gh's jq flag and
    # emits raw strings (there is NO `-r` on `gh pr list` — using it exits non-zero, the cache
    # file is never written, and the owns-match silently returns empty forever).
    if gh pr list --repo "$slug" --state merged --limit 800 \
         --json number,files \
         -q '.[] | . as $pr | .files[]? | "\($pr.number)\t\(.path)"' > "$cf.tmp" 2>/dev/null; then mv "$cf.tmp" "$cf"
    else rm -f "$cf.tmp"; fi
  fi
  cat "$cf" 2>/dev/null
}

# branch_merged_pr <repo-slug> <branch> -> merged PR number or empty. No per-branch API call.
branch_merged_pr(){
  local slug="$1" br="$2"; [ -n "$br" ] || return 0
  _gh_merged_tsv "$slug" | awk -F'\t' -v b="$br" '$1==b{print $2; exit}'
}

# pr_number_is_merged <repo-slug> <pr-number> -> 0 if the PR is in the cached merged set, 1 if not.
# Pure local grep against the cached `<branch>\t<pr#>` TSV — ZERO gh calls.
pr_number_is_merged(){
  local slug="$1" pr="$2"; [ -n "$pr" ] || return 1
  _gh_merged_tsv "$slug" | awk -F'\t' -v p="$pr" '$2==p{found=1; exit} END{exit !found}'
}

# merged_prs_touching_file <repo-slug> <path> -> MERGED PR number that touched <path>, or empty.
# Pure local grep against the cached "<pr#>\t<path>" index — ZERO gh calls, ZERO search calls.
# Empty result + no error = "no cached merged PR touched this path" (caller decides what to do).
# Multi-PR collisions resolve to the FIRST match (the oldest merged PR in the cache), which is
# the right answer for "was the change ever landed" (done.sh:merged_pr_touching_owns only needs
# ANY positive proof, not the most recent).
merged_prs_touching_file(){
  local slug="$1" path="$2"; [ -n "$path" ] || return 0
  _gh_merged_files_tsv "$slug" | awk -F'\t' -v p="$path" '$2==p{print $1; exit}'
}
