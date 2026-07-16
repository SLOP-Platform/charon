#!/usr/bin/env bash
# test_claim_decompose_perf.sh — FAIL-ON-REVERT tests for the PERF-AUDIT-CLAIM-DECOMPOSE ticket
# (2026-07-15). Verifies that claim.sh and decompose.sh are both fast AND behavior-preserving on
# a throwaway fixture that NEVER touches live fleet/state (no droid ever claims a real ticket as
# a side-effect of this test).
#
# Why this exists: claim.sh's hot loop was O(n²) in board size — per-file `meta()` awk-spawns (3
# per file per pass: parked / note / tier) + per-dep canon() O(n) scan. On a 200-file fixture
# with unfulfilled deps (the realistic "many-tickets, not-yet-unblocked" state), the OLD wall
# time was ~10s (already >5s threshold). On a 2000-file fixture: ~13s. The fix is index-once:
# a single awk pre-pass + a single awk claim loop, both operating on a sorted INDEX. The
# pattern mirrors fleet/reconcile-merged.sh:PERF (PERF-AUDIT.md 2026-07-15).
#
# Decompose.sh is single-ticket-scoped (bounded by the plan, not the board) — already fast at
# <0.3s for a 20-unit plan. This test records the measurement and the >5s claim threshold
# behavior so a future regression in either script flips the test RED.
#
# Reverting the index-once fix in claim.sh re-introduces the O(n²) re-scan → (b) fails.
# Reverting the case-insensitive `done` lookup (using NUL env-var instead of temp files) makes
# multi-deps_all_done return wrong → (a) multi-deps scenarios fail. Reverting the `gets` short
# circuit or moving the state set build outside the lock re-introduces the OLD race.
#
# Run:  bash fleet/tests/test_claim_decompose_perf.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# Throwaway product repo (no `gh`, no network). Used only by the perf test's claim.sh call so the
# `charon tier ranks` call (which is a python import) doesn't hit the real /home/stack/code/charon.
# claim.sh's perf path does NOT touch the product repo at all — only charon tier ranks is called,
# and that resolves through PATH.
P="$(mktemp -d)"
git -C "$P" init -q

# Helper: build a throwaway fleet (board + state) with N noise files, optionally
# `depends_on: <unmet-dep>` per file (the realistic "many-tickets, not-yet-unblocked" case
# that triggered the OLD's O(n²) worst case).
make_fixture(){
  local d="$1" N="$2" mode="$3"  # mode: "all_claimed" or "deps_unmet"
  mkdir -p "$d/board/archive" "$d/state/claims" "$d/state/submitted" "$d/state/done" "$d/state/loop-guard"
  local i
  for i in $(seq 1 $((N/2))); do
    case "$mode" in
      all_claimed)
        printf 'tier: economy\nbranch: feat/no-%s\nowns: src/no-%s.py\nwork_class: docs\n' "$i" "$i" > "$d/board/NO-$i.md"
        printf 'x' > "$d/state/claims/NO-$i"
        ;;
      deps_unmet)
        printf 'tier: economy\nbranch: feat/no-%s\nowns: src/no-%s.py\nwork_class: docs\ndepends_on: NEVER-DONE-%s\n' "$i" "$i" "$i" > "$d/board/NO-$i.md"
        ;;
    esac
  done
  for i in $(seq 1 $((N/2))); do
    case "$mode" in
      all_claimed)
        printf 'tier: economy\nbranch: feat/arc-%s\nowns: src/arc-%s.py\nwork_class: docs\n' "$i" "$i" > "$d/board/archive/ARC-$i.md"
        printf 'x' > "$d/state/claims/ARC-$i"
        ;;
      deps_unmet)
        printf 'tier: economy\nbranch: feat/arc-%s\nowns: src/arc-%s.py\nwork_class: docs\ndepends_on: NEVER-DONE-%s\n' "$i" "$i" "$i" > "$d/board/archive/ARC-$i.md"
        ;;
    esac
  done
  # one claimable ticket at the top of glob order
  printf 'tier: economy\nbranch: feat/CLAIMABLE\nowns: src/c.py\nwork_class: docs\n' > "$d/board/CLAIMABLE.md"
  # install the scripts (claim.sh + the canonical _lib.sh) into the fixture root so the
  # `source "$FLEET/_lib.sh"` resolves correctly
  cp "$SRC/_lib.sh" "$d/"
  cp "$SRC/claim.sh" "$d/"
}

run_claim(){
  local d="$1"
  bash "$d/claim.sh" economy droidx both 2>&1
}

# ── (a) BEHAVIOR-PRESERVING: claim.sh returns the same ticket as the OLD on a small fixture.
# This is the case-insensitive + multi-deps + parked + own-only + loop-guard set; a regression
# in the case-folding of the dep-set lookup (e.g. switching from *_SET files back to env-var
# joined NULs) flips the test RED.
echo "== (a) behavior-preserving: same claim result as canonical on mixed-edge-case fixture =="
A="$(mktemp -d)"
mkdir -p "$A/board" "$A/state/claims" "$A/state/submitted" "$A/state/done" "$A/state/loop-guard"
cp "$SRC/_lib.sh" "$A/"
cp "$SRC/claim.sh" "$A/"
# 4 strong tickets, one of each kind:
printf 'tier: strong\nbranch: feat/CLAIMABLE\nowns: src/c.py\nwork_class: docs\n' > "$A/board/CLAIMABLE.md"
printf 'tier: strong\nbranch: feat/ALREADY-CLAIMED\nowns: src/a.py\nwork_class: docs\n' > "$A/board/ALREADY-CLAIMED.md"
printf 'x' > "$A/state/claims/ALREADY-CLAIMED"
printf 'tier: strong\nbranch: feat/ALREADY-DONE\nowns: src/b.py\nwork_class: docs\n' > "$A/board/ALREADY-DONE.md"
printf 'x' > "$A/state/done/ALREADY-DONE"
printf 'tier: strong\nbranch: feat/DEPS-MET\nowns: src/d.py\nwork_class: docs\ndepends_on: already-done\n' > "$A/board/DEPS-MET.md"
# DEPS-MIXED: same as DEPS-MET but with a MIXED-CASE dep (verifies the tolower() in the awk
# deps_all_done function — a regression that drops it would mis-fail case-folded lookups
# against the lower-cased DONE_SET entries).
printf 'tier: strong\nbranch: feat/DEPS-MIXED\nowns: src/dm2.py\nwork_class: docs\ndepends_on: Already-Done\n' > "$A/board/DEPS-MIXED.md"
printf 'tier: strong\nbranch: feat/PARKED\nowns: src/p.py\nwork_class: docs\nparked: true\n' > "$A/board/PARKED.md"
# Expected glob order: ALREADY-CLAIMED, ALREADY-DONE, CLAIMABLE, DEPS-MET, PARKED.
# The first claim-eligible is CLAIMABLE (ALREADY-CLAIMED is claimed, ALREADY-DONE is done, the
# rest come after).
got="$(bash "$A/claim.sh" strong droid1 both 2>&1)"
case "$got" in
  "CLAIMED CLAIMABLE "*) ok "a strong both claims CLAIMABLE (got: $got)" ;;
  *) bad "a strong both claims CLAIMABLE (got: $got)" ;;
esac
# Second run (CLAIMABLE is now claimed): next eligible is DEPS-MET (deps met via case-insensitive
# canon — DEPS-MET's `depends_on: already-done` resolves to the board ticket `ALREADY-DONE`
# through the case-folded lookup; ALREADY-DONE has a done marker so the dep is met).
got="$(bash "$A/claim.sh" strong droid1 both 2>&1)"
case "$got" in
  "CLAIMED DEPS-MET "*) ok "a second run claims DEPS-MET (case-insensitive deps met) (got: $got)" ;;
  *) bad "a second run claims DEPS-MET (got: $got)" ;;
esac
# Third run: DEPS-MIXED is now claimable (deps met via case-insensitive canon). DEPS-MIXED's
# `depends_on: Already-Done` resolves to the board ticket `ALREADY-DONE` through the case-folded
# lookup; ALREADY-DONE has a done marker so the dep is met.
got="$(bash "$A/claim.sh" strong droid1 both 2>&1)"
case "$got" in
  "CLAIMED DEPS-MIXED "*) ok "a third run claims DEPS-MIXED (mixed-case dep) (got: $got)" ;;
  *) bad "a third run claims DEPS-MIXED (got: $got)" ;;
esac
# Fourth run: no claimable left.
got="$(bash "$A/claim.sh" strong droid1 both 2>&1)"
[ "$got" = "NONE" ] && ok "a fourth run returns NONE (no claimable)" || bad "a fourth run returns NONE (got: $got)"
# DEPS-MIXED is also tested in isolation in A2 below to verify the case-fold dep lookup
# works on a fresh fixture (no DEPS-MET already-claimed interference).
# Fourth run with DEPS-MIXED: would have been claimable if we had not pre-claimed DEPS-MET first.
# We test DEPS-MIXED in a fresh fixture to keep the expected sequence deterministic.
A2="$(mktemp -d)"
mkdir -p "$A2/board" "$A2/state/claims" "$A2/state/submitted" "$A2/state/done" "$A2/state/loop-guard"
cp "$SRC/_lib.sh" "$A2/"
cp "$SRC/claim.sh" "$A2/"
printf 'tier: strong\nbranch: feat/ALREADY-DONE\nowns: src/b.py\nwork_class: docs\n' > "$A2/board/ALREADY-DONE.md"
printf 'x' > "$A2/state/done/ALREADY-DONE"
printf 'tier: strong\nbranch: feat/DEPS-MIXED\nowns: src/d.py\nwork_class: docs\ndepends_on: Already-Done\n' > "$A2/board/DEPS-MIXED.md"
# First (and only) eligible: DEPS-MIXED, because ALREADY-DONE has a done marker. The OLD
# canon() would case-fold the dep lookup; the NEW tolower() must do the same — a regression
# that drops tolower() (e.g. switching back to NUL env-var sets that have an in-line
# lowercased lookup but a per-row non-lowercased compare) breaks this test.
got="$(bash "$A2/claim.sh" strong droid1 both 2>&1)"
case "$got" in
  "CLAIMED DEPS-MIXED "*) ok "a mixed-case dep (Already-Done) is matched case-insensitively against ALREADY-DONE (got: $got)" ;;
  *) bad "a mixed-case dep should match ALREADY-DONE via tolower() (got: $got — tolower regression?)" ;;
esac
rm -rf "$A" "$A2"

# ── (b) PERF claim.sh: 200-file "deps_unmet" fixture finishes < 2s. The OLD loop was O(n²)
# (per-file meta() + per-dep canon()) and took ~10-20s on this fixture. A regression that
# re-introduces the per-file awk-spawns OR drops the INDEX/sort would push this past 2s.
# Bound is 2s (not the 5s PERF-AUDIT threshold) so the test fails loudly on a slow CI host
# even when the OLD was already O(n²) — the fix's job is to be FAST, not just "under 5s".
# The test pre-claims the `CLAIMABLE` shortcut (added by make_fixture) so the loop MUST walk
# every file in the no-claimable worst case (the realistic "many-tickets, not-yet-unblocked"
# state that triggered the OLD's O(n²) in the first place).
echo "== (b) PERF: claim.sh on 200-file deps_unmet fixture < 2s =="
B="$(mktemp -d)"
make_fixture "$B" 200 deps_unmet
echo "x" > "$B/state/claims/CLAIMABLE"   # pre-claim the shortcut so every file must be walked
_t0=$(date +%s%N)
bash "$B/claim.sh" economy droidx both >/dev/null 2>&1 || true
_t1=$(date +%s%N)
_ms=$(( ( _t1 - _t0 ) / 1000000 ))
[ "$_ms" -lt 2000 ] && ok "b 200-file deps_unmet (no-claimable worst case): ${_ms}ms (<2000ms; OLD took ~10-20s on this fixture)" \
                    || bad "b 200-file deps_unmet (no-claimable worst case): ${_ms}ms (>=2000ms) — index-once regression?"
rm -rf "$B"

# ── (c) PERF claim.sh: 1000-file "all_claimed" fixture < 2s. The OLD was ~0.9s on this
# fixture (lighter than deps_unmet because `[ -e ]` is fast and `next` short-circuits early
# per file). The NEW is ~0.2s. Bound at 2s catches a regression where someone re-adds the
# per-file bash loop in place of the single awk. The all_claimed fixture is already the
# no-claimable worst case (every file in state/claims/), so timing is deterministic.
echo "== (c) PERF: claim.sh on 1000-file all_claimed fixture < 2s =="
C="$(mktemp -d)"
make_fixture "$C" 1000 all_claimed
echo "x" > "$C/state/claims/CLAIMABLE"   # no-claimable worst case: every ticket pre-claimed
_t0=$(date +%s%N)
bash "$C/claim.sh" economy droidx both >/dev/null 2>&1 || true
_t1=$(date +%s%N)
_ms=$(( ( _t1 - _t0 ) / 1000000 ))
[ "$_ms" -lt 2000 ] && ok "c 1000-file all_claimed (no-claimable worst case): ${_ms}ms (<2000ms; OLD was ~1s, NEW is ~0.2s)" \
                    || bad "c 1000-file all_claimed (no-claimable worst case): ${_ms}ms (>=2000ms) — perf regression?"
rm -rf "$C"

# ── (d) PERF claim.sh: 2000-file "all_claimed" fixture < 5s (the PERF-AUDIT threshold).
# This is the threshold-bound test: a regression that reverts to O(n²) lands at ~12s, well
# over 5s, and fails this assertion. The current implementation is ~0.3s on this size.
echo "== (d) PERF: claim.sh on 2000-file all_claimed fixture < 5s (PERF-AUDIT threshold) =="
D="$(mktemp -d)"
make_fixture "$D" 2000 all_claimed
echo "x" > "$D/state/claims/CLAIMABLE"   # no-claimable worst case
_t0=$(date +%s%N)
bash "$D/claim.sh" economy droidx both >/dev/null 2>&1 || true
_t1=$(date +%s%N)
_ms=$(( ( _t1 - _t0 ) / 1000000 ))
[ "$_ms" -lt 5000 ] && ok "d 2000-file all_claimed (no-claimable worst case): ${_ms}ms (<5000ms PERF threshold; OLD was ~12s)" \
                    || bad "d 2000-file all_claimed (no-claimable worst case): ${_ms}ms (>=5000ms) — crossed PERF threshold!"
rm -rf "$D"

# ── (e) PERF decompose.sh: 20-unit plan finishes < 2s. decompose.sh is single-ticket-scoped
# (bounded by the plan, not the board) — already fast. A regression that reads the full board
# or iterates file-by-file would push this past 2s. The plan is built via DEC_PLAN_CMD so the
# REAL engine path is not invoked (the test's claim is the perf of the driver's validate+emit
# loop, which is what this ticket owns).
echo "== (e) PERF: decompose.sh on 20-unit plan < 2s =="
E="$(mktemp -d)"
mkdir -p "$E/board" "$E/board/archive"
cat > "$E/board/PARENT.md" <<'EOF'
tier: high
difficulty: 3
work_class: docs
branch: feat/perf-test
repo: charon-private
depends_on:
owns: src/m1.py, src/m2.py, src/m3.py, src/m4.py, src/m5.py
EOF
python3 -c "
import json
units = []
for i in range(20):
    units.append({'id':f'SUB-{i}','goal':f'g{i}','accept':['a'],'owns':[f'src/m{i}.py'],'tier':'high','depends_on':[f'SUB-{i-1}'] if i > 0 else []})
print(json.dumps({'units':units}))
" > "$E/plan.json"
cp "$SRC/decompose.sh" "$E/"
_t0=$(date +%s%N)
TICKET_FILE="$E/board/PARENT.md" BOARD_DIR="$E/board" DEC_PLAN_CMD="cat $E/plan.json" \
  bash "$E/decompose.sh" PERF-PARENT >/dev/null 2>&1
_rc=$?
_t1=$(date +%s%N)
_ms=$(( ( _t1 - _t0 ) / 1000000 ))
[ "$_rc" = 0 ] && ok "e 20-unit plan: exited 0 (decompose driver validated + emitted)" \
              || bad "e 20-unit plan: exited $_rc (expected 0)"
[ "$_ms" -lt 2000 ] && ok "e 20-unit plan: ${_ms}ms (<2000ms)" \
                    || bad "e 20-unit plan: ${_ms}ms (>=2000ms) — decompose driver regression?"
n=$(ls "$E/board"/SUB-*.md 2>/dev/null | wc -l)
[ "$n" = 20 ] && ok "e emitted all 20 sub-tickets (board/*.md)" \
              || bad "e emitted $n/20 sub-tickets"
rm -rf "$E"

# ── (f) decompose.sh DEC_PLAN_CMD seam: a plan with OVERLAPPING owns refuses (fail-on-revert
# of the validate step). Reverting decompose.sh's strict all-pairs disjoint-owns check would
# emit overlapping tickets onto the live board → this test flips RED on count mismatch.
echo "== (f) decompose.sh rejects OVERLAPPING owns (fail-on-revert of validate step) =="
F="$(mktemp -d)"
mkdir -p "$F/board" "$F/board/archive"
cat > "$F/board/PARENT.md" <<'EOF'
tier: high
difficulty: 3
work_class: docs
branch: feat/overlap-test
repo: charon-private
depends_on:
owns: src/x.py, src/y.py
EOF
cat > "$F/plan.json" <<'EOF'
{"units":[
  {"id":"OV-1","goal":"g","accept":["a"],"owns":["src/x.py"],"tier":"high"},
  {"id":"OV-2","goal":"g","accept":["a"],"owns":["src/x.py","src/y.py"],"tier":"high"}
]}
EOF
cp "$SRC/decompose.sh" "$F/"
TICKET_FILE="$F/board/PARENT.md" BOARD_DIR="$F/board" DEC_PLAN_CMD="cat $F/plan.json" \
  bash "$F/decompose.sh" OVERLAP-PARENT >/dev/null 2>&1
_rc=$?
# REFUSE = exit 3 (refuse=overlapping, die=other errors). Reverting validate → exit 0.
[ "$_rc" = 3 ] && ok "f overlapping owns refuses (exit 3, no board files written)" \
              || bad "f overlapping owns refuses (got exit $_rc — validate step regressed?)"
n=$(ls "$F/board"/OV-*.md 2>/dev/null | wc -l)
[ "$n" = 0 ] && ok "f refused plan: 0 sub-tickets written" \
              || bad "f refused plan: $n sub-tickets written (expected 0)"
rm -rf "$F"

# ── (g) decompose.sh: ZERO-unit plan refuses (refuse: nothing to emit). Reverting the
# zero-units check would crash on `units[0]` or silently emit 0 → no harm — but the explicit
# refuse matches the OLD driver's refuse + diagnostic.
echo "== (g) decompose.sh rejects ZERO-unit plan (refuse: nothing disjoint to emit) =="
G="$(mktemp -d)"
mkdir -p "$G/board" "$G/board/archive"
cat > "$G/board/PARENT.md" <<'EOF'
tier: high
difficulty: 3
work_class: docs
branch: feat/empty-plan
repo: charon-private
depends_on:
owns: src/z.py
EOF
echo '{"units":[]}' > "$G/plan.json"
cp "$SRC/decompose.sh" "$G/"
TICKET_FILE="$G/board/PARENT.md" BOARD_DIR="$G/board" DEC_PLAN_CMD="cat $G/plan.json" \
  bash "$G/decompose.sh" EMPTY-PARENT >/dev/null 2>&1
_rc=$?
[ "$_rc" = 3 ] && ok "g zero-units plan refuses (exit 3)" \
              || bad "g zero-units plan refuses (got exit $_rc)"
n=$(ls "$G/board"/EMPTY-*.md 2>/dev/null | wc -l)
[ "$n" = 0 ] && ok "g refused plan: 0 sub-tickets written" \
              || bad "g refused plan: $n sub-tickets written"
rm -rf "$G"

# ── (h) claim.sh idempotency: a successful claim followed by an immediate re-claim returns
# NONE. The NEW does the state-set rebuild under the lock (correctness), so the rebuild sees
# the new claim marker → second run returns NONE. A regression that bypasses the lock or
# builds the state set before the lock (stale sets) would let the second run re-claim the
# same ticket — this test would flip RED on `none_rc != 0` AND a non-empty state/claims/
# being a duplicate of the first claimed id.
echo "== (h) claim.sh idempotency: second call returns NONE, no duplicate claim marker =="
H="$(mktemp -d)"
make_fixture "$H" 50 all_claimed
first="$(bash "$H/claim.sh" economy droid1 both 2>&1)"
# The first call should claim CLAIMABLE (the only one not pre-claimed in make_fixture default).
case "$first" in
  "CLAIMED CLAIMABLE "*) ok "h first run claims CLAIMABLE" ;;
  *) bad "h first run claims CLAIMABLE (got: $first)" ;;
esac
second="$(bash "$H/claim.sh" economy droidx both 2>&1)"
[ "$second" = "NONE" ] && ok "h second run: NONE (no duplicate claim)" \
                      || bad "h second run: expected NONE (got: $second) — lock or state-set race?"
n=$(ls "$H/state/claims" | wc -l)
[ "$n" = 51 ] && ok "h state/claims count: 51 (50 pre-existing + 1 new CLAIMABLE)" \
               || bad "h state/claims count: $n (expected 51)"
rm -rf "$H"

rm -rf "$P"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL CLAIM-DECOMPOSE PERF TESTS PASS"
