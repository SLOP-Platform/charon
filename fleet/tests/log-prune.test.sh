#!/usr/bin/env bash
# log-prune.test.sh — FAIL-ON-REVERT self-test for fleet/log-prune.sh.
#
# Operates on a TEMP log dir fixture (never the live fleet). Mirrors the
# branch-reaper.test.sh pattern: env-hook the script's fleet root at a temp dir,
# drive --apply, assert OUTCOMES (not just exit 0).
#
# GREEN-IS-NOT-PROOF: exit 0 does NOT prove correct pruning. The self-test asserts:
#   - the STALE *.log was removed
#   - a FRESH *.log SURVIVED
#   - a sibling NON-LOG file (keep.me) SURVIVED       (guards against an over-broad rm)
#   - board/ and state/ roots are REFUSED             (hard-scope guard)
#
# FAIL-ON-REVERT (the core guard): revert the `-mtime +N` age filter in log-prune.sh
# to a bare `-mtime +0` (matches today, i.e. every file) and the FRESH log is then
# wrongly pruned -> test (c2) goes RED. The `-mtime +N` filter is what protects it.
#
# Run:  bash fleet/tests/log-prune.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# run_prune <fleet_root> [args...]  -- env-hooks LP_FLEET_DIR at the temp root.
run_prune(){
  local root="$1"; shift
  LP_FLEET_DIR="$root" bash "$SRC/log-prune.sh" "$@"
}

# Make a file with a backdated mtime (days ago). Touch -d is portable on GNU+BSD.
backdate(){
  local f="$1" days="$2"
  touch -d "@$(($(date +%s) - days*86400))" "$f"
}

echo "== (a) DRY-RUN default: stale log reported PRUN-able but NOT deleted =="
# In dry-run the candidate must be PRINTED but the file MUST survive on disk.
root="$(mktemp -d)"; logs="$root/state/overnight"
mkdir -p "$logs"
printf 'stale\n' > "$logs/STALE.log";       backdate "$logs/STALE.log" 30
printf 'fresh\n' > "$logs/FRESH.log"
out="$(run_prune "$root" --days 7 2>&1)"; rc=$?
check "a1 dry-run exit 0" "$rc" "0"
echo "$out" | grep -q "PRUNE.*STALE.log" && ok "a2 stale log flagged PRUNE-able" \
                                            || bad "a2 stale log flagged PRUNE-able"
[ -f "$logs/STALE.log" ] && ok "a3 stale log NOT deleted in dry-run" \
                           || bad "a3 stale log NOT deleted in dry-run (got deleted!)"

echo "== (b) --apply deletes the stale log =="
out="$(run_prune "$root" --days 7 --apply 2>&1)"; rc=$?
check "b1 apply exit 0" "$rc" "0"
[ -f "$logs/STALE.log" ] && bad "b2 stale log deleted under --apply" \
                          || ok "b2 stale log deleted under --apply"
echo "$out" | grep -q "pruned: 1 file" && ok "b3 pruned count = 1" \
                                         || bad "b3 pruned count = 1"

echo "== (c) FAIL-ON-REVERT: FRESH log SURVIVES --apply (age filter guard intact) =="
# The fresh log is mtime-now; with --days 7 the -mtime +7 filter MUST exclude it.
# A reverted/over-broad filter (e.g. -mtime +0 or no -mtime) would reap it -> RED.
[ -f "$logs/FRESH.log" ] && ok "c1 fresh log SURVIVED apply (age filter guard intact)" \
                           || bad "c1 fresh log was DELETED under --apply (guard reverted — DATA LOSS)"
# NEGATIVE: prove the guard is what protects. The fresh log must NOT appear as PRUNE-able.
dry="$(run_prune "$root" --days 7 2>&1)"
echo "$dry" | grep -q "PRUNE.*FRESH.log" \
  && bad "c2 fresh log wrongly listed as PRUNE-able (age filter reverted)" \
  || ok "c2 fresh log NOT listed as PRUNE-able (age-filter guard intact)"

echo "== (d) GREEN-IS-NOT-PROOF: a sibling NON-LOG file SURVIVES --apply =="
# Drop a non-log file in the same dir. An over-broad `rm *.log*` or `rm <dir>/*` would
# nuke it. The suffix-locked find MUST leave it alone.
printf 'keep\n' > "$logs/keep.me"
printf 'also-stale\n' > "$logs/ALSO-STALE.log"; backdate "$logs/ALSO-STALE.log" 30
out="$(run_prune "$root" --days 7 --apply 2>&1)"; rc=$?
check "d1 apply exit 0" "$rc" "0"
[ -f "$logs/keep.me" ] && ok "d2 non-log file keep.me SURVIVED (suffix lock intact)" \
                         || bad "d2 non-log file keep.me was DELETED (over-broad rm — DATA LOSS)"
[ -f "$logs/ALSO-STALE.log" ] && bad "d3 second stale log deleted under --apply" \
                              || ok "d3 second stale log deleted under --apply"

echo "== (e) idempotent second --apply run is exit 0, prunes nothing =="
rc=0; run_prune "$root" --days 7 --apply >/dev/null 2>&1 || rc=$?
check "e1 second apply exit 0" "$rc" "0"
out="$(run_prune "$root" --days 7 --apply 2>&1)"
echo "$out" | grep -q "pruned: 0 file" && ok "e2 second run prunes 0 files" \
                                          || bad "e2 second run prunes 0 files"

echo "== (f) HARD-SCOPE: board/ root is REFUSED =="
root2="$(mktemp -d)"; mkdir -p "$root2/board"
out="$(run_prune "$root2" --dir "$root2/board" 2>&1)"; rc=$?
[ "$rc" = "2" ] && ok "f1 board/ refused (exit 2)" \
                || bad "f1 board/ refused (exit 2, got $rc)"
echo "$out" | grep -q "refusing protected tree" && ok "f2 board/ refusal message printed" \
                                                    || bad "f2 board/ refusal message printed"

echo "== (g) HARD-SCOPE: state/ root is REFUSED =="
mkdir -p "$root2/state"
out="$(run_prune "$root2" --dir "$root2/state" 2>&1)"; rc=$?
[ "$rc" = "2" ] && ok "g1 state/ refused (exit 2)" \
                || bad "g1 state/ refused (exit 2, got $rc)"
echo "$out" | grep -q "refusing protected tree" && ok "g2 state/ refusal message printed" \
                                                    || bad "g2 state/ refusal message printed"

echo "== (h) HARD-SCOPE: dir outside fleet root is REFUSED =="
out="$(run_prune "$root2" --dir /tmp 2>&1)"; rc=$?
[ "$rc" = "2" ] && ok "h1 outside-root dir refused (exit 2)" \
                || bad "h1 outside-root dir refused (exit 2, got $rc)"

echo "== (i) SIZE-ROTATE: a large live log is gzipped (rotation bump works) =="
root3="$(mktemp -d)"; mkdir -p "$root3/state/overnight"
big="$root3/state/overnight/BIG.log"
# Make a file just over the 10-byte size threshold so the test is fast and deterministic.
python3 -c 'import sys; sys.stdout.write("x"*200)' > "$big"
# Pre-existing rotation slot to verify the bump path runs end-to-end.
printf 'rot1\n' > "$big.1"
out="$(run_prune "$root3" --days 365 --size-bytes 10 --rotations 3 --apply 2>&1)"; rc=$?
check "i1 rotate apply exit 0" "$rc" "0"
echo "$out" | grep -q "ROTATE.*BIG.log" && ok "i2 big log flagged ROTATE-able" \
                                             || bad "i2 big log flagged ROTATE-able"
[ -f "$big.1.gz" ] && ok "i3 BIG.log.1 was gzipped (to .log.1.gz)" \
                    || bad "i3 BIG.log.1 was gzipped (to .log.1.gz)"
[ -f "$big.2" ] && ok "i4 prior BIG.log.1 bumped to .log.2" \
                   || bad "i4 prior BIG.log.1 bumped to .log.2"
[ -f "$big" ] && bad "i5 live BIG.log was rotated away (moved to .log.1)" \
                || ok "i5 live BIG.log was rotated away (moved to .log.1)"

# cleanup
rm -rf "$root" "$root2" "$root3"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LOG-PRUNE TESTS PASS"
