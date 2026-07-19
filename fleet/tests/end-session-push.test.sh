#!/usr/bin/env bash
# end-session-push.test.sh — FAIL-ON-REVERT tests for the SESSION-END-PUSH-GATE: end-session.sh
# must REFUSE to print CLOSED unless (a) the rig working tree is CLEAN (all session work
# committed, not just the handoff) and (b) local HEAD is not ahead of origin/$cur_branch.
# Reverting either check -> a stranded-commit or dirty-tree case closes anyway -> RED.
#
# Strategy: each test stands up a REAL local "rig" (git init + a local bare "origin" remote +
# an initial commit on master + push to origin) so end-session.sh's branch-guard, status, and
# rev-parse calls all run against real git. The handoff generator + handoff-check are stubbed
# to PASS; the handoff FILE lives inside the rig so commit_handoff operates on a tracked file.
# Push attempts go through a fake $FLEET/land-push.sh (the script's allowed hook) so the test
# controls push success/failure without a real remote.
#
# Covers:
#   (A) diry tree -> REFUSE, no CLOSED, handoff commit still happened (commit_handoff is allowed
#       to commit the handoff first; the gate catches leftover work after).
#   (B) clean tree, HEAD ahead of origin, END_SESSION_PUSH=0 -> REFUSE, no CLOSED, no push.
#   (C) clean tree, HEAD ahead of origin, fake land-push REFUSES -> REFUSE, no CLOSED, no push.
#   (D) clean tree, HEAD == origin (already pushed) -> CLOSED, work on origin.
#   (E) FAIL-ON-REVERT: the dirty-tree check is the only thing keeping (A) from closing — if
#       you delete that block, (A) flips to CLOSED. The test asserts (A) refuses; reverting
#       the gate makes (A) pass — that is the red.
#
# Run:  bash fleet/tests/end-session-push.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

D="$(mktemp -d)"

# --- rig: a real git repo with a local bare "origin" remote and an initial commit on master -
mkdir -p "$D/rig" "$D/origin.git"
git -C "$D/origin.git" init -q --bare
git -C "$D/rig" init -q -b master
git -C "$D/rig" remote add origin "$D/origin.git"
git -C "$D/rig" -c user.email=test@test -c user.name=test commit -q --allow-empty -m init
git -C "$D/rig" push -q origin master
# (No need to capture the initial SHA — each test compares before/after of origin/master.)

# --- stub fleet: a copy of end-session.sh + minimal sibling scripts so END_SESSION_DEPLOY_HOOK
#     and the fake land-push.sh land at $FLEET/land-push.sh exactly as the script expects.
cp "$SRC/end-session.sh" "$D/end-session.sh"
cp "$SRC/deploy-session-end.sh" "$D/deploy-session-end.sh"
# Copy the real land-push.sh if present so the script's `-x "$push_sh"` check passes; we'll
# overwrite $FLEET/land-push.sh with a per-test stub below.
[ -f "$SRC/land-push.sh" ] && cp "$SRC/land-push.sh" "$D/land-push.sh"
# A noop roadmap-html.sh so the advisory regen path doesn't error.
cat > "$D/roadmap-html.sh" <<'HTML'
#!/usr/bin/env bash
exit 0
HTML
chmod +x "$D/roadmap-html.sh"

# --- stub handoff generator + checker: pass every time. The handoff FILE is the rig's own
#     SESSION-HANDOFF-<session>.md so commit_handoff operates on a tracked-path file.
cat > "$D/gen-stub.sh" <<'GEN'
#!/usr/bin/env bash
echo "# machine-state (stub) for ${SESSION:-?}"
GEN
chmod +x "$D/gen-stub.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$D/check-pass.sh"
chmod +x "$D/check-pass.sh"
printf '# id\topened\tsev\tarea\tdesc\tcheck\tstatus\tclosed_by\n' > "$D/reds.tsv"

# Per-test land-push stub: writes its args to $PUSH_LOG and exits $PUSH_RC (default 0).
# $D/land-push.sh is what the script invokes when ahead-of-origin is detected.
cat > "$D/land-push.sh" <<'PUSH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PUSH_LOG"
exit "${PUSH_RC:-0}"
PUSH
chmod +x "$D/land-push.sh"

# Helper: run end-session.sh against the rig with the test-supplied handoff content already
# written to the rig. END_SESSION_GIT=git so commits are real; END_SESSION_PRIV=$D/rig.
# Writes stdout+stderr to $D/last_out and the script's exit code to $D/last_rc.
run_end_session(){
  local handoff_file="$D/rig/SESSION-HANDOFF-${SESSION}.md"
  cp "$D/HO.md" "$handoff_file" 2>/dev/null || true
  : > "$D/push.log"
  SESSION="$SESSION" \
  END_SESSION_GIT=git \
  END_SESSION_HANDOFF_SH="$D/gen-stub.sh" \
  END_SESSION_CHECK_SH="$D/check-pass.sh" \
  END_SESSION_PRIV="$D/rig" \
  END_SESSION_FILE="$handoff_file" \
  END_SESSION_DEPLOY_HOOK="$D/deploy-session-end.sh" \
  FLEET="$D" \
  END_SESSION_PUSH="${END_SESSION_PUSH:-1}" \
  END_SESSION_PUSH_TIMEOUT="${END_SESSION_PUSH_TIMEOUT:-120}" \
  END_SESSION_SECOND_REPO_CHECK="${END_SESSION_SECOND_REPO_CHECK:-0}" \
  END_SESSION_SECOND_REPOS="${END_SESSION_SECOND_REPOS:-}" \
  SESSION_END_REDS_TSV="$D/reds.tsv" \
  SESSION_END_LATEST_TAG_CMD="printf '%s\\n' 'v9.9.9'" \
  SESSION_END_RUNNING_TAG_CMD="printf '%s\\n' 'ghcr.io/slop-platform/charon:v9.9.9'" \
  SESSION_END_CI_GREEN_CMD="printf '%s\\n' 'completed success'" \
  SESSION_END_DEPLOY_SH="$D/deploy-stub.sh" \
  PUSH_LOG="$D/push.log" \
  PUSH_RC="${PUSH_RC:-0}" \
  bash "$D/end-session.sh" >"$D/last_out" 2>&1
  printf '%d' "$?" > "$D/last_rc"
}

# Stub deploy so the post-push deploy hook doesn't try to ssh.
cat > "$D/deploy-stub.sh" <<'DEPLOY'
#!/usr/bin/env bash
exit 0
DEPLOY
chmod +x "$D/deploy-stub.sh"

# Handoff file body — content is irrelevant (stub check always passes).
cat > "$D/HO.md" <<'HO'
# stub handoff (test fixture)
HO

# reset rig: a clean master with a single initial commit pushed to origin.
reset_rig(){
  rm -rf "$D/rig"
  mkdir -p "$D/rig"
  git -C "$D/rig" init -q -b master
  git -C "$D/rig" remote add origin "$D/origin.git"
  git -C "$D/rig" -c user.email=test@test -c user.name=test commit -q --allow-empty -m init
  git -C "$D/rig" push -q -f origin master
  rm -f "$D/rig/SESSION-HANDOFF-sesstest.md"
}

# Run "ahead" by creating a local commit NOT pushed to origin.
make_ahead(){
  git -C "$D/rig" -c user.email=test@test -c user.name=test commit -q --allow-empty -m ahead
}

SESSION=sesstest
END_SESSION_PUSH=1   # default for most tests; (B) overrides to 0

# =============================================================================
echo "== (A) DIRTY TREE -> REFUSE (commit_handoff runs, then dirty check catches leftover) =="
# The handoff file is committed by end-session.sh; an EXTRA uncommitted file in the rig is
# what the dirty-tree gate is meant to catch (uncommitted session work that would strand).
reset_rig
# Stage a pre-existing UNRELATED change (a "session work" file that the droid forgot to commit).
echo "uncommitted session work" > "$D/rig/scratch-note.md"
git -C "$D/rig" add scratch-note.md   # staged but uncommitted -> 'A ' in porcelain, still dirty
run_end_session
out_a="$(cat "$D/last_out")"; rc_a="$(cat "$D/last_rc")"
check "A1 script exits non-zero on dirty tree" "$rc_a" "1"
case "$out_a" in *CLOSED*) bad "A2 no CLOSED print on dirty tree";; *) ok "A2 no CLOSED print on dirty tree";; esac
case "$out_a" in *DIRTY*)  ok  "A3 prints DIRTY message";;        *) bad "A3 prints DIRTY message";; esac
# fail-on-revert assertion: if you delete the dirty check, the script commits the handoff AND
# prints CLOSED. The flip of A2 is the red.
[ -e "$D/rig/SESSION-HANDOFF-sesstest.md" ] && ok "A4 handoff commit was attempted (commit_handoff ran first)" \
                                              || bad "A4 handoff commit was attempted (commit_handoff ran first)"
# A5: the handoff file MUST NOT be on origin/master (work would be stranded). The local commit
# may or may not exist; what matters is that origin/master is unchanged from the rig's prior HEAD.
origin_sha_before_a="$(git -C "$D/rig" rev-parse origin/master 2>/dev/null || echo none)"
[ "$(git -C "$D/origin.git" ls-tree "$origin_sha_before_a" SESSION-HANDOFF-sesstest.md 2>/dev/null | wc -l | tr -d ' ')" = "0" ] \
  && ok "A5 handoff NOT pushed to origin (work would be stranded)" \
  || bad "A5 handoff NOT pushed to origin (work would be stranded)"
# The staged-but-uncommitted scratch-note MUST still be in the rig (NOT silently dropped).
[ -f "$D/rig/scratch-note.md" ] && ok "A6 uncommitted work preserved (operator can fix it)" \
                                  || bad "A6 uncommitted work preserved (operator can fix it)"

# =============================================================================
echo "== (B) UNPUSHED COMMIT, END_SESSION_PUSH=0 -> REFUSE, no push, no CLOSED =="
reset_rig
make_ahead
END_SESSION_PUSH=0 run_end_session
out_b="$(cat "$D/last_out")"; rc_b="$(cat "$D/last_rc")"
check "B1 script exits non-zero when push suppressed" "$rc_b" "1"
case "$out_b" in *CLOSED*) bad "B2 no CLOSED print on unpushed";; *) ok "B2 no CLOSED print on unpushed";; esac
case "$out_b" in *REFUS*)  ok "B3 prints REFUSING";;             *) bad "B3 prints REFUSING";; esac
# B4 asserts land-push was NOT invoked. As originally written (`[ ! -s push.log ]` alone) it was
# INVERTED BY CONSTRUCTION: delete the land-push stub, or the push feature entirely, and the log
# stays empty and B4 goes GREEN — an assertion that passes hardest when the thing it guards is
# missing. Anchor it on a positive control first: the stub must EXIST and be executable, so the
# empty log means "the wired-up pusher was deliberately not called", not "there was no pusher".
if [ ! -x "$D/land-push.sh" ]; then
  bad "B4 land-push stub missing/not executable — the 'not invoked' assertion would be vacuous"
elif [ -s "$D/push.log" ]; then
  bad "B4 land-push NOT invoked (got: $(tr '\n' ' ' < "$D/push.log"))"
else
  ok "B4 land-push present-but-NOT-invoked when push suppressed"
fi
origin_sha_before_b="$(git -C "$D/rig" rev-parse origin/master 2>/dev/null || echo none)"
[ "$(git -C "$D/origin.git" ls-tree "$origin_sha_before_b" SESSION-HANDOFF-sesstest.md 2>/dev/null | wc -l | tr -d ' ')" = "0" ] \
  && ok "B5 handoff NOT pushed to origin (work would be stranded)" \
  || bad "B5 handoff NOT pushed to origin (work would be stranded)"
END_SESSION_PUSH=1   # restore default

# =============================================================================
echo "== (C) UNPUSHED COMMIT, fake land-push REFUSES -> REFUSE, no CLOSED =="
reset_rig
make_ahead
PUSH_RC=3 run_end_session
out_c="$(cat "$D/last_out")"; rc_c="$(cat "$D/last_rc")"
check "C1 script exits non-zero when land-push refuses" "$rc_c" "1"
case "$out_c" in *CLOSED*) bad "C2 no CLOSED print on push refusal";; *) ok "C2 no CLOSED print on push refusal";; esac
case "$out_c" in *"land-push REFUSED"*) ok "C3 prints land-push REFUSED";; *) bad "C3 prints land-push REFUSED";; esac
grep -q "master $D/rig" "$D/push.log" && ok "C4 land-push invoked with master + rig" \
                                       || bad "C4 land-push invoked (log: $(tr '\n' ' ' < "$D/push.log"))"
origin_sha_before_c="$(git -C "$D/rig" rev-parse origin/master 2>/dev/null || echo none)"
[ "$(git -C "$D/origin.git" ls-tree "$origin_sha_before_c" SESSION-HANDOFF-sesstest.md 2>/dev/null | wc -l | tr -d ' ')" = "0" ] \
  && ok "C5 handoff NOT pushed to origin (the fake land-push refuses, not pushes)" \
  || bad "C5 handoff NOT pushed to origin (the fake land-push refuses, not pushes)"

# =============================================================================
echo "== (D) CLEAN + ALREADY PUSHED -> CLOSED, handoff on origin =="
reset_rig
# A clean rig with HEAD == origin/master (no ahead). The handoff commit will create a new local
# commit; land-push stub (PUSH_RC=0) is invoked and just writes to its log. To assert the work
# actually reaches origin, we make the real land-push stub ALSO push the rig to origin.
cat > "$D/land-push.sh" <<'PUSH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PUSH_LOG"
git -C "$2" push origin "$1" 2>>"$PUSH_LOG"
exit "$?"
PUSH
chmod +x "$D/land-push.sh"
run_end_session
out_d="$(cat "$D/last_out")"; rc_d="$(cat "$D/last_rc")"
check "D1 script exits 0 on clean + synced" "$rc_d" "0"
case "$out_d" in *CLOSED*) ok "D2 prints SESSION CLOSED";; *) bad "D2 prints SESSION CLOSED";; esac
# The handoff commit must now be on origin/master (the real test that work actually reached it).
origin_handoff="$(git -C "$D/origin.git" ls-tree master -- SESSION-HANDOFF-sesstest.md 2>/dev/null | wc -l | tr -d ' ')"
check "D3 handoff file present on origin/master" "$origin_handoff" "1"
[ -s "$D/push.log" ] && ok "D4 land-push invoked" || bad "D4 land-push invoked"
# Working tree clean after close.
[ -z "$(git -C "$D/rig" status --porcelain 2>/dev/null)" ] && ok "D5 rig working tree clean after close" \
                                                         || bad "D5 rig working tree clean after close"

# =============================================================================
echo "== (E) FAIL-ON-REVERT: dirty check is the gate that keeps (A) from closing =="
# If you remove the dirty-tree block from end-session.sh, the script commits the handoff and
# proceeds to land-push, then prints CLOSED — A1/A2 flip. This assertion names that explicitly.
case "$out_a" in *CLOSED*) bad "E1 A-case did NOT close (dirty gate held) — good, but reverting the gate would flip this";; *) ok "E1 A-case correctly REFUSED close (dirty gate held)";; esac

# =============================================================================
echo "== (F) SECOND REPO (product) holds unpushed work, rig CLEAN -> REFUSE, names that repo =="
# D1: the gate used to inspect ONLY $PRIV, so session work committed-but-unpushed in the PRODUCT
# repo printed SESSION CLOSED and stranded. Stand up a second real repo + bare origin, leave it
# one commit ahead, and drive a close whose RIG side is entirely clean/synced — the ONLY thing
# that may refuse here is the second-repo check.
mkdir -p "$D/product" "$D/product-origin.git"
git -C "$D/product-origin.git" init -q --bare
git -C "$D/product" init -q -b master
git -C "$D/product" remote add origin "$D/product-origin.git"
git -C "$D/product" -c user.email=test@test -c user.name=test commit -q --allow-empty -m init
git -C "$D/product" push -q origin master
# ...and now the unpushed session work in the product repo.
git -C "$D/product" -c user.email=test@test -c user.name=test commit -q --allow-empty -m "product session work"

reset_rig
# land-push really pushes (as in (D)) so the RIG side goes fully green before the second-repo check.
cat > "$D/land-push.sh" <<'PUSH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PUSH_LOG"
git -C "$2" push origin "$1" 2>>"$PUSH_LOG"
exit "$?"
PUSH
chmod +x "$D/land-push.sh"
END_SESSION_SECOND_REPO_CHECK=1 END_SESSION_SECOND_REPOS="$D/product" run_end_session
out_f="$(cat "$D/last_out")"; rc_f="$(cat "$D/last_rc")"
check "F1 script exits non-zero when the product repo is ahead of its origin" "$rc_f" "1"
case "$out_f" in *CLOSED*) bad "F2 no CLOSED print while product work is unpushed";; *) ok "F2 no CLOSED print while product work is unpushed";; esac
case "$out_f" in *"$D/product"*) ok "F3 names WHICH repo is unpushed (operator knows where to look)";; *) bad "F3 names WHICH repo is unpushed";; esac
# F4 FAIL-ON-REVERT (demonstrated, not asserted): with the second-repo check disabled — which is
# exactly the pre-fix behaviour, a gate that looks only at $PRIV — the identical fixture CLOSES.
# So this whole case goes RED the moment the second-repo check is reverted.
# reset_rig first: F1 already committed+pushed the handoff, so a re-run against that same rig
# would fail at commit_handoff ("nothing to commit") and refuse for an unrelated reason.
reset_rig
END_SESSION_SECOND_REPO_CHECK=0 run_end_session
out_f4="$(cat "$D/last_out")"
case "$out_f4" in
  *CLOSED*) ok "F4 revert-control: rig-only checking DOES close over stranded product work (this is the bug)";;
  *)        bad "F4 revert-control: expected the rig-only path to close (fixture no longer isolates the fix)";;
esac
# F5: a product repo that is CLEAN and synced must NOT block the close (no false refusals).
git -C "$D/product" push -q origin master
reset_rig
END_SESSION_SECOND_REPO_CHECK=1 END_SESSION_SECOND_REPOS="$D/product" run_end_session
out_f5="$(cat "$D/last_out")"; rc_f5="$(cat "$D/last_rc")"
check "F5 clean+synced product repo does NOT block the close" "$rc_f5" "0"
case "$out_f5" in *CLOSED*) ok "F6 prints SESSION CLOSED when BOTH repos are clean";; *) bad "F6 prints SESSION CLOSED when BOTH repos are clean";; esac
# F7: dirty (uncommitted) product work must refuse too, not just unpushed commits.
echo "uncommitted product work" > "$D/product/scratch.md"
reset_rig
END_SESSION_SECOND_REPO_CHECK=1 END_SESSION_SECOND_REPOS="$D/product" run_end_session
out_f7="$(cat "$D/last_out")"; rc_f7="$(cat "$D/last_rc")"
check "F7 dirty product tree refuses the close" "$rc_f7" "1"
case "$out_f7" in *DIRTY*) ok "F8 dirty product refusal says DIRTY and names the repo";; *) bad "F8 dirty product refusal says DIRTY";; esac
rm -f "$D/product/scratch.md"

# =============================================================================
echo "== (G) land-push HANGS -> bounded REFUSE, never an infinite close =="
# D2: `bash land-push.sh` used to run with no timeout, no </dev/null and no GIT_TERMINAL_PROMPT=0,
# so a credential prompt or black-holed remote hung session close FOREVER. This stub sleeps well
# past the timeout; the close must come back, non-zero, inside the bound.
reset_rig
cat > "$D/land-push.sh" <<'PUSH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PUSH_LOG"
sleep 30
exit 0
PUSH
chmod +x "$D/land-push.sh"
g_start="$(date +%s)"
END_SESSION_PUSH_TIMEOUT=2 run_end_session
g_elapsed=$(( $(date +%s) - g_start ))
out_g="$(cat "$D/last_out")"; rc_g="$(cat "$D/last_rc")"
check "G1 script exits non-zero when land-push hangs" "$rc_g" "1"
# The real assertion: it CAME BACK. Without the timeout this test would never reach this line
# (the 30s sleep would outlast the 2s bound and block the whole suite) — remove the bound and
# G2 blows through its ceiling. Ceiling is generous vs the 2s timeout to stay CI-stable.
[ "$g_elapsed" -lt 20 ] && ok "G2 close returned in ${g_elapsed}s — bounded, did NOT hang" \
                         || bad "G2 close took ${g_elapsed}s — the land-push bound is not holding"
case "$out_g" in *"timed out"*) ok "G3 refusal names the timeout as the reason";; *) bad "G3 refusal names the timeout (out: $(printf '%s' "$out_g" | tail -3 | tr '\n' ' '))";; esac
case "$out_g" in *CLOSED*) bad "G4 no CLOSED print after a timed-out push";; *) ok "G4 no CLOSED print after a timed-out push";; esac
# G5: stdin must be EOF inside land-push — a credential prompt can then never wait on a human.
cat > "$D/land-push.sh" <<'PUSH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PUSH_LOG"
if read -r _line; then echo "STDIN-READABLE" >> "$PUSH_LOG"; else echo "STDIN-EOF" >> "$PUSH_LOG"; fi
echo "TERMPROMPT=${GIT_TERMINAL_PROMPT:-unset}" >> "$PUSH_LOG"
git -C "$2" push origin "$1" 2>>"$PUSH_LOG"
exit "$?"
PUSH
chmod +x "$D/land-push.sh"
reset_rig
run_end_session
grep -q 'STDIN-EOF' "$D/push.log" && ok "G5 land-push runs with stdin at EOF (cannot block on a prompt)" \
                                   || bad "G5 land-push stdin is EOF (log: $(tr '\n' ' ' < "$D/push.log"))"
grep -q 'TERMPROMPT=0' "$D/push.log" && ok "G6 GIT_TERMINAL_PROMPT=0 is exported into land-push" \
                                      || bad "G6 GIT_TERMINAL_PROMPT=0 exported (log: $(tr '\n' ' ' < "$D/push.log"))"

rm -rf "$D"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL END-SESSION-PUSH TESTS PASS"
