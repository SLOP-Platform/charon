#!/usr/bin/env bash
# assign-dispatch.test.sh — FAIL-ON-REVERT tests for S4 (Gap A rig facet): the tier dispatcher
# (fleet-droid.sh) must PREFER capability/assign.py's real-outcome ranking (model-scorecard.tsv's
# source=live lane) over the static fleet/tier-models.tsv chain when live data exists for the
# ticket's work_class, and fall straight back to the UNCHANGED static chain when it doesn't.
#
# Drives the REAL fleet-droid.sh via its `resolve <tier> <ticketfile>` dev/test hook (the same
# hook the DETENTION-REDLINE suite uses) — production path == test path, no copy/mock of the
# dispatcher. Isolated via env overrides fleet-droid.sh already supports:
#   CHARON_TIER_MODELS   -> a throwaway tier-models.tsv (never touches the operator-gated real one)
#   CHARON_SCORECARD_TSV -> a throwaway scorecard fixture (never touches the live, grader-owned
#                           fleet/model-scorecard.tsv; this is the SAME env var model-detention.sh
#                           already honors, so detention filtering sees the identical fixture).
#
# Reverting the S4 wiring (removing the assign_reorder_chain call from either the `resolve` hook
# or the main claim loop, or its --candidates/--print-model seam in assign.py) makes test (a) FAIL
# — the static order (modelA,modelB,modelC) would come back unchanged even with live data present
# that should have promoted modelB.
#
# Run:  bash fleet/tests/assign-dispatch.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

# HERMETIC: the resolve hook now runs a gateway CAPPED-filter (CRIPPLE #2). Pin it to an empty
# /charon/status snapshot (nothing capped) so these ranking tests never touch the live gateway.
printf '{"pools":{},"balance":{},"cooldown_seconds":{}}\n' > "$D/status-clean.json"
export CHARON_GATEWAY_STATUS_FILE="$D/status-clean.json"

printf 'strong\tmodelA,modelB,modelC\n' > "$D/tier-models.tsv"
printf 'tier: strong\nwork_class: routing\n' > "$D/ticket.md"

# Real-outcome (source=live) fixture: modelA has a genuine (non-fabricated: gate=fail, not
# gate=pass) BLOCK, modelB has two clean MERGEs, modelC has one clean MERGE. assign.py's
# confidence-aware ranking must pick modelB (best real evidence) over the static cheapest-first
# order (modelA first).
printf '%s\n' \
  '2026-07-01	live	R1	routing	1	modelA	BLOCK	fail	-	10	-	0	n1' \
  '2026-07-01	live	R2	routing	1	modelB	MERGE	pass	-	10	-	0	n2' \
  '2026-07-02	live	R3	routing	1	modelB	MERGE	pass	-	10	-	0	n3' \
  '2026-07-01	live	R4	routing	1	modelC	MERGE	pass	-	10	-	0	n4' \
  > "$D/scorecard-live.tsv"

# CONTROL PANEL (RIG-REDS 2026-07-24). EVAL-PROMOTION-GATE's F13 fix later added a
# per-ref control-panel ADMISSION gate to grades.py `_rows_for()`: a source=live row
# only counts toward a grade once its ref has a MUST-PASS control (strong-control,
# N>=3, mean >= 80) AND a MUST-FAIL control (deepseek-v4-flash, N>=3, mean <= 20).
# This fixture predates that gate and carried NO control rows, so after F13 landed
# EVERY row above was excluded, assign.py REFUSED, and (a)/(d)/(e) went red for a
# reason that has nothing to do with the S4 dispatch wiring under test — a stale
# fixture, not a dispatch regression. Controls are added here so the fixture is
# ADMISSIBLE again; the ranking assertions below are unchanged, so a revert of the
# S4 wiring still flips this test red (fail-on-revert preserved).
for _ref in R1 R2 R3 R4; do
  for _n in 1 2 3; do
    printf '2026-07-01\tlive\t%s\trouting\t1\tstrong-control\tMERGE\tpass\t100\t10\t-\t0\tctl-pass-%s\n' "$_ref" "$_n"
    printf '2026-07-01\tlive\t%s\trouting\t1\tdeepseek-v4-flash\tBLOCK\tfail\t0\t10\t-\t0\tctl-fail-%s\n' "$_ref" "$_n"
  done
done >> "$D/scorecard-live.tsv"

echo "== (a) live data present -> assign.py's pick (modelB) is promoted to the front =="
out="$(CHARON_TIER_MODELS="$D/tier-models.tsv" CHARON_SCORECARD_TSV="$D/scorecard-live.tsv" \
       bash "$SRC/fleet-droid.sh" resolve strong "$D/ticket.md" 2>/dev/null)"
check "a1 real-outcome pick (modelB) leads the resolved chain" "$out" "modelB,modelA,modelC"

echo "== (b) no live data for this work_class -> falls back to the UNCHANGED static chain =="
: > "$D/scorecard-empty.tsv"
out="$(CHARON_TIER_MODELS="$D/tier-models.tsv" CHARON_SCORECARD_TSV="$D/scorecard-empty.tsv" \
       bash "$SRC/fleet-droid.sh" resolve strong "$D/ticket.md" 2>/dev/null)"
check "b1 static chain order preserved with no real-outcome data" "$out" "modelA,modelB,modelC"

echo "== (c) live scorecard has ZERO rows for any of this tier's candidate models -> falls back =="
# A different tier whose static-chain models never appear in the live fixture at all (not even
# via assign.py's generalist cross-class fallback, which grade()s per-MODEL) — so assign.py has
# no evidence for any candidate and must refuse; the dispatcher falls back to the static order.
printf 'strong\tmodelA,modelB,modelC\nfrontier\tmodelX,modelY,modelZ\n' > "$D/tier-models.tsv"
printf 'tier: frontier\nwork_class: routing\n' > "$D/ticket-frontier.md"
out="$(CHARON_TIER_MODELS="$D/tier-models.tsv" CHARON_SCORECARD_TSV="$D/scorecard-live.tsv" \
       bash "$SRC/fleet-droid.sh" resolve frontier "$D/ticket-frontier.md" 2>/dev/null)"
check "c1 static chain order preserved when NO candidate has any live evidence" "$out" "modelX,modelY,modelZ"

echo "== (d) assign.py --print-model machine-readable contract (unit-level seam check) =="
picked="$(python3 "$SRC/capability/assign.py" --work-class routing --tsv "$D/scorecard-live.tsv" \
            --candidates modelA,modelB,modelC --print-model 2>/dev/null)"
check "d1 --print-model prints ONLY the picked model id" "$picked" "modelB"
rc=0
python3 "$SRC/capability/assign.py" --work-class routing --tsv "$D/scorecard-empty.tsv" \
  --candidates modelA,modelB,modelC --print-model >/dev/null 2>&1 || rc=$?
check "d2 --print-model exits 1 (no output) when refused/no data" "$rc" "1"

echo "== (e) --candidates never lets assign.py recommend an UNLISTED model id =="
# modelB has the best real evidence in the fixture overall, but here it is deliberately left OUT
# of --candidates; assign.py must never hand back a model outside the offered set.
picked="$(python3 "$SRC/capability/assign.py" --work-class routing --tsv "$D/scorecard-live.tsv" \
            --candidates modelA,modelC --print-model 2>/dev/null)"
case ",modelA,modelC," in
  *",$picked,"*) ok "e1 pick stays within the offered --candidates set (got '$picked')" ;;
  *) bad "e1 pick stays within the offered --candidates set (got '$picked', outside modelA,modelC)" ;;
esac

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL ASSIGN-DISPATCH TESTS PASS"
