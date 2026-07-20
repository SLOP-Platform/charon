#!/usr/bin/env bash
# handoff-generated-state.test.sh — proves fleet/handoff.sh GENERATES a verifiable truth-of-record
# state block instead of letting a session hand-assert state prose that can lie (operator-flagged
# failure: "PR #103 can't merge" was FALSE and passed the handoff gate).
#
# This is a test of handoff.sh's OUTPUT + its shared generator (fleet/handoff-generated-state.sh).
# It is NOT a gate — it asserts the block is PRODUCED and that generation FAILS SOFT when gh /
# the git remote is DOWN (the 2026-07-19 GitHub-outage class must never HANG or omit state).
#
# Fully self-contained: a gh stub that exits non-zero simulates the outage; nonexistent repo paths
# make `git ls-remote` fail; a tiny HANDOFF_STATE_TIMEOUT proves no hang. Each RED is demonstrated
# by NEUTERING a scratchpad COPY of the generator (never the real file).
#
# Run:  bash fleet/tests/handoff-generated-state.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GEN="$SRC/handoff-generated-state.sh"
HANDOFF="$SRC/handoff.sh"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }
D="$(mktemp -d)"

# A gh stub that ALWAYS fails — simulates a GitHub/gh outage at generation time.
STUB="$D/stub"; mkdir -p "$STUB"
cat > "$STUB/gh" <<'EOF'
#!/usr/bin/env bash
exit 7
EOF
chmod +x "$STUB/gh"

# --- (a) the generator produces a well-formed block against LIVE repos --------------------------
echo "== (a) emit_generated_state produces a delimited, timestamped, machine-parseable block =="
A="$D/a.out"
( set +e; source "$GEN"; emit_generated_state ) > "$A" 2>/dev/null
grep -qE '<!-- GENERATED-STATE v1 \(do not hand-edit\) generated=[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z -->' "$A" \
  && ok "a1 opening marker carries an ISO8601 generated= timestamp" \
  || bad "a1 opening marker / generated= timestamp missing"
grep -q '<!-- /GENERATED-STATE -->' "$A" && ok "a2 closing marker present" || bad "a2 closing marker missing"
grep -qE '^origin-master product = ' "$A" && ok "a3 machine-parseable product SHA line present" || bad "a3 product SHA line missing"
grep -qE '^origin-master rig = '     "$A" && ok "a4 machine-parseable rig SHA line present"     || bad "a4 rig SHA line missing"
grep -qE 'Open PRs — product' "$A" && grep -qE 'Open PRs — rig' "$A" \
  && ok "a5 open-PR sections present for both repos" || bad "a5 open-PR sections missing"
grep -qE 'stranded-work signal' "$A" && ok "a6 stranded-work (ahead/uncommitted) section present" || bad "a6 stranded-work section missing"

# --- (b) RESILIENCE: gh DOWN + remotes unreachable -> block STILL emitted, marked UNAVAILABLE,
#         does NOT hang, exits clean. This is the 2026-07-19 outage class. ----------------------
echo "== (b) gh/network DOWN at generation -> block still emitted with UNAVAILABLE, no hang =="
B="$D/b.out"
t0=$(date +%s)
( set +e
  export PATH="$STUB:$PATH"
  export CHARON_PRODUCT_REPO="$D/no-such-product" CHARON_RIG_REPO="$D/no-such-rig"
  export HANDOFF_STATE_TIMEOUT=3
  source "$GEN"; emit_generated_state
) > "$B" 2>/dev/null
rc=$?
t1=$(date +%s)
check "b1 generator exits 0 even with gh down + bad repos" "$rc" "0"
grep -q '<!-- GENERATED-STATE v1' "$B" && ok "b2 block STILL emitted during outage (not aborted)" || bad "b2 block missing during outage"
grep -qE '^origin-master product = UNAVAILABLE' "$B" \
  && ok "b3 product SHA line EMITTED and marked UNAVAILABLE (not omitted, not fabricated)" \
  || bad "b3 product SHA line not marked UNAVAILABLE"
grep -qE '^origin-master rig = UNAVAILABLE' "$B" \
  && ok "b4 rig SHA line EMITTED and marked UNAVAILABLE" || bad "b4 rig SHA line not marked UNAVAILABLE"
grep -q 'UNAVAILABLE (gh/network down at generation)' "$B" \
  && ok "b5 open-PR section EMITTED and marked UNAVAILABLE" || bad "b5 open-PR UNAVAILABLE marker missing"
# No-hang: 2 SHA + 2x2 PR probes each bounded at 3s; must finish well under a hang threshold.
elapsed=$((t1 - t0))
[ "$elapsed" -le 40 ] && ok "b6 generation did NOT hang under outage (${elapsed}s <= 40s bound)" \
                      || bad "b6 generation took ${elapsed}s — timeout-bounding regressed (would hang a handoff)"

# --- (c) handoff.sh WIRES the generator: its rendered doc contains the block --------------------
echo "== (c) handoff.sh output contains the GENERATED-STATE block (wiring proof) =="
C="$D/c.out"
# CHARON_GATE_ACTIVE=1 trips handoff.sh's reentrancy guard so it SKIPS the heavy gate.sh run.
SESSION=gen-state-test CHARON_GATE_ACTIVE=1 HANDOFF_STATE_TIMEOUT=10 timeout 120 bash "$HANDOFF" > "$C" 2>/dev/null
crc=$?
check "c0 handoff.sh exits 0 (gate skipped via reentrancy guard)" "$crc" "0"
grep -q '<!-- GENERATED-STATE v1' "$C" && grep -q '<!-- /GENERATED-STATE -->' "$C" \
  && ok "c1 handoff.sh emits the GENERATED-STATE block (generation is wired)" \
  || bad "c1 handoff.sh did NOT emit the block — emit_generated_state call is unwired"
grep -qE '^origin-master product = ' "$C" \
  && ok "c2 handoff.sh block carries the machine-parseable SHA lines" || bad "c2 SHA lines missing from handoff.sh output"

# --- (d) RED demonstration #1: neuter the OPENING MARKER on a scratchpad copy -------------------
#   Proves the block-presence assertions (a1/b2/c1) are load-bearing: strip the marker from a COPY
#   and the block is no longer detectable.
echo "== (d) RED: removing the opening marker from a copy makes the block undetectable =="
CP="$D/gen-nomarker.sh"
sed 's/<!-- GENERATED-STATE v1 (do not hand-edit) generated=%s -->/GENERATED-STATE-MARKER-REMOVED/' "$GEN" > "$CP"
DN="$D/d.out"
( set +e; source "$CP"; emit_generated_state ) > "$DN" 2>/dev/null
if grep -q '<!-- GENERATED-STATE v1' "$DN"; then
  bad "d1 neutered copy STILL shows the marker — sed target drifted (test rig wrong)"
else
  ok "d1 neutered copy has NO opening marker -> the marker check is LOAD-BEARING (a real regression would be caught)"
fi

# --- (e) RED demonstration #2: neuter the "always emit the SHA line" fail-soft behavior ---------
#   Proves b3 is load-bearing: if the generator OMITS the SHA line on an outage (the old silent
#   behavior) instead of emitting it marked UNAVAILABLE, the outage block loses the line entirely.
echo "== (e) RED: dropping the emit-on-outage branch makes the block OMIT the SHA line =="
CP2="$D/gen-nofailsoft.sh"
# Turn the UNAVAILABLE branch that PRINTS the product SHA line into a no-op (silent omit).
python3 - "$GEN" "$CP2" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
t = open(src).read()
needle = "      printf 'origin-master product = %s  # %s (%s)\\n' \"$_HS_UNAVAIL\" \"$_HS_UNAVAIL_NOTE\" \"$PROD_SLUG\"\n"
assert needle in t, "emit-on-outage branch not found (test rig drifted)"
t = t.replace(needle, "      :\n", 1)   # silent omit instead of emitting the marked line
open(dst, 'w').write(t)
PY
EN="$D/e.out"
( set +e
  export PATH="$STUB:$PATH"
  export CHARON_PRODUCT_REPO="$D/no-such-product" CHARON_RIG_REPO="$D/no-such-rig"
  export HANDOFF_STATE_TIMEOUT=3
  source "$CP2"; emit_generated_state
) > "$EN" 2>/dev/null
if grep -qE '^origin-master product = ' "$EN"; then
  bad "e1 neutered copy STILL emits a product SHA line — omit didn't take (test rig wrong)"
else
  ok "e1 neutered copy OMITS the product SHA line during outage -> emitting-it-marked-UNAVAILABLE is LOAD-BEARING"
fi

rm -rf "$D"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL HANDOFF-GENERATED-STATE TESTS PASS"
