#!/usr/bin/env bash
# test_foreman_triggers.sh — FAIL-ON-REVERT: each foreman-cadence.sh trigger
# (session-start, post-land, handoff, cadence) surfaces STARVE on a starving
# board and OK on a fed board, all report-only.
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -qiF -- "$2" && ok "$3" || bad "$3 (missing: $2)"; }
no(){  printf '%s' "$1" | grep -qiF -- "$2" && bad "$3 (unexpected: $2)" || ok "$3"; }

cleanup(){ rm -rf "${T:-}"; }
trap cleanup EXIT
T="$(mktemp -d)"

# --- build a hermetic fixture fleet (symlink callees from real fleet) --------
FIX="$T/fix"
mkdir -p "$FIX"
for x in foreman.sh foreman-cadence.sh claim.sh _lib.sh repo-registry.sh \
         loop-guard.sh validate_board.sh model-detention.sh leak-guard.sh \
         tier-models.tsv wci-contention.sh done.sh; do
  [ -e "$SRC/$x" ] && ln -s "$SRC/$x" "$FIX/$x"
done
ln -s "$SRC/checks" "$FIX/checks"
mkdir -p "$FIX/board" "$FIX/state/done" "$FIX/state/loop-guard" \
         "$FIX/state/claims" "$FIX/state/submitted"

CADENCE_SH="$FIX/foreman-cadence.sh"

run_trigger(){
  local trigger="$1"
  FOREMAN_CADENCE_FLEET="$FIX" FOREMAN_FLEET="$FIX" \
    FOREMAN_CADENCE_INTERVAL=0 \
    bash "$CADENCE_SH" "$trigger" 2>&1 || true
}

echo "== (a) STARVING: empty board — every trigger surfaces the loud verdict =="

# (a1) session-start trigger
echo "  (a1) session-start"
out_a1="$(run_trigger session-start)"
has "$out_a1" "[STARVE]"        "(a1) session-start surfaces [STARVE] on empty board"
no  "$out_a1" "--fix" "(a1) session-start NEVER runs --fix"

# (a2) post-land trigger
echo "  (a2) post-land"
out_a2="$(run_trigger post-land)"
has "$out_a2" "[STARVE]"        "(a2) post-land surfaces [STARVE] on empty board"
no  "$out_a2" "--fix" "(a2) post-land NEVER runs --fix"

# (a3) handoff trigger
echo "  (a3) handoff"
out_a3="$(run_trigger handoff)"
has "$out_a3" "[STARVE]"        "(a3) handoff surfaces [STARVE] on empty board"
no  "$out_a3" "--fix" "(a3) handoff NEVER runs --fix"
has "$out_a3" '```'           "(a3) handoff emits fenced block for markdown embedding"

# (a4) cadence trigger
echo "  (a4) cadence"
out_a4="$(run_trigger cadence)"
has "$out_a4" "[STARVE]"        "(a4) cadence surfaces [STARVE] on empty board"
no  "$out_a4" "--fix" "(a4) cadence NEVER runs --fix"

echo "== (b) FED: non-empty board — no false STARVE =="

D_FED="$T/fed"
mkdir -p "$D_FED"
cp -r "$FIX"/* "$D_FED/" 2>/dev/null
for t in frontier strong economy; do
  {
    echo "repo: charon-private"
    echo "tier: $t"
    echo "difficulty: 2"
    echo "work_class: rig-meta"
    echo "branch: feat/fed-${t}"
    echo "owns: fleet/${t}.sh"
    echo "depends_on:"
  } > "$D_FED/board/FED-$t.md"
done

run_trigger_fed(){
  local trigger="$1"
  FOREMAN_CADENCE_FLEET="$D_FED" FOREMAN_FLEET="$D_FED" \
    FOREMAN_CADENCE_INTERVAL=0 \
    bash "$CADENCE_SH" "$trigger" 2>&1 || true
}

echo "  (b1) session-start"
out_b1="$(run_trigger_fed session-start)"
no  "$out_b1" "[STARVE]"  "(b1) session-start no false [STARVE] marker on fed board"
no  "$out_b1" "STARVING TIERS"  "(b1) session-start verdict not STARVING on fed board"
has "$out_b1" "[ok]"    "(b1) session-start surfaces [ok] tiers"

echo "  (b2) post-land"
out_b2="$(run_trigger_fed post-land)"
no  "$out_b2" "[STARVE]"  "(b2) post-land no false [STARVE] marker on fed board"

echo "  (b3) handoff"
out_b3="$(run_trigger_fed handoff)"
no  "$out_b3" "[STARVE]"  "(b3) handoff no false [STARVE] marker on fed board"
has "$out_b3" '```'     "(b3) handoff emits fenced block for fed board"

echo "  (b4) cadence"
out_b4="$(run_trigger_fed cadence)"
no  "$out_b4" "[STARVE]"  "(b4) cadence no false [STARVE] marker on fed board"

echo "== (c) FAIL-ON-REVERT: each trigger subcommand exists in foreman-cadence.sh =="

# If any trigger case is removed from the case statement, the call hits the
# default handler and dies with "unknown subcommand" — the test fails because
# it expects a running foreman, not an error.
for trig in session-start post-land handoff cadence; do
  out_c="$(run_trigger "$trig" 2>&1)" || true
  no  "$out_c" "unknown subcommand" "(c) $trig is a recognized subcommand (not removed)"
  has "$out_c" "FOREMAN"     "(c) $trig runs foreman.sh (not stubbed out)"
done

echo; echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] && echo "ALL FOREMAN-TRIGGERS TESTS PASS" || exit 1
