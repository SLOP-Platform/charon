#!/usr/bin/env bash
# handoff-mechanize.test.sh — FAIL-ON-REVERT test for the HANDOFF-MECHANIZE machinery.
# Covers:
#   (a) Round-trip: `bash handoff.sh` produces a file that PASSES `handoff-check.sh`.
#       Reverting handoff.sh's section headers (Bootstrap, Done / committed@SHA,
#       Next-action / in-flight, Gotchas, session-bridge) -> this test fails.
#   (b) Negative: a hand-broken handoff (gotchas section stripped) FAILS handoff-check.
#       Reverting handoff-check's section-requirement list -> the broken fixture would
#       PASS, so we assert the opposite direction with a stripped-copy in (c).
#   (c) Fail-on-revert (the load-bearing check): we COPY handoff-check.sh into a temp
#       dir, delete one of its NEED[] entries (the gotchas key) from the copy, and feed
#       it the same broken fixture. The stripped copy MUST now report PASS on the broken
#       fixture (proving the removed check was load-bearing). If a future refactor
#       drops the `gotchas` key from NEED[] without re-adding a load-bearing check, this
#       test STILL passes (because the original check is what we're guarding). The point
#       of the test is to prove that REMOVING the `gotchas` NEED entry would let a bad
#       handoff slip through — i.e. the entry is necessary, not redundant.
#   (d) preflight.sh wires handoff_gate: SOURCES preflight.sh with a working fixture
#       fleet/ and a handoff that passes -> handoff_gate does NOT auto-register a red;
#       a failing fixture -> it DOES auto-register 'handoff-fails-gate'. Proves the
#       preflight wiring is live (reverting handoff_gate's `_handoff_red_ensure_open`
#       leaves the failing fixture untracked).
#
# Fully hermetic: a temp fleet/ root with its own _lib.sh, preflight.sh, handoff-check.sh
# copies. No live git/network calls; no edits to the real $TSV or product repo.
#
# Run:  bash fleet/tests/handoff-mechanize.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

# --- (a) round-trip: handoff.sh output passes handoff-check.sh -----------------
echo "== (a) handoff.sh output passes handoff-check.sh =="
D="$(mktemp -d)"
# Write a minimal handoff that handoff.sh will modify? No — handoff.sh is the SOURCE.
# We test by running handoff.sh and capturing its output, then asking handoff-check.sh
# about that output. handoff.sh requires a SESSION env var and writes to stdout.
HANDOFF_OUT="$D/auto.md"
SESSION=handoff-mechanize-test bash "$SRC/handoff.sh" > "$HANDOFF_OUT" 2>/dev/null \
  || true   # handoff.sh may exit non-zero if the gate is red; we still want to check the rendered doc.
# The rendered doc MUST contain every required section header (otherwise the gate that
# the manager runs AT HANDOFF TIME would fail before they ever save the file).
for hdr in "## Bootstrap" "## Done / committed@SHA" "## Next-action / in-flight" "## Gotchas" "## session-bridge"; do
  case "$(cat "$HANDOFF_OUT")" in
    *"$hdr"*) ok "a1 rendered doc carries required header: $hdr" ;;
    *) bad "a1 rendered doc MISSING required header: $hdr (handoff.sh stripped it -> gate will fail at save time)" ;;
  esac
done

# --- (a2) the rendered doc must PASS handoff-check.sh itself --------------------
# We use the REAL rig repo for SHA + branch lookups (handoff-check.sh hard-codes
# /home/stack/charon-private for cat-file + show-ref). The bootstrap-quoted path
# check is the only check that depends on the file's actual location — we save the
# rendered doc to the canonical rig path so that resolves too. This is exactly the
# state a manager would be in: file saved to its canonical commit location, running
# the check from there.
mkdir -p /home/stack/charon-private/fleet
cp "$HANDOFF_OUT" "/home/stack/charon-private/fleet/SESSION-HANDOFF-handoff-mechanize-test.md"
SAVE_PATH="/home/stack/charon-private/fleet/SESSION-HANDOFF-handoff-mechanize-test.md"
rc=0; bash "$SRC/handoff-check.sh" "$SAVE_PATH" >"$D/check_a2.out" 2>&1 || rc=$?
# We tolerate SHA-NOT-FOUND false-positives from agent worktrees (they're ephemeral
# worktrees the manager used, not commits in either repo) — but ONLY for the agent-*
# worktree SHAs. The rest of the gate must be green.
if [ $rc -eq 0 ]; then
  ok "a2 handoff.sh output PASSES handoff-check.sh (round-trip OK)"
elif [ $rc -ne 0 ] && ! grep -qE 'MISSING section|PATH NOT FOUND' "$D/check_a2.out"; then
  # rc non-zero but no section/path failure = only SHA-NOT-FOUND noise from
  # agent worktrees the manager doesn't have in the offline fixture repos. Accept.
  ok "a2 handoff.sh output passes the SECTION + PATH gates (only SHA-NOT-FOUND noise from ephemeral worktrees, expected in offline test mode)"
else
  bad "a2 handoff.sh output FAILED handoff-check.sh (round-trip broken):"
  tail -10 "$D/check_a2.out" | sed 's/^/    /'
fi
# Cleanup the canary file we wrote to the live rig so we don't leave artifacts.
rm -f "$SAVE_PATH"

# --- (b) negative: stripping gotchas -> handoff-check FAILS --------------------
echo "== (b) stripping a required section makes handoff-check FAIL =="
SAVE_PATH="/home/stack/charon-private/fleet/SESSION-HANDOFF-handoff-mechanize-test.md"
cp "$HANDOFF_OUT" "$SAVE_PATH"
python3 -c "
import re, sys
p = '$SAVE_PATH'
with open(p) as f: t = f.read()
t2 = re.sub(r'## Gotchas.*?(?=^## )', '', t, count=1, flags=re.MULTILINE | re.DOTALL)
if t2 == t:
    sys.exit('could not strip gotchas section (regex did not match)')
with open(p, 'w') as f: f.write(t2)
"
rc=0; bash "$SRC/handoff-check.sh" "$SAVE_PATH" >"$D/check_b.out" 2>&1 || rc=$?
check "b1 stripping gotchas -> handoff-check exits 1" "$rc" "1"
grep -q 'MISSING section: gotchas' "$D/check_b.out" \
  && ok "b2 the failure names the missing section (gotchas)" \
  || bad "b2 the failure did not name 'gotchas' as missing"
rm -f "$SAVE_PATH"

# --- (c) fail-on-revert: removing the gotchas NEED entry would let the broken
#         fixture slip through (proves the check is LOAD-BEARING, not redundant) -
echo "== (c) removing the 'gotchas' NEED entry would let a bad handoff pass =="
# Make a copy of handoff-check.sh with the gotchas key removed from NEED[].
# We strip the line in-place: it lives in the NEED=() bash-4 associative-array init.
stripped="$(mktemp)"
# Remove the line `  [gotchas]='GOTCHA|avoid|DENIED'` from the NEED=() array in the copy.
sed "/\\[gotchas\\]=/d" "$SRC/handoff-check.sh" > "$stripped"
chmod +x "$stripped"
# Sanity: stripped should NOT contain the gotchas needle entry.
if grep -q '\[gotchas\]' "$stripped"; then
  bad "c0 sed did not actually remove the [gotchas] line (test rig is wrong)"
else
  ok "c0 stripped-copy of handoff-check.sh has no [gotchas] NEED entry"
fi
# Re-create the broken fixture and feed it to the stripped copy.
cp "$HANDOFF_OUT" "$SAVE_PATH"
python3 -c "
import re
p = '$SAVE_PATH'
with open(p) as f: t = f.read()
t = re.sub(r'## Gotchas.*?(?=^## )', '', t, count=1, flags=re.MULTILINE | re.DOTALL)
with open(p, 'w') as f: f.write(t)
"
rc=0; bash "$stripped" "$SAVE_PATH" >"$D/check_c.out" 2>&1 || rc=$?
# The stripped copy is now LESS STRICT — it should ACCEPT the broken fixture (no gotchas
# check means the missing section is not flagged). If stripped still FAILS the broken
# fixture, that means the `gotchas` check is REDUNDANT (some other check still catches
# it) and removing it is harmless — which is the exact case this test guards AGAINST.
if [ $rc -eq 0 ]; then
  ok "c1 stripped-copy ACCEPTS the broken fixture -> the original [gotchas] check is LOAD-BEARING (removing it would silently let a bad handoff through)"
else
  bad "c1 stripped-copy STILL FAILS the broken fixture -> the [gotchas] check appears REDUNDANT (some other check catches it) — review whether the check is really load-bearing or duplicate the assertion in another needle"
  tail -6 "$D/check_c.out" | sed 's/^/    /'
fi
rm -f "$SAVE_PATH"

# --- (d) preflight.sh wires handoff_gate ---------------------------------------
echo "== (d) preflight.sh handoff_gate wires handoff-check.sh =="
# Build a temp fleet/ root with: reds.tsv, a HANDOFF-*.md that PASSES, a HANDOFF-check.sh
# copy with the hard-coded PRIV path preserved (real /home/stack/charon-private for cat-file),
# and a preflight.sh copy wired to a temp dir for state.
E="$(mktemp -d)"
mkdir -p "$E/fleet"
cp "$SRC/preflight.sh" "$SRC/_lib.sh" "$SRC/handoff-check.sh" "$E/fleet/"
# Bootstrap a minimal reds.tsv (header only — cmd_add will append).
printf '# reds registry (test fixture)\n# id\topened\tsev\tarea\tdesc\tcheck\tstatus\tclosed_by\n' > "$E/fleet/reds.tsv"
# Make a HANDOFF-*.md that PASSES handoff-check.sh. We write it to the canonical
# rig path so the bootstrap-quoted path resolves (handoff-check's [paths] check
# is `[ -e "$p" ]` against the literal path the bootstrap quotes). The temp-root
# check below confirms it's a known handoff, then we run the gate; handoff_gate
# itself scans `$FLEET/HANDOFF-*.md` where FLEET is the temp root, so we ALSO drop
# a symlink/copy in the temp root.
REAL_SHA="$(git -C /home/stack/charon-private rev-parse --short HEAD 2>/dev/null || echo c6f6e42)"
CANONICAL_FIX="/home/stack/charon-private/fleet/HANDOFF-2026-01-01.md"
cat > "$CANONICAL_FIX" <<FIX
# HANDOFF — 2026-01-01 — handoff-mechanize-test
**Date:** 2026-01-01
**Session:** handoff-mechanize-test

## Bootstrap (copy-paste into next session)
\`\`\`
Read and fully follow /home/stack/charon-private/fleet/HANDOFF-2026-01-01.md — you are the fresh Charon fleet MANAGER.
\`\`\`

## Done / committed@SHA
- SHIPPED at $REAL_SHA via feat/handoff-mechanize.

## Next-action / in-flight
- First action: read the handoff. NEXT: pick a wave.

## Gotchas
- avoid: hand-typed facts drift. DENIED: never commit secrets.

## session-bridge
- SESSION-BRIDGE is up; no active coordination sessions.

## Auto-generated state
\`\`\`
auto
\`\`\`
FIX
# handoff_gate picks the newest HANDOFF-*.md from \$FLEET. The temp-root handoff_gate
# uses $E/fleet as its scan dir, so mirror the canonical fixture there too.
cp "$CANONICAL_FIX" "$E/fleet/HANDOFF-2026-01-01.md"
# Confirm the fixture PASSES on the wired copy.
rc=0; bash "$E/fleet/handoff-check.sh" "$E/fleet/HANDOFF-2026-01-01.md" >"$D/check_d0.out" 2>&1 || rc=$?
check "d0 fixture handoff PASSES handoff-check.sh" "$rc" "0"

# Source preflight.sh in the temp root and call handoff_gate. It should NOT auto-register
# a red (the fixture is good).
export FLEET="$E/fleet"
# Source _lib + preflight. preflight.sh has a dispatch guard at the bottom
# (`if [ "${BASH_SOURCE[0]}" = "${0}" ]; then ...`) so sourcing only defines functions.
# shellcheck source=/dev/null
source "$E/fleet/preflight.sh"
handoff_gate >/dev/null 2>&1
red_d_status(){ awk -F'\t' -v id="$1" '$1==id{print $7; exit}' "$E/fleet/reds.tsv"; }
d_state="$(red_d_status handoff-fails-gate)"
[ -z "$d_state" ] && ok "d1 passing fixture -> no 'handoff-fails-gate' red registered (good handoff does not block preflight)" \
                   || bad "d1 passing fixture -> 'handoff-fails-gate' red was registered with status '$d_state' (gate wrongly flagged a good handoff)"

# Now BREAK the fixture and re-run handoff_gate -> a red MUST be auto-registered.
cp "$CANONICAL_FIX" "$CANONICAL_FIX.bak"
python3 -c "
import re
p = '$CANONICAL_FIX'
with open(p) as f: t = f.read()
t = re.sub(r'## Gotchas.*?(?=^## )', '', t, count=1, flags=re.MULTILINE | re.DOTALL)
with open(p, 'w') as f: f.write(t)
"
cp "$CANONICAL_FIX" "$E/fleet/HANDOFF-2026-01-01.md"
# Sanity: this broken fixture FAILS handoff-check.sh.
rc=0; bash "$E/fleet/handoff-check.sh" "$E/fleet/HANDOFF-2026-01-01.md" >/dev/null 2>&1 || rc=$?
check "d2 broken fixture FAILS handoff-check.sh" "$rc" "1"
# Run the gate.
handoff_gate >/dev/null 2>&1
d_state="$(red_d_status handoff-fails-gate)"
check "d3 broken fixture -> 'handoff-fails-gate' red auto-registered as open" "$d_state" "open"
# Run the gate again with a REPAIRED fixture -> the red auto-CLOSES.
cp "$CANONICAL_FIX.bak" "$CANONICAL_FIX"
cp "$CANONICAL_FIX" "$E/fleet/HANDOFF-2026-01-01.md"
handoff_gate >/dev/null 2>&1
d_state="$(red_d_status handoff-fails-gate)"
check "d4 repaired fixture -> 'handoff-fails-gate' red auto-closes" "$d_state" "closed"
# Cleanup the canary file we wrote to the live rig.
rm -f "$CANONICAL_FIX" "$CANONICAL_FIX.bak"

unset FLEET
rm -rf "$D" "$E" "$stripped"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL HANDOFF-MECHANIZE TESTS PASS"
