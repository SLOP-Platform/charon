#!/usr/bin/env bash
# submit-checkin.test.sh — FAIL-ON-REVERT test for the #10 auto-check-in fold-in
# (fleet/submit.sh AUTO CHECK-IN block). Proves that a successful submit AUTOMATICALLY
# produces a per-ticket check-in record in session-notes, in checkin.sh's exact format,
# and that a re-submit does NOT double-write it (idempotent).
#
# Runs submit.sh + checkin.sh from an ISOLATED temp fleet (copies resolve FLEET/state/board/
# session-notes into the temp dir) with a FAKE `gh` on PATH that reports an open PR — so the
# test never touches the live board, live state, or the network. Reverting the AUTO CHECK-IN
# block leaves no session-note -> (a)/(b)/(c) fail.
#
# Run:  bash fleet/tests/submit-checkin.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

ID="AUTO-CHECKIN-TEST"

# isolated temp fleet: copies of the two scripts + a board fixture + empty state/notes + fake gh.
# submit.sh sources repo-registry.sh (MULTI-REPO fold-in) — copy it too, or submit.sh dies
# with "No such file or directory" before it ever reaches the auto-check-in block.
D="$(mktemp -d)"
mkdir -p "$D/board" "$D/state/claims" "$D/session-notes" "$D/bin"
cp "$SRC/submit.sh" "$D/submit.sh"
cp "$SRC/checkin.sh" "$D/checkin.sh"
cp "$SRC/repo-registry.sh" "$D/repo-registry.sh"
cat > "$D/board/$ID.md" <<EOF
tier: economy
branch: feat/auto-checkin-test
owns: /home/stack/charon-private/fleet/submit.sh
scope: Verify the auto check-in fires on submit
EOF
# fake gh: any invocation reports PR #42 open (submit only calls `gh pr list ... -q .[0].number`).
cat > "$D/bin/gh" <<'EOF'
#!/usr/bin/env bash
echo 42
EOF
chmod +x "$D/bin/gh"

# SESSION is REQUIRED (RIG-REDS 2026-07-24). submit.sh's AUTO CHECK-IN block was later
# narrowed to fire ONLY for a NAMED session: with SESSION unset it deliberately writes
# NOTHING, because a `<UTC>-submit-auto.md` note is globbed by no reader (summary.sh /
# next.sh read `*-<SESSION>.md`) and strands untracked in the shared checkout, which is
# what makes land.sh refuse on a dirty tree (see submit.sh's "AUTO (droid) submit" note).
# This test still ran submit with SESSION UNSET, so it was asserting the pre-narrowing
# contract and had been red ever since. Drive the NAMED-session path here; case (d) below
# pins the no-SESSION skip so the narrowing itself is also fail-on-revert covered.
CI_SESSION="submit-checkin-test"
run_submit(){ ( cd "$D" && SESSION="$CI_SESSION" PATH="$D/bin:$PATH" bash "$D/submit.sh" "$ID" ); }
notes(){ cat "$D"/session-notes/*.md 2>/dev/null; }
header_count(){ grep -rcF "] $ID  $ID" "$D/session-notes" 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}'; }

echo "== (a) a successful submit writes a check-in record in checkin.sh's exact format =="
run_submit >/dev/null 2>&1
check "a1 header '[economy] $ID  $ID' present" \
  "$(notes | grep -cF "[economy] $ID  $ID")" "1"
check "a2 'Goal ' line present"  "$(notes | grep -cE '^  Goal ')"  "1"
check "a3 'Built ' line present" "$(notes | grep -cE '^  Built ')" "1"
check "a4 'Files ' line present" "$(notes | grep -cE '^  Files ')" "1"

echo "== (b) the gate context submit already has (open PR #) is threaded into the record =="
check "b1 'Gate  PR #42 open' present" "$(notes | grep -cF 'Gate  PR #42 open')" "1"
# submit itself still succeeded (state marker written)
[ -f "$D/state/submitted/$ID" ] && ok "b2 state/submitted/$ID written" || bad "b2 state/submitted/$ID written"

echo "== (c) re-submit is idempotent — no second check-in for the same ticket =="
run_submit >/dev/null 2>&1
check "c1 exactly ONE check-in header after two submits" "$(header_count)" "1"

echo "== (d) an UNNAMED (droid) submit writes NO check-in note — the narrowing is pinned =="
# Fail-on-revert for the narrowing itself: drop the `[ -z "${SESSION:-}" ]` skip in
# submit.sh and this case goes red (a `*-submit-auto.md` note appears that no reader globs).
D2="$(mktemp -d)"
mkdir -p "$D2/board" "$D2/state/claims" "$D2/session-notes" "$D2/bin"
cp "$SRC/submit.sh" "$SRC/checkin.sh" "$SRC/repo-registry.sh" "$D2/"
cp "$D/board/$ID.md" "$D2/board/$ID.md"
cp "$D/bin/gh" "$D2/bin/gh"
( cd "$D2" && env -u SESSION PATH="$D2/bin:$PATH" bash "$D2/submit.sh" "$ID" ) >/dev/null 2>&1
check "d1 no-SESSION submit still writes the submitted state marker" \
  "$([ -f "$D2/state/submitted/$ID" ] && echo 1 || echo 0)" "1"
check "d2 no-SESSION submit writes NO session-note (no dead submit-auto cruft)" \
  "$(find "$D2/session-notes" -name '*.md' | wc -l)" "0"
rm -rf "$D2"

rm -rf "$D"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL SUBMIT-CHECKIN TESTS PASS"
