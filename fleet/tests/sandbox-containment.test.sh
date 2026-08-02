#!/usr/bin/env bash
# sandbox-containment.test.sh — FAIL-ON-REVERT self-test for the 2026-08-01 sandbox incident.
#
# Subjects:
#   fleet/tests/lib/sandbox.sh          (containment + fail-closed helpers)
#   fleet/checks/sandbox-containment.sh (the merge-blocking static/residue guard)
#
# GREEN IS NOT PROOF, so every block below pairs the FIXED behaviour with the REVERTED
# behaviour and asserts they DIFFER. A block that only asserted "the fix works" would still
# pass if the fix were deleted and the assertion happened to hold for another reason. The
# revert arms here are literal re-creations of the pre-fix code, run against the same fixture.
#
# The incident, in one line: `mktemp -d` roots at $TMPDIR, nothing constrained $TMPDIR, so
# test sandboxes were built INSIDE the repo — and when one vanished, tests running under
# `set -uo pipefail` (no `-e`) fell through a failed `cd` and committed to the LIVE checkout.
# 16 `t <t@t>` commits and an `f.txt` blob reached origin/master that way.
#
# Run:  bash fleet/tests/sandbox-containment.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
# shellcheck source=fleet/tests/lib/sandbox.sh
source "$SRC/tests/lib/sandbox.sh"
CHECK="$SRC/checks/sandbox-containment.sh"

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(sandbox_mk sandbox-containment-test)"
trap "rm -rf $(printf '%q' "$D")" EXIT

# A stand-in for "the live checkout": a real git repo that NOTHING in this test may commit to.
# Using a real repo rather than asserting on strings is the point — the incident was a real
# commit landing in a real repo, so the assertion is "is the commit count still zero".
LIVE="$D/live-checkout"
git init -q "$LIVE"
git -C "$LIVE" config user.email live@live; git -C "$LIVE" config user.name live
printf 'real\n' > "$LIVE/real.txt"
git -C "$LIVE" add real.txt
git -C "$LIVE" commit -q -m base
live_commits(){ git -C "$LIVE" rev-list --count HEAD 2>/dev/null || echo -1; }
BASE_COMMITS="$(live_commits)"

echo "== (a) CONTAINMENT: an in-tree TMPDIR must be REJECTED, not honoured =="
# The exact shape that produced fleet/state/tmpdir-land/ and scratch/fleet-copy/: a caller
# exports a TMPDIR that happens to be inside a git work tree.
INTREE="$LIVE/state/tmpdir-land"
mkdir -p "$INTREE"

got="$(TMPDIR="$INTREE" sandbox_mk probe 2>/dev/null)"
if [ -n "$got" ] && [ -d "$got" ]; then
  ok "a1 sandbox_mk still returned a usable dir (it must not simply die on a bad TMPDIR)"
else
  bad "a1 sandbox_mk returned no usable dir (got '$got')"
fi
case "$got" in
  "$LIVE"/*) bad "a2 CONTAINMENT BROKEN — sandbox was created inside the work tree: $got" ;;
  *)         ok  "a2 sandbox is OUTSIDE the work tree despite an in-tree TMPDIR ($got)" ;;
esac
rm -rf "$got"

# REVERT ARM: the pre-fix behaviour was a bare `mktemp -d`, which honours $TMPDIR blindly.
# If this arm did NOT land inside the work tree, block (a) would be vacuous.
reverted="$(TMPDIR="$INTREE" mktemp -d)"
case "$reverted" in
  "$LIVE"/*) ok  "a3 FAIL-ON-REVERT armed — bare 'mktemp -d' DOES land in-tree ($reverted)" ;;
  *)         bad "a3 revert arm did not reproduce the defect; block (a) proves nothing" ;;
esac
rm -rf "$reverted"

echo "== (b) FAIL-CLOSED: a vanished sandbox must ABORT, never fall through to \$PWD =="
# Reproduce the exact incident conditions: `set -uo pipefail` (NO -e), a process-wide
# GIT_AUTHOR_EMAIL=t@t, a sandbox path that has been deleted, and a `cd` into it followed by
# git writes. Run with CWD = the live checkout, which is what a droid tab actually has.
GONE="$D/deleted-sandbox"

cat > "$D/fixed.sh" <<FIXED
set -uo pipefail
source "$SRC/tests/lib/sandbox.sh"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
( sandbox_cd "$GONE"
  echo one > f.txt && git add f.txt && git commit --quiet -m c1 )
FIXED

cat > "$D/reverted.sh" <<REVERTED
set -uo pipefail
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
( cd "$GONE"
  echo one > f.txt && git add f.txt && git commit --quiet -m c1 )
REVERTED

before="$(live_commits)"
( cd "$LIVE" && bash "$D/fixed.sh" ) >/dev/null 2>&1
rc_fixed=$?
after_fixed="$(live_commits)"
[ "$after_fixed" = "$before" ] \
  && ok "b1 FIXED: sandbox_cd wrote NOTHING to the live checkout (commits still $after_fixed)" \
  || bad "b1 FIXED path committed to the live checkout ($before -> $after_fixed)"
[ "$rc_fixed" -ne 0 ] \
  && ok "b2 FIXED: aborted LOUDLY with a non-zero exit ($rc_fixed), not a silent skip" \
  || bad "b2 FIXED path exited 0 — a vanished sandbox must never look like success"
[ -f "$LIVE/f.txt" ] \
  && bad "b3 FIXED path created f.txt in the live checkout" \
  || ok  "b3 FIXED: no stray f.txt in the live checkout"

# REVERT ARM: plain `cd`. This is the code that actually put `f.txt` and 16 `t <t@t>`
# commits on origin/master. It MUST reproduce here, or block (b) proves nothing.
before="$(live_commits)"
( cd "$LIVE" && bash "$D/reverted.sh" ) >/dev/null 2>&1
after_rev="$(live_commits)"
if [ "$after_rev" -gt "$before" ]; then
  ok "b4 FAIL-ON-REVERT armed — plain 'cd' DID commit to the live checkout ($before -> $after_rev)"
  auth="$(git -C "$LIVE" log -1 --format='%an <%ae>')"
  [ "$auth" = "t <t@t>" ] \
    && ok "b5 revert arm reproduces the exact incident signature: author $auth" \
    || bad "b5 revert arm committed but with author '$auth' (expected 't <t@t>')"
  git -C "$LIVE" reset -q --hard "HEAD~$((after_rev - before))"
  rm -f "$LIVE/f.txt"
else
  bad "b4 revert arm did not reproduce the defect; block (b) proves nothing"
fi

echo "== (e) ESCAPING DELETE: cleanup must never rm -rf ABOVE its own sandbox =="
# The dominant root cause, reproduced exactly: a fixture builder that returns the mktemp dir
# ITSELF, plus a cleanup that deletes `dirname` of it — which is $TMPDIR, the root shared by
# every concurrent test. This is what made fleet/gate.sh unrunnable (124/124 "killed").
E_ROOT="$D/escape-root"
mkdir -p "$E_ROOT"
mk_victim(){ mkdir -p "$E_ROOT/victim-sandbox"; echo x > "$E_ROOT/victim-sandbox/fixture"; }

# FIXED arm: sandbox_rm refuses the parent and the victim survives.
mk_victim
mine="$(TMPDIR="$E_ROOT" sandbox_mk escaper)"
( TMPDIR="$E_ROOT" sandbox_rm "$(dirname "$mine")" ) >/dev/null 2>&1
rc_esc=$?
[ "$rc_esc" -ne 0 ] \
  && ok "e1 FIXED: sandbox_rm REFUSED to delete the temp root (exit $rc_esc)" \
  || bad "e1 sandbox_rm deleted the temp root — the gate-killer is still live"
[ -f "$E_ROOT/victim-sandbox/fixture" ] \
  && ok "e2 FIXED: a CONCURRENT test's sandbox survived the cleanup" \
  || bad "e2 a concurrent test's sandbox was destroyed by another test's cleanup"

# REVERT ARM: the literal pre-fix line. It must destroy the victim, or block (e) is vacuous.
mk_victim
rm -rf "$(dirname "$mine")"
[ -f "$E_ROOT/victim-sandbox/fixture" ] \
  && bad "e3 revert arm did not reproduce the defect; block (e) proves nothing" \
  || ok  "e3 FAIL-ON-REVERT armed — plain 'rm -rf \$(dirname ...)' DID destroy the sibling sandbox"
mkdir -p "$E_ROOT"

echo "== (c) the CHECK catches a fire-time EXIT-trap expansion over a local =="
mkdir -p "$D/scan/checks" "$D/scan/hooks"
cat > "$D/scan/offender.sh" <<'OFF'
#!/usr/bin/env bash
run_it(){
  local TMPDIR; TMPDIR="$(mktemp -d)"
  trap 'rm -rf "$TMPDIR"' EXIT
}
OFF
out="$(SANDBOX_CHECK_SCAN_DIR="$D/scan" SANDBOX_CHECK_ROOT="$D/scan" bash "$CHECK" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "c1 check REDs on the review-pool.sh defect shape" \
                || bad "c1 check passed the defect shape (rc=$rc) — it would not have caught the incident"
case "$out" in *"assigns TMPDIR"*) ok "c2 names the TMPDIR-capture half" ;; *) bad "c2 did not name TMPDIR capture" ;; esac
case "$out" in *"expands \$TMPDIR"*) ok "c3 names the fire-time-expansion half" ;; *) bad "c3 did not name the trap expansion ($out)" ;; esac

# Correct shapes must stay GREEN, or the check gets disabled instead of obeyed.
rm -f "$D/scan/offender.sh"
cat > "$D/scan/good.sh" <<'GOOD'
#!/usr/bin/env bash
MY_WORK="$(mktemp -d)"; trap "rm -rf $(printf '%q' "$MY_WORK")" EXIT
run_it(){
  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
}
other(){ echo "${TMPDIR:-/tmp}"; }
GOOD
SANDBOX_CHECK_SCAN_DIR="$D/scan" SANDBOX_CHECK_ROOT="$D/scan" bash "$CHECK" >/dev/null 2>&1 \
  && ok "c4 correct shapes stay GREEN (definition-time trap, RETURN trap, TMPDIR read)" \
  || bad "c4 FALSE POSITIVE on correct code — a noisy gate is a disabled gate"

echo "== (d) the CHECK catches in-tree sandbox residue =="
mkdir -p "$D/scan/fleet-copy/state/pytmp-inert/x"
out="$(SANDBOX_CHECK_SCAN_DIR="$D/scan" SANDBOX_CHECK_ROOT="$D/scan" bash "$CHECK" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "d1 check REDs on in-tree sandbox residue" \
                || bad "d1 check ignored in-tree residue — the exit-128 tab-killer would recur"
case "$out" in *fleet-copy*) ok "d2 names the offending directory" ;; *) bad "d2 did not name the directory" ;; esac
rm -rf "$D/scan/fleet-copy"

echo
echo "sandbox-containment.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
