#!/usr/bin/env bash
# claim-loop-guard.test.sh — FAIL-ON-REVERT tests for the 2026-07-09 claim-loop fix.
#
# Covers:
#   (a)  claim.sh SKIPS a parked ticket (parked: true field AND note: PARKED fallback) and
#        instead claims the next ready ticket.  FAILS if the parked-skip is reverted.
#   (b)  loop-guard.sh quarantines an id after N zero-commit releases, and claim.sh then
#        SKIPS the quarantined id.  FAILS if the guard or the loop-guard skip is reverted.
#
# Every test runs in a TEMP fleet (copied scripts + fixture board + fixture state). It NEVER
# touches the live fleet/state — safe to run while droids are working.
#
# Run:  bash fleet/tests/claim-loop-guard.test.sh   (exit 0 = all pass, 1 = a failure)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the real fleet/ dir
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# Build an isolated temp fleet with the scripts under test. Returns the dir on stdout.
mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/claim.sh" "$SRC/_lib.sh" "$SRC/loop-guard.sh" "$SRC/release.sh" "$d/"
  mkdir -p "$d/board" "$d/state/claims" "$d/state/submitted" "$d/state/done" "$d/state/loop-guard"
  echo "$d"
}
# claimed id (2nd token of "CLAIMED <id> <file>"), or "NONE".
claimed_id(){ local out; out="$(bash "$1/claim.sh" "$2" "$3" own-only 2>/dev/null)" || true
  case "$out" in CLAIMED\ *) set -- $out; echo "$2";; *) echo NONE;; esac; }

echo "== (a) claim.sh skips a PARKED ticket, claims the next ready one =="

# (a1) explicit `parked: true` field. PARKED-FIELD sorts before READY-A, so if the skip is
# reverted the parked ticket is claimed first and this test fails.
d="$(mk_fleet)"
printf 'tier: sonnet\nparked: true\n'  > "$d/board/PARKED-FIELD.md"
printf 'tier: sonnet\n'                > "$d/board/READY-A.md"
check "a1 parked:true field is skipped -> claims READY-A" "$(claimed_id "$d" sonnet d1)" "READY-A"
rm -rf "$d"

# (a2) `note:` PARKED fallback. AAA-NOTE sorts before ZZZ-READY.
d="$(mk_fleet)"
printf 'tier: sonnet\nnote: PARKED — gated on operator Q1\n' > "$d/board/AAA-NOTE.md"
printf 'tier: sonnet\n'                                       > "$d/board/ZZZ-READY.md"
check "a2 note: PARKED fallback is skipped -> claims ZZZ-READY" "$(claimed_id "$d" sonnet d1)" "ZZZ-READY"
rm -rf "$d"

echo "== (b) loop-guard quarantines after N zero-commit releases; claim.sh then skips it =="

d="$(mk_fleet)"
printf 'tier: sonnet\n' > "$d/board/LOOPY.md"     # sorts before MNEXT -> claimed first if not skipped
printf 'tier: sonnet\n' > "$d/board/MNEXT.md"

# 1st zero-commit release: counts (1/2), exit 0, NO quarantine marker yet.
rc=0; bash "$d/loop-guard.sh" record LOOPY droidX >/dev/null 2>&1 || rc=$?
check "b1 first record exits 0 (no quarantine yet)" "$rc" "0"
[ -e "$d/state/loop-guard/LOOPY" ] && bad "b2 no marker after 1st release" || ok "b2 no marker after 1st release"

# 2nd zero-commit release: reaches threshold -> exit 2, quarantine marker + escalation.
rc=0; err="$(bash "$d/loop-guard.sh" record LOOPY droidX 2>&1 >/dev/null)" || rc=$?
check "b3 second record exits 2 (quarantined)" "$rc" "2"
[ -e "$d/state/loop-guard/LOOPY" ] && ok "b4 quarantine marker written" || bad "b4 quarantine marker written"
case "$err" in *ESCALATION*) ok "b5 escalation line emitted";; *) bad "b5 escalation line emitted (got: $err)";; esac

# claim.sh must now SKIP the quarantined LOOPY and claim MNEXT. Reverting the loop-guard skip
# in claim.sh makes it claim LOOPY (sorts first) -> this fails.
check "b6 claim.sh skips quarantined id -> claims MNEXT" "$(claimed_id "$d" sonnet droidX)" "MNEXT"

# clear re-enables it (manager path).
bash "$d/loop-guard.sh" clear LOOPY >/dev/null 2>&1
[ -e "$d/state/loop-guard/LOOPY" ] && bad "b7 clear removes marker" || ok "b7 clear removes marker"
rm -rf "$d"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL CLAIM-LOOP-GUARD TESTS PASS"
