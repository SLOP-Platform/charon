#!/usr/bin/env bash
# rescue-push.test.sh — fail-on-revert suite for fleet/rescue-push.sh.
#
# HERMETIC: every repo here is a throwaway `mktemp -d` with a LOCAL BARE remote. No network, no
# reference to the live boxes. That is only possible because rescue-push.sh honours
# RESCUE_PUSH_REPOS; the live default is untouched.
#
# TARGET OVERRIDE: RESCUE_PUSH_SH points the whole suite at a DIFFERENT copy of the script, which
# is how the fail-on-revert proof is produced — the identical assertions are re-run against a
# mutated copy and must go RED. A suite that cannot be pointed at a broken build cannot prove it
# would have caught one.
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="${RESCUE_PUSH_SH:-$SRC/rescue-push.sh}"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# ------------------------------------------------------------------ fixture
# Builds one repo carrying ALL of the shapes at once, because the defect this tool exists to close
# is a sweep that covers SOME shapes: the first cut handled no-upstream only and silently left 50
# ahead-of-upstream branches behind. A per-shape fixture would not have caught that.
fixture(){
  local d bare other
  d="$(mktemp -d)"; bare="$d/remote.git"; other="$d/other"
  git init -q --bare "$bare"
  git init -q -b master "$d/repo"
  git -C "$d/repo" remote add origin "$bare"
  printf 'seed\n' > "$d/repo/README"
  git -C "$d/repo" add -A; git -C "$d/repo" commit -q -m seed
  git -C "$d/repo" push -q -u origin master

  # (1) NO UPSTREAM — never published. Invisible to any upstream-relative query.
  git -C "$d/repo" checkout -q -b noup master
  printf 'noup\n' > "$d/repo/noup.txt"; git -C "$d/repo" add -A; git -C "$d/repo" commit -q -m noup

  # (2) AHEAD OF UPSTREAM — published, then committed on top. THE MISSED CLASS.
  git -C "$d/repo" checkout -q -b ahead master
  git -C "$d/repo" push -q -u origin ahead
  printf 'ahead\n' > "$d/repo/ahead.txt"; git -C "$d/repo" add -A; git -C "$d/repo" commit -q -m ahead

  # (3) DIVERGED — remote gains a commit local does not have, local gains one the remote lacks.
  git -C "$d/repo" checkout -q -b div master
  git -C "$d/repo" push -q -u origin div
  git clone -q "$bare" "$other"
  git -C "$other" checkout -q div
  printf 'theirs\n' > "$other/theirs.txt"; git -C "$other" add -A; git -C "$other" commit -q -m theirs
  git -C "$other" push -q origin div
  printf 'mine\n' > "$d/repo/mine.txt"; git -C "$d/repo" add -A; git -C "$d/repo" commit -q -m mine

  # (4) CLEAN — published, nothing new. Must be left ALONE.
  git -C "$d/repo" checkout -q -b clean master
  git -C "$d/repo" push -q -u origin clean

  # (5) backup/* — carries commits but is a snapshot, not work. Must be SKIPPED.
  git -C "$d/repo" checkout -q -b backup/snap master
  printf 'snap\n' > "$d/repo/snap.txt"; git -C "$d/repo" add -A; git -C "$d/repo" commit -q -m snap

  git -C "$d/repo" checkout -q master
  printf '%s' "$d"
}

run(){ RESCUE_PUSH_REPOS="$1/repo" bash "$TOOL" "${2:-}" 2>&1; }
remote_sha(){ git -C "$1/remote.git" rev-parse --verify -q "refs/heads/$2" 2>/dev/null || echo MISSING; }
local_sha(){  git -C "$1/repo"       rev-parse --verify -q "refs/heads/$2" 2>/dev/null || echo MISSING; }
snapshot(){   git -C "$1/remote.git" for-each-ref --format='%(refname) %(objectname)' refs/heads | sort; }

# ================================================================== e. DRY RUN MUTATES NOTHING
d="$(fixture)"
before="$(snapshot "$d")"
out="$(run "$d")"
after="$(snapshot "$d")"
if [ "$before" = "$after" ]; then ok "e: dry run mutates NO remote ref"
else bad "e: dry run CHANGED the remote"$'\n'"$(diff <(echo "$before") <(echo "$after"))"; fi
grep -q 'WOULD PUSH' <<<"$out" && ok "e: dry run reports what it would push" \
                                || bad "e: dry run printed no WOULD PUSH: $out"

# ================================================================== the --push run
d="$(fixture)"
div_remote_before="$(remote_sha "$d" div)"
div_local="$(local_sha "$d" div)"
clean_remote_before="$(remote_sha "$d" clean)"
out="$(run "$d" --push)"; rc=$?
echo "--- rescue-push --push output ---"; printf '%s\n' "$out"; echo "---------------------------------"

# ---- a. NO-UPSTREAM branch is pushed
if [ "$(remote_sha "$d" noup)" = "$(local_sha "$d" noup)" ] && [ "$(remote_sha "$d" noup)" != MISSING ]; then
  ok "a: no-upstream branch was published"
else
  bad "a: no-upstream branch NOT published (remote=$(remote_sha "$d" noup) local=$(local_sha "$d" noup))"
fi

# ---- b. AHEAD-OF-UPSTREAM branch is pushed (the class the narrow first version missed)
if [ "$(remote_sha "$d" ahead)" = "$(local_sha "$d" ahead)" ]; then
  ok "b: ahead-of-upstream branch was published"
else
  bad "b: ahead-of-upstream branch NOT published (remote=$(remote_sha "$d" ahead) local=$(local_sha "$d" ahead))"
fi

# ---- c. DIVERGED branch is rescued to a PARALLEL ref
if [ "$(remote_sha "$d" rescue/div)" = "$div_local" ]; then
  ok "c: diverged branch rescued to parallel ref rescue/div"
else
  bad "c: rescue/div is $(remote_sha "$d" rescue/div), expected local div tip $div_local"
fi
grep -q "DIVERGED -> rescued to 'rescue/div'" <<<"$out" && ok "c: diverged outcome is reported, not silent" \
  || bad "c: no DIVERGED narration in output"

# ---- d. THE SAFETY PROPERTY: a diverged branch is NEVER force-pushed.
# Asserting rescue/div merely EXISTS is not enough — a tool that force-pushed div and THEN wrote
# the rescue ref would satisfy that and still have destroyed the remote side. The load-bearing
# assertion is that refs/heads/div on the remote is BYTE-IDENTICAL to what it was before the run,
# i.e. the remote-only commit is still reachable from it.
div_remote_after="$(remote_sha "$d" div)"
if [ "$div_remote_after" = "$div_remote_before" ]; then
  ok "d: SAFETY — remote 'div' UNCHANGED ($div_remote_before) — not force-pushed"
else
  bad "d: SAFETY VIOLATED — remote 'div' moved $div_remote_before -> $div_remote_after (FORCE PUSH)"
fi
if git -C "$d/remote.git" merge-base --is-ancestor "$div_remote_before" "$div_remote_after" 2>/dev/null; then
  ok "d: SAFETY — the remote-only commit is still reachable on 'div'"
else
  bad "d: SAFETY VIOLATED — the remote-only commit is no longer reachable from 'div'"
fi
# and the local-only work must actually be safe on the parallel ref
if git -C "$d/remote.git" merge-base --is-ancestor "$div_local" "$(remote_sha "$d" rescue/div)" 2>/dev/null; then
  ok "d: the local-only commit is reachable from rescue/div — nothing lost on either side"
else
  bad "d: the local-only commit is NOT reachable from rescue/div — the rescue lost the work"
fi

# ---- f. a branch with nothing at risk is not touched, and backup/* is skipped
[ "$(remote_sha "$d" clean)" = "$clean_remote_before" ] && ok "f: nothing-at-risk branch untouched" \
  || bad "f: 'clean' was modified"
grep -qE '(PUSHED|WOULD PUSH|DIVERGED).*clean' <<<"$out" && bad "f: 'clean' appeared in the action list" \
  || ok "f: 'clean' absent from the action list"
[ "$(remote_sha "$d" backup/snap)" = MISSING ] && ok "f: backup/* skipped (snapshots are not work)" \
  || bad "f: backup/snap was pushed"

echo
echo "rescue-push.test: $PASS passed, $FAIL failed  (target: $TOOL)"
[ "$FAIL" -eq 0 ] || exit 1
