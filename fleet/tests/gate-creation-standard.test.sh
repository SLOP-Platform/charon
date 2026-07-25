#!/usr/bin/env bash
# gate-creation-standard.test.sh — RED-PROOF / FAIL-ON-REVERT tests for the meta-gate
# fleet/checks/gate-creation-standard.sh (ticket GATE-CREATION-STANDARDIZE).
#
# This is the meta-gate's OWN evidence under the standard it enforces: each case below
# demonstrates the gate goes RED on a real failure of the class it guards. If any detection
# branch is reverted/neutered (e.g. the unproofed-gate check is dropped, or `check` starts
# always exiting 0), the corresponding case here exits GREEN-when-it-must-be-RED and the
# test FAILS — proving the meta-gate is load-bearing, not decorative.
#
# Operates entirely in TEMP isolated fixtures via the GCS_* env seams — never touches the
# live fleet/, tools/gates.json, or the real GATE-GAP-LEDGER.tsv. The one exception is the
# final LIVE case, which runs `check` read-only against the real repo and asserts that its
# open findings are EXACTLY the recorded set (see LIVE_KNOWN_OPEN, case 14).
#
# Cases 16-20 cover META-GATE-CALLSITE-ENUM: the audited population is derived by CALL SITE
# (what the enforcement entrypoints invoke), not by directory. Revert that enumerator and
# cases 16/17 go green-when-they-must-be-RED and the suite FAILS.
#
# Run:  bash fleet/tests/gate-creation-standard.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$SRC/checks/gate-creation-standard.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }

# ---------- fixture builder: a minimal FULLY-CONFORMANT world ----------
mk_world(){
  local d; d="$(mktemp -d)"
  mkdir -p "$d/repo/tools" "$d/repo/tests" "$d/checks" "$d/tests" "$d/state"
  cat > "$d/repo/tools/gates.json" <<'JSON'
[
 {"id": "old-legacy", "red_proof": null},
 {"id": "good-gate", "red_proof": "tests/test_good_gate.py"}
]
JSON
  touch "$d/repo/tests/test_good_gate.py"
  printf '#!/usr/bin/env bash\nset -uo pipefail\nexit 0\n' > "$d/checks/sample-gate.sh"
  printf '# red-proof: reverts detection -> this fails\n'   > "$d/tests/sample-gate.test.sh"
  cat > "$d/standard.md" <<'MD'
RED-PROOFED NON-VACUOUS UN-GAMED NOT-INERT FAIL-LOUD DETERMINISTIC
CONTEXT-OF-VALIDITY ARTIFACT-VERIFIED VERIFY-EFFECT CLASS-COVERAGE
classes: built-but-inert deploy-context-blind
MD
  printf 'date\tgates_green\tissue_shipped\troot_class\tgate_improvement\tstatus\n' > "$d/state/ledger.tsv"
  printf '2026-07-01\tg\tissue\tbuilt-but-inert\timprove\tfixed\n' >> "$d/state/ledger.tsv"
  printf 'echo not wired here\n' > "$d/validate_board.sh"
  # a conformant enforcement ENTRYPOINT: it invokes the fleet check, so the call-site
  # enumeration is non-vacuous in every fixture world.
  mkdir -p "$d/ep"
  printf '#!/usr/bin/env bash\nset -uo pipefail\nbash "%s/checks/sample-gate.sh" check\n' "$d" > "$d/ep/preflight.sh"
  echo "$d"
}
# Per-case env overrides (appended LAST so they win over the fixed fixture env).
EXTRA_ENV=()
run_gate(){ # run_gate <world> <mode> [gate args...]
  local d="$1" mode="$2"; shift 2
  env GCS_PRODUCT_REPO="$d/repo" GCS_GATES_JSON="$d/repo/tools/gates.json" \
      GCS_CHECKS_DIR="$d/checks" GCS_TESTS_DIR="$d/tests" \
      GCS_LEDGER="$d/state/ledger.tsv" GCS_STANDARD="$d/standard.md" \
      GCS_VALIDATE_BOARD="$d/validate_board.sh" GCS_LEDGER_MIN=1 \
      GCS_FLEET="$d" GCS_REPO_ROOT="$d" GCS_ENTRYPOINTS="ep/*.sh" GCS_CALLSITE_MIN=1 \
      GCS_BASELINE_GATE_IDS="old-legacy good-gate" \
      GCS_GRANDFATHER_NO_REDPROOF="old-legacy" \
      GCS_BASELINE_CHECKS="sample-gate.sh" \
      GCS_GRANDFATHER_NO_TEST="" GCS_GRANDFATHER_NO_SETLINE="" \
      GCS_GRANDFATHER_CALLSITE_NO_TEST="" \
      ${EXTRA_ENV[@]+"${EXTRA_ENV[@]}"} \
      bash "$GATE" "$mode" "$@" 2>&1
}

# (1) fully-conformant fixture -> GREEN exit 0
D="$(mk_world)"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 0 ] && ok "(1) conformant world -> check GREEN (exit 0)" || bad "(1) conformant world should be GREEN, got exit $rc: $out"

# (2) CORE FAIL-ON-REVERT: a NEW gates.json entry with NO red_proof -> RED naming it.
# If the unproofed-gate detection is ever reverted, this exits 0 and the case fails.
D="$(mk_world)"
python3 - "$D/repo/tools/gates.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d.append({"id": "new-unproofed", "red_proof": None})
json.dump(d, open(p, "w"))
PY
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(2) new gate without red_proof -> RED (exit 1)" || bad "(2) unproofed new gate must be RED, got exit $rc"
has "$out" "unproofed-gate: 'new-unproofed'" "(2b) names the unproofed gate + S1"

# (3) red_proof names a file that does NOT exist -> RED (claimed proof = self-report-lie)
D="$(mk_world)"
python3 - "$D/repo/tools/gates.json" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d.append({"id": "liar", "red_proof": "tests/nope.py"})
json.dump(d, open(p, "w"))
PY
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(3) red_proof file missing -> RED" || bad "(3) missing red_proof file must be RED, got exit $rc"
has "$out" "red-proof-missing-file: 'liar'" "(3b) names the lying entry"

# (4) UN-GAMED: a baseline gate id removed from gates.json -> RED gate-removed
D="$(mk_world)"
printf '[{"id": "good-gate", "red_proof": "tests/test_good_gate.py"}]\n' > "$D/repo/tools/gates.json"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(4) baseline gate removed -> RED" || bad "(4) shrunk node-set must be RED, got exit $rc"
has "$out" "gate-removed: baseline gate 'old-legacy'" "(4b) names the vanished gate"

# (5) NON-VACUOUS: empty registry -> RED vacuous-registry
D="$(mk_world)"
printf '[]\n' > "$D/repo/tools/gates.json"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(5) empty gates.json -> RED" || bad "(5) vacuous registry must be RED, got exit $rc"
has "$out" "vacuous-registry" "(5b) names the vacuous registry"

# (6) new fleet check with NO companion test -> RED no-red-proof-test
D="$(mk_world)"
printf '#!/usr/bin/env bash\nset -uo pipefail\nexit 0\n' > "$D/checks/orphan-gate.sh"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(6) fleet check without companion test -> RED" || bad "(6) untested fleet check must be RED, got exit $rc"
has "$out" "no-red-proof-test: orphan-gate.sh" "(6b) names the orphan check"

# (7) companion test exists but carries NO red-proof/fail-on-revert marker -> RED
D="$(mk_world)"
printf '# only a happy-path assertion\n' > "$D/tests/sample-gate.test.sh"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(7) companion test without red-proof marker -> RED" || bad "(7) markerless companion must be RED, got exit $rc"
has "$out" "no-red-proof-marker" "(7b) names the markerless test"

# (8) FAIL-LOUD: fleet check .sh without set -uo pipefail -> RED fail-quiet
D="$(mk_world)"
printf '#!/usr/bin/env bash\nexit 0\n' > "$D/checks/sample-gate.sh"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(8) fail-quiet check script -> RED" || bad "(8) fail-quiet script must be RED, got exit $rc"
has "$out" "fail-quiet: sample-gate.sh" "(8b) names the fail-quiet script"

# (9) NON-VACUOUS ledger: zero data rows -> RED ledger-vacuous
D="$(mk_world)"
printf 'date\tgates_green\tissue_shipped\troot_class\tgate_improvement\tstatus\n' > "$D/state/ledger.tsv"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(9) empty ledger -> RED" || bad "(9) vacuous ledger must be RED, got exit $rc"
has "$out" "ledger-vacuous" "(9b) names the vacuous ledger"

# (10) malformed ledger row (5 cols) -> RED ledger-malformed (hard error, not silent skip)
D="$(mk_world)"
printf '2026-07-01\tg\tissue\tbuilt-but-inert\tonly-five-cols\n' >> "$D/state/ledger.tsv"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(10) malformed ledger row -> RED" || bad "(10) malformed row must be RED, got exit $rc"
has "$out" "ledger-malformed" "(10b) names the malformed row"

# (11) TRACEABILITY: ledger class absent from the standard -> RED class-untraced
D="$(mk_world)"
printf '2026-07-02\tg\tissue\tnever-heard-of-class\timprove\topen\n' >> "$D/state/ledger.tsv"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(11) untraced ledger class -> RED" || bad "(11) untraced class must be RED, got exit $rc"
has "$out" "class-untraced: ledger root_class 'never-heard-of-class'" "(11b) names the untraced class"

# (12) scan mode: SAME broken world -> advisory lines but ALWAYS exit 0
D="$(mk_world)"
printf '[]\n' > "$D/repo/tools/gates.json"
out="$(run_gate "$D" scan)"; rc=$?
[ $rc -eq 0 ] && ok "(12) scan on broken world -> exit 0 (advisory only)" || bad "(12) scan must always exit 0, got $rc"
has "$out" "GATE-STANDARD-ADVISORY: vacuous-registry" "(12b) scan surfaces the finding as advisory"
has "$out" "GATE-STANDARD-ADVISORY: not-wired" "(12c) scan reports its own unwired state honestly (S8)"

# (13) append: valid row appends + world stays GREEN; unknown class REFUSED; tab REFUSED
D="$(mk_world)"
out="$(run_gate "$D" append "some gates" "an issue" built-but-inert "an improvement" "open")"; rc=$?
[ $rc -eq 0 ] && ok "(13) append valid row -> exit 0" || bad "(13) valid append must succeed, got $rc: $out"
[ "$(grep -vc '^#' "$D/state/ledger.tsv")" -eq 3 ] && ok "(13b) row actually appended" || bad "(13b) ledger row count wrong after append"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 0 ] && ok "(13c) world still GREEN after valid append" || bad "(13c) append broke the world: $out"
out="$(run_gate "$D" append "g" "i" not-a-known-class "imp" "open")"; rc=$?
[ $rc -ne 0 ] && ok "(13d) append with UNTRACED class refused" || bad "(13d) untraced class must be refused"
out="$(run_gate "$D" append "g" "$(printf 'bad\tfield')" built-but-inert "imp" "open")"; rc=$?
[ $rc -ne 0 ] && ok "(13e) append with embedded TAB refused" || bad "(13e) embedded tab must be refused"

# ---------- (16-20) CALL-SITE ENUMERATION (META-GATE-CALLSITE-ENUM) ----------

# (16) CORE FAIL-ON-REVERT for this ticket: a script INVOKED by an enforcement entrypoint but
# living outside fleet/checks/ and carrying no companion test -> RED unaudited-callsite.
# Revert the call-site enumerator (back to the directory glob) and this exits 0 => FAIL.
D="$(mk_world)"
printf '#!/usr/bin/env bash\nset -uo pipefail\nexit 0\n' > "$D/inline-thing.sh"
printf 'bash "%s/inline-thing.sh"\n' "$D" >> "$D/ep/preflight.sh"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(16) invoked-but-untested script outside checks/ -> RED" || bad "(16) call-site member without a red-proof must be RED, got exit $rc: $out"
has "$out" "unaudited-callsite: inline-thing.sh" "(16b) names the unaudited call site (placement is no longer an exemption)"
# ...and a companion carrying the red-proof marker clears it (the exemption is EVIDENCE, not location)
printf '# red-proof: reverts detection -> this fails\n' > "$D/tests/inline-thing.test.sh"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 0 ] && ok "(16c) red-proofed call-site member -> GREEN" || bad "(16c) red-proofed call-site member should clear, got exit $rc: $out"

# (17) TRIGGER-INSTANCE REPRODUCTION (the tier-drift escape, commit 0a759a8): enforcement
# INLINED into validate_board.sh. Under the directory glob this was invisible forever; under
# call-site enumeration validate_board.sh itself joins the audited set and is RED until proofed.
D="$(mk_world)"
cat > "$D/validate_board.sh" <<'VB'
#!/usr/bin/env bash
set -uo pipefail
# INLINE enforcement block (the escape): a tier-drift check that lives in no fleet/checks/ file
if grep -q 'tier: bogus' board.md 2>/dev/null; then echo "TIER-DRIFT"; exit 1; fi
VB
printf 'bash "%s/validate_board.sh"\n' "$D" >> "$D/ep/preflight.sh"
out="$(run_gate "$D" check)"; rc=$?
[ $rc -eq 1 ] && ok "(17) inline enforcement in validate_board.sh -> validate_board.sh is audited and RED" || bad "(17) the tier-drift escape must be impossible, got exit $rc: $out"
has "$out" "unaudited-callsite: validate_board.sh" "(17b) names validate_board.sh itself (the host of the inline block)"

# (18) NON-VACUOUS: an entrypoint set that resolves to zero files -> RED, never a silent pass.
D="$(mk_world)"
EXTRA_ENV=(GCS_ENTRYPOINTS="no-such-dir/*.sh")
out="$(run_gate "$D" check)"; rc=$?
EXTRA_ENV=()
[ $rc -eq 1 ] && ok "(18) zero-resolution entrypoint set -> RED (exit 1)" || bad "(18) a run that examined zero call sites must NOT be green, got exit $rc: $out"
has "$out" "callsite-enum-vacuous" "(18b) names the vacuous enumeration (S2)"
has "$out" "entrypoint-missing: enforcement entrypoint 'no-such-dir" "(18c) names the entrypoint that matched nothing (S3)"

# (19) FLOOR: derived call-site set below GCS_CALLSITE_MIN -> RED callsite-set-shrunk
D="$(mk_world)"
EXTRA_ENV=(GCS_CALLSITE_MIN=99)
out="$(run_gate "$D" check)"; rc=$?
EXTRA_ENV=()
[ $rc -eq 1 ] && ok "(19) call-site set below its floor -> RED" || bad "(19) a shrunk audited population must be RED, got exit $rc: $out"
has "$out" "callsite-set-shrunk" "(19b) names the shrunk set (S3 UN-GAMED)"

# (20) STALE EXEMPTION: a grandfathered name that no longer exists on disk -> RED.
# (Frozen exemptions may only SHRINK; a dangling name is how such a list silently grows.)
D="$(mk_world)"
EXTRA_ENV=(GCS_GRANDFATHER_CALLSITE_NO_TEST="deleted-gate.sh")
out="$(run_gate "$D" check)"; rc=$?
EXTRA_ENV=()
[ $rc -eq 1 ] && ok "(20) grandfathered name absent from disk -> RED" || bad "(20) stale exemption must be RED, got exit $rc: $out"
has "$out" "stale-exemption: GRANDFATHER_CALLSITE_NO_TEST names 'deleted-gate.sh'" "(20b) names the stale exemption"

# (14) LIVE: the real repo/fleet/ledger, read-only.
# ASSERTION CHANGED by META-GATE-CALLSITE-ENUM (2026-07-24), deliberately and on the record:
# this case used to assert LIVE == GREEN. That premise was FALSE — the live tree has been RED
# with 4 unsurfaced findings and this case has been failing (PASS=30 FAIL=1) in a suite that
# no runner executed. Asserting GREEN also creates the wrong incentive: the cheapest way to
# pass is to grandfather real findings away. So the assertion is now "the live open findings
# are EXACTLY the recorded set below" — a NEW finding fails this suite (it must be fixed or
# recorded), and a DISAPPEARING finding also fails it (a finding count that drops is a red
# flag, not a win). Fixing a live finding = deleting its line here, and the suite goes green.
LIVE_KNOWN_OPEN=(
  "unproofed-gate: 'reachability-gate'"                                  # product registry, owned elsewhere
  "no-red-proof-test: large-file-guard.sh"                               # pre-existing fleet check, untested
  "no-red-proof-test: rig-ci-scope.sh"                                   # pre-existing fleet check, untested
  "fail-quiet: fleet/_lib.sh"                                            # surfaced BY call-site enumeration
  "fail-quiet: fleet/gh-cache.sh"                                        # surfaced BY call-site enumeration
  "fail-quiet: fleet/push-verify.sh"                                     # surfaced BY call-site enumeration
  "fail-quiet: fleet/repo-registry.sh"                                   # surfaced BY call-site enumeration
  "fail-quiet: fleet/watchdog/watchdog-lib.sh"                           # surfaced BY call-site enumeration
  "no-red-proof-marker: handoff-generated-state.test.sh covers fleet/handoff.sh"
  "unaudited-callsite: fleet/validate_board.sh"                          # THE trigger instance, deliberately not exempted
  "class-untraced: ledger root_class 'no-decision-time-gate'"            # ledger/standard, owned elsewhere
)
out="$(bash "$GATE" check 2>&1)"; rc=$?
live_n="$(printf '%s\n' "$out" | grep -c '^  RED  [a-z-]*:')"
if [ "$rc" -eq 0 ] || [ "$rc" -eq 1 ]; then
  ok "(14) LIVE check returns a definite verdict (exit $rc)"
else
  bad "(14) LIVE check must exit 0 (GREEN) or 1 (RED), got $rc — an indefinite verdict is not evidence: $out"
fi
[ "$live_n" -eq "${#LIVE_KNOWN_OPEN[@]}" ] \
  && ok "(14b) LIVE open findings = the recorded ${#LIVE_KNOWN_OPEN[@]}" \
  || bad "(14b) LIVE has $live_n open findings, ${#LIVE_KNOWN_OPEN[@]} recorded — a NEW finding must be FIXED or RECORDED here, never suppressed:
$out"
for k in "${LIVE_KNOWN_OPEN[@]}"; do
  has "$out" "$k" "(14c) recorded live finding still present: ${k%%:*}"
done
# and the call-site enumeration is non-vacuous on the REAL tree (a live run that examined
# nothing would sail through every assertion above).
printf '%s\n' "$out" | grep -q 'callsite-enum-vacuous' && bad "(14d) LIVE call-site enumeration is VACUOUS" || ok "(14d) LIVE call-site enumeration is non-vacuous"

# (15) DETERMINISM (S6, dogfooded): LIVE check twice -> identical output + verdict
out2="$(bash "$GATE" check 2>&1)"; rc2=$?
{ [ "$rc" -eq "$rc2" ] && [ "$out" = "$out2" ]; } && ok "(15) LIVE check deterministic (identical verdict + output)" || bad "(15) meta-gate is non-deterministic on the same tree"

echo "----------------------------------------"
echo "PASS=$PASS FAIL=$FAIL"
[ $FAIL -eq 0 ] || exit 1
exit 0
