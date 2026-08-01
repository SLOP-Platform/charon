#!/usr/bin/env bash
# gate-integrity.test.sh — RED-PROOF / fail-on-revert suite for fleet/checks/gate-integrity.sh.
#
# This suite guards THE GATE ON THE GATES, so it is held to that gate's own standard. Every
# assertion runs the REAL fleet/checks/gate-integrity.sh against a REAL (tiny) synthetic tree on
# disk. There is no stub of the detector, and no fixture seam inside the detector that these tests
# take: the synthetic trees exist so that a NEGATIVE case can be constructed (a gate that IS wired,
# with a test that IS allowlisted) — never because the production path is being skipped.
#
# Fail-on-revert: each numbered test names the specific clause of gate-integrity.sh that it goes
# RED on if reverted. Every one was verified by neutering that clause on a SCRATCHPAD COPY, never
# in-tree. Two of them (5, 6) encode defects this gate actually HAD during its own dogfooding.
#
# Hermetic: mktemp -d only. No network, no gh, no git writes to any real repo, no dependency on
# fleet/state/ (so it passes from a fresh checkout with an EMPTY state dir).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="$HERE/fleet/checks/gate-integrity.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ok   $*"; }
no(){ FAIL=$((FAIL+1)); echo "  FAIL $*"; }
chk(){ if [ "$2" = "$3" ]; then ok "$1"; else no "$1 (want '$3', got '$2')"; fi; }
has(){ if printf '%s' "$2" | grep -qF "$3"; then ok "$1"; else no "$1 (output lacked '$3')"; fi; }
hasnt(){ if printf '%s' "$2" | grep -qF "$3"; then no "$1 (output wrongly contained '$3')"; else ok "$1"; fi; }

TMPROOT="$(mktemp -d "${TMPDIR:-/tmp}/gate-integrity-test.XXXXXX")"
trap 'rm -rf "$TMPROOT"' EXIT

# Build a synthetic rig: one gate, optionally a caller, optionally a test, optionally allowlisted.
#   $2 wired=1     a non-test script actually invokes the gate
#   $3 claim=1     the gate's header claims it is wired into caller.sh
#   $4 test=1      a companion test exists   $5 allow=1 it is in CI_SUITES  $6 rc=1 it asserts rc!=0
mk(){
  local d="$1" wired="$2" claim="$3" tst="$4" allow="$5" rc="$6"
  mkdir -p "$d/fleet/checks" "$d/fleet/tests"
  {
    echo '#!/usr/bin/env bash'
    echo '# widget-guard.sh — a synthetic gate.'
    [ "$claim" = 1 ] && echo '# Wired into caller.sh as a blocking gate.'
    echo 'set -uo pipefail'
    echo 'exit 0'
  } > "$d/fleet/checks/widget-guard.sh"
  {
    echo '#!/usr/bin/env bash'
    echo '# a caller that mentions widget-guard.sh only in THIS comment'
    [ "$wired" = 1 ] && echo 'bash "$(dirname "$0")/checks/widget-guard.sh"   # trailing comment'
    echo 'exit 0'
  } > "$d/fleet/caller.sh"
  if [ "$tst" = 1 ]; then
    {
      echo '#!/usr/bin/env bash'
      echo '# suite for widget-guard.sh'
      echo 'bash widget-guard.sh; rc=$?'
      # The rc-assertion marker is written ONLY in the rc=1 variant. It has to carry no
      # "red-proof"/"fail-on-revert" wording otherwise, or _asserts_nonzero_rc matches the
      # HEADER and the rc=0 fixture stops being a negative case.
      [ "$rc" = 1 ] && echo '[ "$rc" = "1" ] || exit 1   # fail-on-revert: gate must go RED'
      echo 'exit 0'
    } > "$d/fleet/tests/widget-guard.test.sh"
  fi
  # The CI-scope stub lives OUTSIDE fleet/checks/ on purpose: anything in the checks dir is itself
  # a gate in this gate's universe, so a stub parked there generated its own G1/G3 findings and
  # every substring assertion below matched the STUB's finding instead of widget-guard's. That is
  # a fixture that makes the suite green for the wrong reason — the class under test.
  {
    echo '#!/usr/bin/env bash'
    echo 'CI_SUITES=('
    [ "$allow" = 1 ] && echo '  widget-guard.test.sh'
    echo ')'
    echo 'case "${1:-}" in suites) printf "%s\n" "${CI_SUITES[@]+${CI_SUITES[@]}}";; esac'
  } > "$d/fleet/ci-scope.sh"
}

run(){ # run <tree> <mode>
  GI_ROOT="$1" GI_CHECKS_DIR="$1/fleet/checks" GI_TESTS_DIR="$1/fleet/tests" \
  GI_CI_SCOPE="$1/fleet/ci-scope.sh" GI_GATE_EXTRAS=" " GI_UNENFORCED_MAX=99 \
  bash "$GATE" "${2:-scan}" 2>&1
}

echo "== G1 INERT: a gate nothing calls =="
# 1. Reverting _callers to count ANY mention (dropping the comment strip / the tests exclusion)
#    makes this GREEN — which is how a gate mentioned in twelve comments and invoked by none
#    stayed invisible.
T="$TMPROOT/g1"; mk "$T" 0 0 1 1 1
OUT="$(run "$T")"
has "1 unwired gate is reported INERT" "$OUT" "G1 INERT"
# 2. NEGATIVE CONTROL. Same tree, gate genuinely invoked. Without this a detector that always
#    says INERT would look perfect.
T="$TMPROOT/g1neg"; mk "$T" 1 0 1 1 1
OUT="$(run "$T")"
hasnt "2 a genuinely-wired gate is NOT reported INERT" "$OUT" "G1 INERT"

echo "== G2 FALSE-CLAIM: header asserts wiring that does not exist =="
# 3. This is the shape large-file-guard.sh shipped. Reverting the `_invokes` check to trust the
#    claim (or dropping the G2 block) makes it GREEN.
T="$TMPROOT/g2"; mk "$T" 0 1 1 1 1
OUT="$(run "$T")"
has "3 false wiring claim is reported" "$OUT" "G2 FALSE-CLAIM"
# 4. NEGATIVE CONTROL: the claim is TRUE (caller really invokes it) -> no finding.
T="$TMPROOT/g2neg"; mk "$T" 1 1 1 1 1
OUT="$(run "$T")"
hasnt "4 a TRUE wiring claim is not flagged" "$OUT" "G2 FALSE-CLAIM"

echo "== the two defects this gate itself had (regression locks) =="
# 5. PIPEFAIL/SIGPIPE MASK. `_invokes` was `sed ... | grep -qF`; grep -q exits on match, sed takes
#    SIGPIPE, pipefail promotes 141, and a TRUE match reads as NO MATCH — the fleet/land.sh:14
#    shape that went undetected.
#    THE FIXTURE SIZE IS LOAD-BEARING. Written first against a 3-line caller, this test passed
#    even with the buggy pipeline restored: sed finished before grep -q exited, so no SIGPIPE
#    ever occurred and the test proved nothing. That is this repo's fixture-bypass class inside
#    the suite guarding against it. The match must be at the TOP of a file long enough that sed
#    is still writing when grep exits — hence 20k trailing lines.
T="$TMPROOT/pipe"; mk "$T" 1 0 1 1 1
{ echo '#!/usr/bin/env bash'
  echo 'bash "$(dirname "$0")/checks/widget-guard.sh"   # trailing comment'
  awk 'BEGIN{for(i=0;i<20000;i++) print "# filler line to keep sed writing after grep -q exits"}'
} > "$T/fleet/caller.sh"
OUT="$(run "$T")"
hasnt "5 early match in a large file is still seen (no SIGPIPE/pipefail mask)" "$OUT" "G1 INERT"
# 6. DETERMINISM. The same defect made results vary run to run. Ten runs, one answer.
A=""; for _i in 1 2 3 4 5 6 7 8 9 10; do A="$A$(run "$T" | grep -c 'G1 INERT')"; done
chk "6 ten runs agree (deterministic)" "$A" "0000000000"

echo "== G3 UNPROVEN: can it fail? =="
# 7. No companion test at all.
T="$TMPROOT/g3a"; mk "$T" 1 0 0 0 0
OUT="$(run "$T")"
has "7 gate with no companion test is UNPROVEN" "$OUT" "has NO companion test"
# 8. Test exists but is NOT in the literal CI_SUITES allowlist — the land-safety.test.sh instance.
#    Reverting the allowlist lookup to "a test file exists" makes this GREEN, which is precisely
#    the over-claim this gate must never make.
T="$TMPROOT/g3b"; mk "$T" 1 0 1 0 1
OUT="$(run "$T")"
has "8 test outside CI_SUITES is UNPROVEN" "$OUT" "NOT in the LITERAL CI_SUITES allowlist"
# 9. Test exists, allowlisted, but never asserts a non-zero rc.
T="$TMPROOT/g3c"; mk "$T" 1 0 1 1 0
OUT="$(run "$T")"
has "9 test that never asserts rc!=0 is UNPROVEN" "$OUT" "never asserts a NON-ZERO rc"
# 10. NEGATIVE CONTROL: wired + tested + allowlisted + asserts rc -> no findings at all.
T="$TMPROOT/g3neg"; mk "$T" 1 1 1 1 1
OUT="$(run "$T")"
has "10 a fully-live gate yields zero findings" "$OUT" "0 finding(s)"

echo "== self-exclusion: the detector's own prose is not wiring =="
# 6c. gate-integrity.sh's finding MESSAGES name other gates in QUOTED strings, which comment-
#     stripping does not remove. Without self-exclusion the detector counts itself as a caller of
#     every gate it mentions and silently suppresses true G1 findings — it did exactly that to
#     gate-creation-standard.sh. The fixture plants a DECOY at the path _caller_files excludes
#     (fleet/checks/<this script's basename>) that "mentions" the gate on a non-comment line.
#     Reverting the `grep -vxF "$self_rel"` makes the decoy count as a caller and this goes RED.
T="$TMPROOT/self"; mk "$T" 0 0 1 1 1
printf '#!/usr/bin/env bash\nmsg="owned by widget-guard.sh; see there"\n' \
  > "$T/fleet/checks/$(basename "$GATE")"
OUT="$(GI_ROOT="$T" GI_CHECKS_DIR="$T/fleet/checks" GI_TESTS_DIR="$T/fleet/tests" \
       GI_CI_SCOPE="$T/fleet/ci-scope.sh" GI_GATE_EXTRAS=" " GI_UNENFORCED_MAX=99 \
       bash "$GATE" keys 2>&1)"
has "6c a decoy naming the gate in the detector's own file is NOT counted as a caller" \
  "$OUT" "G1:widget-guard.sh"

echo "== honesty: never report 'proven' =="
# 11. This gate answers only the CHEAP half of "can it fail" — it executes no suite. If it ever
#     starts claiming proof, that is the defect class it exists to detect, occurring inside it.
T="$TMPROOT/hon"; mk "$T" 1 1 1 1 1
OUT="$(run "$T")"
has "11 output states clean gates are UNREFUTED, not proven" "$OUT" "UNREFUTED, not proven"

echo "== ratchet + modes =="
# 12. scan is ADVISORY: findings present, exit 0. Reverting `exit 0` to `exit $RET` would make a
#     legacy backlog block every preflight, and the gate would be disabled within a week.
T="$TMPROOT/rat"; mk "$T" 0 1 0 0 0
run "$T" scan >/dev/null 2>&1; chk "12 scan exits 0 despite findings (advisory)" "$?" "0"
# 13. check is the RATCHET: non-baseline findings are RED. This is the fail-on-revert core —
#     if `check` stops returning non-zero the whole gate is decorative.
run "$T" check >/dev/null 2>&1; chk "13 check exits 1 on a new finding (RED)" "$?" "1"
# 14. ...and a finding named in GI_BASELINE does NOT red, so legacy debt does not block.
GI_BASELINE="G1:widget-guard.sh G2:widget-guard.sh:caller.sh G3:widget-guard.sh:no-test" \
  GI_ROOT="$T" GI_CHECKS_DIR="$T/fleet/checks" GI_TESTS_DIR="$T/fleet/tests" \
  GI_CI_SCOPE="$T/fleet/ci-scope.sh" GI_GATE_EXTRAS=" " GI_UNENFORCED_MAX=99 \
  bash "$GATE" check >/dev/null 2>&1
chk "14 baselined findings do not RED the ratchet" "$?" "0"
# 15. usage error is exit 2, not a silent 0 (uncertainty must never resolve to green).
run "$T" bogus >/dev/null 2>&1; chk "15 unknown mode exits 2" "$?" "2"

echo "== reentrancy [[fleet-selfcheck-forkbomb-class]] =="
# 16. A gate that runs a gate that runs it is a fork bomb. The child refuses.
T="$TMPROOT/re"; mk "$T" 0 0 0 0 0
GATE_INTEGRITY_ACTIVE=1 bash "$GATE" scan >/dev/null 2>&1
chk "16 refuses to run as its own child" "$?" "0"
OUT="$(GATE_INTEGRITY_ACTIVE=1 bash "$GATE" scan 2>&1)"
has "16b refusal is stated, not silent" "$OUT" "reentrancy guard"

echo "== WIRING (an unwired gate-on-gates would be self-refuting) =="
# 17. The whole point of this gate is that gates get built and never wired. Its own wiring is
#     therefore asserted, not assumed. All three clauses have already failed in practice here:
#       17a preflight's cmd_detect must actually CALL the detector, not merely define it;
#       17b the detector guards on `[ -x ]`, so a non-executable committed mode bit makes it
#           silently no-op behind a green preflight — the previous gate on this branch shipped
#           exactly that way;
#       17c CI must run this suite: fleet/tests/ is an ALLOWLIST, excluded by default.
PF="$HERE/fleet/preflight.sh"
chk "17a preflight cmd_detect calls detect_gate_integrity" \
  "$(sed -n '/^cmd_detect(){/,/^}/p' "$PF" | grep -c '^[[:space:]]*detect_gate_integrity$')" "1"
if [ -x "$GATE" ]; then ok "17b checks/gate-integrity.sh is executable"; else no "17b gate not executable — preflight's [ -x ] guard would silently skip it"; fi
chk "17c suite is in the CI allowlist" \
  "$(bash "$HERE/fleet/checks/rig-ci-scope.sh" suites | grep -c '^gate-integrity.test.sh$')" "1"
# 18. And the committed MODE BIT, not just the working-tree bit — `chmod +x` that never made it
#     into the index is the same silent no-op.
chk "18 committed file mode is executable (100755)" \
  "$(cd "$HERE" && git ls-files -s fleet/checks/gate-integrity.sh | awk '{print $1}')" "100755"

echo
echo "gate-integrity.test.sh: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
