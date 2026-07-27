#!/usr/bin/env bash
# review-dispensation-canary.test.sh — plane-canary dogfood for the "review" plane
# (fleet/plane-canary-registry.tsv row: review / fleet/checks/reconcile-review-gate.sh /
# THIS file / owner REVIEW-DISPENSATION-CANARY).
#
# ================================ WHY THIS EXISTS ================================
# This is the #200 no-op-review class canary: PR #200 (fleet/board/REVIEWER-TAB-POOL.md
# BOUNCE-1) shipped a reviewer!=builder guard that was a STRUCTURAL NO-OP — it compared
# two DISJOINT identity namespaces (a shared GitHub bot login vs. a per-droid
# CHARON_DROID_ID) so the comparison could never match, and self-review sailed through.
# The bounce note is explicit: "Test MUST include reviewer==builder -> BLOCKED (real
# production identities, not fabricated matching values)". A fabricated pair like
# "model-same"/"model-same" (the placeholder RECONCILE-REVIEW-GATE's own test uses,
# see fleet/tests/reconcile-review-gate.test.sh section (f)) proves the comparison
# OPERATOR works in the abstract; it does NOT prove it fires against identity strings
# shaped like what the fleet actually writes. This dogfood closes that gap by seeding
# with model identifiers this fleet has actually recorded as real per-ticket builders
# (fleet/state/model-used/<TICKET> — gitignored ephemeral rig state, not available in
# a hermetic worktree at test time, so the literal values are pinned here with their
# provenance rather than read live):
#   BUILDER_MODEL           = deepseek-v4-flash   (fleet/state/model-used/REVIEWER-TAB-POOL
#                              — the exact model that authored PR #200, per
#                              fleet/board/REVIEWER-TAB-POOL.md BOUNCE-1)
#   DISTINCT_REVIEWER_MODEL = glm-5.2             (fleet/state/model-used/FAIL-LOUD-CONTRACT,
#                              MODEL-GRADE-PRESEED, DISCOVERY-SOURCE-ADAPTERS — a genuinely
#                              different model this fleet has actually used as a builder)
#
# FOLDS INTO RECONCILE-REVIEW-GATE (per fleet/board/REVIEW-DISPENSATION-CANARY.md's note:
# "FOLDS INTO ... do NOT fork a second review-gate checker"). This file does NOT
# reimplement or modify fleet/checks/reconcile-review-gate.sh — it drives the REAL,
# UNMODIFIED check via its documented env-override seams (same seams
# fleet/tests/reconcile-review-gate.test.sh uses) and adds the one class not yet
# exercised there: builder==reviewer proven with real production identity strings
# instead of tautological placeholders, plus two composite/#200-shape smokes:
# reviewed_sha != merged_sha, and an unreviewed hot-path merge.
#
# FULLY HERMETIC: every fixture lives under a mktemp -d tree (board/state/review-log/
# reviewed dirs), wired in via REVIEW_GATE_BOARD / REVIEW_GATE_STATE /
# REVIEW_GATE_REVIEW_LOG / REVIEW_GATE_REVIEWED / REVIEW_GATE_MERGE_SHA. No live
# board/PR/reviewed state is ever touched.
#
# Covers:
#   (a1) builder==reviewer, REAL production identities on the SAME reviewed/<id>
#        marker (the literal #200 shape)                          -> R-J BLOCK
#   (a2) FAIL-ON-REVERT / non-tautology proof: identical fixture, still labeled a
#        "self-review test", reviewer swapped to a DIFFERENT real identity -> GREEN.
#        Proves (a1)'s BLOCK tracked genuine identity-equality content, not a label.
#   (a3) GUARD-REVERTED proof: the exact (a1) fault run against a $TMP-only MUTATED
#        COPY of reconcile-review-gate.sh with the builder==reviewer comparison
#        neutralized (the real, committed script is never touched) -> the mutated
#        copy wrongly returns GREEN, proving the fault would be silently missed if
#        this comparison were ever reverted/dropped from the real check.
#   (b)  reviewed_sha != merged_sha -> R-K BLOCK (composite smoke — the exhaustive
#        R-K unit coverage is RECONCILE-REVIEW-GATE's own test; not duplicated here)
#   (c)  an unreviewed hot-path PR merged (no docs/review-log fragment AND no
#        reviewed/<id> marker at all) -> R-J BLOCK
#   Each fault fixture has a "correct flow" counterpart (distinct real reviewer,
#   matching sha, fragment present) -> GREEN.
#
# Run:  bash fleet/tests/review-dispensation-canary.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # .../fleet
GATE="$SRC/checks/reconcile-review-gate.sh"
[ -f "$GATE" ] || { echo "FAIL: cannot find $GATE (RECONCILE-REVIEW-GATE dep not landed?)" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

FIXTURE_SHA="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
STALE_SHA="1111111111111111111111111111111111111111"

# Real production model identities (see header provenance comment above) — NOT
# fabricated matching placeholders like "model-x"/"model-x".
BUILDER_MODEL="deepseek-v4-flash"
DISTINCT_REVIEWER_MODEL="glm-5.2"

run_gate() { # <gate-binary>
  # NOTE: cmd_check() (fleet/checks/reconcile-review-gate.sh:338-354) writes the
  # per-offender R-J/R-K/R-L lines to STDERR on BLOCK, and only the GREEN summary
  # to stdout. Merge both so assertions can grep the offender detail either way.
  REVIEW_GATE_BOARD="$BOARD" \
  REVIEW_GATE_STATE="$STATE" \
  REVIEW_GATE_REVIEW_LOG="$REVIEW_LOG" \
  REVIEW_GATE_REVIEWED="$REVIEWED" \
  REVIEW_GATE_MERGE_SHA="$FIXTURE_SHA" \
    bash "${1:-$GATE}" check 2>&1
}

fresh_fixture() {
  TMP="$(mktemp -d)"
  BOARD="$TMP/board"
  STATE="$TMP/state"
  REVIEW_LOG="$TMP/docs/review-log"
  REVIEWED="$STATE/reviewed"
  DONE="$STATE/done"
  mkdir -p "$BOARD" "$DONE" "$REVIEW_LOG" "$REVIEWED"
}

mk_ticket() { # <id> <tier> <owns> [work_class]
  local id="$1" tier="$2" owns="$3" wc="${4:-docs}"
  cat > "$BOARD/$id.md" <<EOF
tier: $tier
branch: feat/$id
owns: $owns
work_class: $wc
EOF
}

mk_done() { # <id> <sha>
  local id="$1" sha="$2"
  printf '%s\tmerged:%s\tbranch:feat/%s\n' "$(date -u +%FT%TZ)" "$sha" "$id" > "$DONE/$id"
}

mk_reviewed() { # <id> <sha> <author> <reviewer> <verdict> [findings]
  local id="$1" sha="$2" author="$3" reviewer="$4" verdict="$5" findings="${6:-0}"
  cat > "$REVIEWED/$id" <<EOF
reviewed_sha=$sha
author_model=$author
reviewer=$reviewer
verdict=$verdict
findings=$findings
EOF
}

mk_log() { # <id>
  local id="$1"
  cat > "$REVIEW_LOG/$id.md" <<EOF
# $id -- Review Log
Fixture ticket $id.
EOF
}

# ============================================================
# (a1) builder==reviewer, REAL production identities, SAME marker -> R-J BLOCK
#      (the literal #200 shape: fleet/board/REVIEWER-TAB-POOL.md BOUNCE-1 B1)
# ============================================================
echo "== (a1) builder==reviewer (real identities: $BUILDER_MODEL / $BUILDER_MODEL) -> R-J BLOCK =="
fresh_fixture
mk_ticket "SELF-REVIEW-TEST" "hot-path" "src/charon/canary_selfreview.py"
mk_done "SELF-REVIEW-TEST" "$FIXTURE_SHA"
mk_log "SELF-REVIEW-TEST"
mk_reviewed "SELF-REVIEW-TEST" "$FIXTURE_SHA" "$BUILDER_MODEL" "$BUILDER_MODEL" "CONFIRMED-CLEAN" 0
out="$(run_gate)"; rc=$?
[ "$rc" -ne 0 ] && ok "a1 self-review with REAL identities ($BUILDER_MODEL==$BUILDER_MODEL) -> BLOCK" \
                || bad "a1 self-review with REAL identities should be BLOCK (rc=$rc)
$out"
printf '%s' "$out" | grep -q "reviewer ($BUILDER_MODEL) is the same as author_model ($BUILDER_MODEL)" \
  && ok "a1 BLOCK line names the real self-review identity, not a placeholder" \
  || bad "a1 BLOCK line did not name the real identities
$out"
rm -rf "$TMP"

# ============================================================
# (a2) FAIL-ON-REVERT / non-tautology proof: SAME "self-review test" ticket,
#      SAME author, reviewer swapped to a DIFFERENT real identity -> GREEN.
#      If (a1)'s BLOCK were driven by a tautology (e.g. keying off the ticket
#      being LABELED a self-review test, rather than genuine field equality),
#      this would incorrectly still BLOCK. It does not: only the actual
#      identity-equality content decides the verdict.
# ============================================================
echo "== (a2) fail-on-revert: same 'self-review test' ticket, reviewer swapped to a DIFFERENT real identity ($DISTINCT_REVIEWER_MODEL) -> GREEN, proving (a1) isn't a tautology =="
fresh_fixture
mk_ticket "SELF-REVIEW-TEST" "hot-path" "src/charon/canary_selfreview.py"
mk_done "SELF-REVIEW-TEST" "$FIXTURE_SHA"
mk_log "SELF-REVIEW-TEST"
mk_reviewed "SELF-REVIEW-TEST" "$FIXTURE_SHA" "$BUILDER_MODEL" "$DISTINCT_REVIEWER_MODEL" "CONFIRMED-CLEAN" 0
out="$(run_gate)"; rc=$?
[ "$rc" -eq 0 ] && ok "a2 non-tautology proof: distinct real reviewer ($DISTINCT_REVIEWER_MODEL != $BUILDER_MODEL) on an identically-labeled ticket -> GREEN" \
                || bad "a2 non-tautology proof FAILED: distinct-reviewer ticket was still BLOCKED (rc=$rc) — assertion (a1) may be keyed off the label, not the identity content
$out"
rm -rf "$TMP"

# ============================================================
# (a3) GUARD-REVERTED proof: run the EXACT (a1) fault against a $TMP-only mutated
#      COPY of reconcile-review-gate.sh with the builder==reviewer comparison
#      neutralized. The real, committed script (fleet/checks/reconcile-review-gate.sh,
#      owned by RECONCILE-REVIEW-GATE) is never touched — only a throwaway copy is.
#      This proves: IF that comparison were ever silently reverted/dropped from the
#      real check, the #200 fault would sail through GREEN (missed) exactly as it
#      did in PR #200 — the concrete "revert the guard -> the fault is missed" proof.
# ============================================================
echo "== (a3) GUARD-REVERTED: neutralize the builder==reviewer comparison on a throwaway copy -> the SAME (a1) fault is silently missed (GREEN) =="
MUT_TMP="$(mktemp -d)"
MUT_GATE="$MUT_TMP/reconcile-review-gate-GUARD-REVERTED.sh"
sed 's/if \[ "\$R_REVIEWER" = "\$R_AUTHOR" \]; then/if false; then/' "$GATE" > "$MUT_GATE"
diff -q "$GATE" "$MUT_GATE" >/dev/null 2>&1 \
  && bad "a3 setup: mutated copy is byte-identical to the real gate — the sed neutralization did not take effect" \
  || ok "a3 setup: mutated copy differs from the real, committed reconcile-review-gate.sh (only a \$TMP copy was touched)"
grep -q '\$R_REVIEWER" = "\$R_AUTHOR"' "$GATE" \
  && ok "a3 setup: the real, committed script still has its self-review comparison intact (unmodified, as scoped)" \
  || bad "a3 setup: the real script's self-review comparison line is missing — unexpected drift"

fresh_fixture
mk_ticket "SELF-REVIEW-TEST" "hot-path" "src/charon/canary_selfreview.py"
mk_done "SELF-REVIEW-TEST" "$FIXTURE_SHA"
mk_log "SELF-REVIEW-TEST"
mk_reviewed "SELF-REVIEW-TEST" "$FIXTURE_SHA" "$BUILDER_MODEL" "$BUILDER_MODEL" "CONFIRMED-CLEAN" 0
out="$(run_gate "$MUT_GATE")"; rc=$?
[ "$rc" -eq 0 ] && ok "a3 GUARD-REVERTED: the identical #200-shape self-review fixture is MISSED (GREEN) once the comparison is neutralized — proving the real check's comparison is load-bearing, not decorative" \
                || bad "a3 GUARD-REVERTED: mutated copy unexpectedly still BLOCKED (rc=$rc) — the neutralization did not disable the guard as intended
$out"
rm -rf "$TMP" "$MUT_TMP"

# ============================================================
# (b) reviewed_sha != merged_sha -> R-K BLOCK (composite smoke; the exhaustive R-K
#     unit coverage lives in RECONCILE-REVIEW-GATE's own fleet/tests/
#     reconcile-review-gate.test.sh section (b) — this re-asserts the SAME real,
#     unmodified check catches it, not a duplicate unit)
# ============================================================
echo "== (b) reviewed_sha != merged_sha -> R-K BLOCK (composite smoke) =="
fresh_fixture
mk_ticket "STALE-SHA-TEST" "hot-path" "src/charon/canary_stalesha.py"
mk_done "STALE-SHA-TEST" "$FIXTURE_SHA"
mk_log "STALE-SHA-TEST"
mk_reviewed "STALE-SHA-TEST" "$STALE_SHA" "$BUILDER_MODEL" "$DISTINCT_REVIEWER_MODEL" "CONFIRMED-CLEAN" 0
out="$(run_gate)"; rc=$?
[ "$rc" -ne 0 ] && ok "b reviewed_sha ($STALE_SHA) != merged_sha ($FIXTURE_SHA) -> BLOCK" \
                || bad "b stale reviewed_sha should be BLOCK (rc=$rc)
$out"
printf '%s' "$out" | grep -q "R-K" \
  && ok "b BLOCK line is classified R-K (stale review)" \
  || bad "b BLOCK line did not cite R-K
$out"
# correct-flow counterpart: matching sha -> GREEN
mk_reviewed "STALE-SHA-TEST" "$FIXTURE_SHA" "$BUILDER_MODEL" "$DISTINCT_REVIEWER_MODEL" "CONFIRMED-CLEAN" 0
out="$(run_gate)"; rc=$?
[ "$rc" -eq 0 ] && ok "b correct flow: matching reviewed_sha -> GREEN" \
                || bad "b correct flow: matching reviewed_sha should be GREEN (rc=$rc)
$out"
rm -rf "$TMP"

# ============================================================
# (c) unreviewed hot-path PR merged: no docs/review-log fragment AND no
#     reviewed/<id> marker at all -> R-J BLOCK
# ============================================================
echo "== (c) unreviewed hot-path merge (no review-log fragment, no reviewed marker) -> R-J BLOCK =="
fresh_fixture
mk_ticket "UNREVIEWED-HOTPATH-TEST" "hot-path" "src/charon/canary_unreviewed.py"
mk_done "UNREVIEWED-HOTPATH-TEST" "$FIXTURE_SHA"
# deliberately: no mk_log, no mk_reviewed — this IS the fault
out="$(run_gate)"; rc=$?
[ "$rc" -ne 0 ] && ok "c hot-path merge with NO review evidence at all -> BLOCK" \
                || bad "c unreviewed hot-path merge should be BLOCK (rc=$rc)
$out"
printf '%s' "$out" | grep -q "R-J" \
  && ok "c BLOCK line is classified R-J (no review-log fragment / no marker)" \
  || bad "c BLOCK line did not cite R-J
$out"
# correct-flow counterpart: fragment + distinct-reviewer marker, matching sha -> GREEN
mk_log "UNREVIEWED-HOTPATH-TEST"
mk_reviewed "UNREVIEWED-HOTPATH-TEST" "$FIXTURE_SHA" "$BUILDER_MODEL" "$DISTINCT_REVIEWER_MODEL" "CONFIRMED-CLEAN" 0
out="$(run_gate)"; rc=$?
[ "$rc" -eq 0 ] && ok "c correct flow: fragment + distinct-reviewer marker + matching sha -> GREEN" \
                || bad "c correct flow should be GREEN (rc=$rc)
$out"
rm -rf "$TMP"

# ============================================================
# Composite baseline: all three fault classes correctly resolved on ONE board
# at once -> GREEN (the "correct review flow -> GREEN" top-level requirement)
# ============================================================
echo "== composite baseline: all three classes correctly resolved together -> GREEN =="
fresh_fixture
mk_ticket "SELF-REVIEW-TEST" "hot-path" "src/charon/canary_selfreview.py"
mk_done "SELF-REVIEW-TEST" "$FIXTURE_SHA"
mk_log "SELF-REVIEW-TEST"
mk_reviewed "SELF-REVIEW-TEST" "$FIXTURE_SHA" "$BUILDER_MODEL" "$DISTINCT_REVIEWER_MODEL" "CONFIRMED-CLEAN" 0
mk_ticket "STALE-SHA-TEST" "hot-path" "src/charon/canary_stalesha.py"
mk_done "STALE-SHA-TEST" "$FIXTURE_SHA"
mk_log "STALE-SHA-TEST"
mk_reviewed "STALE-SHA-TEST" "$FIXTURE_SHA" "$BUILDER_MODEL" "$DISTINCT_REVIEWER_MODEL" "CONFIRMED-CLEAN" 0
mk_ticket "UNREVIEWED-HOTPATH-TEST" "hot-path" "src/charon/canary_unreviewed.py"
mk_done "UNREVIEWED-HOTPATH-TEST" "$FIXTURE_SHA"
mk_log "UNREVIEWED-HOTPATH-TEST"
mk_reviewed "UNREVIEWED-HOTPATH-TEST" "$FIXTURE_SHA" "$BUILDER_MODEL" "$DISTINCT_REVIEWER_MODEL" "CONFIRMED-CLEAN" 0
out="$(run_gate)"; rc=$?
[ "$rc" -eq 0 ] && ok "composite: correct review flow across all three classes -> GREEN" \
                || bad "composite: correct review flow should be GREEN (rc=$rc)
$out"
rm -rf "$TMP"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL REVIEW-DISPENSATION-CANARY TESTS PASS"
