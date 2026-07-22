#!/usr/bin/env bash
# rule-coverage.test.sh — FAIL-ON-REVERT tests for the COVERAGE META-GATE
# (fleet/checks/rule-coverage.sh), which mechanizes MANAGER-OPERATING-RULES §11: every
# mechanizable rule MUST be a gate; a mechanizable rule left un-gated (a silent GAP) is RED.
#
# Operates entirely in a TEMP isolated fixture (RULE_COVERAGE_* env overrides) — never touches
# the live fleet/state/RULE-REGISTRY.tsv, the live doc, or the real artifact tree.
#
# Covers (each is load-bearing — reverting the named branch of rule-coverage.sh flips it RED):
#   (a) ALL-COVERED registry (mechanized->real artifact; guidance; gap held by an ACTIVE
#       time-boxed exemption) -> GREEN (exit 0). Coverage % printed.
#   (b) CORE: a mechanizable GAP with NO exemption -> RED (exit 1). This is the teeth. If the
#       gap-blocking branch is reverted (gaps stop blocking), (b) wrongly exits 0 and fails RED.
#   (c) CORE: a `mechanized` row pointing at a NONEXISTENT artifact -> RED (fake-green caught).
#       Reverting the artifact-existence check makes (c) wrongly pass and this fails RED.
#   (d) an EXPIRED time-boxed exemption on a gap -> RED (the force-function actually expires).
#   (e) a phantom/stale row whose doc_anchor is NOT in the doc -> RED (registry<->doc integrity).
#   (f) COMPLETENESS FLOOR: fewer registry rows than doc rule-bullets -> RED (unclassified rule).
#   (g) a `mechanized` row whose artifact EXISTS but lacks the required ::token -> RED (unwired).
#
# Run:  bash fleet/tests/rule-coverage.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$SRC/checks/rule-coverage.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
ROOT="$D/root"
mkdir -p "$ROOT"
# A real enforcing artifact the mechanized rows can point at (existence + token wiring).
printf '#!/usr/bin/env bash\n# WIRED_TOKEN present\necho gate\n' > "$ROOT/real-gate.sh"

DOC="$D/rules.md"
cat > "$DOC" <<'MD'
# FIXTURE RULES
- Alpha rule: a mechanized example rule
- Beta rule: a guidance example rule
- Gamma rule: a gap example rule
MD

REG="$D/registry.tsv"
export RULE_COVERAGE_REGISTRY="$REG" RULE_COVERAGE_RULES_DOC="$DOC" \
       RULE_COVERAGE_ROOT="$ROOT" RULE_COVERAGE_TODAY="2026-07-14"

# row <rule_id> <cls> <ref> <anchor> [notes]  -> one TSV registry line
row(){ printf 'r-%s\tsec\tone line\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "${5:-}"; }

# ---- (a) all-covered -> GREEN ----
{
  row mech mechanized "real-gate.sh::WIRED_TOKEN" "Alpha rule"
  row guid guidance "judgment-only cadence rule" "Beta rule"
  row gap  gap "TARGET-GATE to build" "Gamma rule" "exempt-until:2026-12-31 pending build"
} > "$REG"
out="$(bash "$GATE" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(a) all-covered registry -> GREEN" || bad "(a) all-covered -> GREEN (got exit $rc: $out)"
has "$out" "coverage" "(a) prints a coverage summary"

# ---- (b) CORE: mechanizable GAP with NO exemption -> RED ----
{
  row mech mechanized "real-gate.sh::WIRED_TOKEN" "Alpha rule"
  row guid guidance "judgment-only" "Beta rule"
  row gap  gap "TARGET-GATE to build" "Gamma rule"
} > "$REG"
out="$(bash "$GATE" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(b) un-exempted mechanizable GAP -> RED (core, load-bearing)" \
                || bad "(b) un-exempted mechanizable GAP -> RED (got exit 0 — GATE REVERTED)"
has "$out" "GAP" "(b) message names the gap"

# ---- (c) CORE: mechanized -> nonexistent artifact -> RED ----
{
  row mech mechanized "does-not-exist.sh" "Alpha rule"
  row guid guidance "judgment-only" "Beta rule"
  row gap  gap "TARGET" "Gamma rule" "exempt-until:2026-12-31 pending"
} > "$REG"
out="$(bash "$GATE" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(c) mechanized -> nonexistent artifact -> RED (fake-green caught)" \
                || bad "(c) mechanized -> nonexistent artifact -> RED (got exit 0 — fake-green not caught)"
has "$out" "does NOT exist" "(c) message says the artifact does not exist"

# ---- (d) EXPIRED exemption on a gap -> RED ----
{
  row mech mechanized "real-gate.sh::WIRED_TOKEN" "Alpha rule"
  row guid guidance "judgment-only" "Beta rule"
  row gap  gap "TARGET" "Gamma rule" "exempt-until:2020-01-01 stale"
} > "$REG"
bash "$GATE" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && ok "(d) EXPIRED exemption -> RED (force-function expires)" \
                || bad "(d) EXPIRED exemption -> RED (got exit 0 — exemption never expires)"

# ---- (e) phantom doc_anchor -> RED ----
{
  row mech mechanized "real-gate.sh::WIRED_TOKEN" "Alpha rule"
  row guid guidance "judgment-only" "Beta rule"
  row gap  gap "TARGET" "Delta rule NOT in the doc" "exempt-until:2026-12-31 pending"
} > "$REG"
out="$(bash "$GATE" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(e) phantom doc_anchor -> RED" || bad "(e) phantom doc_anchor -> RED (got exit 0)"
has "$out" "phantom" "(e) message flags the phantom/stale row"

# ---- (f) completeness floor: fewer rows than doc bullets -> RED ----
{
  row mech mechanized "real-gate.sh::WIRED_TOKEN" "Alpha rule"
  row guid guidance "judgment-only" "Beta rule"
} > "$REG"   # 2 rows vs 3 doc bullets
out="$(bash "$GATE" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(f) completeness floor (unclassified rule) -> RED" \
                || bad "(f) completeness floor -> RED (got exit 0 — new rule slipped unclassified)"
has "$out" "completeness floor" "(f) message names the completeness floor"

# ---- (g) mechanized artifact exists but required token absent -> RED ----
{
  row mech mechanized "real-gate.sh::MISSING_TOKEN" "Alpha rule"
  row guid guidance "judgment-only" "Beta rule"
  row gap  gap "TARGET" "Gamma rule" "exempt-until:2026-12-31 pending"
} > "$REG"
out="$(bash "$GATE" 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(g) mechanized artifact exists but NOT wired (token absent) -> RED" \
                || bad "(g) unwired mechanized artifact -> RED (got exit 0)"
has "$out" "not wired\|NOT wired" "(g) message flags the unwired artifact"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL RULE-COVERAGE TESTS PASS"
