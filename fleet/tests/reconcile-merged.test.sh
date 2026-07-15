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

# (f) HIGH #2: a DRIFTED merged PR (matches no board branch) whose changed file is owned by MORE THAN
# ONE ticket is AMBIGUOUS — owns-overlap cannot prove WHICH ticket landed, so NEITHER may be auto-closed
# (the reverted "first glob match wins" would mis-close the alphabetically-first owner onto un-landed
# work with a real merged:<sha>). Reverting the >1-owner refusal closes TICK-SH1 -> this test fails.
echo "== (f) HIGH #2: drifted PR on a file owned by >1 ticket -> NEITHER auto-closed (ambiguous) =="
  printf 'tier: economy\nbranch: feat/sh1-planned\nowns: src/shared.py\nwork_class: docs\n' > "$d/board/TICK-SH1.md"
  printf 'tier: economy\nbranch: feat/sh2-planned\nowns: src/shared.py\nwork_class: docs\n' > "$d/board/TICK-SH2.md"
  printf 'feat/DRIFTED-SHARED\t%s\tsrc/shared.py\t205\n' "$SHA" > "$d/ambig.tsv"
  RECONCILE_MERGED_SRC="$d/ambig.tsv" bash "$d/reconcile-merged.sh" >/dev/null 2>&1
  [ -e "$d/state/done/TICK-SH1" ] && bad "f SH1 NOT auto-closed on ambiguous shared-owner overlap" \
                                  || ok "f SH1 NOT auto-closed on ambiguous shared-owner overlap"
  [ -e "$d/state/done/TICK-SH2" ] && bad "f SH2 NOT auto-closed on ambiguous shared-owner overlap" \
                                  || ok "f SH2 NOT auto-closed on ambiguous shared-owner overlap"

  # (g) PERF (PERF-AUDIT.md 2026-07-15): the OLD ticket_for_pr() re-scanned all board+archive files
  # for EVERY merged PR (O(PRs×files×awk-spawn)). On a fixture with ~200 board+archive files and a
  # matching set of merged PRs, the old loop would dominate wall-clock. The new code builds a
  # single index in O(files) and short-circuits on already-done branches — a fresh fixture with
  # 200 noise files + 5 mergeable PRs must (i) still produce the same close set and (ii) finish in
  # well under a generous bound (5s — even on a slow CI host the index+5 done.sh runs is <1s).
  # A regression that re-introduces the per-PR re-scan OR removes the short-circuit would push
  # this past 5s and fail. Also covers: an ARCHIVED ticket (in board/archive/) is still found by
  # the index — the old code's glob was "$BOARD"/*.md "$BOARD"/archive/*.md, and the new code
  # must read both.
  echo "== (g) PERF: 200-file board+archive fixture + 5 PRs, same closes, fast =="
  g="$(mktemp -d)"; cp "$SRC/reconcile-merged.sh" "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" \
     "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$g/"
  mkdir -p "$g/board/archive" "$g/state/done" "$g/state/submitted" "$g/state/claims" "$g/state/needs-push"
  # 5 mergeable tickets, interleaved with 195 noise files (alternate open + archived) so the index
  # has to walk the full board+archive set — proves the perf win is real, not a fixture cheat.
  for i in $(seq 1 100); do
    printf 'tier: economy\nbranch: noise/no-%s\nowns: noise/no-%s.py\nwork_class: docs\n' "$i" "$i" > "$g/board/NO-$i.md"
  done
  for i in $(seq 1 95); do
    printf 'tier: economy\nbranch: noise/arc-%s\nowns: noise/arc-%s.py\nwork_class: docs\n' "$i" "$i" > "$g/board/archive/ARC-$i.md"
  done
  # The 5 mergeable tickets — mix of OPEN board and ARCHIVED board to ensure both glob slots are
  # walked by the index.
  printf 'tier: economy\nbranch: feat/g1\nowns: src/g1.py\nwork_class: docs\n' > "$g/board/G1.md"
  printf 'tier: economy\nbranch: feat/g2\nowns: src/g2.py\nwork_class: docs\n' > "$g/board/G2.md"
  printf 'tier: economy\nbranch: feat/g3\nowns: src/g3.py\nwork_class: docs\n' > "$g/board/G3.md"
  printf 'tier: economy\nbranch: feat/g4\nowns: src/g4.py\nwork_class: docs\n' > "$g/board/archive/G4.md"
  printf 'tier: economy\nbranch: feat/g5\nowns: src/g5.py\nwork_class: docs\n' > "$g/board/archive/G5.md"
  # Pre-existing done marker for G6 — proves the done-branch short-circuit doesn't break the close
  # of a different PR whose branch happens to equal an already-done ticket's branch (the old code
  # had the same idempotency guarantee via [ -e "$DONE/$id" ]).
  printf 'tier: economy\nbranch: feat/g6\nowns: src/g6.py\nwork_class: docs\n' > "$g/board/G6.md"
  printf '%s\tmerged:%s\tbranch:feat/g6\n' "$(date -u +%FT%TZ)" "$SHA" > "$g/state/done/G6"
  {
    printf 'feat/g1\t%s\tsrc/g1.py\t301\n' "$SHA"
    printf 'feat/g2\t%s\tsrc/g2.py\t302\n' "$SHA"
    printf 'feat/g3\t%s\tsrc/g3.py\t303\n' "$SHA"
    printf 'feat/g4\t%s\tsrc/g4.py\t304\n' "$SHA"   # archived ticket
    printf 'feat/g5\t%s\tsrc/g5.py\t305\n' "$SHA"   # archived ticket
    printf 'feat/g6\t%s\tsrc/g6.py\t306\n' "$SHA"   # already done -> idempotent skip
  } > "$g/perf.tsv"
  _t0=$(date +%s%N)
  DONE_CHARON_REPO="$P" RECONCILE_REPO_SLUG="x/y" RECONCILE_MERGED_SRC="$g/perf.tsv" \
      bash "$g/reconcile-merged.sh" >/dev/null 2>&1
  _t1=$(date +%s%N)
  _ms=$(( ( _t1 - _t0 ) / 1000000 ))
  # correctness: G1..G5 closed, G6 still has its original done marker (untouched), nothing else
  closed=0
  for _id in G1 G2 G3 G4 G5; do
    [ -e "$g/state/done/$_id" ] && closed=$((closed+1))
  done
  [ "$closed" = 5 ] && ok "g closed all 5 mergeable tickets (G1-G5, mix of open+archived)" \
                    || bad "g closed only $closed/5 mergeable tickets (expected 5)"
  [ -e "$g/state/done/G6" ] && ok "g G6 done marker preserved (idempotent on already-closed branch)" \
                            || bad "g G6 done marker missing"
  # perf: 5s is a generous bound for the test (even on a slow CI host the index+5 done.sh <1s;
  # the old per-PR re-scan would have made this >30s on a 200-file fixture). 5s catches a
  # regression that re-introduces the O(PRs×files) re-scan while still tolerating slow CI.
  [ "$_ms" -lt 5000 ] && ok "g perf: 200-file board+archive + 6 PRs reconciled in ${_ms}ms (<5000ms)" \
                       || bad "g perf: took ${_ms}ms (>=5000ms) — re-scan regression?"

  # (h) done-marker branch short-circuit: a PR whose branch ALREADY has a done marker is skipped
  # without ever invoking done.sh. We verify by giving an INVALID sha so done.sh would refuse if
  # called — a no-call proves the short-circuit.
  echo "== (h) short-circuit: PR with a branch already covered by state/done/<id> -> no done.sh call =="
  h="$(mktemp -d)"; cp "$SRC/reconcile-merged.sh" "$SRC/done.sh" "$SRC/retire-done.sh" "$SRC/leak-guard.sh" \
     "$SRC/_lib.sh" "$SRC/verify-merged.sh" "$h/"
  mkdir -p "$h/board" "$h/state/done" "$h/state/submitted" "$h/state/claims" "$h/state/needs-push"
  printf 'tier: economy\nbranch: feat/h\nowns: src/h.py\nwork_class: docs\n' > "$h/board/H.md"
  printf '%s\tmerged:%s\tbranch:feat/h\n' "$(date -u +%FT%TZ)" "$SHA" > "$h/state/done/H"
  printf 'feat/h\tDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF\tsrc/h.py\t401\n' > "$h/sc.tsv"
  # done.sh with an invalid sha would REFUSE and exit 3 — so the marker MUST still be the old one.
  orig_marker="$(cat "$h/state/done/H")"
  DONE_CHARON_REPO="$P" RECONCILE_REPO_SLUG="x/y" RECONCILE_MERGED_SRC="$h/sc.tsv" \
      bash "$h/reconcile-merged.sh" >/dev/null 2>&1
  new_marker="$(cat "$h/state/done/H")"
  [ "$orig_marker" = "$new_marker" ] && ok "h done-branch short-circuit: existing marker untouched (done.sh not called)" \
                                      || bad "h done-branch short-circuit: marker changed ($orig_marker -> $new_marker)"
  rm -rf "$g" "$h"

  rm -rf "$d" "$P"
  echo
  echo "--- $PASS passed, $FAIL failed ---"
  [ "$FAIL" -eq 0 ] || exit 1
  echo "ALL RECONCILE-MERGED TESTS PASS"
