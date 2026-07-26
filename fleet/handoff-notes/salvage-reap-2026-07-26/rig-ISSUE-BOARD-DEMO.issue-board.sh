#!/usr/bin/env bash
# issue-board.sh — SG ISSUE-CONTROL-PLANE, LEG 2 (SURFACE) — PROTOTYPE / DOGFOOD DEMO.
#
# Design of record: fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md §3 (SURFACE LOUDLY).
# This is the AGGREGATOR/surfacer: it treats every EXISTING detector as a
# StackStorm-style *sensor*, runs each against the LIVE fleet, unions their
# verdicts into ONE board (state/issue-board.tsv) and prints ONE loud
# SessionStart-style summary line. It is REPORT-ONLY (never --fix): acting stays
# a manager decision (foreman-cadence doctrine).
#
# NOT the production build — the real build adds the KS29 detector-registry
# (so a new failure-class = 1 row) and the LEG-3 gated rule->action layer.
# This prototype hard-wires the 6 detectors named in the design to PROVE the
# surface leg on real current state.
#
# DISCIPLINE (plane-canary.sh:245): capture-then-check, NEVER pipe-mask. Every
# sensor runs into a captured file + rc, then we parse the file. A sensor that
# ERRORS is surfaced as its own RED row (a detector cannot silently go empty).
#
# Columns: severity | class | issue | source_detector | first_seen | age
#   first_seen: wall-clock stamp at this run (fresh demo => all "now").
#   age: ticks since first_seen (0 in this fresh demo; real build persists+ages).
#
# Env:
#   CHARON_PRODUCT_REPO  product repo for the inert sensor (default /home/stack/code/charon)
#   BOARD_TEST_SCAN      path to a precomputed gate-test scan (PASS/RED\tname per line);
#                        if set+readable the tests sensor reads it instead of re-running
#                        all 74 tests (keeps the surfacer cheap; the real build caches this).
#   BOARD_TEST_TIMEOUT   per-test timeout secs when running the scan inline (default 20)
#   BOARD_SKIP_TESTS=1   skip the (heavy) gate-test sensor entirely
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$FLEET/.." && pwd)"
# LIVE fleet checkout — state (claims, loop-guard, runlog) lives in the MAIN
# checkout, NOT in a per-worktree copy. State-reading sensors MUST run there or
# they read an empty worktree state and silently under-count. The board TSV
# still writes to THIS (worktree) state so the demo does not pollute live.
LIVE_ROOT="${CHARON_LIVE_FLEET:-/home/stack/charon-private}"
[ -d "$LIVE_ROOT/fleet" ] || LIVE_ROOT="$ROOT"
STATE="$FLEET/state"
BOARD="$STATE/issue-board.tsv"
PRODUCT_REPO="${CHARON_PRODUCT_REPO:-/home/stack/code/charon}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
NOW="$(date '+%Y-%m-%dT%H:%M:%S')"

mkdir -p "$STATE"
# TSV header
printf 'severity\tclass\tissue\tsource_detector\tfirst_seen\tage\n' > "$BOARD"

# counters (per severity + per class)
RED=0; YELLOW=0
declare -A CLASSN

emit(){ # emit <severity> <class> <issue-text> <detector>
  local sev="$1" cls="$2" issue="$3" det="$4"
  # tabs/newlines out of the issue text so the TSV stays one-row-per-issue
  issue="$(printf '%s' "$issue" | tr '\t\n' '  ')"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$sev" "$cls" "$issue" "$det" "$NOW" "0" >> "$BOARD"
  case "$sev" in RED) RED=$((RED+1));; YELLOW) YELLOW=$((YELLOW+1));; esac
  CLASSN[$cls]=$(( ${CLASSN[$cls]:-0} + 1 ))
}

# A sensor that could not be wired / errored is itself surfaced RED (never empty-masked).
sensor_fault(){ emit RED detector-fault "SENSOR $1 could not run: $2" "issue-board.sh"; }

# ─────────────────────────────────────────────────────────────────────────────
# SENSOR 1 — inert code (built-but-not-wired). tools/check_inert_code.py
# ─────────────────────────────────────────────────────────────────────────────
sensor_inert(){
  local out="$TMP/inert.out" rc
  if [ ! -f "$PRODUCT_REPO/tools/check_inert_code.py" ]; then
    sensor_fault check_inert_code "not found at $PRODUCT_REPO/tools/check_inert_code.py"; return
  fi
  ( cd "$PRODUCT_REPO" && python3 tools/check_inert_code.py ) >"$out" 2>&1; rc=$?
  # RED: undisposed dead symbols (gate FAIL). "N dead symbol(s) found, M tracked"
  local found tracked undisposed
  found=$(grep -oE '[0-9]+ dead symbol\(s\) found' "$out" | grep -oE '^[0-9]+' | head -1)
  tracked=$(grep -oE 'found, [0-9]+ tracked' "$out" | grep -oE '[0-9]+' | head -1)
  found="${found:-0}"; tracked="${tracked:-0}"
  undisposed=$(( found - tracked ))
  if [ "$rc" -ne 0 ] && [ "$undisposed" -le 0 ]; then
    # non-zero exit but no clear undisposed count => surface the gate failure
    undisposed=$(grep -ciE 'undisposed|not disposed|FAIL' "$out"); undisposed="${undisposed:-1}"
  fi
  if [ "$undisposed" -gt 0 ]; then
    emit RED inert "$undisposed inert symbol(s) with NO disposition (wire/delete/keep-why) — gate RED" tools/check_inert_code.py
  fi
  # YELLOW: symbols dispositioned wire/delete = pending action (an open issue, just triaged)
  local pend
  pend=$(grep -cE '^\s*\[(wire|delete)\]' "$out")
  if [ "${pend:-0}" -gt 0 ]; then
    emit YELLOW inert-pending "$pend inert symbol(s) dispositioned wire/delete — pending action" tools/check_inert_code.py
  fi
  # info: stale disposition entries (symbol no longer dead)
  local stale
  stale=$(grep -oE '[0-9]+ disposition entries are stale' "$out" | grep -oE '^[0-9]+' | head -1)
  if [ -n "${stale:-}" ] && [ "$stale" -gt 0 ]; then
    emit YELLOW inert-stale-disposition "$stale disposition entry(ies) stale (symbol no longer dead — prune)" tools/check_inert_code.py
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# SENSOR 2 — unwired/proofless planes. plane-canary.sh reconcile
# ─────────────────────────────────────────────────────────────────────────────
sensor_planes(){
  local out="$TMP/planes.out" rc
  ( cd "$LIVE_ROOT" && bash fleet/plane-canary.sh reconcile ) >"$out" 2>&1; rc=$?
  if ! grep -qE 'PLANE-CANARY reconcile: (GREEN|RED)' "$out"; then
    sensor_fault plane-canary "reconcile produced no verdict banner (rc=$rc)"; return
  fi
  # each "  RED    plane 'X': <reason>" line is one issue
  while IFS= read -r line; do
    local plane reason
    plane=$(printf '%s' "$line" | grep -oE "plane '[^']+'" | head -1)
    reason=$(printf '%s' "$line" | sed -E "s/^\s*RED\s+//")
    emit RED unwired-plane "$reason" "plane-canary.sh reconcile"
  done < <(grep -E "^\s*RED\s+plane '" "$out")
}

# ─────────────────────────────────────────────────────────────────────────────
# SENSOR 3 — stale claims (dead lease). reconcile-stale-claims.sh (DRY-RUN)
# ─────────────────────────────────────────────────────────────────────────────
sensor_claims(){
  local out="$TMP/claims.out" rc
  ( cd "$LIVE_ROOT" && bash fleet/reconcile-stale-claims.sh ) >"$out" 2>&1; rc=$?
  if ! grep -qE 'reconcile-stale-claims: done' "$out"; then
    sensor_fault reconcile-stale-claims "no completion line (rc=$rc)"; return
  fi
  # RED: would-hold / held (unmerged work on a dead lease — must not be released)
  local hold held
  hold=$(grep -oE 'would-hold:\s+[0-9]+' "$out" | grep -oE '[0-9]+' | head -1); hold="${hold:-0}"
  held=$(grep -oE 'held \(unresolved\):[0-9]+' "$out" | grep -oE '[0-9]+' | head -1); held="${held:-0}"
  local red_claims=$(( hold + held ))
  [ "$red_claims" -gt 0 ] && emit RED stale-claim "$red_claims dead-lease claim(s) with UNMERGED work — held loud (not released)" "reconcile-stale-claims.sh"
  # YELLOW: format-drift claims the reconciler cannot parse (each SKIP line = one)
  while IFS= read -r line; do
    local id
    id=$(printf '%s' "$line" | grep -oE 'SKIP\s+\S+' | awk '{print $2}')
    emit YELLOW stale-claim-driftfmt "claim '$id' format-drift — unparseable owner, reconciler cannot classify" "reconcile-stale-claims.sh"
  done < <(grep -E '^SKIP\s' "$out")
}

# ─────────────────────────────────────────────────────────────────────────────
# SENSOR 4 — quarantined tickets (loop-guard spin). loop-guard.sh list
# ─────────────────────────────────────────────────────────────────────────────
sensor_quarantine(){
  local out="$TMP/lg.out" rc
  ( cd "$LIVE_ROOT" && bash fleet/loop-guard.sh list ) >"$out" 2>&1; rc=$?
  if [ "$rc" -ne 0 ] && ! [ -s "$out" ]; then
    sensor_fault loop-guard "list exited $rc with no output"; return
  fi
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    local id
    id=$(printf '%s' "$line" | cut -d: -f1)
    emit YELLOW quarantined "ticket '$id' QUARANTINED by loop-guard (zero-commit spin) — clear once block fixed" "loop-guard.sh list"
  done < "$out"
}

# ─────────────────────────────────────────────────────────────────────────────
# SENSOR 5 — failing gate-tests (board-correctness class). fleet/tests/*.test.sh
# ─────────────────────────────────────────────────────────────────────────────
sensor_gatetests(){
  [ "${BOARD_SKIP_TESTS:-0}" = "1" ] && { emit YELLOW gate-test-skipped "gate-test sensor skipped (BOARD_SKIP_TESTS=1)" "issue-board.sh"; return; }
  local scan="$TMP/testscan.tsv"
  if [ -n "${BOARD_TEST_SCAN:-}" ] && [ -r "$BOARD_TEST_SCAN" ]; then
    scan="$BOARD_TEST_SCAN"
  else
    local to="${BOARD_TEST_TIMEOUT:-20}" t name
    : > "$scan"
    for t in "$ROOT"/fleet/tests/*.test.sh; do
      name=$(basename "$t" .test.sh)
      if timeout "$to" bash "$t" >/dev/null 2>&1; then printf 'PASS\t%s\n' "$name" >>"$scan"
      else printf 'RED\t%s\n' "$name" >>"$scan"; fi
    done
  fi
  if ! [ -s "$scan" ]; then sensor_fault gate-tests "scan produced no results"; return; fi
  while IFS=$'\t' read -r verdict name _; do
    [ "$verdict" = "RED" ] || continue
    local rc=""
    case "$name" in *" (rc="*) rc="${name#* (rc=}"; rc=" [rc=${rc%)}]"; name="${name%% (rc=*}";; esac
    emit RED gate-test-red "gate-test '$name' FAILS$rc — board-correctness class (a red test can silently red the queue)" "fleet/tests/$name.test.sh"
  done < "$scan"
}

# ─────────────────────────────────────────────────────────────────────────────
# SENSOR 6 — done-but-unmerged / un-pushed. git across worktrees
# ─────────────────────────────────────────────────────────────────────────────
sensor_git(){
  local wt br ahead pushed
  while read -r wt; do
    [ -z "$wt" ] && continue
    br=$(git -C "$wt" branch --show-current 2>/dev/null) || continue
    [ -z "$br" ] && continue
    ahead=$(git -C "$wt" rev-list --count origin/master.."$br" 2>/dev/null) || ahead=0
    [ "${ahead:-0}" -gt 0 ] || continue
    pushed=$(git -C "$wt" ls-remote origin "$br" 2>/dev/null | wc -l)
    if [ "${pushed:-0}" -eq 0 ]; then
      emit RED unpushed "branch '$br' has $ahead local commit(s) NOT on origin (work-loss risk / un-pushed)" "git rev-list/ls-remote"
    else
      emit YELLOW done-unmerged "branch '$br' +$ahead commit(s) pushed but NOT merged to master (open/unretired)" "git rev-list/ls-remote"
    fi
  done < <(git -C "$LIVE_ROOT" worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2}')
}

# ── run every sensor ─────────────────────────────────────────────────────────
sensor_inert
sensor_planes
sensor_claims
sensor_quarantine
sensor_gatetests
sensor_git

TOTAL=$(( $(wc -l < "$BOARD") - 1 ))

# ── SURFACE: SessionStart-style summary line ─────────────────────────────────
inert_n="${CLASSN[inert]:-0}"
plane_n="${CLASSN[unwired-plane]:-0}"
stale_n=$(( ${CLASSN[stale-claim]:-0} + ${CLASSN[stale-claim-driftfmt]:-0} ))
quar_n="${CLASSN[quarantined]:-0}"
gtest_n="${CLASSN[gate-test-red]:-0}"
git_n=$(( ${CLASSN[unpushed]:-0} + ${CLASSN[done-unmerged]:-0} ))

if [ "$TOTAL" -eq 0 ]; then
  SUMMARY="✅ ISSUE-BOARD: 0 issues across all sensors — fleet clean"
else
  SUMMARY="⚠️ ISSUE-BOARD: ${RED} RED · ${YELLOW} YELLOW — ${plane_n} unwired-plane · ${gtest_n} gate-red · ${git_n} git · ${stale_n} stale-claim · ${quar_n} quarantined · ${inert_n} inert — run 'fleet/issue-board.sh' to triage"
fi

# loud banner + the one SessionStart line (surfaced to manager/supervisor)
echo "════════════════════════════════════════════════════════════"
echo " SG ISSUE-BOARD (SURFACE leg, prototype) — $NOW"
echo " board: $BOARD"
echo "════════════════════════════════════════════════════════════"
column -t -s $'\t' "$BOARD" 2>/dev/null | head -60 || cat "$BOARD"
echo "────────────────────────────────────────────────────────────"
echo "$SUMMARY"

# non-zero if any RED (so a firing layer can gate on it)
[ "$RED" -eq 0 ]
