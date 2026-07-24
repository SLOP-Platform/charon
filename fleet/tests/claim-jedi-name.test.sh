#!/usr/bin/env bash
# claim-jedi-name.test.sh — FAIL-ON-REVERT test for the mechanized Jedi-name allocator.
#
# Covers:
#   (a) Regression fixture: luminara-unduli in git history but NOT in live tree
#       -> allocator excludes it.  Reverting the git-history exclusion half
#       -> luminara becomes claimable -> test goes RED (proved in selftest B1).
#   (b) Pool exhaustion -> non-zero exit + no name on stdout.
#   (c) Concurrent invocations never return the same name.
#   (d) Pool file integrity: non-empty, one slug per line, no duplicates.
#
# Run:  bash fleet/tests/claim-jedi-name.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# ── (1) Run the allocator's own selftest ──────────────────────────────────
echo "== (1) claim-jedi-name.sh --selftest =="
rc=0
bash "$SRC/claim-jedi-name.sh" --selftest || rc=$?
if [ "$rc" -eq 0 ]; then
  ok "1 selftest passes"
else
  bad "1 selftest failed (rc=$rc)"
fi

# ── (2) Pool-file integrity checks ───────────────────────────────────────
echo "== (2) pool-file integrity =="
POOL="$SRC/state/jedi-name-pool.txt"

if [ -f "$POOL" ]; then
  ok "2a pool file exists"
else
  bad "2a pool file missing: $POOL"
fi

count=0
count="$(grep -c . "$POOL" 2>/dev/null || echo 0)"
if [ "$count" -gt 30 ]; then
  ok "2b pool has >30 entries ($count) — sufficient for fleet operation"
else
  bad "2b pool has only $count entries (expected >30)"
fi

# Every line is a non-empty kebab-case slug (lowercase, hyphens, alphanum).
line_num=0 bad_slugs=0
while IFS= read -r line; do
  line_num=$((line_num+1))
  [ -z "$line" ] && continue
  if ! echo "$line" | grep -qE '^[a-z][a-z0-9]*(-[a-z][a-z0-9]*)*$'; then
    bad "2c line $line_num: invalid slug format: '$line'"
    bad_slugs=$((bad_slugs+1))
  fi
done < "$POOL"
[ "$bad_slugs" -eq 0 ] && ok "2c all pool entries are valid kebab-case slugs"

# No duplicate entries.
dupes=""
dupes="$(sort "$POOL" | uniq -d)"
if [ -z "$dupes" ]; then
  ok "2d no duplicate pool entries"
else
  bad "2d duplicate pool entries: $dupes"
fi

# Verify key historical Jedi names are in the pool (luminara-unduli is the
# regression fixture's name — it MUST be present in the pool so the exclusion
# set can exclude it; the whole mechanism relies on pool-membership).
echo "== (3) key historical names in pool =="
for name in luminara-unduli aayla-secura ahsoka-tano obi-wan-kenobi mace-windu; do
  if grep -qxF "$name" "$POOL" 2>/dev/null; then
    ok "3 '$name' in pool"
  else
    bad "3 '$name' NOT in pool — exclusion-set cannot exclude a non-member"
  fi
done

# ── summary ──────────────────────────────────────────────────────────────
echo
echo "--- $PASS passed, $FAIL failed ---"
if [ "$FAIL" -gt 0 ]; then
  echo "CLAIM-JEDI-NAME TEST FAILED"
  exit 1
fi
echo "ALL CLAIM-JEDI-NAME TESTS PASS"
exit 0
