#!/usr/bin/env bash
# session-start-hook.test.sh — FAIL-ON-REVERT self-test for fleet/hooks/session-start.sh
# (SYNC-SCHEDULE / mechanized anti-clobber gate).
#
# Operates on THROWAWAY bare "origin" + clone fixtures — never the live repos.
# Covers:
#   (a) FRESH: local clone == origin -> sync reports "current", hook prints OK, no STALE banner.
#   (b) STALE-CLEAN: local clone behind origin, working tree clean -> sync-checkouts.sh FF's
#       it forward; hook reports OK (current) afterward — this is the primary clobber-fix path.
#   (c) STALE-DIRTY: local clone behind origin AND has an uncommitted tracked change -> sync
#       CANNOT fast-forward (dirty guard) -> hook prints the loud STALE banner (fail-loud path).
#   (d) hardcoded-origin/main REGRESSION GUARD: asserts the hook's freshness check does NOT
#       use a literal "origin/main" (would silently misreport on these master-default fixtures).
#
# Run:  bash fleet/tests/session-start-hook.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

# --- build a throwaway "origin" (bare) + a "product" clone + a "rig" clone -----------------
git init --quiet --bare "$D/origin.git"
git clone --quiet "$D/origin.git" "$D/seed"
(
  cd "$D/seed"
  echo "one" > f.txt && git add f.txt && git commit --quiet -m c1
  echo "two" >> f.txt && git add f.txt && git commit --quiet -m c2
  git branch -M master
  git push --quiet origin master
)
git clone --quiet "$D/origin.git" "$D/product"
git clone --quiet "$D/origin.git" "$D/rig"
(cd "$D/product" && git checkout --quiet -B master origin/master)
(cd "$D/rig"     && git checkout --quiet -B master origin/master)

run_hook(){
  SESSION_START_PRODUCT="$D/product" \
  SESSION_START_PRIV="$D/rig" \
  SYNC_CHECKOUTS_PRODUCT="$D/product" \
  SYNC_CHECKOUTS_PRIV="$D/rig" \
  bash "$SRC/hooks/session-start.sh" 2>&1
}

echo "== (a) FRESH: both clones current with origin =="
out="$(run_hook)"
case "$out" in
  *STALE*) bad "a1 no STALE banner when fresh" ;;
  *) ok "a1 no STALE banner when fresh" ;;
esac
case "$out" in
  *"[product] OK"*"[rig] OK"*|*"[product] OK"*) ok "a2 reports OK for product" ;;
  *) bad "a2 reports OK for product ($out)" ;;
esac

echo "== (b) STALE-CLEAN: origin advances, clones behind, working trees clean -> FF then OK =="
(
  cd "$D/seed"
  echo "three" >> f.txt && git add f.txt && git commit --quiet -m c3
  git push --quiet origin master
)
out="$(run_hook)"
case "$out" in
  *"FF'd"*) ok "b1 sync-checkouts FF'd the behind clones" ;;
  *) bad "b1 sync-checkouts FF'd the behind clones (out: $out)" ;;
esac
case "$out" in
  *STALE*) bad "b2 no STALE banner after successful FF" ;;
  *) ok "b2 no STALE banner after successful FF" ;;
esac
prod_sha_after="$(git -C "$D/product" rev-parse --short HEAD)"
origin_sha="$(git -C "$D/seed" rev-parse --short HEAD)"
[ "$prod_sha_after" = "$origin_sha" ] && ok "b3 product HEAD now matches origin HEAD" \
  || bad "b3 product HEAD matches origin HEAD (got $prod_sha_after want $origin_sha)"

echo "== (c) STALE-DIRTY: origin advances again, clone has an uncommitted tracked change -> FAIL LOUD =="
(
  cd "$D/seed"
  echo "four" >> f.txt && git add f.txt && git commit --quiet -m c4
  git push --quiet origin master
)
echo "dirty-edit" >> "$D/product/f.txt"   # uncommitted tracked change — sync must refuse to FF
out="$(run_hook)"
case "$out" in
  *"TRACKED changes present"*) ok "c1 sync-checkouts refuses to FF a dirty repo" ;;
  *) bad "c1 sync-checkouts refuses to FF a dirty repo (out: $out)" ;;
esac
case "$out" in
  *"STALE"*"product"*|*"STALE"*) ok "c2 hook prints a loud STALE banner when FF failed" ;;
  *) bad "c2 hook prints a loud STALE banner when FF failed (out: $out)" ;;
esac
case "$out" in
  *"do NOT trust a handoff until reconciled"*) ok "c3 hook prints the do-not-trust closing line" ;;
  *) bad "c3 hook prints the do-not-trust closing line" ;;
esac
git -C "$D/product" checkout --quiet -- f.txt   # clean up for tidiness (repo is throwaway anyway)

echo "== (d) regression guard: hook must never hardcode origin/main in CODE (comments may mention it) =="
if grep -v '^\s*#' "$SRC/hooks/session-start.sh" | grep -q "origin/main"; then
  bad "d1 session-start.sh must not hardcode origin/main"
else
  ok "d1 session-start.sh does not hardcode origin/main"
fi
if grep -v '^\s*#' "$SRC/sync-checkouts.sh" 2>/dev/null | grep -q "origin/main"; then
  bad "d2 sync-checkouts.sh must not hardcode origin/main"
else
  ok "d2 sync-checkouts.sh does not hardcode origin/main"
fi

echo
echo "--- $PASS passed, $FAIL failed ---"
if [ "$FAIL" -ne 0 ]; then
  echo "SESSION-START-HOOK SELF-TEST FAILED"
  exit 1
fi
echo "ALL SESSION-START-HOOK SELF-TESTS PASS"
exit 0
