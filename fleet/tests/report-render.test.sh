#!/usr/bin/env bash
# report-render.test.sh — FAIL-ON-REVERT test for the canonical roadmap renderer
# (fleet/report.sh). Renders a FIXTURE ROADMAP.tsv and asserts the grouped
# structure + a known row + terse flattening. Reverting report.sh (dropping the
# PROGRAM grouping, the dot mapping, the padding, or the terse mode) flips an
# assertion and the test fails. It never touches the live ROADMAP.tsv.
#
# Run:  bash fleet/tests/report-render.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT="$SRC/report.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ # has <label> <needle> <<< haystack
  local label="$1" needle="$2" hay; hay="$(cat)"
  case "$hay" in *"$needle"*) ok "$label" ;; *) bad "$label (missing: $needle)" ;; esac
}
hasnt(){ local label="$1" needle="$2" hay; hay="$(cat)"
  case "$hay" in *"$needle"*) bad "$label (unexpected: $needle)" ;; *) ok "$label" ;; esac
}

# --- fixture: two projects, mixed statuses, out-of-alpha id to prove input order ---
FIX="$(mktemp)"
cat > "$FIX" <<'TSV'
# comment line — must be skipped
Alpha	A1	done	-	first-thing	do the first thing

Alpha	A2	building	now	second-thing	do the second thing
Beta	B9	parked	next	beta-thing	the beta thing
Alpha	A3	not-started	next	third-thing	do the third thing
TSV

export ROADMAP_TSV="$FIX"

echo "== full grouped mode =="
FULL="$(bash "$REPORT")"
printf '%s' "$FULL" | has  "program 1 header is first project"  "PROGRAM 1 — ALPHA"
printf '%s' "$FULL" | has  "program 2 header is second project" "PROGRAM 2 — BETA"
# phase column: done -> '-', building -> 'now', everything else -> 'next' (its own aligned column)
printf '%s' "$FULL" | has  "done row: green dot + '-' phase"     "🟢  -"
printf '%s' "$FULL" | has  "building row: orange dot + 'now'"    "🟠  now"
printf '%s' "$FULL" | has  "parked row: brown dot + 'next'"      "🟤  next"
printf '%s' "$FULL" | has  "not-started row: white dot + 'next'" "⚪  next"
# wide id->name gap (>=3 spaces) proves the widened column spacing is in effect
printf '%s' "$FULL" | has  "done row body, wide id/name gap"     "A1   first-thing"
printf '%s' "$FULL" | has  "building row body"                   "A2   second-thing"
printf '%s' "$FULL" | has  "parked row body under Beta"          "B9   beta-thing"
printf '%s' "$FULL" | has  "not-started row body"                "A3   third-thing"
printf '%s' "$FULL" | has  "totals footer present"               "Totals:"
printf '%s' "$FULL" | hasnt "comment line not rendered"          "comment line"

# input-order preserved within a project: A1 before A2 before A3 (all before Beta block)
ORDER="$(printf '%s\n' "$FULL" | grep -oE 'A[0-9]|B[0-9]' | tr '\n' ' ')"
case "$ORDER" in "A1 A2 A3 B9 "*) ok "input order preserved (A1 A2 A3 B9)";; *) bad "input order (got: $ORDER)";; esac

# grouping: the Beta header comes AFTER all Alpha rows
a_last="$(printf '%s\n' "$FULL" | grep -n 'A3 .*third-thing' | head -1 | cut -d: -f1)"
b_hdr="$(printf '%s\n' "$FULL" | grep -n 'PROGRAM 2 — BETA' | head -1 | cut -d: -f1)"
[ -n "$a_last" ] && [ -n "$b_hdr" ] && [ "$b_hdr" -gt "$a_last" ] \
  && ok "Beta group renders after all Alpha rows" \
  || bad "grouping order (a_last=$a_last b_hdr=$b_hdr)"

echo "== terse mode =="
TERSE="$(bash "$REPORT" --terse)"
printf '%s' "$TERSE" | hasnt "terse has no PROGRAM headers" "PROGRAM"
printf '%s' "$TERSE" | has   "terse row carries project + id" "Alpha  A1   first-thing"
printf '%s' "$TERSE" | has   "terse row carries phase column" "🟢  -"
printf '%s' "$TERSE" | has   "terse row for Beta"             "Beta"
tcount="$(printf '%s\n' "$TERSE" | grep -cE '^.+ (Alpha|Beta) ')"
[ "$tcount" -eq 4 ] && ok "terse prints one line per item (4)" || bad "terse line count (got $tcount)"

echo "== bad arg rejected =="
rc=0; bash "$REPORT" --bogus >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] && ok "unknown arg exits 2" || bad "unknown arg exit (got $rc)"

echo "== missing roadmap fails loud =="
rc=0; ROADMAP_TSV=/no/such/roadmap.tsv bash "$REPORT" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 1 ] && ok "missing roadmap exits 1" || bad "missing roadmap exit (got $rc)"

rm -f "$FIX"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL REPORT-RENDER TESTS PASS"
