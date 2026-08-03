#!/usr/bin/env bash
# preserve-unpushed.test.sh — FAIL-ON-REVERT tests for FRONTIER-TAB-DEATH (2026-08-01).
#
# THE DEFECT (measured, five frontier tabs in one session). A droid COMMITS its work, the tab ends
# early, and the EXIT trap `cleanup()` in fleet-droid.sh reaches `safe_worktree_remove`, which
# refuses:
#     leak-guard: REFUSING to remove <wt> — 1 commit(s) on HEAD are not on any remote (unpushed
#     work). Nothing removed; resolve by hand.
# That refusal is CORRECT and is deliberately left alone. The defect is that nothing ever PUBLISHED
# the branch, so the launcher manufactured stranded work and a human had to rescue the commits.
#
# The fix is ORDERING: publish the branch before the guard is consulted, using the mechanisms that
# already exist (a `state/needs-push/<id>` marker, `git push -u origin <branch>`, and
# `fleet/land-needs-push.sh` as the recovery path).
#
# These tests run the REAL fleet/preserve-unpushed.sh and the REAL `cleanup()` body extracted out of
# fleet/fleet-droid.sh against REAL git fixtures. They do not re-implement either. Deleting the
# preserve step, moving it after `safe_worktree_remove`, or letting it clear the marker without a
# successful publish all turn them red.
#
# Run:  bash fleet/tests/preserve-unpushed.test.sh   (exit 0 = all pass, 1 = a failure)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$SRC/fleet-droid.sh"
PRESERVE="$SRC/preserve-unpushed.sh"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

[ -r "$LAUNCHER" ] || { echo "FAIL: cannot read $LAUNCHER"; exit 1; }
[ -r "$PRESERVE" ] || { echo "FAIL: cannot read $PRESERVE — the preserve step is GONE"; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

SBOX="$TMP/fleetbox"; mkdir -p "$SBOX/state/needs-push"
for _f in preserve-unpushed.sh leak-guard.sh release.sh _lib.sh droid-bridge.sh; do
  [ -e "$SRC/$_f" ] && ln -sf "$SRC/$_f" "$SBOX/$_f"
done

fixture(){
  local n="$1"
  local noremote="${2:-}"
  local d="$TMP/$n"
  rm -rf "$d"; mkdir -p "$d"
  git init -q --bare "$d/remote.git"
  git init -q "$d/repo"
  git -C "$d/repo" config user.email t@t; git -C "$d/repo" config user.name test
  git -C "$d/repo" commit -q --allow-empty -m base
  git -C "$d/repo" branch -M master
  if [ "$noremote" = --no-remote ]; then
    git -C "$d/repo" remote add origin "$d/nonexistent.git"
  else
    git -C "$d/repo" remote add origin "$d/remote.git"
    git -C "$d/repo" push -q origin master
  fi
  git -C "$d/repo" fetch -q origin 2>/dev/null
  git -C "$d/repo" worktree add -q "$d/wt" -b feat/work >/dev/null 2>&1
  git -C "$d/wt" config user.email t@t; git -C "$d/wt" config user.name test
  git -C "$d/wt" commit -q --allow-empty -m "droid work (committed, never pushed)"
  mkdir -p "$d/fleetstate/needs-push"
}
unpushed_count(){ git -C "$1" rev-list --count HEAD --not --remotes 2>/dev/null; }

echo "== (1) committed-but-unpushed work is PUBLISHED before cleanup =="
fixture f1
check "1a fixture really has unpushed work" "$(unpushed_count "$TMP/f1/wt")" "1"
bash "$PRESERVE" "$TMP/f1/repo" "$TMP/f1/wt" feat/work TICKET "$TMP/f1/fleetstate/needs-push" >/dev/null 2>&1; rc1=$?
check "1b preserve reports safe-to-clean (exit 0)" "$rc1" "0"
check "1c the commits are now on a remote" "$(unpushed_count "$TMP/f1/wt")" "0"
check "1d the branch exists on the remote" \
  "$(git -C "$TMP/f1/remote.git" rev-parse --verify -q refs/heads/feat/work >/dev/null 2>&1 && echo yes || echo no)" "yes"
check "1e the needs-push marker is cleared once published" \
  "$([ -e "$TMP/f1/fleetstate/needs-push/TICKET" ] && echo present || echo absent)" "absent"

echo "== (2) after publishing, leak-guard no longer has to refuse =="
source "$SRC/leak-guard.sh"
rm -rf "$TMP/f1/needs-push-empty"; mkdir -p "$TMP/f1/needs-push-empty"
safe_worktree_remove "$TMP/f1/repo" "$TMP/f1/wt" TICKET "$TMP/f1/needs-push-empty" >/dev/null 2>&1; rc2=$?
check "2a safe_worktree_remove now ALLOWS removal (exit 0)" "$rc2" "0"
check "2b the worktree is gone" "$([ -d "$TMP/f1/wt" ] && echo present || echo absent)" "absent"

echo "== (3) an UNPUBLISHABLE branch keeps the marker and keeps the work =="
fixture f3 --no-remote
before3="$(unpushed_count "$TMP/f3/wt")"
out3="$(bash "$PRESERVE" "$TMP/f3/repo" "$TMP/f3/wt" feat/work TICKET "$TMP/f3/fleetstate/needs-push" 2>&1)"; rc3=$?
check "3a preserve refuses to declare it safe (exit 1)" "$rc3" "1"
check "3b the needs-push marker is LIVE" \
  "$([ -e "$TMP/f3/fleetstate/needs-push/TICKET" ] && echo present || echo absent)" "present"
check "3c the work is still on disk, unchanged" "$(unpushed_count "$TMP/f3/wt")" "$before3"
check "3d it names the existing recovery path" \
  "$(printf '%s' "$out3" | grep -c 'land-needs-push.sh TICKET')" "1"
check "3e the live marker makes leak-guard refuse (work is protected)" \
  "$(safe_worktree_remove "$TMP/f3/repo" "$TMP/f3/wt" TICKET "$TMP/f3/fleetstate/needs-push" >/dev/null 2>&1; echo $?)" "2"

echo "== (4) a fully-published branch is a no-op, and mints NO marker =="
fixture f4
git -C "$TMP/f4/wt" push -q -u origin feat/work 2>/dev/null
bash "$PRESERVE" "$TMP/f4/repo" "$TMP/f4/wt" feat/work TICKET "$TMP/f4/fleetstate/needs-push" >/dev/null 2>&1; rc4=$?
check "4a exit 0 with nothing to do" "$rc4" "0"
check "4b no spurious needs-push marker" \
  "$([ -e "$TMP/f4/fleetstate/needs-push/TICKET" ] && echo present || echo absent)" "absent"

echo "== (5) the REAL cleanup() publishes before it removes (ordering) =="
fixture f5
cleanup_body="$(awk '/^cleanup\(\)\{/{f=1} f{print} f&&/^\}/{exit}' "$LAUNCHER")"
[ -n "$cleanup_body" ] || bad "5-setup could not extract cleanup() from $LAUNCHER"
cat > "$TMP/f5/run.sh" <<EOF
set -euo pipefail
FLEET="$SBOX"
source "\$FLEET/leak-guard.sh"
DROID=frontier-test; REPO="$TMP/f5/repo"; wt="$TMP/f5/wt"
current=TICKET; branch=feat/work; PUSH_MODE=off
$cleanup_body
cleanup
EOF
( cd "$TMP/f5" && bash "$TMP/f5/run.sh" ) >"$TMP/f5/out" 2>&1; rc5=$?
check "5a cleanup() itself does not fault" "$rc5" "0"
check "5b cleanup() PUBLISHED the branch to the remote" \
  "$(git -C "$TMP/f5/remote.git" rev-parse --verify -q refs/heads/feat/work >/dev/null 2>&1 && echo yes || echo no)" "yes"
check "5c the published sha is the droid's commit" \
  "$(git -C "$TMP/f5/remote.git" rev-parse refs/heads/feat/work 2>/dev/null)" \
  "$(git -C "$TMP/f5/repo" rev-parse refs/heads/feat/work 2>/dev/null)"

echo "== (6) the AUTO-COMMIT shape: a droid that never committed at all =="
fixture f6
echo "half-done work the droid never committed" > "$TMP/f6/wt/WIP.txt"
git -C "$TMP/f6/wt" add WIP.txt
before6="$(git -C "$TMP/f6/repo" rev-parse refs/heads/feat/work)"
cat > "$TMP/f6/run.sh" <<EOF
set -euo pipefail
FLEET="$SBOX"
source "\$FLEET/leak-guard.sh"
DROID=strong-test; REPO="$TMP/f6/repo"; wt="$TMP/f6/wt"
current=TICKET; branch=feat/work; PUSH_MODE=off
$cleanup_body
cleanup
EOF
( cd "$TMP/f6" && bash "$TMP/f6/run.sh" ) >"$TMP/f6/out" 2>&1
check "6a cleanup() auto-committed the uncommitted work" \
  "$([ "$(git -C "$TMP/f6/repo" rev-parse refs/heads/feat/work)" != "$before6" ] && echo yes || echo no)" "yes"
check "6b the auto-commit reached the remote (not stranded)" \
  "$(git -C "$TMP/f6/remote.git" rev-parse refs/heads/feat/work 2>/dev/null)" \
  "$(git -C "$TMP/f6/repo" rev-parse refs/heads/feat/work 2>/dev/null)"
check "6c the auto-committed file is IN the published commit" \
  "$(git -C "$TMP/f6/repo" show --name-only --pretty=format: refs/heads/feat/work 2>/dev/null | grep -c '^WIP.txt$')" "1"
check "6d no needs-push marker is left behind once published" \
  "$([ -e "$SBOX/state/needs-push/TICKET" ] && echo present || echo absent)" "absent"

echo
echo "== preserve-unpushed: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
