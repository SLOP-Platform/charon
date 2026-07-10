#!/usr/bin/env bash
# reconcile-merged.test.sh — FAIL-ON-REVERT tests for the #2 auto-done-on-merge safety-net
# (fleet/reconcile-merged.sh). Runs entirely OFFLINE via the RECONCILE_MERGED_SRC fixture hook
# (no gh / no network) in an isolated temp fleet. NEVER touches the live fleet/state.
#
# Covers:
#   (a) a MERGED branch whose ticket is not yet done -> reconcile runs done.sh -> state/done/<id>.
#   (b) a ticket NOT in the merged list is left untouched.
#   (c) a merged branch with NO board ticket is ignored (no crash).
#   (d) idempotent: a second run makes no further change and still exits 0.
# Reverting the reconcile loop leaves TICK-A un-done -> (a) fails.
#
# Run:  bash fleet/tests/reconcile-merged.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/reconcile-merged.sh" "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" "$d/"
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/submitted" "$d/state/claims" "$d/state/needs-push"
  printf 'tier: economy\nbranch: feat/tick-a\nwork_class: docs\n' > "$d/board/TICK-A.md"
  printf 'tier: economy\nbranch: feat/tick-b\nwork_class: docs\n' > "$d/board/TICK-B.md"
  echo "$d"
}

d="$(mk_fleet)"
# merged list: TICK-A's branch + one branch that maps to no ticket.
printf 'feat/tick-a\nfeat/orphan-none\n' > "$d/merged.txt"

# run offline (fixture hook); done.sh --no-verify never calls gh.
RECONCILE_MERGED_SRC="$d/merged.txt" bash "$d/reconcile-merged.sh" >/dev/null 2>&1

[ -e "$d/state/done/TICK-A" ] && ok "a merged TICK-A auto-closed (state/done written)" \
                              || bad "a merged TICK-A auto-closed (state/done written)"
[ -e "$d/state/done/TICK-B" ] && bad "b non-merged TICK-B left OPEN" \
                              || ok "b non-merged TICK-B left OPEN"
# (c) no crash on the orphan branch -> exit 0
RECONCILE_MERGED_SRC="$d/merged.txt" bash "$d/reconcile-merged.sh" >/dev/null 2>&1
check "c orphan merged branch ignored (exit 0)" "$?" "0"
# (d) idempotent second run: exit 0, TICK-A still done, TICK-B still open
rc=0; RECONCILE_MERGED_SRC="$d/merged.txt" bash "$d/reconcile-merged.sh" >/dev/null 2>&1 || rc=$?
check "d second run idempotent (exit 0)" "$rc" "0"
[ -e "$d/state/done/TICK-A" ] && ok "d TICK-A stays done" || bad "d TICK-A stays done"
[ -e "$d/state/done/TICK-B" ] && bad "d TICK-B stays open" || ok "d TICK-B stays open"
rm -rf "$d"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL RECONCILE-MERGED TESTS PASS"
