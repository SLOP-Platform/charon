#!/usr/bin/env bash
# reconcile-review-gate.test.sh — FAIL-ON-REVERT tests for the review-gate axis
# (§2.1) + fail-closed taxonomy (§2.2) from UNIFIED-RECONCILIATION-GATE-DESIGN.md.
#
# Covers:
#   (a) a ≥hot-path change with no marker → R-J RED, then add matching-sha marker → GREEN
#   (b) a marker with stale sha → R-K RED
#   (c) an UNKNOWN src/charon/*.py path → classified hot-path (fail-closed) → review required
#   (d) an economy ticket with no marker → GREEN (no review needed below hot-path)
#   (e) R-L doom loop: verdict=FIXES without follow-up → RED
#   (f) reviewer == author_model (self-review) → RED
#   (g) operator-reviewed (reviewer=operator) regardless of author → GREEN
#   (h) unknown work_class → fail-closed to hot-path → review required
#   (i) docs/ path with standard tier → no review required (below hot-path threshold)
#   (j) fail-on-revert proof: removing the fail-closed taxonomy line makes (c) go GREEN
#
# Each test section builds ISOLATED fixtures so previous RED tickets never
# interfere with subsequent GREEN assertions.
#
# Run:  bash fleet/tests/reconcile-review-gate.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATE="$SRC/checks/reconcile-review-gate.sh"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }

FIXTURE_SHA="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
STALE_SHA="1111111111111111111111111111111111111111"

run_gate() {
  REVIEW_GATE_BOARD="$BOARD" \
  REVIEW_GATE_STATE="$STATE" \
  REVIEW_GATE_REVIEW_LOG="$REVIEW_LOG" \
  REVIEW_GATE_REVIEWED="$REVIEWED" \
  REVIEW_GATE_MERGE_SHA="$FIXTURE_SHA" \
    bash "$GATE" check 2>/dev/null
}

# Create a fresh fixture and set up globals BOARD, STATE, REVIEW_LOG, REVIEWED, DONE
fresh_fixture() {
  TMP="$(mktemp -d)"
  BOARD="$TMP/board"
  STATE="$TMP/state"
  REVIEW_LOG="$TMP/docs/review-log"
  REVIEWED="$STATE/reviewed"
  DONE="$STATE/done"
  mkdir -p "$BOARD" "$DONE" "$REVIEW_LOG" "$REVIEWED"
}

# Helper: create a board ticket
mk_ticket() {
  local id="$1"
  local tier="$2"
  local owns="$3"
  local wc="${4:-docs}"
  cat > "$BOARD/$id.md" <<EOF
tier: $tier
branch: feat/$id
owns: $owns
work_class: $wc
EOF
}

# Helper: create a done marker
mk_done() {
  local id="$1" sha="$2"
  printf '%s\tmerged:%s\tbranch:feat/%s\n' "$(date -u +%FT%TZ)" "$sha" "$id" > "$DONE/$id"
}

# Helper: create a reviewed marker
mk_reviewed() {
  local id="$1" sha="$2" author="$3" reviewer="$4" verdict="$5" findings="${6:-0}"
  cat > "$REVIEWED/$id" <<EOF
reviewed_sha=$sha
author_model=$author
reviewer=$reviewer
verdict=$verdict
findings=$findings
EOF
}

# Helper: create a review-log fragment
mk_log() {
  local id="$1"
  cat > "$REVIEW_LOG/$id.md" <<EOF
# $id -- Review Log
Fixture ticket $id.
EOF
}

# ============================================================
# (a) ≥hot-path change with NO marker → R-J RED, then add → GREEN
# ============================================================
echo "== (a) ≥hot-path with no marker → R-J RED, add marker → GREEN =="
fresh_fixture
mk_ticket "TICK-A" "hot-path" "src/charon/a.py"
mk_done "TICK-A" "$FIXTURE_SHA"
run_gate && bad "a R-J: hot-path ticket with no review evidence should be RED" \
         || ok "a R-J: hot-path ticket with no review evidence → RED"
mk_log "TICK-A"
mk_reviewed "TICK-A" "$FIXTURE_SHA" "model-m" "operator" "CONFIRMED-CLEAN" 0
run_gate && ok "a GREEN: hot-path ticket with matching-sha marker → GREEN" \
         || bad "a GREEN: hot-path ticket with matching-sha marker should be GREEN"
rm -rf "$TMP"

# ============================================================
# (b) marker with STALE sha → R-K RED
# ============================================================
echo "== (b) stale reviewed sha → R-K RED =="
fresh_fixture
mk_ticket "TICK-B" "hot-path" "src/charon/b.py"
mk_done "TICK-B" "$FIXTURE_SHA"
mk_log "TICK-B"
mk_reviewed "TICK-B" "$STALE_SHA" "model-x" "operator" "CONFIRMED-CLEAN" 0
run_gate && bad "b R-K: stale reviewed_sha should be RED" \
         || ok "b R-K: stale reviewed_sha → RED"
rm -rf "$TMP"

# ============================================================
# (c) UNKNOWN src/charon/*.py path → classified hot-path (fail-closed)
# ============================================================
echo "== (c) unknown src/charon/*.py path → fail-closed hot-path → review required =="
fresh_fixture
mk_ticket "TICK-C" "economy" "src/charon/unknown_module.py"
mk_done "TICK-C" "$FIXTURE_SHA"
run_gate && bad "c fail-closed: unknown src/charon path with economy tier → should be RED" \
         || ok "c fail-closed: unknown src/charon path → RED (R-J)"
mk_log "TICK-C"
mk_reviewed "TICK-C" "$FIXTURE_SHA" "model-y" "operator" "CONFIRMED-CLEAN" 0
run_gate && ok "c GREEN: fail-closed path with matching-sha marker → GREEN" \
         || bad "c GREEN: fail-closed path with matching-sha marker should be GREEN"
rm -rf "$TMP"

# ============================================================
# (d) economy ticket with NO marker → GREEN (below hot-path threshold)
# ============================================================
echo "== (d) economy ticket with no marker → GREEN (below hot-path) =="
fresh_fixture
mk_ticket "TICK-D" "economy" "docs/readme.md"
mk_done "TICK-D" "$FIXTURE_SHA"
run_gate && ok "d GREEN: economy docs change with no marker → GREEN" \
         || bad "d GREEN: economy docs change with no marker should be GREEN"
rm -rf "$TMP"

# ============================================================
# (e) R-L doom loop: verdict=FIXES without follow-up → RED
# ============================================================
echo "== (e) verdict=FIXES at merge sha without CONFIRMED-CLEAN → R-L RED =="
fresh_fixture
mk_ticket "TICK-E" "hot-path" "src/charon/e.py"
mk_done "TICK-E" "$FIXTURE_SHA"
mk_log "TICK-E"
mk_reviewed "TICK-E" "$FIXTURE_SHA" "model-z" "model-w" "FIXES" 3
run_gate && bad "e R-L: verdict=FIXES with no follow-up should be RED" \
         || ok "e R-L: verdict=FIXES with no follow-up → RED"
mk_reviewed "TICK-E" "$FIXTURE_SHA" "model-z" "model-w" "CONFIRMED-CLEAN" 0
run_gate && ok "e GREEN: CONFIRMED-CLEAN at merge sha → GREEN" \
         || bad "e GREEN: CONFIRMED-CLEAN at merge sha should be GREEN"
rm -rf "$TMP"

# ============================================================
# (f) self-review: reviewer == author_model → RED (unless operator)
# ============================================================
echo "== (f) self-review (reviewer == author) → RED =="
fresh_fixture
mk_ticket "TICK-F" "hot-path" "src/charon/f.py"
mk_done "TICK-F" "$FIXTURE_SHA"
mk_log "TICK-F"
mk_reviewed "TICK-F" "$FIXTURE_SHA" "model-same" "model-same" "CONFIRMED-CLEAN" 0
run_gate && bad "f self-review: same author and reviewer should be RED" \
         || ok "f self-review: same author and reviewer → RED"
rm -rf "$TMP"

# ============================================================
# (g) operator-reviewed always GREEN regardless of author_model
# ============================================================
echo "== (g) operator-reviewed → GREEN regardless of author =="
fresh_fixture
mk_ticket "TICK-G" "hot-path" "src/charon/g.py"
mk_done "TICK-G" "$FIXTURE_SHA"
mk_log "TICK-G"
mk_reviewed "TICK-G" "$FIXTURE_SHA" "model-any" "operator" "CONFIRMED-CLEAN" 0
run_gate && ok "g GREEN: operator-reviewed → GREEN" \
         || bad "g GREEN: operator-reviewed should be GREEN"
rm -rf "$TMP"

# ============================================================
# (h) unknown work_class → fail-closed to hot-path → review required
# ============================================================
echo "== (h) unknown work_class → fail-closed hot-path =="
fresh_fixture
mk_ticket "TICK-H" "economy" "docs/h.txt" "not-a-real-work-class"
mk_done "TICK-H" "$FIXTURE_SHA"
run_gate && bad "h fail-closed: unknown work_class should enforce review → RED" \
         || ok "h fail-closed: unknown work_class → RED (R-J)"
mk_log "TICK-H"
mk_reviewed "TICK-H" "$FIXTURE_SHA" "model-h" "operator" "CONFIRMED-CLEAN" 0
run_gate && ok "h GREEN: fail-closed work_class with matching-sha marker → GREEN" \
         || bad "h GREEN: fail-closed work_class with matching-sha marker should be GREEN"
rm -rf "$TMP"

# ============================================================
# (i) docs/ path with standard tier → no review (below hot-path threshold)
# ============================================================
echo "== (i) standard docs change → GREEN (no review) =="
fresh_fixture
mk_ticket "TICK-I" "standard" "docs/changelog.md"
mk_done "TICK-I" "$FIXTURE_SHA"
run_gate && ok "i GREEN: standard docs change with no marker → GREEN (below hot-path)" \
         || bad "i GREEN: standard docs change with no marker should be GREEN"
rm -rf "$TMP"

# ============================================================
# (j) FAIL-ON-REVERT proof: removing fail-closed taxonomy makes (c) go GREEN
# ============================================================
echo "== (j) FAIL-ON-REVERT: removing fail-closed src/charon rule makes this pass silently =="
echo "  classify_ticket() maps src/charon/* → hot-path (tier 3) by default."
echo "  TICK-J has tier=economy + owns=src/charon/unknown.py. With fail-closed: hot-path"
echo "  → RED (R-J). Without fail-closed: economy (tier 1) → GREEN (no review needed)."
echo "  Reverting that default makes this test GREEN → proving absence ≠ pass."
fresh_fixture
mk_ticket "TICK-J" "economy" "src/charon/secret_new_feature.py"
mk_done "TICK-J" "$FIXTURE_SHA"
run_gate && bad "j fail-on-revert: unknown src/charon with economy tier should be RED" \
         || ok "j fail-on-revert: unknown src/charon path → RED (fail-closed working)"
mk_log "TICK-J"
mk_reviewed "TICK-J" "$FIXTURE_SHA" "model-j" "operator" "CONFIRMED-CLEAN" 0
run_gate && ok "j GREEN: fail-closed path with matching-sha marker → GREEN" \
         || bad "j GREEN: fail-closed path with matching-sha marker should be GREEN"
rm -rf "$TMP"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL RECONCILE-REVIEW-GATE TESTS PASS"
