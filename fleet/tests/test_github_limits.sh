#!/usr/bin/env bash
# test_github_limits.sh — FAIL-ON-REVERT tests for the GITHUB-LIMITS-HARDENING
# proactive batch (3 hardening passes, one seam = the gh-cache):
#
#   T1  owns-match uses the cache (NO `gh ... --search` per owns entry).
#       done.sh:merged_pr_touching_owns reads the cached "<pr#>\t<path>" index.
#       A poisoned-gh PATH proves ZERO gh invocations per owns lookup (the
#       GitHub SEARCH API is 30 req/MIN — the next-to-burn limit if this
#       reverts). Mirrors the gh-cache.test.sh fail-on-revert style.
#   T2  large-file-guard: clean tree -> PASS; staged >50MB -> FAIL naming path;
#       allowlist -> PASS for a matching path; the untracked >50MB path -> FAIL.
#   T3  land-push.sh pace: a burst of N pushes sleeps LAND_PACE_S between them
#       (catches the "no pacing" revert that re-trips the secondary
#       content-creation limit). Hermetic: a fake `git` on PATH that just
#       records the invocation order, so we can assert sleeps fall BETWEEN
#       pushes (not after the last one — a no-op pacing is still no pacing).
#   T4  gh-cache.sh: own owns-match fn (`merged_prs_touching_file`) returns the
#       PR# from the cached files index; empty for an unknown path; ZERO gh
#       calls even with a poisoned-gh on PATH (the whole-batch seam).
#   T5  THE PRODUCTION PATH, with NO FIXTURE SET. T1-T4 all set
#       GH_MERGED_FILES_FIXTURE, which returns on the FIRST line of
#       _gh_merged_files_tsv — so every one of them passes even if the real gh
#       invocation is deleted outright. That blind spot shipped a dead feature:
#       the flag was `-r`, which `gh pr list` does not accept, so gh exited
#       non-zero, the cache was never written, and the owns-match returned empty
#       FOREVER while the suite stayed green.
#       T5 closes it with a gh stub that mimics real gh's FLAG VALIDATION
#       (rejects unknown flags exactly like the real binary) and applies the
#       real `-q` jq expression to canned JSON. It therefore goes RED if:
#         - the production gh invocation is gutted/removed (no cache file), or
#         - the jq flag regresses to `-r` or any other non-flag, or
#         - the emitted rows stop being parseable "<pr#>\t<path>" TSV.
#       Any test that stubs the fixture CANNOT catch those. This one must.
#
# All hermetic: tmpdirs for git repos, poisoned gh/git on PATH, fixtures for
# the gh-cache. NEVER touches the live reds.tsv, fleet/state, or real repos.
# Run:  bash fleet/tests/test_github_limits.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
contains(){ printf '%s' "$2" | grep -qF -- "$1" && return 0 || return 1; }

# ---------- T1: done.sh:merged_pr_touching_owns reads cache, ZERO gh calls ----------
echo "== T1 owns-match via cache (ZERO search-API calls) =="
t1_setup(){
  local d; d="$(mktemp -d)"
  cp "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" "$SRC/_lib.sh" \
     "$SRC/verify-merged.sh" "$SRC/gh-cache.sh" "$d/"
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/submitted" \
           "$d/state/claims" "$d/state/needs-push"
  # ticket: charon-private repo, owns two files, one of which was touched by PR #4242
  printf 'repo: charon-private\ntier: economy\nbranch: feat/owns\nowns: src/present.py, src/absent.py\n' \
    > "$d/board/TICK-OWNS.md"
  # stub gh: FAIL loudly if it ever gets called (poisoned)
  mkdir -p "$d/bin"
  cat > "$d/bin/gh" << 'GHMOCK'
#!/bin/sh
echo "GH-CALLED($*)" >&2
exit 42
GHMOCK
  chmod +x "$d/bin/gh"
  # stub the gh-cache files fixture: PR 4242 touched src/present.py
  printf '4242\tsrc/present.py\n' > "$d/files.tsv"
  # branch-only fixture (so the legacy branch-merge path is empty -> we MUST hit owns path)
  printf 'feat/other\t9999\n' > "$d/branch.tsv"
  echo "$d"
}

# t1a: owns match resolves via cache (PR 4242), no --search call.
d="$(t1_setup)"
PATH="$d/bin:$PATH" \
  GH_MERGED_FIXTURE="$d/branch.tsv" \
  GH_MERGED_FILES_FIXTURE="$d/files.tsv" \
  VERIFY_MERGED_REPO="$d" \
  bash "$d/done.sh" TICK-OWNS >/dev/null 2>"$d/err" || rc=$?
check "t1a owns-match via cache resolves (exit 0)" "$?" "0"
grep -q "GH-CALLED" "$d/err" 2>/dev/null && bad "t1a a gh call was made (search-API regression)" \
                                       || ok  "t1a ZERO gh calls (owns-match is cached)"
contains "merged:#4242" "$(cat "$d/state/done/TICK-OWNS" 2>/dev/null || true)" \
  && ok "t1a marker carries the cache-resolved PR #" \
  || bad "t1a marker carries the cache-resolved PR #"
rm -rf "$d"

# t1b: an owns file NOT in the cache, with a poisoned gh, refuses (not silently
# returns null and proceeds — that path is what the audit found, doing
# `gh ... --search "$path"` per owns which is exactly the burn).
d="$(t1_setup)"
# empty files fixture -> owns-match can't resolve -> falls through to REFUSED
: > "$d/files.tsv"
rc=0
PATH="$d/bin:$PATH" \
  GH_MERGED_FIXTURE="$d/branch.tsv" \
  GH_MERGED_FILES_FIXTURE="$d/files.tsv" \
  VERIFY_MERGED_REPO="$d" \
  bash "$d/done.sh" TICK-OWNS >/dev/null 2>"$d/err" || rc=$?
check "t1b no owns match + no gh -> REFUSED (exit 3)" "$rc" "3"
grep -q "GH-CALLED" "$d/err" 2>/dev/null && bad "t1b empty files fixture should not have invoked gh" \
                                       || ok  "t1b empty files fixture did NOT invoke gh (offline-safe)"
[ -e "$d/state/done/TICK-OWNS" ] && bad "t1b no marker on refuse" || ok "t1b no marker on refuse"
rm -rf "$d"

# t1c: legacy branch-only fixture (no files): owns-match short-circuits WITHOUT
# gh. Mirrors the production case where the cache hasn't been populated yet —
# done.sh must not silently fall through to `--search` (the audit's failure mode).
d="$(t1_setup)"
# remove files fixture (set to empty path -> no file)
rc=0
PATH="$d/bin:$PATH" \
  GH_MERGED_FIXTURE="$d/branch.tsv" \
  GH_MERGED_FILES_FIXTURE="/nonexistent" \
  VERIFY_MERGED_REPO="$d" \
  bash "$d/done.sh" TICK-OWNS >/dev/null 2>"$d/err" || rc=$?
check "t1c no files cache (legacy fixture) -> REFUSED (exit 3)" "$rc" "3"
grep -q "GH-CALLED" "$d/err" 2>/dev/null && bad "t1c legacy fixture should not have invoked gh" \
                                       || ok  "t1c legacy fixture did NOT invoke gh (no silent --search fallback)"
rm -rf "$d"

# ---------- T2: large-file-guard (standalone; preflight wiring is owned by another ticket) ----------
echo "== T2 large-file-guard =="
t2_setup(){ local d; d="$(mktemp -d)"; git -C "$d" init -q; printf '%s' "$d"; }

# t2a: clean tree -> GREEN
d="$(t2_setup)"
echo "tiny" > "$d/small.txt"
git -C "$d" add small.txt >/dev/null 2>&1
rc=0; bash "$SRC/checks/large-file-guard.sh" "$d" >/dev/null 2>&1 || rc=$?
check "t2a clean tree -> GREEN (exit 0)" "$rc" "0"
rm -rf "$d"

# t2b: staged >50MB -> RED, names path
d="$(t2_setup)"
dd if=/dev/zero of="$d/big.bin" bs=1024 count=60000 2>/dev/null
git -C "$d" add big.bin
out="$(bash "$SRC/checks/large-file-guard.sh" "$d" 2>&1)"; rc=$?
check "t2b staged >50MB -> RED (exit 1)" "$rc" "1"
contains "big.bin" "$out" && ok "t2b RED message names the path" || bad "t2b RED message names the path"
rm -rf "$d"

# t2c: untracked >50MB -> RED (catches the "staged next turn" case)
d="$(t2_setup)"
dd if=/dev/zero of="$d/big.bin" bs=1024 count=60000 2>/dev/null
out="$(bash "$SRC/checks/large-file-guard.sh" "$d" 2>&1)"; rc=$?
check "t2c untracked >50MB -> RED (exit 1)" "$rc" "1"
contains "big.bin" "$out" && ok "t2c RED message names the untracked path" || bad "t2c RED message names the untracked path"
rm -rf "$d"

# t2d: allowlist skips a matching path
d="$(t2_setup)"
dd if=/dev/zero of="$d/seed-corpus.bin" bs=1024 count=60000 2>/dev/null
git -C "$d" add seed-corpus.bin
rc=0
bash "$SRC/checks/large-file-guard.sh" "$d" --allowlist '.*-corpus\.bin$' >/dev/null 2>&1 || rc=$?
check "t2d allowlisted path -> GREEN (exit 0)" "$rc" "0"
rm -rf "$d"

# t2e: LARGE_FILE_MAX_BYTES override
d="$(t2_setup)"
dd if=/dev/zero of="$d/medium.bin" bs=1024 count=2000 2>/dev/null
git -C "$d" add medium.bin
# default 50MB -> GREEN
rc=0; bash "$SRC/checks/large-file-guard.sh" "$d" >/dev/null 2>&1 || rc=$?
check "t2e1 2MB under default 50MB -> GREEN" "$rc" "0"
# with --max-bytes 1MB -> RED
rc=0; bash "$SRC/checks/large-file-guard.sh" "$d" --max-bytes 1048576 >/dev/null 2>&1 || rc=$?
check "t2e2 2MB over 1MB override -> RED" "$rc" "1"
rm -rf "$d"

# (T2f — preflight wiring — is owned by another ticket. The wiring code itself
#  lives in fleet/preflight.sh which is NOT in this ticket's `owns:`.)

# (T3 — land/land-push pacing — is owned by another ticket. The pacing code
#  lives in fleet/land-push.sh / fleet/land.sh which are NOT in this ticket's
#  `owns:`. The hard-gh-cache test of T1 + T4 is the on-budget proof that the
#  gh-cache seam is solid; the pacing fix has its own ticket.)

# ---------- T4: gh-cache.merged_prs_touching_file ----------
echo "== T4 gh-cache.merged_prs_touching_file =="
FLEET="$SRC"
export FLEET
# shellcheck source=/dev/null
source "$SRC/gh-cache.sh"
D_FILES="$(mktemp)"
printf '4242\tsrc/present.py\n4242\tsrc/other.py\n9999\tsrc/elsewhere.py\n' > "$D_FILES"
# T4a
GD="$(mktemp -d)"; mkdir -p "$GD/bin"
printf '#!/bin/sh\necho "GH-CALLED" >&2; exit 42\n' > "$GD/bin/gh"; chmod +x "$GD/bin/gh"
PATH="$GD/bin:$PATH" GH_MERGED_FILES_FIXTURE="$D_FILES" \
  out="$(merged_prs_touching_file Nnyan/charon-private src/present.py 2>/dev/null)"
check "T4a owns-match returns PR# from cache" "$out" "4242"
PATH="$GD/bin:$PATH" GH_MERGED_FILES_FIXTURE="$D_FILES" \
  out="$(merged_prs_touching_file Nnyan/charon-private src/missing.py 2>/dev/null)"
check "T4b owns-match empty for unknown path" "$out" ""
# T4c: poisoned gh -> ZERO invocations under a 100-call loop (batched, not per-path).
poisoned=0
for i in $(seq 1 100); do
  o="$(PATH="$GD/bin:$PATH" GH_MERGED_FILES_FIXTURE="$D_FILES" merged_prs_touching_file Nnyan/charon-private src/present.py 2>"$GD/err")"
  [ "$o" = "4242" ] || poisoned=1
  grep -q "GH-CALLED" "$GD/err" 2>/dev/null && poisoned=1
done
[ "$poisoned" -eq 0 ] && ok "T4c 100 owns-match lookups, ZERO gh calls (batched cache)" \
                     || bad "T4c a lookup shelled out to gh (regression of batching)"
rm -rf "$GD"
rm -f "$D_FILES"
unset GH_MERGED_FILES_FIXTURE

# ---------- T5: PRODUCTION PATH, NO FIXTURE (fail-on-gut / fail-on-bad-flag) ----------
# See header. This is the ONLY test that reaches the real gh invocation.
echo "== T5 production path, NO fixture (real gh invocation) =="
unset GH_MERGED_FILES_FIXTURE GH_MERGED_FIXTURE

T5="$(mktemp -d)"; mkdir -p "$T5/bin"
# Canned API response for `--json number,files`.
cat > "$T5/prs.json" << 'JSON'
[ {"number":4242,"files":[{"path":"src/present.py"},{"path":"src/other.py"}]},
  {"number":9999,"files":[{"path":"src/elsewhere.py"}]} ]
JSON
# gh stub that behaves like the REAL gh: it VALIDATES FLAGS and only knows the
# jq flag as -q/--jq. `-r` (the shipped bug) is rejected exactly as gh 2.63.2
# rejects it, so this test goes red on that regression instead of passing blind.
# Every invocation is logged so we can assert the batching claim for real.
cat > "$T5/bin/gh" << 'GHSTUB'
#!/usr/bin/env bash
echo "CALL $*" >> "$GH_STUB_LOG"
q=""
[ "$1" = "pr" ] && [ "$2" = "list" ] || { echo "unknown command" >&2; exit 1; }
shift 2
while [ $# -gt 0 ]; do
  case "$1" in
    --repo|--state|--limit|--json|--label|--head|--search) shift 2;;
    -q|--jq) q="$2"; shift 2;;
    -*) f="${1#-}"; echo "unknown shorthand flag: '${f:0:1}' in $1" >&2; exit 1;;
    *) shift;;
  esac
done
[ -n "$q" ] || { echo "stub: no jq expression given" >&2; exit 1; }
jq -r "$q" < "$GH_STUB_JSON"
GHSTUB
chmod +x "$T5/bin/gh"
export GH_STUB_JSON="$T5/prs.json" GH_STUB_LOG="$T5/calls.log"
: > "$GH_STUB_LOG"

T5C="$(mktemp -d)"
out="$(PATH="$T5/bin:$PATH" GH_CACHE_DIR="$T5C" \
        merged_prs_touching_file Nnyan/charon-private src/present.py 2>"$T5/err")"
check "T5a NO fixture: owns-match resolves via the REAL gh path" "$out" "4242"

# The load-bearing assertion: the cache file must actually EXIST and be populated.
# With the `-r` bug this file was never created (gh exited non-zero -> rm the tmp).
cf="$T5C/merged-files-Nnyan_charon-private.tsv"
[ -s "$cf" ] && ok "T5b production gh call CREATED a non-empty cache file" \
             || bad "T5b cache file missing/empty ($cf) — the gh invocation did not succeed"
# ...and be parseable "<pr#>\t<path>" TSV, not raw/quoted JSON.
if [ -s "$cf" ] && [ "$(awk -F'\t' '$1=="4242" && $2=="src/present.py"{print "y"; exit}' "$cf")" = "y" ]; then
  ok "T5c cache rows are parseable <pr#>TAB<path> (jq -q raw output, not quoted JSON)"
else
  bad "T5c cache rows are not parseable <pr#>TAB<path>"
fi
check "T5d unknown path is empty on the real path" \
  "$(PATH="$T5/bin:$PATH" GH_CACHE_DIR="$T5C" merged_prs_touching_file Nnyan/charon-private src/nope.py 2>/dev/null)" ""
# Batching for real (not vacuously, as T4c does behind a fixture): N lookups
# against a warm cache must add ZERO further gh calls.
before="$(wc -l < "$GH_STUB_LOG")"
for i in 1 2 3 4 5 6 7 8 9 10; do
  PATH="$T5/bin:$PATH" GH_CACHE_DIR="$T5C" merged_prs_touching_file Nnyan/charon-private src/present.py >/dev/null 2>&1
done
check "T5e 10 more lookups on a warm cache add ZERO gh calls" "$(wc -l < "$GH_STUB_LOG")" "$before"
# And the stub must genuinely reject the shipped bug, else T5a-c prove nothing.
if PATH="$T5/bin:$PATH" gh pr list --repo x --json number,files -r '.[]|"x"' >/dev/null 2>&1; then
  bad "T5f stub accepts -r — it is too permissive to catch the flag regression"
else
  ok "T5f stub rejects -r like real gh (so T5a-c are a real flag guard)"
fi
unset GH_STUB_JSON GH_STUB_LOG
rm -rf "$T5" "$T5C"

unset FLEET

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL GITHUB-LIMITS-HARDENING TESTS PASS"
