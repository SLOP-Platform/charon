#!/usr/bin/env bash
# pr-queue.test.sh — FAIL-ON-REVERT tests for fleet/pr-queue.sh (the REST+ETag queue
# generator that replaced review-pool.sh's GraphQL-burning queue_gen()).
#
# Every test runs against a STUB `gh` installed on PATH, so the suite makes ZERO real API
# calls and is safe to run while the GitHub buckets are exhausted. It also never touches
# the live fleet/state — REVIEW_POOL_STATE points at a fresh temp dir per test.
#
# What each group proves, and what reverting it would cost:
#   (a) transport   — REST only. A revert to `gh pr list` / `gh pr view` is caught directly.
#   (b) author      — column 3 is the LAST COMMIT'S GIT AUTHOR NAME (the droid id), NOT
#                     `user.login`. user.login is the same GitHub account for every droid,
#                     so a "harmless" switch to the free list field silently disables
#                     review-pool.sh's B1 reviewer!=builder guard forever.
#   (c) format      — six columns, jq-@tsv escaping, ISO ts: review-pool.sh's claim_next
#                     and cmd_review parse this file POSITIONALLY.
#   (d) etag/304    — a 304 reuses the cached payload and makes ZERO further calls; a 304
#                     with no cached payload REFUSES rather than emitting an empty queue.
#   (e) ttl + lock  — N tabs regenerate ONCE, not N times.
#   (f) dedup       — the old appender turned 23 PRs into 66 rows under 3 tabs.
#   (g) refusal     — a rate-limit outage exits NON-ZERO and leaves the previous queue
#                     intact. It must NEVER be mistakable for a drained backlog.
#
# Run:  bash fleet/tests/pr-queue.test.sh   (exit 0 = all pass, 1 = a failure)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the real fleet/ dir
PQ="$SRC/pr-queue.sh"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

TAB="$(printf '\t')"

# ─────────────────────────────────────────────────────────────────────────────────────
# Harness: a temp env with a STUB gh on PATH.
#
# The stub is deliberately FAITHFUL on the two behaviours the production code depends on:
#   * it exits 1 on a 304 (real `gh api` does), so the test proves pr-queue.sh drives off
#     the parsed HTTP status and not off gh's exit code;
#   * it emits headers, a blank line, then the body, exactly as `gh api -i` does.
# It logs every invocation so a test can assert on CALL COUNT — the property the whole
# file exists for.
# ─────────────────────────────────────────────────────────────────────────────────────
mk_env(){
  local d; d="$(mktemp -d)"
  mkdir -p "$d/bin" "$d/state" "$d/logs" "$d/fix"
  cat > "$d/bin/gh" <<'STUB'
#!/usr/bin/env bash
# stub gh — serves fixtures from $STUB_FIX, logs every call to $STUB_LOG.
printf '%s\n' "$*" >> "$STUB_LOG"
[ "${1:-}" = "api" ] || { echo "stub gh: only 'api' is supported (got: $*)" >&2; exit 90; }
path="${2:-}"
inm=""
for a in "$@"; do case "$a" in "If-None-Match: "*) inm="${a#If-None-Match: }";; esac; done

if [ "$path" = "rate_limit" ]; then
  printf '{"resources":{"core":{"limit":5000,"remaining":%s,"used":1}}}\n' "${STUB_CORE_REMAINING:-4999}"
  exit 0
fi

# Deliberate hard-failure hook (network fault / 5xx), for the refusal tests.
if [ -n "${STUB_HTTP_FAIL:-}" ]; then
  printf 'HTTP/2.0 %s Server Error\r\n\r\n' "$STUB_HTTP_FAIL"
  exit 1
fi

case "$path" in
  *"/pulls?"*)      name="pulls" ;;
  *"/pulls/"*"/commits"*) n="${path#*/pulls/}"; n="${n%%/commits*}"; name="commits-$n" ;;
  *) echo "stub gh: unmapped path $path" >&2; exit 91 ;;
esac
body="$STUB_FIX/$name.json"
[ -f "$body" ] || { printf 'HTTP/2.0 404 Not Found\r\n\r\n'; exit 1; }
etag="W/\"etag-$name-$(cksum < "$body" | tr -d ' ')\""

[ -n "${STUB_SLOW:-}" ] && sleep 0.4

# Conditional hit -> 304, empty body, EXIT 1 (matches real gh).
if [ -n "$inm" ] && [ "$inm" = "$etag" ]; then
  printf '%s\n' "304 $path" >> "$STUB_LOG.304"
  printf 'HTTP/2.0 304 Not Modified\r\n'
  printf 'Etag: %s\r\n' "${etag#W/}"
  printf '\r\n'
  exit 1
fi
printf 'HTTP/2.0 200 OK\r\n'
printf 'Etag: %s\r\n' "$etag"
printf 'Content-Type: application/json\r\n'
printf '\r\n'
cat "$body"
exit 0
STUB
  chmod +x "$d/bin/gh"
  echo "$d"
}

# run_pq <envdir> [args...] — invoke pr-queue.sh in the temp env. Echoes stderr to $d/err.
run_pq(){
  local d="$1"; shift
  PATH="$d/bin:$PATH" \
  STUB_FIX="$d/fix" STUB_LOG="$d/logs/gh.log" \
  STUB_CORE_REMAINING="${STUB_CORE_REMAINING:-4999}" \
  STUB_HTTP_FAIL="${STUB_HTTP_FAIL:-}" STUB_SLOW="${STUB_SLOW:-}" \
  REVIEW_POOL_STATE="$d/state" \
  REVIEW_LOG_DIR="$d/reviewlog" \
  REVIEW_POOL_REPOS="charon-private" \
  bash "$PQ" "$@" 2>"$d/err"
}
calls(){ wc -l < "$1/logs/gh.log" 2>/dev/null | tr -d ' '; }
calls_matching(){ grep -c -- "$2" "$1/logs/gh.log" 2>/dev/null || echo 0; }

# a two-PR fixture. NOTE user.login is "Nnyan" on BOTH — that is the real production
# shape (every droid pushes through one account) and is what makes (b) load-bearing.
seed_pulls(){
  cat > "$1/fix/pulls.json" <<'JSON'
[
 {"number":346,"title":"fix(review-pool): B1 fail-closed","html_url":"https://github.com/Nnyan/charon-private/pull/346",
  "user":{"login":"Nnyan"},"head":{"sha":"55e9dd171ec93aaf466b04cd482969391323462b"}},
 {"number":345,"title":"fix(shared-namespace-contention): split claim","html_url":"https://github.com/Nnyan/charon-private/pull/345",
  "user":{"login":"Nnyan"},"head":{"sha":"63ece1f4aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}
]
JSON
  cat > "$1/fix/commits-346.json" <<'JSON'
[{"sha":"aaa","commit":{"author":{"name":"frontier-3044776"}}},
 {"sha":"55e9dd171ec93aaf466b04cd482969391323462b","commit":{"author":{"name":"frontier-3044776"}}}]
JSON
  cat > "$1/fix/commits-345.json" <<'JSON'
[{"sha":"63ece1f4aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","commit":{"author":{"name":"saba-sebatyne"}}}]
JSON
}

echo "== (a) transport: REST only, no GraphQL verbs =="
d="$(mk_env)"; seed_pulls "$d"
run_pq "$d" gen --force >/dev/null
Q="$d/state/review-queue.tsv"
[ -s "$Q" ] && ok "a1 queue file written" || bad "a1 queue file written (err: $(cat "$d/err"))"
# `gh pr list` / `gh pr view` are the GraphQL calls that exhausted the 5k bucket. Any
# revert to them shows up here immediately.
if grep -qE '(^| )pr (list|view|diff)( |$)' "$d/logs/gh.log"; then
  bad "a2 no 'gh pr list/view' (GraphQL) calls"
else ok "a2 no 'gh pr list/view' (GraphQL) calls"; fi
if grep -q 'repos/Nnyan/charon-private/pulls?state=open' "$d/logs/gh.log"; then
  ok "a3 used the REST /pulls list endpoint"
else bad "a3 used the REST /pulls list endpoint (log: $(cat "$d/logs/gh.log"))"; fi
rm -rf "$d"

echo "== (b) author semantics: last commit's git author name, NOT user.login =="
d="$(mk_env)"; seed_pulls "$d"
run_pq "$d" gen --force >/dev/null
Q="$d/state/review-queue.tsv"
a346="$(awk -F'\t' '$1==346{print $3}' "$Q")"
a345="$(awk -F'\t' '$1==345{print $3}' "$Q")"
check "b1 PR346 author = droid id from last commit" "$a346" "frontier-3044776"
check "b2 PR345 author = droid id from last commit" "$a345" "saba-sebatyne"
# The crux: if someone "optimises away" the commits call and uses the free user.login
# from the list payload, BOTH rows become "Nnyan", B1 never fires, and self-review is
# silently re-enabled. This assertion is the tripwire.
if [ "$a346" = "Nnyan" ] || [ "$a345" = "Nnyan" ]; then
  bad "b3 author is NOT the GitHub login (B1 would be disabled)"
else ok "b3 author is NOT the GitHub login (B1 stays armed)"; fi
# last commit, not first: commits-346 has two entries with the same name, commits-345 one;
# use a PR whose first and last authors differ to make ordering observable.
cat > "$d/fix/commits-345.json" <<'JSON'
[{"sha":"x","commit":{"author":{"name":"FIRST-commit-author"}}},
 {"sha":"y","commit":{"author":{"name":"LAST-commit-author"}}}]
JSON
rm -rf "$d/state/pr-queue-cache/author"          # force a re-lookup
run_pq "$d" gen --force >/dev/null
check "b4 takes the LAST commit's author, not the first" \
      "$(awk -F'\t' '$1==345{print $3}' "$d/state/review-queue.tsv")" "LAST-commit-author"
rm -rf "$d"

echo "== (c) output-format parity with review-pool.sh queue_gen =="
d="$(mk_env)"; seed_pulls "$d"
# A title containing a TAB and a NEWLINE: jq's @tsv escaped these, and review-pool.sh's
# awk readers parse positionally, so a raw tab would shift the author column.
python3 - "$d/fix/pulls.json" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p))
d[0]["title"]="tab\there and\nnewline"
json.dump(d,open(p,"w"))
PY
run_pq "$d" gen --force >/dev/null
Q="$d/state/review-queue.tsv"
check "c1 one row per open PR" "$(wc -l < "$Q" | tr -d ' ')" "2"
check "c2 exactly 6 tab-separated columns" \
      "$(awk -F'\t' '{print NF}' "$Q" | sort -u | tr '\n' ' ' | tr -d ' ')" "6"
check "c3 col2 is the repo KEY (not the owner/repo slug)" \
      "$(awk -F'\t' 'NR==1{print $2}' "$Q")" "charon-private"
check "c4 col5 is the PR html url" \
      "$(awk -F'\t' '$1==346{print $5}' "$Q")" "https://github.com/Nnyan/charon-private/pull/346"
if awk -F'\t' 'NR==1{print $6}' "$Q" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'; then
  ok "c5 col6 is an ISO8601 UTC timestamp"
else bad "c5 col6 is an ISO8601 UTC timestamp (got '$(awk -F'\t' 'NR==1{print $6}' "$Q")')"; fi
check "c6 embedded tab/newline escaped @tsv-style (row stays one line)" \
      "$(awk -F'\t' '$1==346{print $4}' "$Q")" 'tab\there and\nnewline'
# skip rules: an existing review-log removes the PR from the queue (same as queue_gen)
mkdir -p "$d/reviewlog"; : > "$d/reviewlog/346@charon-private.md"
run_pq "$d" gen --force >/dev/null
check "c7 PR with an existing review-log is skipped" "$(wc -l < "$Q" | tr -d ' ')" "1"
mkdir -p "$d/state/review-done"; : > "$d/state/review-done/345@charon-private"
run_pq "$d" gen --force >/dev/null
check "c8 PR with a recorded verdict is skipped" "$(wc -l < "$Q" | tr -d ' ')" "0"
rm -rf "$d"

echo "== (c') repo-key mapping has not drifted from review-pool.sh =="
# repo_slug() is REPLICATED, not sourced (review-pool.sh cannot be sourced: its top-level
# dispatch would start a review loop). This diffs the two case tables so the duplication
# can never silently diverge — a wrong slug would queue PRs from the wrong repo.
slugs(){ sed -n '/^repo_slug(){/,/^}/p' "$1" | grep -oE '[a-z-]+\)[[:space:]]*echo "[^"]*"' | tr -s ' '; }
if [ "$(slugs "$PQ")" = "$(slugs "$SRC/review-pool.sh")" ] && [ -n "$(slugs "$PQ")" ]; then
  ok "c9 repo_slug() table matches review-pool.sh exactly"
else
  bad "c9 repo_slug() table drifted from review-pool.sh"
  diff <(slugs "$PQ") <(slugs "$SRC/review-pool.sh") || true
fi

echo "== (d) ETag: 304 reuses the cached payload with ZERO further calls =="
d="$(mk_env)"; seed_pulls "$d"
run_pq "$d" gen --force >/dev/null
first="$(calls "$d")"
cp "$d/state/review-queue.tsv" "$d/q1"
rc=0; run_pq "$d" gen --force >/dev/null || rc=$?
[ -s "$d/logs/gh.log.304" ] && ok "d1 second sweep got a 304 (conditional request sent)" \
  || bad "d1 second sweep got a 304 (no If-None-Match / etag not stored)"
# Exit code FIRST: real `gh api` exits 1 on a 304, so a sweep that trusts gh's rc instead
# of the parsed HTTP status turns the free path into a hard failure. Without this, the
# "identical queue" check below passes vacuously (a refusal leaves the queue untouched).
check "d2 304 sweep SUCCEEDS (gh's rc=1 on 304 must not be trusted)" "$rc" "0"
check "d2b 304 sweep reproduces the identical queue" "$(cmp -s "$d/q1" "$d/state/review-queue.tsv" && echo same)" "same"
# The author lookups are keyed by head SHA, so an unchanged PR costs ZERO commits calls.
check "d3 unchanged PRs cost ZERO /commits calls on the 2nd sweep" \
      "$(calls_matching "$d" '/commits')" "2"
[ "$(calls "$d")" -lt $(( first * 2 )) ] && ok "d4 2nd sweep is cheaper than the 1st (revalidate, not refetch)" \
  || bad "d4 2nd sweep cost as much as the 1st ($(calls "$d") vs $first)"
# THE empty-queue-lie guard: a 304 whose cached body vanished must REFUSE, never emit [].
rm -f "$d/state/pr-queue-cache/pulls-Nnyan_charon-private.json"
rc=0; run_pq "$d" gen --force >/dev/null || rc=$?
[ "$rc" -ne 0 ] && ok "d5 304 with a missing cached body REFUSES (rc=$rc)" || bad "d5 304 with a missing cached body REFUSES"
check "d6 ...and leaves the previous queue intact" "$(cmp -s "$d/q1" "$d/state/review-queue.tsv" && echo same)" "same"
rm -rf "$d"

echo "== (e) TTL skip and regeneration lock =="
d="$(mk_env)"; seed_pulls "$d"
run_pq "$d" gen --force >/dev/null
n="$(calls "$d")"
run_pq "$d" gen >/dev/null                       # no --force, queue is seconds old
check "e1 TTL-fresh queue: ZERO extra gh calls" "$(calls "$d")" "$n"
grep -q 'fresh' "$d/err" && ok "e2 TTL skip is reported" || bad "e2 TTL skip is reported"
rc=0; PR_QUEUE_TTL_S=0 run_pq "$d" gen >/dev/null || rc=$?
[ "$(calls "$d")" -gt "$n" ] && ok "e3 TTL=0 forces a refresh" || bad "e3 TTL=0 forces a refresh"

# Concurrency: 5 tabs fire at once against a SLOW gh. Exactly ONE may run the sweep; the
# rest must block on the lock and then find the queue fresh. Without the lock (or without
# the double-checked TTL after acquiring it) all 5 sweep, which is the 7x amplification
# that drained the bucket.
d2="$(mk_env)"; seed_pulls "$d2"
for i in 1 2 3 4 5; do STUB_SLOW=1 run_pq "$d2" gen >/dev/null & done
wait
sweeps="$(calls_matching "$d2" 'pulls?state=open')"
check "e4 5 concurrent tabs produce exactly ONE list sweep" "$sweeps" "1"
check "e5 ...and exactly one queue file, not five appended copies" "$(wc -l < "$d2/state/review-queue.tsv" | tr -d ' ')" "2"
rm -rf "$d" "$d2"

echo "== (f) dedup on (num, repo) =="
d="$(mk_env)"; seed_pulls "$d"
# duplicate rows in the upstream payload (and the old code APPENDED across tabs)
python3 - "$d/fix/pulls.json" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p)); json.dump(d+d+d,open(p,"w"))
PY
run_pq "$d" gen --force >/dev/null
check "f1 3x-duplicated payload yields one row per (num,repo)" \
      "$(wc -l < "$d/state/review-queue.tsv" | tr -d ' ')" "2"
run_pq "$d" gen --force >/dev/null
check "f2 repeated regeneration OVERWRITES, never appends" \
      "$(wc -l < "$d/state/review-queue.tsv" | tr -d ' ')" "2"
check "f3 keys are unique" \
      "$(awk -F'\t' '{print $1"@"$2}' "$d/state/review-queue.tsv" | sort -u | wc -l | tr -d ' ')" "2"
rm -rf "$d"

echo "== (g) refusals are LOUD, non-zero, and never look like a drained backlog =="
d="$(mk_env)"; seed_pulls "$d"
run_pq "$d" gen --force >/dev/null                 # seed a good queue first
cp "$d/state/review-queue.tsv" "$d/good"
rc=0; STUB_CORE_REMAINING=5 run_pq "$d" gen --force >"$d/out" || rc=$?
check "g1 low REST budget exits 3 (not 0)" "$rc" "3"
grep -q 'REFUSED' "$d/err" && ok "g2 refusal is loud on stderr" || bad "g2 refusal is loud on stderr"
grep -qi 'EXHAUSTED' "$d/err" && ok "g3 stderr names the outage explicitly" || bad "g3 stderr names the outage explicitly"
# THE failure class: the queue must be left ALONE, not truncated to zero rows.
check "g4 the previous queue is UNCHANGED (not emptied)" "$(cmp -s "$d/good" "$d/state/review-queue.tsv" && echo same)" "same"
check "g5 refusal did not emit an empty queue to stdout" "$(wc -c < "$d/out" | tr -d ' ')" "0"
check "g6 queue still has its rows after the refusal" "$(wc -l < "$d/state/review-queue.tsv" | tr -d ' ')" "2"
# a 5xx / transport fault must refuse the same way
rc=0; STUB_HTTP_FAIL=500 run_pq "$d" gen --force >/dev/null || rc=$?
check "g7 an API fetch failure exits 4 (not 0)" "$rc" "4"
check "g8 ...and still leaves the queue intact" "$(cmp -s "$d/good" "$d/state/review-queue.tsv" && echo same)" "same"
# an UNREADABLE budget is treated as exhausted, never as "plenty of room"
rc=0; STUB_CORE_REMAINING='"nonsense"' run_pq "$d" gen --force >/dev/null || rc=$?
check "g9 unparseable rate_limit refuses (rc=3)" "$rc" "3"
rm -rf "$d"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL PR-QUEUE TESTS PASS"
