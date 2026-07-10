#!/usr/bin/env bash
# reconcile-merged.test.sh — FAIL-ON-REVERT tests for the #2 auto-done-on-merge safety-net AND the
# Wave-A HIGH #2 fix (fleet/reconcile-merged.sh must map merged PR -> ticket by VERIFIED MERGE /
# owns-OVERLAP, not a bare branch-name string, and close via done.sh --merged-sha, not --no-verify).
# Runs entirely OFFLINE via the RECONCILE_MERGED_SRC fixture hook against an ISOLATED product git
# repo (never the real one; no gh / no network). NEVER touches the live fleet/state.
#
# Covers:
#   (a) a MERGED PR whose branch matches a ticket -> done.sh runs -> state/done/<id> with merged:<sha>.
#   (b) a ticket NOT in the merged list is left OPEN.
#   (c) HIGH #2: a merged PR whose branch does NOT match any ticket but whose files OVERLAP a
#       ticket's owns -> that ticket is auto-closed (branch-drift tolerant).
#   (d) a merged branch mapping to NO ticket is ignored (no crash, exit 0).
#   (e) idempotent second run: exit 0, prior closes unchanged.
# Reverting the owns-overlap mapping leaves TICK-C un-done -> (c) fails. Reverting the reconcile loop
# leaves TICK-A un-done -> (a) fails.
#
# Run:  bash fleet/tests/reconcile-merged.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# isolated product repo with an origin/master ref so `merge-base --is-ancestor <sha> origin/master`
# resolves offline.
P="$(mktemp -d)"
git -C "$P" init -q
git -C "$P" commit -q --allow-empty -m base
SHA="$(git -C "$P" rev-parse HEAD)"
git -C "$P" update-ref refs/remotes/origin/master "$SHA"

d="$(mktemp -d)"
cp "$SRC/reconcile-merged.sh" "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" \
   "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$d/"
mkdir -p "$d/board/archive" "$d/state/done" "$d/state/submitted" "$d/state/claims" "$d/state/needs-push"
printf 'tier: economy\nbranch: feat/tick-a\nowns: src/a.py\nwork_class: docs\n' > "$d/board/TICK-A.md"
printf 'tier: economy\nbranch: feat/tick-b\nowns: src/b.py\nwork_class: docs\n' > "$d/board/TICK-B.md"
# TICK-C: its real merge landed on a DIFFERENT branch than its board meta (drift) — must map by owns.
printf 'tier: economy\nbranch: feat/tick-c-planned\nowns: src/c.py\nwork_class: docs\n' > "$d/board/TICK-C.md"

# merged-PR fixture: TSV branch\tsha\tfiles\tpr
{
  printf 'feat/tick-a\t%s\tsrc/a.py\t101\n' "$SHA"          # (a) branch match
  printf 'feat/DRIFTED-NAME\t%s\tsrc/c.py\t103\n' "$SHA"    # (c) owns overlap, branch mismatch
  printf 'feat/orphan-none\t%s\tsrc/zzz.py\t109\n' "$SHA"   # (d) maps to nothing
} > "$d/merged.tsv"

export DONE_CHARON_REPO="$P" VERIFY_MERGED_REPO="$P" RECONCILE_REPO_SLUG="x/y"
run_reconcile(){ RECONCILE_MERGED_SRC="$d/merged.tsv" bash "$d/reconcile-merged.sh" >/dev/null 2>&1; }

run_reconcile
# (a)
if [ -e "$d/state/done/TICK-A" ]; then ok "a merged TICK-A auto-closed"; else bad "a merged TICK-A auto-closed"; fi
grep -q "merged:$SHA" "$d/state/done/TICK-A" 2>/dev/null && ok "a marker carries merged:<sha> proof" \
                                                         || bad "a marker carries merged:<sha> proof"
# (b)
[ -e "$d/state/done/TICK-B" ] && bad "b non-merged TICK-B left OPEN" || ok "b non-merged TICK-B left OPEN"
# (c) HIGH #2: owns-overlap mapping despite branch-name mismatch
[ -e "$d/state/done/TICK-C" ] && ok "c owns-overlap mapped a drifted-branch merge -> TICK-C closed" \
                              || bad "c owns-overlap mapped a drifted-branch merge -> TICK-C closed"
# (d) orphan branch ignored, exit 0
rc=0; run_reconcile || rc=$?
[ "$rc" = 0 ] && ok "d orphan merged branch ignored (exit 0)" || bad "d orphan merged branch ignored (exit 0, got $rc)"
# (e) idempotent
rc=0; run_reconcile || rc=$?
[ "$rc" = 0 ] && ok "e second run idempotent (exit 0)" || bad "e second run idempotent (exit 0, got $rc)"
[ -e "$d/state/done/TICK-A" ] && ok "e TICK-A stays done" || bad "e TICK-A stays done"
[ -e "$d/state/done/TICK-B" ] && bad "e TICK-B stays open" || ok "e TICK-B stays open"

rm -rf "$d" "$P"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL RECONCILE-MERGED TESTS PASS"
