#!/usr/bin/env bash
# land-safety.test.sh — FAIL-ON-REVERT tests for LAND-SAFETY-FIX (FIX 1a/1b/1c).
#
# THE BUGS (2026-07-18), all one class: a push path that reports SUCCESS without verifying WHAT
# it pushed.
#   (a) land-push.sh pushed the LOCAL REF matching the NAME given, not HEAD. With HEAD on a
#       feature branch, `land-push.sh master` printed "pushing 'master'" + exit 0 while publishing
#       NOTHING. The explicit `HEAD:master` refspec DOES work and MUST keep working — that is how
#       master was reconciled.
#   (b) land.sh ran `git branch -f <branch> HEAD` and IGNORED the rc. With a live worktree holding
#       that branch, `branch -f` fails ("cannot force update the branch ... used by worktree at
#       ..."), land.sh fell through and pushed the STALE same-named local ref — the wrong-commit
#       merge (be41ece instead of the rebuilt HEAD).
#   (c) that worktree-held condition had no detection at all — a silent wrong push instead of an
#       actionable message.
#
# NON-FIXTURE: these run the REAL land-push.sh / land.sh / push-verify.sh files (copied verbatim
# into a temp FLEET so the AUTONOMOUS lever and state dir are hermetic — the CODE is the real
# code, never a transcription) against REAL git objects in REAL repos with a REAL bare remote and
# a REAL second worktree. No stubs of the broken lines.
#
# ── FAIL-ON-REVERT (each assertion names the exact revert that turns it RED) ─────────────────
#   R1 — land-push.sh: delete the `if [ "$BRANCH" = "$SRC" ]` HEAD-mismatch block (restore the
#        bare `git push origin "$BRANCH"` behaviour).            RED: assertion 1.
#   R2 — land.sh step 4: restore `git branch -f "$BRANCH" HEAD && echo …` (drop the
#        pv_branch_holder check, the `if ! git branch -f` rc check and the BR_SHA==HEAD_SHA
#        check).                                                  RED: assertions 3 and 4.
#   R3 — push-verify.sh:pv_push_verified: delete the `[ "$now" != "$sha" ]` mismatch block (i.e.
#        trust the push command's own exit code).                 RED: assertion 5.
#   R4 — land-push.sh: replace `pv_push_verified …` with `git -C "$REPO" push origin "$BRANCH"`.
#        RED: assertion 2 (HEAD:master stops publishing / stops being proven) and 5.
set -uo pipefail
FLEET_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fails=0
# LOW-7: this line printed `$((fails==0))` as the PASS COUNT, so 7 green assertions
# reported "1 pass". Count the passes for real.
passes=0
ok(){ passes=$((passes+1)); printf '  ok   %s\n' "$1"; }
bad(){ printf '  FAIL %s\n' "$1"; fails=$((fails+1)); }

D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT

# A hermetic copy of the REAL scripts under test + an AUTONOMOUS lever they can see.
F="$D/fleet"; mkdir -p "$F/state"
cp "$FLEET_SRC/land-push.sh" "$FLEET_SRC/land.sh" "$FLEET_SRC/push-verify.sh" "$F/"
: > "$F/state/AUTONOMOUS"

git_q(){ git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }

# ── a REAL bare remote + a REAL clone with master and a feature branch ───────────────────────
REMOTE="$D/remote.git"; git init -q --bare -b master "$REMOTE"
R="$D/repo"; git init -q -b master "$R"
git -C "$R" config user.email t@t; git -C "$R" config user.name t
git -C "$R" remote add origin "$REMOTE"
echo base > "$R/f"; git -C "$R" add f; git -C "$R" commit -qm base
git -C "$R" push -q origin master
BASE_SHA="$(git -C "$R" rev-parse HEAD)"

# HEAD moves onto a feature branch carrying the real work; local master stays STALE at BASE_SHA.
git -C "$R" checkout -q -b feature
echo work > "$R/f"; git -C "$R" commit -qam work
WORK_SHA="$(git -C "$R" rev-parse HEAD)"

# ── 1. land-push.sh <bare name> while HEAD is elsewhere -> must REFUSE (not report success) ──
#    REVERT R1 to make this RED.
out="$(bash "$F/land-push.sh" master "$R" --gate true 2>&1)"; rc=$?
remote_master="$(git -C "$R" ls-remote origin refs/heads/master | awk '{print $1}')"
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'REFUSING'; then
  ok "1 land-push REFUSES a bare-name push whose local ref is not HEAD (rc=$rc)"
else
  bad "1 land-push accepted a bare-name push with HEAD elsewhere (rc=$rc) — the false-success bug: $out"
fi
[ "$remote_master" = "$BASE_SHA" ] \
  && ok "1b remote master untouched by the refused push" \
  || bad "1b remote master moved to $remote_master on a refused push"

# ── 2. the explicit HEAD:master refspec still works AND is PROVEN (guards over-fixing) ───────
#    REVERT R4 to make this RED.
out="$(bash "$F/land-push.sh" HEAD:master "$R" --gate true 2>&1)"; rc=$?
remote_master="$(git -C "$R" ls-remote origin refs/heads/master | awk '{print $1}')"
if [ "$rc" -eq 0 ] && [ "$remote_master" = "$WORK_SHA" ] && printf '%s' "$out" | grep -q 'PROVEN'; then
  ok "2 land-push HEAD:master publishes HEAD and PROVES it via ls-remote"
else
  bad "2 land-push HEAD:master rc=$rc remote=$remote_master want=$WORK_SHA: $out"
fi

# ── 3/4. land.sh with the target branch HELD BY ANOTHER WORKTREE (the live trigger) ──────────
# Rebuild: a repo whose local 'feat' ref is STALE while a second worktree holds 'feat', and HEAD
# (elsewhere) carries the real work. Pre-fix: `git branch -f feat HEAD` fails, land.sh ignores the
# rc and pushes the STALE feat -> the wrong commit lands. REVERT R2 to make these RED.
REMOTE2="$D/remote2.git"; git init -q --bare -b master "$REMOTE2"
R2="$D/repo2"; git init -q -b master "$R2"
git -C "$R2" config user.email t@t; git -C "$R2" config user.name t
git -C "$R2" remote add origin "$REMOTE2"
echo base > "$R2/f"; git -C "$R2" add f; git -C "$R2" commit -qm base
git -C "$R2" push -q origin master
git -C "$R2" branch feat                       # 'feat' = the STALE ref (== base)
STALE_SHA="$(git -C "$R2" rev-parse feat)"
git -C "$R2" worktree add -q "$D/held" feat    # a LIVE worktree holds 'feat' -> branch -f will fail
git -C "$R2" checkout -q -b rebuilt
echo rebuilt > "$R2/f"; git -C "$R2" commit -qam rebuilt
REBUILT_SHA="$(git -C "$R2" rev-parse HEAD)"

out="$(bash "$F/land.sh" feat "$R2" --base master --gate true 2>&1)"; rc=$?
pushed="$(git -C "$R2" ls-remote origin refs/heads/feat | awk '{print $1}')"
if [ "$pushed" != "$STALE_SHA" ]; then
  ok "3 land.sh did NOT publish the stale worktree-held ref (the wrong-commit merge)"
else
  bad "3 land.sh PUBLISHED the stale ref $STALE_SHA (want: never) — wrong-commit merge reproduced: $out"
fi
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'checked out by another worktree'; then
  ok "4 land.sh detects the holding worktree and fails CLOSED with an actionable message (rc=$rc)"
else
  bad "4 land.sh gave no worktree-held diagnosis (rc=$rc): $out"
fi
# Must be LAND.SH's own diagnosis (a `land:`-prefixed line), not git's incidental fatal — under
# the R2 revert git itself prints the path, so a bare grep for it passes for the WRONG reason.
printf '%s\n' "$out" | grep -q "^land:.*$D/held" \
  && ok "4b land.sh's own message names the holding worktree path" \
  || bad "4b land.sh printed no such diagnosis of its own: $out"

# ── 5. THE CORE ASSERTION: a push that "succeeds" while the remote does NOT become the intended
# sha must FAIL. Simulated for real: the bare remote's post-receive hook rewinds master, so
# `git push` exits 0 and the remote sha is NOT what we published. Only the ls-remote proof can
# catch this. REVERT R3 (or R4) to make this RED.
REMOTE3="$D/remote3.git"; git init -q --bare -b master "$REMOTE3"
R3="$D/repo3"; git init -q -b master "$R3"
git -C "$R3" config user.email t@t; git -C "$R3" config user.name t
git -C "$R3" remote add origin "$REMOTE3"
echo one > "$R3/f"; git -C "$R3" add f; git -C "$R3" commit -qm one
git -C "$R3" push -q origin master
DECOY="$(git -C "$R3" rev-parse HEAD)"
echo two > "$R3/f"; git -C "$R3" commit -qam two
INTENDED3="$(git -C "$R3" rev-parse HEAD)"
cat > "$REMOTE3/hooks/post-receive" <<EOF
#!/bin/sh
# accept the push, then silently rewind master — a push that exits 0 without the remote ever
# becoming the intended sha (exactly the false-success class under test).
git update-ref refs/heads/master $DECOY
EOF
chmod +x "$REMOTE3/hooks/post-receive"

out="$(bash "$F/land-push.sh" HEAD:master "$R3" --gate true 2>&1)"; rc=$?
now3="$(git -C "$R3" ls-remote origin refs/heads/master | awk '{print $1}')"
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'REMOTE MISMATCH'; then
  ok "5 a push whose remote sha != intended sha FAILS loudly (rc=$rc; remote=${now3:0:7} intended=${INTENDED3:0:7})"
else
  bad "5 land-push reported SUCCESS (rc=$rc) while origin/master is ${now3:0:7}, not ${INTENDED3:0:7}: $out"
fi

echo "land-safety: $passes pass ($fails failure(s))"
[ "$fails" -eq 0 ]
