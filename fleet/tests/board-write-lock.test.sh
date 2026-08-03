#!/usr/bin/env bash
# board-write-lock.test.sh — FAIL-ON-REVERT tests for the BOARD-WRITE LOCK.
#
# THE LOSSES THIS CLOSES (2026-07-24, both real, both same day):
#   (a) a sub's bare `git commit` swept another lane's staged `git mv board/X.md
#       board/archive/X.md` out of the SHARED main-checkout index — a bare `git commit` takes the
#       WHOLE index, not just the paths the caller `git add`ed;
#   (b) master moved (rebase) under a live sub and its uncommitted work was stashed+dropped.
# Board serialisation was an UNENFORCED CONVENTION ("you are the only board writer"). It failed.
#
# WHAT IS PROVEN (each assertion names the revert that turns it RED):
#   1 ENFORCEMENT — the pre-commit hook REFUSES a bare `git add`+`git commit` on a board path
#     (exit 4), and ALLOWS the same commit through `board-lock.sh commit`.
#     Revert: `cmd_pre_commit(){ return 0; }`, or drop the board-lock line from hooks/pre-commit.
#   2 PATHSPEC-LIMITED COMMIT — a FOREIGN staged path (another lane's staged rename) is NOT swept
#     into the board commit and is still staged afterwards, with its content intact.
#     Revert: `git commit --only -- "$@"` -> bare `git commit`.
#   3 TWO CONCURRENT WRITERS — the second writer is REFUSED (exit 1) while the first holds; the
#     LOSER neither corrupts nor silently loses content (its edit survives on disk, uncommitted).
#     Revert: drop the `[ -f "$HOLD" ]` conflict branch in _acquire_locked.
#   4 FAIL-CLOSED under a genuinely-held flock — with the SAME state/lock fd held by another
#     process, a commit REFUSES (exit 70) rather than proceeding unlocked.
#     Revert: replace `flock -w` with a bare `flock -n || true`.
#   5 MASTER MOVED UNDER ME — a commit whose pinned base != HEAD REFUSES (exit 3).
#     Revert: drop the base/HEAD comparison in _commit_locked.
#   6 STALE HOLD is bounded and LOUD, never silently stealable — a stale hold with a DEAD holder
#     is reclaimed with a loud banner (no deadlock); a stale hold with a LIVE holder is REFUSED
#     and needs an explicit `steal --force`.
#     Revert: auto-reclaim any stale hold regardless of holder liveness.
#   7 GUARDED SET — a NON-board path commits normally with no lock (the gate is scoped, not a
#     blanket commit ban). Revert: drop the `_is_board_path` filter.
#   8 MAIN-CHECKOUT ADVISORY — a board commit in the main checkout on master fires the advisory
#     (exit 7) and is refused, with the ergonomic worktree path printed.
#     Revert: drop the `_is_main_checkout` check in _commit_locked.
#   9 RETIRE_DONE_BYPASS — auto-admin archive moves bypass the advisory but still require the lock.
#     Revert: remove the RETIRE_DONE_BYPASS guard.
#   10 WORKTREE — a linked worktree (not the main checkout) is NOT refused.
#     Revert: change _is_main_checkout to always return 0.
#
# NO-LOCAL-MASTER-COMMITS TEST STRATEGY:
#   REPO (the bare repo directory) = main checkout (on master). It is the MAIN CHECKOUT so _is_main_checkout
#   returns true, and advisory fires. Tests 8-10 run from REPO directly.
#   WT (a linked worktree on a feature branch, NOT master) = the WORKTREE for tests 1-7. _is_main_checkout
#   returns false here, so the advisory does not fire and tests 1-7 pass normally.
#   Both REPO and WT share the same FLEET (via symlink or same $TMP/fleet path).
#
# Hermetic: the REAL fleet/board-lock.sh and the REAL fleet/hooks/pre-commit are copied verbatim
# into a temp FLEET (the CODE is the real code, never a transcription) and driven against a real
# git repo under mktemp -d. No network, no gh, ~2s.
set -uo pipefail

REAL_FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
ok()  { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ── hermetic FLEET carrying the REAL scripts ────────────────────────────────────────────────
FLEET="$TMP/fleet"
mkdir -p "$FLEET/hooks" "$FLEET/board" "$FLEET/state"
cp "$REAL_FLEET/board-lock.sh"    "$FLEET/board-lock.sh"
cp "$REAL_FLEET/hooks/pre-commit" "$FLEET/hooks/pre-commit"
# FIXTURE-DRIFT GUARD (2026-08-01): board-lock.sh parses frontmatter via checks/substrate_first_gate.py,
# which is FAIL-CLOSED on missing module. The fixture must carry the real dependency.
cp -r "$REAL_FLEET/checks" "$FLEET/checks"
chmod +x "$FLEET/board-lock.sh" "$FLEET/hooks/pre-commit"
BL="$FLEET/board-lock.sh"

# work-lease.sh is the hook's SECOND leg. Stub it to a pass so this suite isolates the BOARD leg
# (work-lease.test.sh owns proving the lease leg). The board leg still runs for real.
printf '#!/usr/bin/env bash\nexit 0\n' > "$FLEET/work-lease.sh"; chmod +x "$FLEET/work-lease.sh"

# ── REPO: the bare repo directory (shared git dir for all worktrees) ────────────────────
REPO="$TMP/repo"
mkdir -p "$REPO"
git -C "$REPO" init -q 2>/dev/null
git -C "$REPO" config user.email t@t; git -C "$REPO" config user.name t
git -C "$REPO" config commit.gpgsign false
git -C "$REPO" checkout -b master -q 2>/dev/null || git -C "$REPO" branch -m main master 2>/dev/null || true
# Hook: write an actual script (not a symlink to the real fleet) so it uses the TEST's FLEET.
# The real fleet/hooks/pre-commit resolves to the real fleet dir. A test-specific hook uses the TEST's FLEET.
# Use absolute path so it works from any location.
printf '#!/usr/bin/env bash\nset -uo pipefail\nexport FLEET="%s"\nexec bash "$FLEET/board-lock.sh" pre-commit\nexec bash "$FLEET/work-lease.sh" pre-commit\n' "$FLEET" > "$FLEET/hooks/pre-commit-test"
chmod +x "$FLEET/hooks/pre-commit-test"
# Install the test hook (not a symlink) in the shared git dir.
ln -sf "$FLEET/hooks/pre-commit-test" "$REPO/.git/hooks/pre-commit"

# ── MAIN CHECKOUT: worktree on master (IS a main checkout, fires advisory) ───────────────
MAIN="$TMP/main"
git -C "$REPO" worktree add -b master "$MAIN" -q 2>/dev/null || true
# Copy fleet files into MAIN worktree (board files must live in the worktree for git to track them).
mkdir -p "$MAIN/fleet/state" "$MAIN/fleet/board"
cp -r "$FLEET/checks" "$MAIN/fleet/checks"
printf '#!/usr/bin/env bash\nexit 0\n' > "$MAIN/fleet/work-lease.sh"; chmod +x "$MAIN/fleet/work-lease.sh"
# Copy board-lock.sh into the worktree's fleet so board-lock.sh resolves FLEET correctly.
cp "$REAL_FLEET/board-lock.sh" "$MAIN/fleet/board-lock.sh"
chmod +x "$MAIN/fleet/board-lock.sh"
printf 'id\tstatus\n' > "$MAIN/fleet/state/ROADMAP.tsv"
printf 'repo: charon\ntier: strong\nwork_class: docs\n' > "$MAIN/fleet/board/SEED.md"
printf 'lane-b original\n' > "$MAIN/other-lane.txt"
git -C "$REPO" add -A >/dev/null 2>&1
git -C "$REPO" -c core.hooksPath=/dev/null commit -q -m seed --no-verify
BASE_SHA="$(git -C "$REPO" rev-parse HEAD)"

# ── WT: linked worktree on a feature branch (NOT master, so advisory does NOT fire) ────────
WT="$TMP/wt"
git -C "$REPO" worktree add -b wt-board "$WT" -q 2>/dev/null || true
# Copy fleet files into WT as well.
mkdir -p "$WT/fleet/state" "$WT/fleet/board"
cp -r "$FLEET/checks" "$WT/fleet/checks"
cp "$REAL_FLEET/board-lock.sh" "$WT/fleet/board-lock.sh"
chmod +x "$WT/fleet/board-lock.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$WT/fleet/work-lease.sh"; chmod +x "$WT/fleet/work-lease.sh"
# Copy the seeded board files into WT (WT doesn't have them since we only added WT, not committed to it).
cp "$MAIN/fleet/state/ROADMAP.tsv" "$WT/fleet/state/ROADMAP.tsv"
cp "$MAIN/fleet/board/SEED.md" "$WT/fleet/board/SEED.md"
# Copy pre-commit hook into WT's .git/hooks (it shares the same git dir, but be safe).
mkdir -p "$WT/.git/hooks" 2>/dev/null || true
ln -sf "$FLEET/hooks/pre-commit" "$WT/.git/hooks/pre-commit" 2>/dev/null || true

# run() executes in WT (linked worktree, NOT main checkout — advisory does not fire).
# run_main() executes in MAIN (main checkout, IS main checkout — advisory fires).
# FLEET must be exported so the pre-commit hook (installed at $REPO) can find the WT's fleet state.
run(){ ( export FLEET="$WT/fleet"; cd "$WT"; "$@" ) >"$TMP/out" 2>"$TMP/err"; echo $?; }
run_main(){ ( export FLEET="$MAIN/fleet"; cd "$MAIN"; "$@" ) >"$TMP/out" 2>"$TMP/err"; echo $?; }
BL_WT="$WT/fleet/board-lock.sh"
BL_MAIN="$MAIN/fleet/board-lock.sh"
# Tests 1-7 run in WT, so use BL_WT.
BL="$BL_WT"

echo "== 1. ENFORCEMENT: an UNLOCKED board commit is refused; the locked one is allowed"
printf '# A edit\n' >> "$WT/fleet/board/SEED.md"
git -C "$WT" add fleet/board/SEED.md >/dev/null
rc="$(run git commit -q -m 'board-hygiene: sneak it in')"
# git reports its OWN 1 when a hook rejects, so assert git refused AND that the gate arm itself
# returns the documented 4.
[ "$rc" = "1" ] && ok "bare board commit REFUSED by the hook (git exit 1)" || bad "bare board commit not refused (exit $rc)"
grep -q 'BOARD-WRITE REFUSED' "$TMP/err" && ok "refusal is LOUD and names the fix" \
  || bad "refusal message missing (err: $(head -3 "$TMP/err"))"
rc="$(run bash "$BL" pre-commit)"
[ "$rc" = "4" ] && ok "the gate arm itself returns the documented exit 4" || bad "gate arm exit not 4 (got $rc)"
[ "$(git -C "$WT" rev-parse HEAD)" = "$BASE_SHA" ] && ok "nothing was committed" || bad "a commit slipped through"
grep -q 'A edit' "$WT/fleet/board/SEED.md" && ok "refused writer's content NOT lost" || bad "content lost on refusal"

rc="$(run bash "$BL" commit --session A -m 'board-hygiene: A' -- fleet/board/SEED.md)"
[ "$rc" = "0" ] && ok "board-lock.sh commit ALLOWED (exit 0)" || bad "locked commit refused (exit $rc): $(cat "$TMP/err")"
git -C "$WT" log -1 --format=%s | grep -q 'board-hygiene: A' && ok "the board commit landed" || bad "board commit missing"
A_SHA="$(git -C "$WT" rev-parse HEAD)"

echo "== 2. PATHSPEC-LIMITED: a FOREIGN staged path is not swept, and survives intact"
printf 'lane-b staged work\n' > "$WT/other-lane.txt"
git -C "$WT" add other-lane.txt >/dev/null
printf '# A edit 2\n' >> "$WT/fleet/board/SEED.md"
rc="$(run bash "$BL" commit --session A -m 'board-hygiene: A2' -- fleet/board/SEED.md)"
[ "$rc" = "0" ] && ok "scoped commit succeeded with a foreign path staged" || bad "scoped commit failed (exit $rc): $(cat "$TMP/err")"
files="$(git -C "$WT" show --name-only --format= HEAD)"
if echo "$files" | grep -q 'other-lane.txt'; then
  bad "REGRESSION: the foreign staged path was SWEPT into the board commit (bare git commit)"
else
  ok "foreign staged path NOT swept into the board commit"
fi
git -C "$WT" diff --cached --name-only | grep -q 'other-lane.txt' \
  && ok "foreign path is STILL staged after the board commit" || bad "foreign staged entry was consumed/lost"
grep -q 'lane-b staged work' "$WT/other-lane.txt" && ok "foreign content intact on disk" || bad "foreign content corrupted"
git -C "$WT" reset -q >/dev/null 2>&1

echo "== 3. TWO CONCURRENT WRITERS: one refused, loser loses nothing"
rc="$(run bash "$BL" acquire A)"
[ "$rc" = "0" ] && ok "writer A takes the hold (exit 0)" || bad "A could not acquire (exit $rc)"
printf '# B edit\n' >> "$WT/fleet/board/SEED.md"      # B's in-flight edit, on disk
rc_b="$(run bash "$BL" commit --session B -m 'board-hygiene: B' -- fleet/board/SEED.md)"
[ "$rc_b" = "1" ] && ok "writer B REFUSED while A holds (exit 1)" || bad "B was not refused (exit $rc_b)"
grep -q 'BOARD-LOCK CONFLICT' "$TMP/err" && ok "B's refusal names the holder" || bad "conflict message missing"
grep -q 'B edit' "$WT/fleet/board/SEED.md" && ok "LOSER's content survives on disk (not corrupted, not lost)" \
  || bad "loser's content was lost"
[ "$(git -C "$WT" rev-parse HEAD)" != "$A_SHA" ] || ok "no commit was made by the loser"
rc="$(run bash "$BL" release A)"; [ "$rc" = "0" ] || bad "release A failed (exit $rc)"

echo "== 4. FAIL-CLOSED: a genuinely held flock refuses the write, never proceeds unlocked"
# Hold the SAME state/lock fd from another process for longer than the wait bound.
( flock 9; sleep 4 ) 9>>"$FLEET/state/lock" &
HOLDER=$!
sleep 0.3
rc="$(cd "$WT" && BOARD_LOCK_WAIT_S=1 bash "$BL" commit --session C -m 'board-hygiene: C' -- fleet/board/SEED.md >"$TMP/out" 2>"$TMP/err"; echo $?)"
[ "$rc" = "70" ] && ok "commit REFUSED while the flock is held (exit 70, fail-closed)" || bad "not fail-closed (exit $rc)"
grep -q 'fail-closed' "$TMP/err" && ok "fail-closed refusal is explicit" || bad "fail-closed message missing"
wait "$HOLDER" 2>/dev/null
rc="$(run bash "$BL" commit --session C -m 'board-hygiene: C' -- fleet/board/SEED.md)"
[ "$rc" = "0" ] && ok "same commit succeeds once the flock is free (non-vacuous)" || bad "commit still fails after unlock (exit $rc): $(cat "$TMP/err")"

echo "== 5. MASTER MOVED UNDER ME: refuse, do not silently proceed"
rc="$(run bash "$BL" acquire D)"; [ "$rc" = "0" ] || bad "D acquire failed (exit $rc)"
printf 'someone-elses-land\n' > "$WT/unrelated.txt"       # another lane lands: HEAD moves
git -C "$WT" add unrelated.txt >/dev/null
git -C "$WT" -c core.hooksPath=/dev/null commit -q -m 'land: other lane' --no-verify
printf '# D edit\n' >> "$WT/fleet/board/SEED.md"
rc="$(run bash "$BL" commit --session D -m 'board-hygiene: D' -- fleet/board/SEED.md)"
[ "$rc" = "3" ] && ok "commit REFUSED because HEAD moved under the holder (exit 3)" || bad "master-moved not detected (exit $rc)"
grep -q 'BASE MOVED UNDER THE BOARD LOCK' "$TMP/err" && ok "master-moved refusal is LOUD, naming both shas" \
  || bad "master-moved banner missing"
grep -q 'D edit' "$WT/fleet/board/SEED.md" && ok "D's edit survives the refusal" || bad "D's edit lost"
rc="$(run bash "$BL" release D)"; [ "$rc" = "0" ] || bad "release D failed"

echo "== 6. STALE HOLD: bounded, LOUD, never silently stealable"
# 6a. stale + holder DEAD -> reclaimed loudly (the fleet can never deadlock on a crashed writer)
rc="$(run bash "$BL" acquire E)"; [ "$rc" = "0" ] || bad "E acquire failed"
sed -i 's/^heartbeat:.*/heartbeat: 1/; s/^pid:.*/pid: 999999/' "$FLEET/state/board-lock"
rc="$(cd "$WT" && BOARD_LOCK_STALE_S=5 bash "$BL" acquire F >"$TMP/out" 2>"$TMP/err"; echo $?)"
[ "$rc" = "0" ] && ok "stale hold with a DEAD holder is reclaimed (no deadlock)" || bad "stale+dead not reclaimed (exit $rc)"
grep -q 'RECLAIMING STALE BOARD LOCK' "$TMP/err" && ok "the reclaim is LOUD (banner + audit log)" || bad "reclaim was silent"
grep -q 'RECLAIMING STALE BOARD LOCK' "$FLEET/state/board-lock.log" && ok "reclaim recorded in board-lock.log" \
  || bad "reclaim not written to the audit log"
rc="$(run bash "$BL" release F)"; [ "$rc" = "0" ] || bad "release F failed"

# 6b. stale + holder ALIVE -> REFUSED; only an explicit steal --force takes it
rc="$(run bash "$BL" acquire G)"; [ "$rc" = "0" ] || bad "G acquire failed"
sleep 30 & LIVE=$!
sed -i "s/^heartbeat:.*/heartbeat: 1/; s/^pid:.*/pid: $LIVE/" "$FLEET/state/board-lock"
rc="$(cd "$WT" && BOARD_LOCK_STALE_S=5 bash "$BL" acquire H >"$TMP/out" 2>"$TMP/err"; echo $?)"
[ "$rc" = "1" ] && ok "stale hold with a LIVE holder is REFUSED (exit 1), not silently stolen" \
  || bad "a live holder was robbed (exit $rc)"
grep -q 'NOT STEALING' "$TMP/err" && ok "the stale-but-alive refusal is LOUD and prints the steal command" \
  || bad "stale-but-alive banner missing"
rc="$(cd "$WT" && BOARD_LOCK_STALE_S=5 bash "$BL" steal H --force >"$TMP/out" 2>"$TMP/err"; echo $?)"
[ "$rc" = "0" ] && ok "an EXPLICIT steal --force takes it" || bad "explicit steal failed (exit $rc)"
grep -q 'FORCED BOARD-LOCK STEAL' "$TMP/err" && ok "the forced steal is LOUD + logged" || bad "forced steal was quiet"
kill "$LIVE" 2>/dev/null; wait "$LIVE" 2>/dev/null
rc="$(run bash "$BL" release H)"; [ "$rc" = "0" ] || bad "release H failed"

echo "== 7. SCOPE: a non-board commit is untouched by the gate"
printf 'plain\n' > "$WT/plain.txt"
git -C "$WT" add plain.txt >/dev/null
rc="$(run git commit -q -m 'plain: not a board path')"
[ "$rc" = "0" ] && ok "a non-board commit needs no board lock (gate is scoped, not a commit ban)" \
  || bad "the gate blocked an unrelated commit (exit $rc): $(cat "$TMP/err")"

echo "== 8. MAIN-CHECKOUT ADVISORY: board commit in main checkout on master is refused"
# MAIN is the main checkout (on master), so the advisory fires.
printf '# SEED2 edit\n' >> "$MAIN/fleet/board/SEED.md"
git -C "$MAIN" add fleet/board/SEED.md >/dev/null
rc="$(run_main bash "$BL_MAIN" commit --session I -m 'board-hygiene: I' -- fleet/board/SEED.md >"$TMP/out" 2>"$TMP/err"; echo $?)"
[ "$rc" = "7" ] && ok "main-checkout board commit REFUSED (exit 7)" || bad "main-checkout not refused (exit $rc)"
grep -q 'ADVISORY' "$TMP/err" && ok "advisory refusal message present" || bad "advisory message missing"
grep -q 'worktree-commit-and-land' "$TMP/err" && ok "ergonomic replacement path printed" || bad "ergonomic path not shown"
grep -q 'main-checkout-advisory-refused' "$TMP/err" && ok "refusal is logged" || bad "advisory not logged"
[ "$(git -C "$MAIN" rev-parse HEAD)" = "$BASE_SHA" ] && ok "nothing committed in main checkout" || bad "commit slipped through main checkout"
git -C "$MAIN" reset -q >/dev/null 2>&1

echo "== 9. MAIN-CHECKOUT RETIRE_DONE_BYPASS: auto-admin archive moves bypass advisory but still lock"
# RETIRE_DONE_BYPASS=1 bypasses the advisory but still requires the board lock.
mkdir -p "$MAIN/fleet/board/archive"
cp "$MAIN/fleet/board/SEED.md" "$MAIN/fleet/board/archive/SEED.md"
git -C "$MAIN" add fleet/board/archive/SEED.md >/dev/null
rc="$(run_main RETIRE_DONE_BYPASS=1 bash "$BL_MAIN" commit --session retire-done -m 'board-hygiene: retire' -- fleet/board/archive/SEED.md >"$TMP/out" 2>"$TMP/err"; echo $?)"
[ "$rc" = "0" ] && ok "RETIRE_DONE_BYPASS=1 allows main-checkout commit (exit 0)" || bad "bypass failed (exit $rc)"
git -C "$MAIN" log -1 --format=%s | grep -q 'board-hygiene: retire' && ok "archive commit landed" || bad "archive commit missing"

echo "== 10. WORKTREE: board commit from a linked worktree is NOT refused"
# WT is a linked worktree on wt-board (NOT master), so _is_main_checkout returns false.
printf '# WT edit\n' >> "$WT/fleet/board/SEED.md"
git -C "$WT" add fleet/board/SEED.md >/dev/null
rc="$(run bash "$BL" commit --session J -m 'board-hygiene: J' -- fleet/board/SEED.md >"$TMP/out" 2>"$TMP/err"; echo $?)"
[ "$rc" = "0" ] && ok "worktree board commit ALLOWED (exit 0)" || bad "worktree commit refused (exit $rc)"
git -C "$WT" log -1 --format=%s | grep -q 'board-hygiene: J' && ok "worktree commit landed" || bad "worktree commit missing"

echo
if [ "$fails" -eq 0 ]; then echo "board-write-lock: PASS"; exit 0
else echo "board-write-lock: FAIL ($fails)"; exit 1; fi
