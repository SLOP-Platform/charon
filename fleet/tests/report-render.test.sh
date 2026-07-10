#!/usr/bin/env bash
# report-render.test.sh — FAIL-ON-REVERT test for the canonical roadmap renderer
# (fleet/report.sh). Renders a FIXTURE ROADMAP.tsv and asserts the grouped
# structure + wave sub-grouping + the done ✅/Done treatment + terse flattening.
# Reverting report.sh (dropping the PROJECT grouping, the wave sub-headers, the
# ✅/Done status treatment, the status symbols, the padding, or the terse mode)
# flips an assertion and the test fails. It never touches the live ROADMAP.tsv.
#
# Run:  bash fleet/tests/report-render.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT="$SRC/report.sh"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
# NOTE: haystack is passed as $3 (NOT piped in). A pipe would run the helper in a
# subshell and its ok/bad counter bumps would be lost — masking a real revert.
has(){ # has <label> <needle> <haystack>
  local label="$1" needle="$2" hay="$3"
  case "$hay" in *"$needle"*) ok "$label" ;; *) bad "$label (missing: $needle)" ;; esac
}
hasnt(){ local label="$1" needle="$2" hay="$3"
  case "$hay" in *"$needle"*) bad "$label (unexpected: $needle)" ;; *) ok "$label" ;; esac
}

# --- fixture --------------------------------------------------------------------
# Alpha: has waves (Wave A, Wave B) + a wave-less item (-> Unscheduled).
# Beta:  NO waves -> renders FLAT (no sub-headers).
# Mixed statuses incl. done (✅/Done) and an out-of-alpha id to prove input order.
FIX="$(mktemp)"
cat > "$FIX" <<'TSV'
# comment line — must be skipped
Alpha	A1	done	-	first-thing	do the first thing	Wave A

Alpha	A2	building	now	second-thing	do the second thing	Wave A
Alpha	A3	queued	next	third-thing	do the third thing	Wave B
Alpha	A4	designed	next	fourth-thing	do the fourth thing
Beta	B9	parked	next	beta-thing	the beta thing
Beta	B8	not-started	next	beta-two	another beta thing
TSV

export ROADMAP_TSV="$FIX"

echo "== full grouped mode =="
FULL="$(bash "$REPORT")"
has  "project 1 header is first project (PROJECT not PROGRAM)"  "PROJECT 1 — ALPHA"  "$FULL"
has  "project 2 header is second project"                       "PROJECT 2 — BETA"   "$FULL"
hasnt "no legacy PROGRAM header"                                "PROGRAM"            "$FULL"

# status column + phase word are DERIVED from status:
#   done -> ✅ + "Done" ; building -> 🟠 + "now" ; else -> circle + "next"
has  "done row: check mark + 'Done' phase"   "✅  Done"   "$FULL"
has  "building row: orange dot + 'now'"      "🟠  now"    "$FULL"
has  "queued row: yellow dot + 'next'"       "🟡  next"   "$FULL"
has  "designed row: purple dot + 'next'"     "🟣  next"   "$FULL"
has  "parked row: brown dot + 'next'"        "🟤  next"   "$FULL"
has  "not-started row: white dot + 'next'"   "⚪  next"   "$FULL"
# done rows no longer show a green dot or a '-' phase
hasnt "done row has no green dot"            "🟢"         "$FULL"
hasnt "done row has no '-' phase"            "  -  "      "$FULL"

# wide id->name gap (>=3 spaces) proves the widened column spacing is in effect,
# AND alignment holds across ✅-rows and circle-rows (id column lines up).
has  "done row body, wide id/name gap"       "A1   first-thing"   "$FULL"
has  "building row body"                     "A2   second-thing"  "$FULL"
has  "queued row body"                       "A3   third-thing"   "$FULL"
has  "designed row body (unscheduled)"       "A4   fourth-thing"  "$FULL"
has  "parked row body under Beta"            "B9   beta-thing"    "$FULL"
has  "totals footer present"                 "Totals:"            "$FULL"
has  "totals uses ✅ for done"               "✅ done="           "$FULL"
hasnt "comment line not rendered"            "comment line"       "$FULL"

# --- wave sub-grouping (Alpha has waves) ---
has  "Alpha renders Wave A sub-header"       "  Wave A"       "$FULL"
has  "Alpha renders Wave B sub-header"       "  Wave B"       "$FULL"
has  "wave-less item under Unscheduled"      "  Unscheduled"  "$FULL"
# exactly one Unscheduled sub-header (only Alpha has a wave-less item)
uns="$(printf '%s\n' "$FULL" | grep -c '^  Unscheduled$')"
[ "$uns" -eq 1 ] && ok "exactly one Unscheduled sub-header" || bad "Unscheduled count (got $uns)"

# --- Beta renders FLAT (no wave / Unscheduled sub-headers in its section) ---
BETA="$(printf '%s\n' "$FULL" | awk '/PROJECT 2 — BETA/{f=1} /^Totals:/{f=0} f')"
hasnt "Beta section has no Wave sub-header"        "Wave"         "$BETA"
hasnt "Beta section has no Unscheduled sub-header" "Unscheduled"  "$BETA"

# --- ONE blank line after EVERY PROJECT header ---
after1="$(printf '%s\n' "$FULL" | awk '/PROJECT 1 — ALPHA/{getline; print ($0=="")?"BLANK":"NOTBLANK"; exit}')"
after2="$(printf '%s\n' "$FULL" | awk '/PROJECT 2 — BETA/{getline; print ($0=="")?"BLANK":"NOTBLANK"; exit}')"
[ "$after1" = BLANK ] && ok "blank line after PROJECT 1 header" || bad "no blank after PROJECT 1 (got $after1)"
[ "$after2" = BLANK ] && ok "blank line after PROJECT 2 header" || bad "no blank after PROJECT 2 (got $after2)"

# input-order preserved within a project: A1 A2 A3 A4 before Beta block (B9 B8)
ORDER="$(printf '%s\n' "$FULL" | grep -oE 'A[0-9]|B[0-9]' | tr '\n' ' ')"
case "$ORDER" in "A1 A2 A3 A4 B9 B8 "*) ok "input order preserved (A1 A2 A3 A4 B9 B8)";; *) bad "input order (got: $ORDER)";; esac

# grouping: the Beta header comes AFTER all Alpha rows
a_last="$(printf '%s\n' "$FULL" | grep -n 'A4 .*fourth-thing' | head -1 | cut -d: -f1)"
b_hdr="$(printf '%s\n' "$FULL" | grep -n 'PROJECT 2 — BETA' | head -1 | cut -d: -f1)"
[ -n "$a_last" ] && [ -n "$b_hdr" ] && [ "$b_hdr" -gt "$a_last" ] \
  && ok "Beta group renders after all Alpha rows" \
  || bad "grouping order (a_last=$a_last b_hdr=$b_hdr)"

echo "== terse mode =="
TERSE="$(bash "$REPORT" --terse)"
hasnt "terse has no PROJECT headers"   "PROJECT"                 "$TERSE"
hasnt "terse has no wave sub-headers"  "Wave A"                  "$TERSE"
has   "terse row carries project + id" "Alpha  A1   first-thing" "$TERSE"
has   "terse done row: ✅ + Done"      "✅  Done"                "$TERSE"
has   "terse row for Beta"             "Beta"                    "$TERSE"
tcount="$(printf '%s\n' "$TERSE" | grep -cE ' (Alpha|Beta) ')"
[ "$tcount" -eq 6 ] && ok "terse prints one line per item (6)" || bad "terse line count (got $tcount)"

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
