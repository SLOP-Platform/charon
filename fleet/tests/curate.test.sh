#!/usr/bin/env bash
# curate.test.sh — FAIL-ON-REVERT self-test for fleet/memory/curate.sh.
#
# Operates on TEMP fixture directories (never the real memory store).
#
# Covers:
#   (a) DRY-RUN default: duplicates flagged + stale note proposed for archive.
#   (b) --apply: duplicate is archived (moved to archive/) + stale note archived.
#   (c) FAIL-ON-REVERT: DEDUP_DISABLE=1 + DECAY_DISABLE=1 → neither flagged (red).
#   (d) Normal (non-duplicate, recent) notes are NOT flagged.
#   (e) Conflict flag: notes sharing a tag are reported.
#
# Run:  bash fleet/tests/curate.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# Build a temp notes directory with fixture memory notes.
# Returns the fixture path.
mk_fixture(){
  local root; root="$(mktemp -d)"
  local now; now=$(date +%s)
  local thirty_days_ago=$(( now - 30*86400 ))
  local sixty_days_ago=$(( now - 60*86400 ))

  # (1) Two duplicate notes — identical content, different names
  cat > "$root/dup-alpha.md" <<-NOTE
	tags: test, duplicate
	last_referenced: $thirty_days_ago
	status: verified
	
	The color of the sky is blue during clear weather.
	This is a verified observation.
	NOTE

  cat > "$root/dup-beta.md" <<-NOTE
	tags: test, duplicate
	last_referenced: $thirty_days_ago
	status: verified
	
	The color of the sky is blue during clear weather.
	This is a verified observation.
	NOTE

  # (2) One stale note — last_referenced is 60 days ago (>30d threshold)
  cat > "$root/stale-old.md" <<-NOTE
	tags: test, stale
	last_referenced: $sixty_days_ago
	status: inferred
	
	The grass is green in spring.
	This fact has not been referenced in a while.
	NOTE

  # (3) Normal recent notes — should not be flagged
  cat > "$root/recent-weather.md" <<-NOTE
	tags: test, weather
	last_referenced: $now
	status: verified
	
	Water freezes at 0 degrees Celsius.
	NOTE

  cat > "$root/recent-earth.md" <<-NOTE
	tags: test, geography
	last_referenced: $now
	status: verified
	
	The Earth is round.
	NOTE

  echo "$root"
}

run_curate(){
  # run_curate <fixture_dir> [extra_env...] [--apply]
  local fixture="$1"; shift
  CURATE_NOTES_DIR="$fixture" \
    CURATE_DECAY_DAYS=30 \
    "$@" \
    bash "$SRC/memory/curate.sh" "$@"
  # But we need to separate env vars from script args — use a wrapper
}

echo "== (a) DRY-RUN: duplicates flagged + stale note proposed =="
D="$(mk_fixture)"
out="$(CURATE_NOTES_DIR="$D" CURATE_DECAY_DAYS=30 bash "$SRC/memory/curate.sh" 2>&1)"; rc=$?
check "a1 dry-run exit 0" "$rc" "0"
echo "$out" | grep -q "dup-alpha" && ok "a2 dup-alpha flagged" \
                                  || bad "a2 dup-alpha flagged"
echo "$out" | grep -q "dup-beta"  && ok "a3 dup-beta flagged"  \
                                  || bad "a3 dup-beta flagged"
echo "$out" | grep -q "DUPLICATE" && ok "a4 duplicate group detected" \
                                  || bad "a4 duplicate group detected"
echo "$out" | grep -q "stale-old" && ok "a5 stale-old flagged for decay" \
                                  || bad "a5 stale-old flagged for decay"
echo "$out" | grep -q "STALE"     && ok "a6 STALE marker present" \
                                  || bad "a6 STALE marker present"
# Normal notes should NOT be flagged by DEDUP or DECAY
echo "$out" | grep -q "DEDUP.*recent-weather" && bad "a7 recent-weather NOT in DEDUP" \
                                               || ok "a7 recent-weather NOT in DEDUP"
echo "$out" | grep -q "STALE.*recent-weather" && bad "a8 recent-weather NOT in STALE" \
                                               || ok "a8 recent-weather NOT in STALE"
echo "$out" | grep -q "DEDUP.*recent-earth"   && bad "a9 recent-earth NOT in DEDUP" \
                                               || ok "a9 recent-earth NOT in DEDUP"
echo "$out" | grep -q "STALE.*recent-earth"   && bad "a10 recent-earth NOT in STALE" \
                                               || ok "a10 recent-earth NOT in STALE"

# Conflict flag: dup-alpha + dup-beta + recent-weather share 'test' tag
echo "$out" | grep -q "TAG.*test" && ok "a11 conflict tag 'test' flagged" \
                                   || bad "a11 conflict tag 'test' flagged"

echo "== (b) --apply archives duplicate and stale note =="
# Ensure original files exist
[ -f "$D/dup-alpha.md" ]   && ok "b1 dup-alpha exists before apply"  \
                            || bad "b1 dup-alpha exists before apply"
[ -f "$D/dup-beta.md" ]    && ok "b2 dup-beta exists before apply"   \
                            || bad "b2 dup-beta exists before apply"
[ -f "$D/stale-old.md" ]   && ok "b3 stale-old exists before apply"  \
                            || bad "b3 stale-old exists before apply"
[ -f "$D/recent-weather.md" ] && ok "b4 recent-weather exists"       \
                               || bad "b4 recent-weather exists"
out="$(CURATE_NOTES_DIR="$D" CURATE_DECAY_DAYS=30 bash "$SRC/memory/curate.sh" --apply 2>&1)"; rc=$?
check "b5 apply exit 0" "$rc" "0"
# dup-beta should be archived (it's the one archived, alpha is keeper)
[ -f "$D/dup-alpha.md" ]                      && ok "b6 dup-alpha kept" \
                                               || bad "b6 dup-alpha kept"
[ ! -f "$D/dup-beta.md" ]                     && ok "b7 dup-beta archived" \
                                               || bad "b7 dup-beta archived"
# stale-old should be archived
[ ! -f "$D/stale-old.md" ]                    && ok "b8 stale-old archived" \
                                               || bad "b8 stale-old archived"
# recent notes should remain
[ -f "$D/recent-weather.md" ]                 && ok "b9 recent-weather preserved" \
                                               || bad "b9 recent-weather preserved"
[ -f "$D/recent-earth.md" ]                   && ok "b10 recent-earth preserved" \
                                               || bad "b10 recent-earth preserved"
# archive dir should contain the moved files
ls "$D/archive/"* >/dev/null 2>&1             && ok "b11 archive dir has content" \
                                               || bad "b11 archive dir has content"
[ -f "$D/archive/stale-old.md" ]              && ok "b12 stale-old in archive" \
                                               || bad "b12 stale-old in archive"

echo "== (c) FAIL-ON-REVERT: DEDUP_DISABLE + DECAY_DISABLE → neither flagged =="
D2="$(mk_fixture)"
out="$(CURATE_NOTES_DIR="$D2" CURATE_DECAY_DAYS=30 CURATE_DEDUP_DISABLE=1 CURATE_DECAY_DISABLE=1 bash "$SRC/memory/curate.sh" 2>&1)"; rc=$?
check "c1 disabled exit 0" "$rc" "0"
echo "$out" | grep -q "DUPLICATE" && bad "c2 duplicate NOT flagged with dedup disabled" \
                                   || ok "c2 duplicate NOT flagged with dedup disabled"
echo "$out" | grep -q "STALE"     && bad "c3 stale NOT flagged with decay disabled" \
                                   || ok "c3 stale NOT flagged with decay disabled"

echo "== (d) No-op on empty notes dir =="
D3="$(mktemp -d)"
out="$(CURATE_NOTES_DIR="$D3" bash "$SRC/memory/curate.sh" 2>&1)"; rc=$?
check "d1 empty dir exit 0" "$rc" "0"

echo "== (e) No false-positive on notes with unique content =="
D4="$(mktemp -d)"
now=$(date +%s)
for i in a b c; do
  cat > "$D4/$i.md" <<-NOTE
	tags: unique-$i
	last_referenced: $now
	status: verified
	
	This is unique note $i with distinct content.
	NOTE
done
out="$(CURATE_NOTES_DIR="$D4" CURATE_DECAY_DAYS=30 bash "$SRC/memory/curate.sh" 2>&1)"; rc=$?
check "e1 unique exit 0" "$rc" "0"
echo "$out" | grep -q "DUPLICATE" && bad "e2 no duplicate flag on unique notes" \
                                   || ok "e2 no duplicate flag on unique notes"
echo "$out" | grep -q "STALE"     && bad "e3 no stale flag on recent notes" \
                                   || ok "e3 no stale flag on recent notes"

# cleanup
rm -rf "$D" "$D2" "$D3" "$D4"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL CURATE TESTS PASS"
