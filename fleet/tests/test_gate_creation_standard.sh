#!/usr/bin/env bash
# test_gate_creation_standard.sh — RED-PROOF / FAIL-ON-REVERT tests for the meta-gate
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
# final LIVE case, which runs `check` read-only against the real repo and asserts GREEN
# (accept item 4: the seeded ledger classes each trace to a concrete standard item).
#
# Run:  bash fleet/tests/test_gate_creation_standard.sh   (exit 0 = all pass)
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
  echo "$d"
}
run_gate(){ # run_gate <world> <mode> [gate args...]
  local d="$1" mode="$2"; shift 2
  env GCS_PRODUCT_REPO="$d/repo" GCS_GATES_JSON="$d/repo/tools/gates.json" \
      GCS_CHECKS_DIR="$d/checks" GCS_TESTS_DIR="$d/tests" \
      GCS_LEDGER="$d/state/ledger.tsv" GCS_STANDARD="$d/standard.md" \
      GCS_VALIDATE_BOARD="$d/validate_board.sh" GCS_LEDGER_MIN=1 \
      GCS_BASELINE_GATE_IDS="old-legacy good-gate" \
      GCS_GRANDFATHER_NO_REDPROOF="old-legacy" \
      GCS_BASELINE_CHECKS="sample-gate.sh" \
      GCS_GRANDFATHER_NO_TEST="" GCS_GRANDFATHER_NO_SETLINE="" \
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

# (14) LIVE: the real repo/fleet/ledger conforms to the standard TODAY (read-only).
# Proves accept item 4: every seeded ledger class traces to a concrete standard item, the
# seeded grandfather baselines match reality, and the meta-gate is green at introduction.
out="$(bash "$GATE" check 2>&1)"; rc=$?
[ $rc -eq 0 ] && ok "(14) LIVE check -> GREEN (seeded ledger + standard + baselines conform)" || bad "(14) LIVE check must be GREEN, got exit $rc: $out"

# (15) DETERMINISM (S6, dogfooded): LIVE check twice -> identical output + verdict
out2="$(bash "$GATE" check 2>&1)"; rc2=$?
{ [ "$rc" -eq "$rc2" ] && [ "$out" = "$out2" ]; } && ok "(15) LIVE check deterministic (identical verdict + output)" || bad "(15) meta-gate is non-deterministic on the same tree"

echo "----------------------------------------"
echo "PASS=$PASS FAIL=$FAIL"
[ $FAIL -eq 0 ] || exit 1
exit 0
