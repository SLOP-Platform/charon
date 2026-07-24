#!/usr/bin/env bash
# end-session-stale-guard.test.sh — FAIL-ON-REVERT test for the M2 STALE-HANDOFF GUARD.
#
# The bug: end-session.sh's Phase-1 gate was a bare `[ ! -f "$file" ]` existence check. A REUSED
# session name that finds a SESSION-HANDOFF-<name>.md committed by a PRIOR session (days ago) was
# treated as "already generated", fell through to Phase 2, passed handoff-check on the STALE
# content, and committed a days-old handoff as this session's work. The guard REFUSES when the
# handoff file exists, is tracked & UNMODIFIED vs HEAD, and its LAST COMMIT predates this process's
# start (END_SESSION_PROC_START) — the signature of a file written by a previous session.
#
# Strategy: a REAL local rig (git init + a commit), a handoff file committed into it, and
# END_SESSION_PROC_START forced to AFTER that commit so the file looks stale. Every git/status/log
# call in the guard runs against real git.
#
# Covers:
#   (A) STALE file (committed, clean, commit < PROC_START) -> REFUSE, names PREDATES, no re-commit.
#   (B) FRESH this-session file (UNCOMMITTED/untracked) -> guard does NOT fire (proceeds to Phase 2).
#   (C) committed file whose commit is NOT before PROC_START -> guard does NOT fire (time-gated).
#   (D) FAIL-ON-REVERT: strip the guard block from a copy of end-session.sh and run the SAME stale
#       fixture — the stale refusal DISAPPEARS and it falls through past Phase 1. That flip is the red.
#
# Run:  bash fleet/tests/end-session-stale-guard.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
SESSION=luminara-unduli
HF="SESSION-HANDOFF-$SESSION.md"

# stub handoff-check: PASS every time (so the ONLY thing that can refuse is the stale guard / commit)
printf '#!/usr/bin/env bash\nexit 0\n' > "$D/check-pass.sh"; chmod +x "$D/check-pass.sh"
printf '#!/usr/bin/env bash\necho "# stub machine-state"\n' > "$D/gen-stub.sh"; chmod +x "$D/gen-stub.sh"

# Build a rig with the handoff committed. $1 = commit epoch to stamp on the handoff commit.
build_rig_committed(){
  local when="$1"
  rm -rf "$D/rig"; mkdir -p "$D/rig"
  git -C "$D/rig" init -q -b master
  git -C "$D/rig" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  printf '# prior-session handoff (committed %s)\n' "$when" > "$D/rig/$HF"
  git -C "$D/rig" add "$HF"
  GIT_AUTHOR_DATE="@$when" GIT_COMMITTER_DATE="@$when" \
    git -C "$D/rig" -c user.email=t@t -c user.name=t commit -q -m "prior handoff" -- "$HF"
}

# Run end-session against the rig. $1 = END_SESSION_PROC_START, $2 = script path (default real).
run_es(){
  local proc_start="$1" script="${2:-$SRC/end-session.sh}"
  SESSION="$SESSION" \
  END_SESSION_GIT=git \
  END_SESSION_PROC_START="$proc_start" \
  END_SESSION_HANDOFF_SH="$D/gen-stub.sh" \
  END_SESSION_CHECK_SH="$D/check-pass.sh" \
  END_SESSION_PRIV="$D/rig" \
  END_SESSION_FILE="$D/rig/$HF" \
  END_SESSION_DEPLOY_HOOK="$D/nope.sh" \
  FLEET="$D" \
  END_SESSION_PUSH=0 \
  END_SESSION_SECOND_REPO_CHECK=0 \
    bash "$script" >"$D/out" 2>&1
  printf '%d' "$?" > "$D/rc"
}

# =============================================================================
echo "== (A) STALE committed handoff (commit < PROC_START) -> REFUSE =="
COMMIT_AT=1700000000                       # fixed old epoch
build_rig_committed "$COMMIT_AT"
sha_before="$(git -C "$D/rig" rev-parse HEAD)"
run_es "$((COMMIT_AT + 100000))"           # process starts long AFTER the commit -> stale
out_a="$(cat "$D/out")"; rc_a="$(cat "$D/rc")"
check "A1 refuses (non-zero) on a stale reused-name handoff" "$rc_a" "1"
case "$out_a" in *"PREDATES this session's start"*) ok "A2 refusal names PREDATES this session's start";; *) bad "A2 refusal names PREDATES (out: $(printf '%s' "$out_a" | tr '\n' ' '))";; esac
case "$out_a" in *"STALE handoff"*) ok "A3 refusal says STALE handoff / reused name";; *) bad "A3 refusal says STALE handoff";; esac
case "$out_a" in *CLOSED*) bad "A4 no CLOSED print on a stale handoff";; *) ok "A4 no CLOSED print on a stale handoff";; esac
check "A5 stale file was NOT re-committed (HEAD unchanged)" "$(git -C "$D/rig" rev-parse HEAD)" "$sha_before"

# =============================================================================
echo "== (B) FRESH this-session handoff (UNCOMMITTED) -> guard does NOT fire =="
# Legit Phase-2 flow: end-session itself commits the handoff, so at decision time this-session's
# file is untracked/dirty. The guard must skip it and proceed to Phase 2 (checking handoff).
rm -rf "$D/rig"; mkdir -p "$D/rig"
git -C "$D/rig" init -q -b master
git -C "$D/rig" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
printf '# fresh handoff written THIS session\n' > "$D/rig/$HF"   # untracked, never committed
run_es "$(date +%s)"
out_b="$(cat "$D/out")"
case "$out_b" in *"STALE handoff"*|*"PREDATES"*) bad "B1 guard WRONGLY fired on an uncommitted this-session file";; *) ok "B1 guard does NOT fire on an uncommitted this-session file";; esac
case "$out_b" in *"checking handoff"*) ok "B2 proceeded to Phase 2 (checking handoff)";; *) bad "B2 expected Phase 2 to run (out: $(printf '%s' "$out_b" | tr '\n' ' '))";; esac

# =============================================================================
echo "== (C) committed handoff whose commit is NOT before PROC_START -> guard does NOT fire =="
# Time-gate control: if the file was committed at/after this process started (e.g. an idempotent
# re-run within the same session), it is NOT stale and must not be refused for staleness.
build_rig_committed "$COMMIT_AT"
run_es "$((COMMIT_AT - 100))"              # process 'started' BEFORE the commit -> not stale
out_c="$(cat "$D/out")"
case "$out_c" in *"STALE handoff"*|*"PREDATES"*) bad "C1 guard WRONGLY fired when commit is not before PROC_START";; *) ok "C1 guard is time-gated: no stale refusal when commit >= PROC_START";; esac

# =============================================================================
echo "== (D) FAIL-ON-REVERT: strip the guard -> stale fixture stops refusing for staleness =="
# Remove the M2 guard block (from its banner comment up to the Phase-1 banner) from a copy, then
# run the SAME stale fixture (A). Without the guard the stale message must VANISH and control must
# fall through past Phase 1. If the strip changed nothing, the guard was not load-bearing.
awk '/# -- M2 STALE-HANDOFF GUARD/{skip=1} /# -- Phase 1: generate machine-state/{skip=0} !skip' \
  "$SRC/end-session.sh" > "$D/end-session-reverted.sh"
# Sanity: the strip actually removed lines (otherwise the awk markers drifted and the test is vacuous).
lines_full="$(wc -l < "$SRC/end-session.sh")"
lines_rev="$(wc -l < "$D/end-session-reverted.sh")"
if [ "$lines_rev" -lt "$lines_full" ]; then
  ok "D0 guard block was actually removed from the reverted copy ($lines_full -> $lines_rev lines)"
else
  bad "D0 reverted copy is not smaller ($lines_full -> $lines_rev) — awk markers drifted, revert control vacuous"
fi
build_rig_committed "$COMMIT_AT"
run_es "$((COMMIT_AT + 100000))" "$D/end-session-reverted.sh"
out_d="$(cat "$D/out")"
case "$out_d" in
  *"STALE handoff"*|*"PREDATES"*) bad "D1 reverted end-session STILL printed the stale refusal — guard not load-bearing";;
  *)                              ok  "D1 revert-control: without the guard, the stale fixture no longer refuses for staleness (this is the red on revert)";;
esac
# And it must have fallen through past Phase 1 into the normal close machinery.
case "$out_d" in *"checking handoff"*|*"commit FAILED"*|*"handoff-check PASSED"*) ok "D2 revert-control fell through past Phase 1 into the normal path";; *) bad "D2 expected fall-through past Phase 1 (out: $(printf '%s' "$out_d" | tr '\n' ' '))";; esac

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || { echo "END-SESSION-STALE-GUARD TEST FAILED"; exit 1; }
echo "ALL END-SESSION-STALE-GUARD TESTS PASS"
