#!/usr/bin/env bash
# rule-sync.test.sh — FAIL-ON-REVERT tests for the F47 RULE-SYNC-GATE
# (fleet/checks/rule-sync.sh), which mechanizes the operator's two-way rule-port
# enforcement (Charon <-> SLOP <-> KSF, GAP-REGISTER A3, 2026-07-12).
#
# Operates entirely in a TEMP isolated register (RULE_SYNC_REGISTER env override) and
# stubs the SLOP CLI / KSF gh lookup paths (RULE_SYNC_SLOP_CLI / RULE_SYNC_KSF_GH_REPO
# pointed at non-existent files) so the test NEVER calls out to a real sibling repo.
# RULE_SYNC_DRY_RUN=1 is forced on so even if a stub accidentally returned a real
# create-path, the gate would still print WOULD-CREATE rather than mutate state.
#
# Covers (every assertion is FAIL-ON-REVERT — if the gate is ever regressed to ignore
# one of these, the corresponding case below goes RED):
#   (a) an into-charon row with charon_status=gap AND action!=port-to-charon
#       -> `check` FAILS (exit 1) and the message names the offending rule id.
#       Core rule 1: untriaged inbound gaps MUST be caught (the silent-regress miss
#       that motivated the ticket in the first place).
#   (b) an out-of-charon row with action=file-slop-ticket (no linked_ticket column,
#       no matching ticket in the stubbed SLOP) -> `check` FAILS (exit 1) AND the
#       summary line names the correct target repo (slop). The "WOULD-CREATE-SLOP"
#       tag confirms the gate actually TRIED to create the ticket (idempotency path).
#   (c) an out-of-charon row with action=file-ksf-ticket under the same conditions
#       -> `check` FAILS (exit 1) AND the summary names ksf.
#   (d) a fully-triaged register: every inbound gap has action=port-to-charon AND
#       every out-of-charon row has linked_ticket populated -> `check` PASSES (exit 0).
#   (e) `scan` mode ALWAYS exits 0 (advisory) regardless of how many offenders the
#       register has — consumed by validate_board.sh, never fails the board on its own.
#
# Run:  bash fleet/tests/rule-sync.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$SRC/checks/rule-sync.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -qF -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }
hasre(){ printf '%s' "$1" | grep -qE -- "$2" && ok "$3" || bad "$3 (missing regex '$2')"; }

# --- stub env: never touches a real sibling repo. RULES FOR THE TEST:
#  - RULE_SYNC_SLOP_CLI points at a non-existent file so slop_lookup returns empty
#    (treats as "no existing ticket") and slop_create prints WOULD-CREATE-*
#  - RULE_SYNC_KSF_GH_REPO is the same as the real one (the script only calls `gh` on
#    the lookup path which we don't reach in the bad case; in the GREEN case the
#    linked_ticket is caller-asserted so gh is never called). Setting it to a
#    syntactically-valid owner/repo avoids the auto-derive path.
#  - RULE_SYNC_DRY_RUN=1 forces WOULD-CREATE for the create branches — even if a stub
#    path mistakenly returned "no error", the gate still does not mutate state.
D="$(mktemp -d)"
export RULE_SYNC_REGISTER="$D/REGISTER.tsv"
export RULE_SYNC_SLOP_CLI="$D/nonexistent-query.py"
export RULE_SYNC_KSF_GH_REPO="test/test"
export RULE_SYNC_SLOP_BATCH="BATCH-TEST"
export RULE_SYNC_DRY_RUN="1"

# Helper: write a header + N data rows to the test register. Each row is given as a
# list of 8 tab-separated fields (matching the live register schema exactly so the
# parser handles test rows the same way it handles real rows).
write_register(){
  local header="$1"; shift
  {
    echo "# RULE-SYNC-REGISTER.tsv (test fixture)"
    echo "$header"
  } > "$RULE_SYNC_REGISTER"
  for row in "$@"; do
    printf '%s\n' "$row" >> "$RULE_SYNC_REGISTER"
  done
}

HDR='source_framework	rule_id	rule_summary	charon_status	direction	mechanized	action	note'

# --- (a) untriaged inbound gap -> RED. LOAD-BEARING for the original GAP-REGISTER miss.
write_register "$HDR" \
  "slop	SLOP-INV:9.9	Test rule that Charon lacks — should not be silently missed	gap	into-charon	none	none	will-trigger-RED"
out="$(bash "$GATE" check 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(a) untriaged inbound gap RED (core, load-bearing check)" \
                || bad "(a) untriaged inbound gap RED (core, load-bearing check) (got exit 0 — GATE REVERTED)"
has "$out" "SLOP-INV:9.9"      "(a) message names the offending rule"
has "$out" "UNTRIAGED"         "(a) message says why (UNTRIAGED)"
has "$out" "RED"               "(a) summary flags RED"

# --- (b) missing out-of-charon SLOP ticket -> RED, summary names 'slop'.
# Note: the gate's WOULD-CREATE branch produces action=WOULD-CREATE-SLOP, which is the
# strongest "actually tried to create the ticket" signal we can emit under dry-run.
write_register "$HDR" \
  "charon	CHARON-MECH:fake-slop-mech	Stub mechanism needing an SLOP equivalent	ported	out-of-charon	none	file-slop-ticket	will-trigger-RED-with-slop"
out="$(bash "$GATE" check 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(b) missing out-of-charon SLOP ticket RED (idempotent-create path)" \
                || bad "(b) missing out-of-charon SLOP ticket RED (got exit 0 — GATE REVERTED)"
has "$out" "CHARON-MECH:fake-slop-mech"   "(b) message names the offending rule"
has "$out" "WOULD-CREATE-SLOP"            "(b) summary says the gate tried to create in SLOP"
hasre "$out" "(SLOP|slop)"                "(b) summary names the correct target repo: slop"

# --- (c) missing out-of-charon KSF ticket -> RED, summary names 'ksf'.
write_register "$HDR" \
  "charon	CHARON-MECH:fake-ksf-mech	Stub mechanism needing a KSF equivalent	ported	out-of-charon	none	file-ksf-ticket	will-trigger-RED-with-ksf"
out="$(bash "$GATE" check 2>&1)"; rc=$?
[ "$rc" -ne 0 ] && ok "(c) missing out-of-charon KSF ticket RED" \
                || bad "(c) missing out-of-charon KSF ticket RED (got exit 0 — GATE REVERTED)"
has "$out" "CHARON-MECH:fake-ksf-mech" "(c) message names the offending rule"
has "$out" "WOULD-CREATE-KSF"          "(c) summary says the gate tried to create in KSF"
has "$out" "ksf"                       "(c) summary names the correct target repo: ksf"

# --- (d) fully-triaged register -> GREEN. linked_ticket column populated for the
# out-of-charon rows, action=port-to-charon for the inbound gap. This is the
# "register is healthy" case the gate must accept without false-RED.
HDR_LINKED='source_framework	rule_id	rule_summary	charon_status	direction	mechanized	action	note	linked_ticket'
write_register "$HDR_LINKED" \
  "slop	SLOP-INV:9.10	Triaged inbound gap with explicit port decision	gap	into-charon	none	port-to-charon	operator-decided	-" \
  "charon	CHARON-MECH:clean-slop	Already-linked SLOP work, ticket id recorded	ported	out-of-charon	none	file-slop-ticket	has-ticket	BL-1234" \
  "charon	CHARON-MECH:clean-ksf	Already-linked KSF work, issue number recorded	ported	out-of-charon	none	file-ksf-ticket	has-ticket	#42"
out="$(bash "$GATE" check 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(d) fully-triaged register GREEN" \
                || bad "(d) fully-triaged register GREEN (got exit $rc — GATE FALSE-RED)"
has "$out" "linked=" "(d) summary shows linked count"
has "$out" "BL-1234"  "(d) caller-asserted SLOP link is preserved (BL-1234)"
has "$out" "#42"      "(d) caller-asserted KSF link is preserved (#42)"

# --- (e) scan ALWAYS exits 0, even when the register is full of offenders. ADVISORY
# surface for validate_board.sh — must never fail the board on its own.
write_register "$HDR" \
  "slop	SLOP-INV:9.99	Another untriaged inbound gap	gap	into-charon	none	none	advisory-test" \
  "charon	CHARON-MECH:advisory-1	Another unlinked outbound row	ported	out-of-charon	none	file-slop-ticket	advisory-test"
out="$(bash "$GATE" scan 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "(e1) scan mode always exits 0 even with offenders (advisory)" \
                || bad "(e1) scan mode always exits 0 (got $rc)"
has "$out" "UNSYNCED"        "(e2) scan surfaces the offenders (UNSYNCED line)"
has "$out" "ADVISORY"        "(e3) scan summary calls itself ADVISORY"

# --- (f) scan names the correct target repo in its summary lines too, so a manager
# reading the advisory surface sees the cross-repo assignments at a glance.
# Use a fully-linked register to test the ASSIGNED line that the scan emits for each
# out-of-charon row (see cmd_scan's LINKED branch).
write_register "$HDR_LINKED" \
  "charon	CHARON-MECH:scan-slop-marker	linked slop row	ported	out-of-charon	none	file-slop-ticket	linked	BL-9999" \
  "charon	CHARON-MECH:scan-ksf-marker	linked ksf row	ported	out-of-charon	none	file-ksf-ticket	linked	#77"
out="$(bash "$GATE" scan 2>&1)"
has "$out" "CHARON-MECH:scan-slop-marker" "(f) scan surfaces the SLOP-linked row"
has "$out" "CHARON-MECH:scan-ksf-marker"  "(f) scan surfaces the KSF-linked row"
has "$out" "slop"                         "(f) scan summary names slop target repo"
has "$out" "ksf"                          "(f) scan summary names ksf target repo"

rm -rf "$D"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL RULE-SYNC-GATE TESTS PASS"
