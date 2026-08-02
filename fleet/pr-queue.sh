#!/usr/bin/env bash
# fleet/pr-queue.sh — generate the reviewer-pool queue over the REST API with ETag
# revalidation, a TTL, a regeneration lock and dedup-on-write.
#
# ─────────────────────────────────────────────────────────────────────────────────────
# WHY THIS FILE EXISTS (measured 2026-08-01, not theory)
# ─────────────────────────────────────────────────────────────────────────────────────
# review-pool.sh's queue_gen() burns GraphQL quota proportional to (open PRs x tabs):
#   - 1x `gh pr list`  per repo    (2 repos)          -> GraphQL
#   - 1x `gh pr view <n> --json commits` per open PR  -> GraphQL   (~16 PRs)
#   = ~18 GraphQL calls per cycle PER TAB. At a 45s poll x 7 reviewer tabs that is
#   >10,000 calls/hr against a 5,000/hr GraphQL bucket. It exhausted the bucket in
#   under an hour and every reviewer tab then saw an EMPTY queue — which is
#   indistinguishable, from the tab's point of view, from "the backlog is drained".
#
# Three measured facts drive the design; do not re-derive them:
#   1. REST core is a SEPARATE 5,000/hr bucket. While GraphQL sat at 0/5000, core was
#      untouched at 5000/5000, and `gh api repos/{o}/{r}/pulls?state=open&per_page=100`
#      returned all 16 open PRs.
#   2. Conditional requests are FREE. Sending `If-None-Match` and receiving `304 Not
#      Modified` did NOT increment `x-ratelimit-used` across repeated requests. So the
#      steady state of this generator costs ZERO quota, not "a bit less quota".
#   3. `gh api` exits NON-ZERO (rc=1) on a 304. A naive `|| return` therefore treats the
#      cheapest, most common, most desirable outcome as a failure. Status is parsed from
#      the response line, and rc is deliberately ignored in favour of it.
#
# THE FAILURE CLASS THIS FILE REFUSES TO REPRODUCE
#   A rate-limit outage must NEVER look like a drained backlog. That exact confusion bit
#   this rig twice on 2026-08-01. Every failure path here is LOUD + non-zero and leaves
#   the previous queue file byte-for-byte intact; there is no path that writes an empty
#   or partial queue. The queue is built in a temp file and moved into place only after
#   every repo fetched successfully.
#
# ─────────────────────────────────────────────────────────────────────────────────────
# RELATIONSHIP TO review-pool.sh  (NOT edited — owned by ticket REVIEWER-TAB-POOL/PR #346)
# ─────────────────────────────────────────────────────────────────────────────────────
# This is a drop-in replacement for `review-pool.sh queue`: same output file, same six
# TSV columns, same skip rules. review-pool.sh's claim/review halves are untouched and
# keep working against the file this writes.
#
# repo_slug()/repo_path() are REPLICATED here, not sourced. review-pool.sh cannot be
# sourced cleanly: it runs `set -euo pipefail`, mkdir -p, and a top-level dispatch that
# calls main_loop() on any unknown argv — sourcing it would start a review loop. The
# duplication is guarded by a drift test (fleet/tests/pr-queue.test.sh, case "parity")
# which diffs the two case-arm tables and FAILS if they ever disagree.
#
# WHY NOT fleet/gh-cache.sh: that module batches MERGED-PR / hold-label lookups on an
# mtime TTL via `gh pr list` (GraphQL). Different endpoint, different bucket, no
# revalidation. Extending it would have meant bolting a REST+ETag transport onto a
# GraphQL cache; this stays a separate transport with its own cache dir.
#
# WHY NOT `gh api --cache <ttl>`: gh's built-in cache serves a STALE body for the whole
# TTL. ETag revalidation returns FRESH data for zero quota, which is strictly better —
# a PR opened 5s ago is visible immediately instead of up to TTL late.
#
# ─────────────────────────────────────────────────────────────────────────────────────
# AUTHOR SEMANTICS  (read before "simplifying" this — B1 depends on it)
# ─────────────────────────────────────────────────────────────────────────────────────
# Column 3 (author_droid) feeds review-pool.sh's B1 guard (reviewer != builder), which
# fails CLOSED on an unknown author. Its meaning is PRESERVED EXACTLY:
#
#     old: gh pr view <n> --json commits --jq '.commits[-1].authors[0].name'
#     new: gh api repos/<slug>/pulls/<n>/commits?per_page=100  ->  .[-1].commit.author.name
#
# Both are the GIT AUTHOR NAME of the PR's LAST commit, i.e. the droid id
# (e.g. "frontier-3044776"). Verified on the live PR #346: both paths yield
# "frontier-3044776", which is also the Author recorded in docs/review-log/346@charon-private.md.
#
# `user.login` from the /pulls LIST payload is deliberately NOT used even though it is
# free. Every droid pushes through ONE GitHub account, so user.login is "Nnyan" on all
# 16 open PRs. Using it would make author_droid a constant that matches no droid id, so
# the B1 reviewer==builder check would never fire again — a silent correctness hole, not
# a refactor. Measured, not assumed.
#
# The per-PR commits call is kept off the hot path by caching the author under the PR's
# HEAD SHA (from the free list payload). An unchanged PR costs ZERO calls; a PR only
# pays one REST call the first time a new head commit appears. Combined with the 304 on
# the list itself, a steady-state cycle across 7 tabs costs 0 quota.
#
# Pagination: /pulls/{n}/commits is paginated (30 default). `.[-1]` of page 1 would be
# the 30th commit, NOT the last — the wrong droid id. per_page=100 plus a `Link:
# rel="last"` follow makes `.[-1]` genuinely last. Whitespace is stripped from the
# result to match PR #346's fix (a trailing newline would defeat the string compare).
#
# ─────────────────────────────────────────────────────────────────────────────────────
# Usage:
#   pr-queue.sh [gen] [--force]   regenerate the queue (TTL-skipped unless --force)
#   pr-queue.sh items             print the current queue (no API calls)
#   pr-queue.sh status            queue/cache/rate-limit summary
#
# Env:
#   REVIEW_POOL_REPOS      comma-separated repo keys      (default: charon,charon-private)
#   REVIEW_POOL_STATE      state root                     (default: <fleet>/state)
#   REVIEW_LOG_DIR         review-log dir (skip rule)     (default: <fleet>/../docs/review-log)
#   PR_QUEUE_TTL_S         skip regen if queue newer than (default: 120)
#   PR_QUEUE_MIN_CORE      refuse below this REST budget  (default: 100)
#   PR_QUEUE_LOCK_WAIT_S   flock wait                     (default: 60)
#   PR_QUEUE_CACHE_DIR     etag/payload cache             (default: <state>/pr-queue-cache)
#
# Exit codes (a caller MUST be able to tell these apart from "no work"):
#   0  queue regenerated, or TTL-fresh and left alone
#   2  usage error
#   3  REFUSED: REST budget too low / unverifiable  (NOT "empty backlog")
#   4  REFUSED: an API fetch or transform failed    (NOT "empty backlog")
#   5  REFUSED: missing prerequisite binary
set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# A reviewer tab started from a non-login shell loses ~/.local/bin, and with it `gh`.
# APPEND, never prepend (fleet-droid.sh:29-32): an already-resolvable binary — a test
# stub on PATH, a deliberate operator override — must keep winning. This only adds a
# fallback location. Prepending here would silently defeat the test PATH shim.
case ":${PATH}:" in
  *":$HOME/.local/bin:"*) : ;;
  *) [ -d "$HOME/.local/bin" ] && export PATH="$PATH:$HOME/.local/bin" ;;
esac

STATE="${REVIEW_POOL_STATE:-$FLEET/state}"
QUEUE_TSV="${PR_QUEUE_TSV:-$STATE/review-queue.tsv}"
CACHE_DIR="${PR_QUEUE_CACHE_DIR:-$STATE/pr-queue-cache}"
AUTHOR_DIR="$CACHE_DIR/author"
# A DEDICATED lock file, not $STATE/lock. The flock PATTERN is the rig's (claim.sh:
# `exec 9>"$LOCK"; flock 9`; board-lock.sh's fail-closed `flock -w`), but the lock FILE
# must not be shared: $STATE/lock is the claim/board/work-lease lock and is taken for
# microseconds. Regeneration holds its lock across NETWORK calls, so sharing would stall
# every droid's claim behind GitHub latency.
LOCK="${PR_QUEUE_LOCK:-$STATE/pr-queue.lock}"
DONE_DIR="$STATE/review-done"
REVIEW_LOG_DIR="${REVIEW_LOG_DIR:-$(cd "$FLEET/../docs/review-log" 2>/dev/null && pwd || echo "$FLEET/../docs/review-log")}"
REVIEW_POOL_REPOS="${REVIEW_POOL_REPOS:-charon,charon-private}"
TTL_S="${PR_QUEUE_TTL_S:-120}"
MIN_CORE="${PR_QUEUE_MIN_CORE:-100}"
LOCK_WAIT_S="${PR_QUEUE_LOCK_WAIT_S:-60}"

mkdir -p "$STATE" "$CACHE_DIR" "$AUTHOR_DIR" "$DONE_DIR"
: >>"$LOCK"

usage(){ sed -n '/^# Usage:/,/^set -euo pipefail$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2; }

# ---- loud refusal -------------------------------------------------------------------
# Every refusal goes through here. The banner exists so a refusal cannot be skimmed past
# in a tab's scrollback and mistaken for a quiet "nothing to review" cycle.
die_loud(){
  local code="$1"; shift
  {
    echo "########################################################################"
    echo "## pr-queue: REFUSED (exit $code) — THE QUEUE WAS NOT REGENERATED"
    while [ "$#" -gt 0 ]; do echo "## $1"; shift; done
    echo "## The existing queue file (if any) is UNCHANGED. This is NOT an empty backlog."
    echo "########################################################################"
  } >&2
  exit "$code"
}

# ---- repo helpers (REPLICATED from review-pool.sh — see header; parity-tested) -------
repo_slug(){
  case "${1:-}" in
    charon)        echo "SLOP-Platform/charon" ;;
    charon-private) echo "Nnyan/charon-private" ;;
    *)             echo "" ;;  # unknown; caller handles
  esac
}

# (review-pool.sh's repo_path() is deliberately NOT replicated: this generator never
# touches a local checkout, and an unused copy would be one more thing to drift.)

# ---- prerequisites ------------------------------------------------------------------
# python3 (not jq) does the JSON->TSV transform. python3 is already a HARD fleet prereq
# (fleet-droid.sh preflights it); jq is not preflighted anywhere, so depending on it
# would add a new way for a fresh box to fail. `gh --jq` is unusable here because the
# 304 path has no body to pipe through gh at all — the reuse comes from a local file.
require_bins(){
  local missing=()
  local b; for b in gh python3 flock; do
    command -v "$b" >/dev/null 2>&1 || missing+=("$b")
  done
  [ "${#missing[@]}" -eq 0 ] || die_loud 5 "missing required binaries: ${missing[*]}"
}

# ---- conditional (ETag) REST fetch ---------------------------------------------------
# gh_conditional <cache-key> <api-path>
#   Prints the path of a file holding the JSON body. Uses If-None-Match; on 304 it
#   reuses the cached body and makes ZERO further calls.
#
# Contract notes that are easy to get wrong:
#   * `gh api` exits 1 on 304. rc is therefore NOT the success signal — the parsed HTTP
#     status is. Treating rc as authoritative turns the free path into a hard failure.
#   * The etag is refreshed only on a 200. GitHub echoes a STRONG etag on the 304 while
#     the 200 carried the WEAK (`W/"..."`) form; both revalidate, but re-storing on 304
#     would churn the cache for no gain and risks a form we never proved round-trips.
#   * A 304 with NO cached body is a cache/disk inconsistency, not a success — it is a
#     hard failure, because silently returning "[]" here is precisely the empty-queue lie.
#   * The `Link: rel="last"` target is written to <key>.link, NOT to a shell variable:
#     callers invoke this inside `$( )`, and an exported variable dies with the subshell.
gh_conditional(){
  local key="$1" path="$2"
  local body="$CACHE_DIR/$key.json" etagf="$CACHE_DIR/$key.etag" linkf="$CACHE_DIR/$key.link"
  local raw; raw="$(mktemp)"
  local -a hdr=()
  if [ -s "$etagf" ]; then hdr=(-H "If-None-Match: $(cat "$etagf")"); fi

  # rc intentionally discarded (see above); status drives everything.
  gh api "$path" ${hdr[@]+"${hdr[@]}"} -i >"$raw" 2>/dev/null || true

  local status; status="$(head -1 "$raw" | tr -d '\r' | awk '{print $2}')" || true
  case "$status" in
    304)
      rm -f "$raw"
      # 304 means the payload we already hold is still current: reuse it, ZERO further calls.
      [ -s "$body" ] || { echo "pr-queue: 304 for $path but cached body '$body' is missing/empty" >&2; return 1; }
      printf '%s\n' "$body"; return 0 ;;
    200) ;;
    *)
      echo "pr-queue: unexpected HTTP status '${status:-<none>}' for $path" >&2
      head -1 "$raw" >&2 || true
      rm -f "$raw"; return 1 ;;
  esac

  # Split at the FIRST blank (CR-stripped) line: everything before it is headers.
  local hdrs; hdrs="$(mktemp)"
  awk 'BEGIN{h=1} {line=$0; sub(/\r$/,"",line); if(h && line==""){h=0; next} if(h) print line > HDR; else print line > BODY}' \
     HDR="$hdrs" BODY="$body.tmp" "$raw"
  rm -f "$raw"
  [ -f "$body.tmp" ] || : > "$body.tmp"

  local et; et="$(awk 'tolower($1)=="etag:"{sub(/^[^:]*:[ \t]*/,""); print; exit}' "$hdrs" | tr -d '\r')" || true
  local last; last="$(awk 'tolower($1)=="link:"{sub(/^[^:]*:[ \t]*/,""); print; exit}' "$hdrs" | tr -d '\r' \
                   | tr ',' '\n' | awk '/rel="last"/{ if (match($0,/<[^>]*>/)) print substr($0,RSTART+1,RLENGTH-2); exit }')" || true
  rm -f "$hdrs"

  mv "$body.tmp" "$body"
  # Only refresh the etag on a 200 — see the note above on weak vs strong forms.
  [ -z "$et" ] || printf '%s' "$et" > "$etagf"
  printf '%s' "$last" > "$linkf"
  printf '%s\n' "$body"
}

# ---- JSON -> TSV --------------------------------------------------------------------
# rows_from_pulls <body.json>  ->  "<num>\t<title>\t<html_url>\t<head_sha>" per open PR.
#
# Field escaping reproduces jq's @tsv EXACTLY (backslash, tab, newline, CR), because the
# old generator piped through `| @tsv` and review-pool.sh's awk readers parse the result
# positionally. A raw tab or newline in a PR title would otherwise shift every later
# column — and column 3 is the B1 author field.
rows_from_pulls(){
  python3 - "$1" <<'PY'
import json, sys
def tsv(s):
    s = "" if s is None else str(s)
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
try:
    data = json.load(open(sys.argv[1]))
except Exception as e:                                  # noqa: BLE001 - any parse fault is fatal
    print("pr-queue: cannot parse pulls payload: %s" % e, file=sys.stderr)
    sys.exit(1)
if not isinstance(data, list):
    print("pr-queue: pulls payload is not a list", file=sys.stderr)
    sys.exit(1)
for pr in data:
    print("\t".join([
        tsv(pr.get("number")),
        tsv(pr.get("title")),
        tsv(pr.get("html_url")),
        tsv((pr.get("head") or {}).get("sha")),
    ]))
PY
}

# last_commit_author <commits.json> -> git author NAME of the LAST commit (see header).
last_commit_author(){
  python3 - "$1" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
if not isinstance(data, list) or not data:
    sys.exit(1)
name = (((data[-1] or {}).get("commit") or {}).get("author") or {}).get("name") or ""
print(name)
PY
}

# ---- author lookup (head-SHA cached) -------------------------------------------------
# pr_author <repo_key> <slug> <num> <head_sha>
# Prints the droid id, or empty on failure. EMPTY IS SAFE: review-pool.sh's B1 guard
# fails CLOSED on an unknown author (PR #346), so an unverifiable author blocks the
# claim rather than allowing a self-review. Never invent a value here.
pr_author(){
  local repo_key="$1" slug="$2" num="$3" sha="$4"
  local cf="$AUTHOR_DIR/${repo_key}-${num}-${sha}"
  if [ -s "$cf" ]; then cat "$cf"; return 0; fi

  local key="commits-${slug//\//_}-${num}" body
  body="$(gh_conditional "$key" "repos/$slug/pulls/$num/commits?per_page=100")" || return 0
  # >100 commits: page 1's last row is commit #100, not the last one — the WRONG droid id.
  # Follow the Link rel="last" target (written to <key>.link by gh_conditional).
  local linkf="$CACHE_DIR/$key.link" lastpath=""
  [ -s "$linkf" ] && lastpath="$(cat "$linkf")"
  if [ -n "$lastpath" ]; then
    body="$(gh_conditional "${key}-last" "${lastpath#*://api.github.com/}")" || return 0
  fi

  local name; name="$(last_commit_author "$body" 2>/dev/null || true)"
  # Match PR #346's fix: jq/JSON output can carry a stray newline, and 'droid\n' != 'droid'
  # silently re-opens the reviewer==builder hole the B1 guard exists to close.
  name="$(printf '%s' "$name" | tr -d '[:space:]')"
  [ -z "$name" ] || printf '%s' "$name" > "$cf"
  printf '%s' "$name"
}

# ---- rate-limit preflight ------------------------------------------------------------
# /rate_limit does not itself consume quota. An UNREADABLE budget refuses just as loudly
# as a low one: "I could not check" and "I have room" must never collapse into the same
# branch, or the outage reappears disguised as an empty queue.
check_rate(){
  local out rem
  out="$(gh api rate_limit 2>/dev/null)" || die_loud 3 \
    "could not read GitHub rate_limit (network/auth failure)." \
    "Refusing to regenerate: an unverifiable budget is treated as exhausted."
  rem="$(printf '%s' "$out" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d["resources"]["core"]["remaining"])
except Exception:
    print("")' 2>/dev/null)"
  case "$rem" in
    ''|*[!0-9]*) die_loud 3 "rate_limit payload had no numeric resources.core.remaining." ;;
  esac
  if [ "$rem" -lt "$MIN_CORE" ]; then
    die_loud 3 \
      "GitHub REST core budget is EXHAUSTED: remaining=$rem (floor=$MIN_CORE)." \
      "Reviewer tabs must treat this as an OUTAGE, not as 'no PRs to review'." \
      "Wait for the hourly reset, or raise PR_QUEUE_MIN_CORE deliberately."
  fi
  echo "$rem"
}

# ---- queue generation ----------------------------------------------------------------
queue_fresh(){
  # true if the queue file exists and is younger than the TTL.
  [ -f "$QUEUE_TSV" ] || return 1
  local now mt; now="$(date +%s)"; mt="$(stat -c %Y "$QUEUE_TSV" 2>/dev/null || echo 0)"
  [ "$(( now - mt ))" -lt "$TTL_S" ]
}

gen(){
  local force="${1:-false}"

  # First TTL check is UNLOCKED and is the whole point of the lock design: N tabs polling
  # a fresh queue never even contend for the lock.
  if [ "$force" != "true" ] && queue_fresh; then
    echo "pr-queue: queue is fresh (< ${TTL_S}s) — skipping regeneration" >&2
    return 0
  fi

  require_bins

  exec 9>"$LOCK"
  # FAIL-CLOSED like board-lock.sh: a lock we cannot take is a refusal, never a
  # free-for-all. N tabs racing a regeneration would otherwise each burn a full sweep.
  flock -w "$LOCK_WAIT_S" 9 || die_loud 4 \
    "could not take the regeneration lock ($LOCK) within ${LOCK_WAIT_S}s."

  # DOUBLE-CHECKED TTL: the tab that waited on the lock is now looking at the queue the
  # lock HOLDER just wrote. This is what makes N tabs regenerate ONCE, not N times.
  if [ "$force" != "true" ] && queue_fresh; then
    echo "pr-queue: another tab regenerated the queue while we waited — skipping" >&2
    return 0
  fi

  check_rate >/dev/null

  local ts; ts="$(date -u +%FT%TZ)"
  local tmp; tmp="$(mktemp)"
  # Build into a temp file and move it into place only on FULL success. A partial sweep
  # must never become the live queue — a half-queue reads as "the rest was reviewed".
  local ok=true
  local r
  IFS=',' read -ra REPOS <<< "$REVIEW_POOL_REPOS"
  for r in "${REPOS[@]}"; do
    r="$(printf '%s' "$r" | tr -d ' ')"
    [ -z "$r" ] && continue
    local slug; slug="$(repo_slug "$r")"
    [ -z "$slug" ] && { echo "pr-queue: WARN unknown repo key '$r' — skipping" >&2; continue; }

    local body
    # sort/direction pinned so row ORDER is deterministic and matches the previous
    # generator's newest-first listing (claim_next takes the FIRST claimable row).
    if ! body="$(gh_conditional "pulls-${slug//\//_}" "repos/$slug/pulls?state=open&per_page=100&sort=created&direction=desc")"; then
      echo "pr-queue: ERROR could not fetch open PRs for $slug" >&2
      ok=false; break
    fi

    local rows
    if ! rows="$(rows_from_pulls "$body")"; then
      echo "pr-queue: ERROR could not parse open-PR payload for $slug" >&2
      ok=false; break
    fi

    # Field split uses `mapfile + awk`, NOT `IFS=$'\t' read`. Bash's IFS read COLLAPSES
    # consecutive tabs, so one empty column silently shifts every later field left — the
    # exact bug PR #346 had to fix in review-pool.sh's claim_next, where it slid the PR
    # title into the B1 author slot. awk preserves field POSITION including empties.
    local line num title url sha
    local -a f=()
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      mapfile -t f < <(printf '%s' "$line" | awk -F'\t' '{for (i=1; i<=NF; i++) print $i}')
      num="${f[0]:-}"; title="${f[1]:-}"; url="${f[2]:-}"; sha="${f[3]:-}"
      [ -z "$num" ] && continue
      local key="${num}@${r}"
      # Same two skip rules as review-pool.sh queue_gen: a recorded verdict, or an
      # existing review-log file, means this PR is already reviewed.
      [ -f "$DONE_DIR/$key" ] && continue
      [ -f "$REVIEW_LOG_DIR/${key}.md" ] && continue
      local author; author="$(pr_author "$r" "$slug" "$num" "$sha")"
      printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$num" "$r" "$author" "$title" "$url" "$ts" >> "$tmp"
    done <<< "$rows"
  done

  if [ "$ok" != "true" ]; then
    rm -f "$tmp"
    die_loud 4 "at least one repo could not be fetched or parsed." \
                "Writing a partial queue would look like a drained backlog."
  fi

  # DEDUP on (num, repo). The previous generator APPENDED (`done >> "$QUEUE_TSV"`), and
  # with several tabs regenerating concurrently the same PR landed many times — measured
  # 23 real entries becoming 66 rows under 3 tabs. First row wins, order preserved.
  awk -F'\t' '!seen[$1 FS $2]++' "$tmp" > "$tmp.dedup"
  mv "$tmp.dedup" "$QUEUE_TSV"
  rm -f "$tmp"

  # Bound the author cache: entries are keyed by head SHA, so every force-push leaves a
  # dead file behind forever. Cheap sweep, no cron, no separate reaper script.
  find "$AUTHOR_DIR" -type f -mtime +7 -delete 2>/dev/null || true

  echo "pr-queue: wrote $(wc -l < "$QUEUE_TSV") queue rows to $QUEUE_TSV" >&2
}

# ---- read-only subcommands ------------------------------------------------------------
cmd_items(){ [ -f "$QUEUE_TSV" ] || return 0; cat "$QUEUE_TSV"; }

cmd_status(){
  echo "=== PR Queue (REST + ETag) ==="
  echo "Queue file:  $QUEUE_TSV"
  if [ -f "$QUEUE_TSV" ]; then
    echo "Rows:        $(wc -l < "$QUEUE_TSV")"
    echo "Age:         $(( $(date +%s) - $(stat -c %Y "$QUEUE_TSV" 2>/dev/null || echo 0) ))s (TTL ${TTL_S}s)"
  else
    echo "Rows:        0 (never generated)"
  fi
  echo "Cache dir:   $CACHE_DIR"
  echo "Etags:       $(find "$CACHE_DIR" -maxdepth 1 -name '*.etag' 2>/dev/null | wc -l)"
  echo "Authors:     $(find "$AUTHOR_DIR" -type f 2>/dev/null | wc -l) cached"
  echo "Repos:       $REVIEW_POOL_REPOS"
  if command -v gh >/dev/null 2>&1; then
    echo "REST core:   $(gh api rate_limit --jq '.resources.core.remaining' 2>/dev/null || echo '?') remaining (floor $MIN_CORE)"
  fi
}

# ---- dispatch --------------------------------------------------------------------------
CMD="${1:-gen}"; shift 2>/dev/null || true
case "$CMD" in
  gen)   case "${1:-}" in --force) gen true ;; ''|*) gen false ;; esac ;;
  --force) gen true ;;
  items) cmd_items ;;
  status) cmd_status ;;
  --help|-h) usage ;;
  *)     echo "pr-queue: unknown command '$CMD'" >&2; usage ;;
esac
