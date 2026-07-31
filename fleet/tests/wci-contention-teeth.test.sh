#!/usr/bin/env bash
# wci-contention-teeth.test.sh — FAIL-ON-REVERT tests for the TEETH added to
# fleet/wci-contention.sh (2026-07-24): fail-CLOSED exit codes, the idempotent
# board-valid AUTO-TICKET generator, its self-closing reconcile leg, and the
# default-OFF ratchet.
#
# HERMETIC: every case builds its own throwaway fleet under `mktemp -d` (board +
# state + ROADMAP.tsv), and NEVER reads or writes the live fleet/board, the live
# ROADMAP, or the product repo. No network.
#
# NAMED `*.test.sh` DELIBERATELY: fleet/gate.sh globs `$FLEET/tests/*.test.sh`. A
# `test_*.sh` name (e.g. the former tests/test_wci_strict.sh, renamed to wci-strict.test.sh in this change) is NOT matched by
# that glob and therefore never runs in the gate — a test nobody executes is not a gate.
#
# Covers, by execution:
#   (A) FAIL-CLOSED. Bad flag / bad N / missing board / ZERO tickets scanned / tickets
#       with no owns at all => exit 2. Each of those used to `exit 0` — a complaint on
#       stderr followed by a SUCCESS receipt, which every caller read as "no contention".
#       Revert any one of them to `exit 0` and the matching case here goes RED.
#   (B) GENERATE. One ticket per contended PATH, priority 1, dep-ordered behind every
#       live owner, with a matching ROADMAP.tsv row — and the REAL fleet/validate_board.sh
#       must report GREEN on the resulting board (a generator that reds the board is worse
#       than no generator).
#   (C) IDEMPOTENCY (the load-bearing property). Re-running never creates a second ticket
#       for the same path, and never appends a second roadmap row.
#   (D) EXISTING COVERAGE. A live decompose-intent ticket, or a live ticket already owning
#       exactly that path, suppresses creation (no duplicate, no validate_board WCI-2
#       redundancy red).
#   (E) SELF-CLOSING / NON-ACCRETING. Contention below threshold, or an owner carrying
#       `serial_justified:`, PARKS the auto-ticket; a CLAIMED auto-ticket is never parked.
#   (F) ANTI-ACCRETION. The auto-ticket is excluded from the contention count it tracks
#       (else the remedy sustains the disease forever).
#   (G) RATCHET default-OFF. An ancient unactioned auto-ticket exits 0 with no flag, and
#       exits 1 only when --ratchet is explicitly armed.
#
# Run:  bash fleet/tests/wci-contention-teeth.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }
no(){  printf '%s' "$1" | grep -q -- "$2" && bad "$3 (unexpected '$2')" || ok "$3"; }
rc_is(){ [ "$1" = "$2" ] && ok "$3 (rc=$1)" || bad "$3 (expected rc=$2, got rc=$1)"; }

WCI="$SRC/wci-contention.sh"

# A fixture fleet carrying the REAL validate_board.sh + its dependencies, so board
# validity is PROVEN by the actual validator, not asserted. Same harness shape as
# fleet/tests/board-correctness.test.sh (reused, not reinvented).
mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/wci-contention.sh" "$SRC/validate_board.sh" "$d/"
  cp -r "$SRC/capability" "$d/capability"
  cp -r "$SRC/checks" "$d/checks"
  mkdir -p "$d/board/archive" "$d/state/done" "$d/state/claims" "$d/state/submitted"
  printf '# roadmap fixture\n' > "$d/state/ROADMAP.tsv"
  printf '%s' "$d"
}
# mk_ticket <dir> <id> <owns-csv> [extra-line...]
mk_ticket(){
  local d="$1" id="$2" owns="$3"; shift 3
  {
    echo "repo: charon-private"
    echo "tier: strong"
    # difficulty 2 deliberately: >=3 with >1 owned surface trips the (unrelated)
    # parallelizability gate inside validate_board.sh and would drown this fixture in
    # noise that has nothing to do with the generator under test.
    echo "difficulty: 2"
    echo "work_class: rig-meta"
    echo "branch: feat/${id,,}"
    echo "depends_on:"
    echo "owns: $owns"
    echo "ds: |"
    echo "  ## Dependencies & sequence"
    echo "  wave 1; concurrency-safe"
    for x in "$@"; do echo "$x"; done
  } > "$d/board/$id.md"
}
# A board where fleet/god.sh is owned by 4 tickets (>= default N=4), each ALSO owning a
# private path so no two tickets share an identical owns set.
mk_contended(){
  local d="$1"
  mk_ticket "$d" T1 "fleet/god.sh, fleet/a.sh"
  mk_ticket "$d" T2 "fleet/god.sh, fleet/b.sh"
  mk_ticket "$d" T3 "fleet/god.sh, fleet/c.sh"
  mk_ticket "$d" T4 "fleet/god.sh, fleet/d.sh"
}
run(){ # run <fleet-dir> <args...> -> stdout+stderr in $OUT, rc in $RC
  local d="$1"; shift
  OUT="$(bash "$d/wci-contention.sh" "$@" 2>&1)"; RC=$?
}
vb(){ CHARON_REPO="$1" bash "$1/validate_board.sh" 2>&1; }
# The generator's contract is "never RED the board". A contended fixture is ALREADY red by
# construction (that is what contention means to validate_board), so the honest assertion is
# that no RED line names the AUTO-TICKET — not that the fixture is clean.
# An owns-collision RED lists ALL owners of the path but only the UNSEQUENCED pairs in
# [brackets]. Being named as an owner is expected (the auto-ticket does own the file); being
# named in a PAIR is the failure — that would mean its deps did not sequence it.
_auto_red_lines(){
  vb "$1" | grep 'RED' | awk '/WCI-DEC/{
    if ($0 ~ /owns-collision/) { p=$0; sub(/.*\[/, "", p); if (p ~ /WCI-DEC/) print }
    else print }'
}
no_auto_red(){ # no_auto_red <fleet-dir> <label>
  local l n; l="$(_auto_red_lines "$1")"; n=0; [ -n "$l" ] && n="$(printf '%s\n' "$l" | grep -c .)"
  [ "$n" = 0 ] && ok "$2" || bad "$2 ($n RED line(s) implicate the auto-ticket: $(printf '%s' "$l" | head -2))"
}

echo "== (A) FAIL-CLOSED: uncertainty must never exit 0 =="
d="$(mk_fleet)"; mk_contended "$d"
run "$d" --bogus-flag;         rc_is "$RC" 2 "(A1) unknown flag is RED"
run "$d" notanumber;           rc_is "$RC" 2 "(A2) non-integer N is RED"
run "$d" 0;                    rc_is "$RC" 2 "(A3) N=0 is RED"
run "$d" --ratchet=notanumber; rc_is "$RC" 2 "(A4) non-integer --ratchet DAYS is RED"
rm -rf "$d"

d="$(mk_fleet)"; rm -rf "$d/board"
run "$d";                      rc_is "$RC" 2 "(A5) missing board dir is RED"
has "$OUT" "no board dir"      "(A5) ... and says why"
rm -rf "$d"

d="$(mk_fleet)"   # board/ exists but holds ZERO ticket files
run "$d";                      rc_is "$RC" 2 "(A6) ZERO tickets scanned is RED (zero discovery != no contention)"
has "$OUT" "ZERO ticket files" "(A6) ... and names the vacuous-scan reason"
rm -rf "$d"

d="$(mk_fleet)"; mk_ticket "$d" NOOWNS ""   # a ticket file with an EMPTY owns:
run "$d";                      rc_is "$RC" 2 "(A7) tickets scanned but NO owns at all is RED (metric undefined)"
rm -rf "$d"

# Guard the other direction: a healthy, uncontended board must still be GREEN, else the
# fail-closed work would red every preflight on the rig.
d="$(mk_fleet)"; mk_ticket "$d" S1 "fleet/one.sh"; mk_ticket "$d" S2 "fleet/two.sh"
run "$d";                      rc_is "$RC" 0 "(A8) healthy uncontended board is still GREEN (no false RED)"
has "$OUT" "no DECOMPOSE CANDIDATE" "(A8) ... with the advisory clean line"
rm -rf "$d"

echo
echo "== (B) GENERATE: the advisory becomes TRACKED, BOARD-VALID work =="
d="$(mk_fleet)"; mk_contended "$d"
run "$d" --generate;           rc_is "$RC" 0 "(B1) --generate succeeds"
has "$OUT" "CREATE WCI-DEC-FLEET-GOD-SH" "(B1) creates the decompose ticket for the contended path"
tk="$d/board/WCI-DEC-FLEET-GOD-SH.md"
[ -f "$tk" ] && ok "(B2) ticket file written" || bad "(B2) ticket file written"
grep -q '^priority: 1$' "$tk" && ok "(B3) ticket is priority: 1 (PRIORITY-LADDER.md int band)" \
  || bad "(B3) ticket is priority: 1"
grep -q '^owns: fleet/god.sh$' "$tk" && ok "(B4) owns the contended path" || bad "(B4) owns the contended path"
grep -q '^depends_on: T1, T2, T3, T4$' "$tk" && ok "(B5) dep-ordered behind EVERY live owner" \
  || bad "(B5) dep-ordered behind every live owner ($(grep -m1 '^depends_on:' "$tk"))"
grep -q '^dep-kind: build$' "$tk" && ok "(B6) carries dep-kind: build (justifies the sequencing)" \
  || bad "(B6) carries dep-kind: build"
grep -q 'fail-on-revert' "$tk" && ok "(B7) acceptance is non-vacuous + fail-on-revert" \
  || bad "(B7) acceptance is fail-on-revert"
grep -qi '## Dependencies & sequence' "$tk" && ok "(B8) carries the D&S standing-rule section" \
  || bad "(B8) carries the D&S section"
rows="$(grep -c 'WCI-DEC-FLEET-GOD-SH' "$d/state/ROADMAP.tsv")"
[ "$rows" = 1 ] && ok "(B9) exactly ONE matching ROADMAP.tsv row" || bad "(B9) ROADMAP rows = $rows (want 1)"

# THE proof, part 1: the REAL validator must not raise a single RED naming the auto-ticket.
no_auto_red "$d" "(B10) fleet/validate_board.sh raises NO red against the auto-ticket"
vout="$(vb "$d")"
no "$vout" "WCI redundancy" "(B11) no WCI redundancy red anywhere on the board"
printf '%s' "$vout" | grep 'owns-collision LIVE' | sed 's/.*\[//' | grep -q 'WCI-DEC' \
  && bad "(B12) auto-ticket appears in an UNSEQUENCED owns-collision pair (its deps failed to sequence it)" \
  || ok "(B12) auto-ticket is dep-ORDERED behind its owners (never in an unsequenced pair)"

echo
echo "== (C) IDEMPOTENCY: re-running must NEVER spam the board =="
run "$d" --generate;           rc_is "$RC" 0 "(C1) second --generate run succeeds"
has "$OUT" "EXISTS WCI-DEC-FLEET-GOD-SH" "(C2) recognises its own prior ticket by contended PATH"
no  "$OUT" "CREATE "           "(C3) creates NOTHING on the second run"
n="$(ls "$d/board" | grep -c '^WCI-DEC-')"
[ "$n" = 1 ] && ok "(C4) still exactly ONE auto-ticket on the board" || bad "(C4) auto-tickets on board = $n (want 1)"
rows="$(grep -c 'WCI-DEC-FLEET-GOD-SH' "$d/state/ROADMAP.tsv")"
[ "$rows" = 1 ] && ok "(C5) still exactly ONE ROADMAP row" || bad "(C5) ROADMAP rows = $rows (want 1)"

echo
echo "== (F) ANTI-ACCRETION: the remedy is not counted as the disease =="
run "$d"
has "$OUT" "owned by 4 tickets" "(F1) auto-ticket is EXCLUDED from the contention count it tracks"
rm -rf "$d"

echo
echo "== (B16) a fully-GREEN board stays GREEN after generation =="
# Contention that is already dep-SEQUENCED (a hand-off chain) validates GREEN. Generating
# into it is the strongest board-validity proof available: GREEN before, GREEN after.
d="$(mk_fleet)"
mk_ticket "$d" C1 "fleet/god.sh, fleet/a.sh"
mk_ticket "$d" C2 "fleet/god.sh, fleet/b.sh" "dep-kind: build"
mk_ticket "$d" C3 "fleet/god.sh, fleet/c.sh" "dep-kind: build"
mk_ticket "$d" C4 "fleet/god.sh, fleet/d.sh" "dep-kind: build"
sed -i 's/^depends_on:$/depends_on: C1/' "$d/board/C2.md"
sed -i 's/^depends_on:$/depends_on: C2/' "$d/board/C3.md"
sed -i 's/^depends_on:$/depends_on: C3/' "$d/board/C4.md"
vb "$d" >/dev/null 2>&1 && ok "(B16) sequenced-contention fixture is GREEN before generation" \
  || bad "(B16) fixture not GREEN before generation: $(vb "$d" | grep -m3 'RED')"
run "$d" --generate
has "$OUT" "CREATE WCI-DEC-FLEET-GOD-SH" "(B17) generates into the green board"
vb "$d" >/dev/null 2>&1 && ok "(B18) board is STILL GREEN after generation (auto-ticket is board-valid)" \
  || bad "(B18) generation RED-ed a green board: $(vb "$d" | grep -m3 'RED')"
rm -rf "$d"

echo
echo "== (D) EXISTING COVERAGE: link, never duplicate =="
d="$(mk_fleet)"; mk_contended "$d"
mk_ticket "$d" DECOMPOSE-GOD "fleet/god.sh, fleet/seams.sh"
run "$d" --generate
has "$OUT" "COVERED fleet/god.sh" "(D1) a live decompose-intent ticket suppresses creation"
[ ! -f "$d/board/WCI-DEC-FLEET-GOD-SH.md" ] && ok "(D2) no duplicate ticket emitted" || bad "(D2) duplicate ticket emitted"
rm -rf "$d"

d="$(mk_fleet)"; mk_contended "$d"; mk_ticket "$d" SOLO-OWNER "fleet/god.sh"
run "$d" --generate
has "$OUT" "identical owns set" "(D3) a live ticket owning EXACTLY that path suppresses creation (WCI-2 guard)"
[ ! -f "$d/board/WCI-DEC-FLEET-GOD-SH.md" ] && ok "(D4) no redundant-owns ticket emitted" || bad "(D4) redundant ticket emitted"
rm -rf "$d"

echo
echo "== (B13) --dry-run plans but writes NOTHING =="
d="$(mk_fleet)"; mk_contended "$d"
run "$d" --generate --dry-run
has "$OUT" "DRY-RUN would CREATE" "(B13) dry-run reports the plan"
[ -z "$(ls "$d/board" | grep '^WCI-DEC-' || true)" ] && ok "(B14) dry-run wrote no ticket" || bad "(B14) dry-run wrote a ticket"
grep -q 'WCI-DEC' "$d/state/ROADMAP.tsv" && bad "(B15) dry-run touched ROADMAP.tsv" || ok "(B15) dry-run left ROADMAP.tsv alone"
rm -rf "$d"

echo
echo "== (E) SELF-CLOSING: an auto-ticket must not outlive its contention =="
d="$(mk_fleet)"; mk_contended "$d"
run "$d" --generate
rm -f "$d/board/T3.md" "$d/board/T4.md"          # contention drops from 4 to 2 (< N)
run "$d" --generate
has "$OUT" "STALE WCI-DEC-FLEET-GOD-SH" "(E1) contention below threshold PARKS the auto-ticket"
grep -q '^parked: true$' "$d/board/WCI-DEC-FLEET-GOD-SH.md" && ok "(E2) explicit 'parked: true' (not note-only)" \
  || bad "(E2) explicit parked: true field"
grep -q $'WCI-DEC-FLEET-GOD-SH\tparked' "$d/state/ROADMAP.tsv" && ok "(E3) ROADMAP row marked parked" \
  || bad "(E3) ROADMAP row marked parked"
grep -q '^depends_on:$' "$d/board/WCI-DEC-FLEET-GOD-SH.md" \
  && ok "(E4a) parking CLEARS depends_on (a retired ticket must not leave dangling deps)" \
  || bad "(E4a) parked ticket still carries deps: $(grep -m1 '^depends_on:' "$d/board/WCI-DEC-FLEET-GOD-SH.md")"
no_auto_red "$d" "(E4b) validate_board.sh raises NO red against the parked auto-ticket"
rm -rf "$d"

d="$(mk_fleet)"; mk_contended "$d"
run "$d" --generate
# an owner declares the file serial BY DESIGN -> the decompose ticket is no longer wanted
printf 'serial_justified: the file is one indivisible sensor\n' >> "$d/board/T1.md"
run "$d" --generate
has "$OUT" "serial_justified" "(E5) a justified-serial owner PARKS the auto-ticket"
grep -q '^parked: true$' "$d/board/WCI-DEC-FLEET-GOD-SH.md" && ok "(E6) ... with the explicit parked field" \
  || bad "(E6) parked field after serial_justified"
rm -rf "$d"

d="$(mk_fleet)"; mk_contended "$d"
run "$d" --generate
: > "$d/state/claims/WCI-DEC-FLEET-GOD-SH"        # a droid is working on it
rm -f "$d/board/T3.md" "$d/board/T4.md"
run "$d" --generate
has "$OUT" "BLOCKED-STALE" "(E7) a CLAIMED auto-ticket is never silently parked"
grep -q '^parked: true$' "$d/board/WCI-DEC-FLEET-GOD-SH.md" && bad "(E8) parked a claimed ticket (parked-but-claimed red)" \
  || ok "(E8) claimed ticket left un-parked"
rm -rf "$d"

echo
echo "== (G) RATCHET: built, DEFAULT OFF =="
d="$(mk_fleet)"; mk_contended "$d"
run "$d" --generate
tk="$d/board/WCI-DEC-FLEET-GOD-SH.md"
sed -i 's/^created: .*/created: 2020-01-01/' "$tk"      # ancient + unactioned
run "$d";            rc_is "$RC" 0 "(G1) an ancient unactioned auto-ticket does NOT escalate by default (ratchet OFF)"
run "$d" --generate; rc_is "$RC" 0 "(G2) ... and --generate alone still does not escalate"
run "$d" --ratchet 7
rc_is "$RC" 1 "(G3) armed --ratchet escalates an auto-ticket ignored beyond the threshold"
has "$OUT" "RATCHET ESCALATION" "(G4) ... and names the escalation"
sed -i "s/^created: .*/created: $(date +%F)/" "$tk"
run "$d" --ratchet 7; rc_is "$RC" 0 "(G5) a FRESH auto-ticket does not escalate (non-vacuous: the ratchet reads the date)"
rm -rf "$d"

echo
echo "== (H) the preflight.sh LEG: fail-closed + acts on what it finds =="
# The leg is exercised by SOURCING preflight.sh into a throwaway fleet (its dispatch guard
# makes sourcing side-effect-free) and calling the one function. reds.tsv is the fixture's.
mk_pf_fleet(){
  local d; d="$(mk_fleet)"
  cp "$SRC/preflight.sh" "$SRC/_lib.sh" "$d/"
  printf '# id\topened\tsev\tarea\tdesc\tcheck\tstatus\tclosed_by\n' > "$d/reds.tsv"
  printf '%s' "$d"
}
leg(){ # leg <dir> -> $OUT
  OUT="$(cd "$1" && WCI_AUTOTICKET="${WCI_AUTOTICKET:-1}" bash -c '
    source ./preflight.sh
    detect_wci_contention' 2>&1)"
}

d="$(mk_pf_fleet)"; mk_contended "$d"; rm -f "$d/wci-contention.sh"
leg "$d"
has "$OUT" "DETECTOR MISSING" "(H1) a MISSING detector is loud (was: silent 'return 0')"
grep -q 'wci-contention-detector-broken' "$d/reds.tsv" \
  && ok "(H2) ... and AUTO-REGISTERS a tracked, preflight-blocking red" \
  || bad "(H2) no red registered for the missing detector"
rm -rf "$d"

d="$(mk_pf_fleet)"; mk_contended "$d"; rm -rf "$d/board"
leg "$d"
has "$OUT" "DETECTOR REFUSED" "(H3) a detector that REFUSES (rc 2) is loud"
grep -q 'wci-contention-detector-broken' "$d/reds.tsv" \
  && ok "(H4) ... and AUTO-REGISTERS a tracked red (fail-closed, not a clean pass)" \
  || bad "(H4) no red registered for the refusing detector"
rm -rf "$d"

d="$(mk_pf_fleet)"; mk_contended "$d"
leg "$d"
has "$OUT" "AUTO-TICKETED at priority 1" "(H5) the leg reports the candidates as TRACKED work"
has "$OUT" "CREATE WCI-DEC-FLEET-GOD-SH"  "(H6) ... and surfaces what it created"
[ -f "$d/board/WCI-DEC-FLEET-GOD-SH.md" ] && ok "(H7) the leg actually generated the ticket" \
  || bad "(H7) the leg generated no ticket"
rm -rf "$d"

d="$(mk_pf_fleet)"; mk_contended "$d"
WCI_AUTOTICKET=0 leg "$d"
has "$OUT" "auto-ticketing SUPPRESSED" "(H8) WCI_AUTOTICKET=0 is an honest, LOUD suppression"
[ ! -f "$d/board/WCI-DEC-FLEET-GOD-SH.md" ] && ok "(H9) ... and writes nothing" || bad "(H9) wrote a ticket while suppressed"
rm -rf "$d"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] && { echo "ALL WCI-CONTENTION-TEETH TESTS PASS"; exit 0; } || exit 1
