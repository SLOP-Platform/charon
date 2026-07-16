#!/usr/bin/env bash
# reconcile-held-markers.test.sh — FAIL-ON-REVERT tests for the HELD-marker backfill
# (fleet/reconcile-held-markers.sh). Runs entirely OFFLINE via the RECONCILE_HELD_SRC fixture
# hook against an ISOLATED product git repo (no gh / no network) and an ISOLATED board.
# NEVER touches the live fleet/state.
#
# Covers (fail-on-revert):
#   (a) a HELD marker whose (repo, branch) is in the merged-PR fixture -> backfilled with
#       `merged:<sha>`, the sha is an ancestor of origin/master -> verify_merged returns 0
#       OFFLINE (the fast local path; no gh call) -> retire-done will now archive it.
#   (b) a HELD marker with no merged PR in the fixture -> stays HELD, NO rewrite, and is
#       LISTED in the needs-action output (not silently archived — matches retire-done G3c).
#   (c) a marker that ALREADY carries `merged:<sha>` (verified) -> SKIPPED (idempotent).
#   (d) a marker that carries `merged:#<pr>` (PR-number proof only) -> HELD; if the (repo,
#       branch) has a sha, the marker is UPGRADED to `merged:<sha>` so verify_merged's local
#       ancestor path takes over (the whole reason this script exists).
#   (e) a marker for an UNKNOWN repo (no slug map) -> listed, not backfilled, not archived.
#   (f) BATCHED lookup: N markers across R repos must result in <= R queries, not N (the
#       O(markers * network) -> O(repos) trap). Verified by routing `gh` through a stub
#       that records each invocation.
#
# Run:  bash fleet/tests/reconcile-held-markers.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# ---- isolated product repo (charon default), with origin/master ref so sha-ancestry resolves ----
P="$(mktemp -d)"
git -C "$P" init -q
mkdir -p "$P/src"; echo x > "$P/src/present.py"
git -C "$P" add -A; git -C "$P" commit -q -m base
SHA="$(git -C "$P" rev-parse HEAD)"
git -C "$P" update-ref refs/remotes/origin/master "$SHA"

# second repo, just for the cross-repo batched-lookup test (a different origin/master ref
# proves the per-repo fan-out). The real script derives the slug from `repo:` so we mock by
# routing the charon-private slugs through this same repo and asserting the fixture is
# consulted PER distinct repo, not per marker.
P2="$(mktemp -d)"
git -C "$P2" init -q
echo y > "$P2/rig.md"
git -C "$P2" add -A; git -C "$P2" commit -q -m rig-base
SHA2="$(git -C "$P2" rev-parse HEAD)"
git -C "$P2" update-ref refs/remotes/origin/master "$SHA2"

d="$(mktemp -d)"
cp "$SRC/reconcile-held-markers.sh" "$d/"

# ---------------- fixture (a)(b)(c)(d)(e): product-repo markers ----------------
mkdir -p "$d/board/archive" "$d/state/done"
# TICK-A: HELD (date only, no merged line at all) -> branch is in fixture -> should be backfilled
printf 'tier: strong\ndifficulty: 3\nwork_class: rig-meta\nbranch: feat/tick-a\nrepo: charon\n' \
  > "$d/board/TICK-A.md"
printf '2026-07-10T00:00:00Z\n' > "$d/state/done/TICK-A"
# TICK-B: HELD (date only) -> branch is NOT in fixture -> should stay HELD + listed
printf 'tier: strong\ndifficulty: 3\nwork_class: rig-meta\nbranch: feat/tick-b-never-merged\nrepo: charon\n' \
  > "$d/board/TICK-B.md"
printf '2026-07-10T00:00:00Z\n' > "$d/state/done/TICK-B"
# TICK-C: ALREADY has merged:<sha> -> SKIPPED (idempotent), line untouched
printf 'tier: strong\ndifficulty: 3\nwork_class: rig-meta\nbranch: feat/tick-c\nrepo: charon\n' \
  > "$d/board/TICK-C.md"
printf '2026-07-10T00:00:00Z\tmerged:%s\tbranch:feat/tick-c\n' "$SHA" > "$d/state/done/TICK-C"
# TICK-D: HELD with `merged:#101` (PR-number proof only) -> branch in fixture -> UPGRADED to merged:<sha>
printf 'tier: strong\ndifficulty: 3\nwork_class: rig-meta\nbranch: feat/tick-d\nrepo: charon\n' \
  > "$d/board/TICK-D.md"
printf '2026-07-10T00:00:00Z\tmerged:#101\tbranch:feat/tick-d\n' > "$d/state/done/TICK-D"
# TICK-E: HELD with no merged line + UNKNOWN repo -> listed as needs-action (no slug map)
printf 'tier: strong\ndifficulty: 3\nwork_class: rig-meta\nbranch: feat/tick-e\nrepo: zorkmid\n' \
  > "$d/board/TICK-E.md"
printf '2026-07-10T00:00:00Z\n' > "$d/state/done/TICK-E"

# merged-PR fixture: repo\tbranch\tsha
{
  printf 'charon\tfeat/tick-a\t%s\n' "$SHA"   # (a) HELD -> backfilled
  printf 'charon\tfeat/tick-d\t%s\n' "$SHA"   # (d) PR-only -> upgraded to sha
} > "$d/merged.tsv"

export RECONCILE_HELD_SRC="$d/merged.tsv"
export RECONCILE_HELD_DONE_DIR="$d/state/done" RECONCILE_HELD_BOARD_DIR="$d/board"
out="$(bash "$d/reconcile-held-markers.sh" 2>&1)"; rc=$?
check "exit 0 on success" "$rc" "0"

# (a) TICK-A: backfilled with merged:<sha>; line still starts with the original date
grep -q "^2026-07-10T00:00:00Z	merged:$SHA	branch:feat/tick-a$" "$d/state/done/TICK-A" \
  && ok "a TICK-A marker rewritten with merged:<sha>" \
  || bad "a TICK-A marker rewritten with merged:<sha> (got: $(cat "$d/state/done/TICK-A"))"
# (a) verify_merged now returns 0 OFFLINE (no gh) — the whole reason this script exists
export FLEET="$d" VERIFY_MERGED_REPO="$P"
# shellcheck source=/dev/null
source "$SRC/_lib.sh"
verify_merged TICK-A && ok "a verify_merged TICK-A passes OFFLINE after backfill" \
                     || bad "a verify_merged TICK-A passes OFFLINE after backfill"
# (b) TICK-B: untouched, still date-only
[ "$(cat "$d/state/done/TICK-B")" = "2026-07-10T00:00:00Z" ] \
  && ok "b TICK-B marker UNCHANGED (no merged PR)" \
  || bad "b TICK-B marker UNCHANGED (got: $(cat "$d/state/done/TICK-B"))"
# (b) TICK-B appears in the needs-action list
printf '%s' "$out" | grep -q "TICK-B" && ok "b TICK-B listed as needs-action" \
                                   || bad "b TICK-B listed as needs-action"
# (c) TICK-C: untouched (idempotent on already-merged:<sha>)
[ "$(cat "$d/state/done/TICK-C")" = "2026-07-10T00:00:00Z	merged:$SHA	branch:feat/tick-c" ] \
  && ok "c TICK-C (already merged:<sha>) left UNCHANGED (idempotent)" \
  || bad "c TICK-C (already merged:<sha>) left UNCHANGED (got: $(cat "$d/state/done/TICK-C"))"
# (d) TICK-D: upgraded from merged:#101 to merged:<sha>
grep -q "^2026-07-10T00:00:00Z	merged:$SHA	branch:feat/tick-d$" "$d/state/done/TICK-D" \
  && ok "d TICK-D upgraded from merged:#101 to merged:<sha>" \
  || bad "d TICK-D upgraded from merged:#101 to merged:<sha> (got: $(cat "$d/state/done/TICK-D"))"
# (e) TICK-E: unknown repo, listed not backfilled
[ "$(cat "$d/state/done/TICK-E")" = "2026-07-10T00:00:00Z" ] \
  && ok "e TICK-E (unknown repo) UNCHANGED" \
  || bad "e TICK-E (unknown repo) UNCHANGED (got: $(cat "$d/state/done/TICK-E"))"
printf '%s' "$out" | grep -q "TICK-E" && ok "e TICK-E listed as needs-action" \
                                   || bad "e TICK-E listed as needs-action"
unset FLEET VERIFY_MERGED_REPO RECONCILE_HELD_SRC RECONCILE_HELD_DONE_DIR RECONCILE_HELD_BOARD_DIR 2>/dev/null || true

# ---------------- (f) BATCHED lookup: assert <= R gh invocations for N markers across R repos ----
# N markers split between 2 repos (charon, charon-private) -> the script MUST make at most 2
# gh calls (one per distinct repo), not N. The O(markers * network) trap is the regression
# class this ticket pairs with DONE-SH-REPO-AWARE / RECONCILE-MERGED-PERF.
# Critically: do NOT pass RECONCILE_HELD_SRC here — that would short-circuit to the fixture
# path and the stub would never be invoked. An unset env var forces the real gh path.
echo "== (f) batched lookup: stub gh, count invocations =="
BD="$(mktemp -d)"
cp "$SRC/reconcile-held-markers.sh" "$BD/"
mkdir -p "$BD/board" "$BD/state/done"
# 5 markers in charon + 5 markers in charon-private
i=0
while [ "$i" -lt 5 ]; do
  i=$((i+1))
  printf 'tier: strong\nbranch: feat/c-%d\nrepo: charon\n' "$i" > "$BD/board/TICK-C$i.md"
  printf '2026-07-10T00:00:00Z\n' > "$BD/state/done/TICK-C$i"
  printf 'tier: strong\nbranch: feat/p-%d\nrepo: charon-private\n' "$i" > "$BD/board/TICK-P$i.md"
  printf '2026-07-10T00:00:00Z\n' > "$BD/state/done/TICK-P$i"
done

# gh stub: record each invocation to a fixed log path (the stub runs in a clean env so we
# cannot rely on the test process's STUB_LOG var being inherited). Emit empty TSV so the
# script's marker-upgrade phase reports needs-action (we are only asserting CALL COUNT here).
STUB_DIR="$(mktemp -d)"
STUB_LOG="/tmp/reconcile-held-gh-stub.log"
cat > "$STUB_DIR/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> /tmp/reconcile-held-gh-stub.log
exit 0
EOF
chmod +x "$STUB_DIR/gh"
rm -f "$STUB_LOG"

# Make absolutely sure the stub wins: prepend its dir to PATH (bash's lookup cache
# will be re-resolved at each new `bash` invocation). The script's `command -v gh` is what
# gates the gh path, so the stub must be findable on PATH at that point.
PATH="$STUB_DIR:$PATH" \
  RECONCILE_HELD_DONE_DIR="$BD/state/done" RECONCILE_HELD_BOARD_DIR="$BD/board" \
  bash "$BD/reconcile-held-markers.sh" >/dev/null 2>&1
# Count distinct --repo <slug> invocations (not total args).
invocations="$(grep -c '^pr list' "$STUB_LOG" 2>/dev/null || echo 0)"
# (1) CORRECTNESS: 2 distinct repos -> exactly 2 gh calls (not 0 = stub never invoked, not 10
#     = per-marker antipattern regressed). The exact-equality assertion makes the test
#     FAIL if EITHER direction breaks.
check "f gh called exactly 2 times (one per distinct repo), got $invocations" \
  "$( [ "$invocations" -eq 2 ] && echo yes || echo no )" "yes"
# (2) REGRESSION GUARD (separate from (1)): gh MUST NOT be called per-marker. If a future
#     refactor reintroduces the O(markers * network) trap, this assertion fails first.
check "f gh NOT called per-marker (regression guard), got $invocations" \
  "$( [ "$invocations" -lt 10 ] && echo yes || echo no )" "yes"

# Cleanup
rm -f "$STUB_LOG"

rm -rf "$BD" "$STUB_DIR"
rm -rf "$d" "$P" "$P2"

# ---------------- (g) no board file at all (orphan marker) ----------------
# A HELD marker with NO board file (board/<id>.md AND board/archive/<id>.md both missing) must
# still be processable: default repo=charon, branch=n/a, list as needs-action. Reverting the
# `repo=""; branch=""` initialization makes this fail under `set -u` (unbound variable).
echo "== (g) orphan marker: no board file =="
OD="$(mktemp -d)"
cp "$SRC/reconcile-held-markers.sh" "$OD/"
mkdir -p "$OD/state/done" "$OD/board"
printf '2026-07-10T00:00:00Z\n' > "$OD/state/done/ORPHAN"
rc=0; bash "$OD/reconcile-held-markers.sh" >/dev/null 2>&1 || rc=$?
check "g orphan marker processed without error (exit 0)" "$rc" "0"
[ "$(cat "$OD/state/done/ORPHAN")" = "2026-07-10T00:00:00Z" ] \
  && ok "g orphan marker UNCHANGED (no merged PR found)" \
  || bad "g orphan marker UNCHANGED (got: $(cat "$OD/state/done/ORPHAN"))"
rm -rf "$OD"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL RECONCILE-HELD-MARKERS TESTS PASS"
