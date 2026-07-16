#!/usr/bin/env bash
# budget-derive.test.sh — FAIL-ON-REVERT tests for EVAL-DERIVED-BUDGETS
# (fleet/benchmark/budget-derive.py).
#
# Design of record: fleet/state/PREFLIGHT-DESIGN-V2.md §LATENCY-BUDGET.
# Adversarial review: fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md §F8.
#
# Fully HERMETIC: writes a fixture model-scorecard.tsv + fixture LEG-RANK.tsv
# into a mktemp dir and points budget-derive.py at them via --scorecard /
# --leg-rank / --results-dir (an empty dir — no result cards). No network, no
# live ledger, no live rank file. The REAL budget-derive.py is exercised
# unmodified; only its inputs are fixtures.
#
# Covers (ticket's FAIL-ON-REVERT clause, EVAL-DERIVED-BUDGETS.md bottom):
#   (a) given a fixture time distribution, the derived budget == p95+margin
#       (revert the derivation -> it returns the hardcoded 480 -> test fails).
#       This is the exact clause: "given a fixture time distribution, the
#       derived budget == p95+margin (revert the derivation -> it returns the
#       hardcoded 480 -> test fails)."
#   (b) a leg with 2x tok_s gets ~half the wall-clock ceiling for the SAME
#       token budget (proves normalization, not a flat number). This is the
#       exact clause: "a leg with 2x tok_s gets ~half the wall-clock ceiling
#       for the same token budget (proves normalization, not a flat number)."
#   (c) sanity: KNOWN-GOOD filter — a BLOCK row (the too-slow tail) is NOT
#       allowed to raise the p95 (would re-introduce the RFL-3 499s truncation
#       as 'evidence' the budget should be 499).
#   (d) sanity: legacy work_class -> canonical mapping — a row tagged
#       'bugfix'/'ci-infra' contributes to the canonical 'coding' bucket
#       (EVAL-TAXONOMY-ALIGN dependency made load-bearing).
#   (e) sanity: insufficient-data bucket -> safe default (NOT 0, so the DETAIN
#       threshold is never absent on an uncalibrated class).
#
# Run:  bash fleet/tests/budget-derive.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="$SRC/benchmark/budget-derive.py"
[ -f "$TOOL" ] || { echo "FAIL: cannot find $TOOL" >&2; exit 1; }
command -v python3 >/dev/null || { echo "FAIL: python3 not found" >&2; exit 1; }

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }
has(){ printf '%s' "$1" | grep -q -- "$2" && ok "$3" || bad "$3 (missing '$2')"; }
not_has(){ printf '%s' "$1" | grep -q -- "$2" && bad "$3 (unexpectedly contains '$2')" || ok "$3"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

EMPTY_DIR="$D/empty-results"; mkdir -p "$EMPTY_DIR"
SC="$D/model-scorecard.tsv"
LR="$D/LEG-RANK.tsv"
OUT="$D/budgets.tsv"

# ── fixture scorecard: 21 good 'coding' rows (p95 lands EXACTLY on idx 19) ──
# n=21 -> p95 rank = 0.95*(21-1) = 19.0 -> idx 19 (0-based), NO interpolation.
# sorted good times: [20,31,35,40,50,60,70,80,90,100,110,120,130,140,150,160,170,180,190,200,250]
#                       0  1  2  3  4  5  6  7  8   9  10  11  12  13  14  15  16  17  18  19  20
# p95 = 200 (idx 19). Expected budget = 200 * 1.5 = 300.
#
# Three good rows are tagged with different LEGACY fleet classes (bugfix,
# ci-infra, routing) -> all must resolve to canonical 'coding' (covers (d)).
# One BLOCK row at 499s (a DETAIN(latency) tail) MUST be excluded (covers (c))
# — if it leaked in, the p95 would jump to ~499*1.5=748.5, not 300.
 TIMES=(20 31 35 40 50 60 70 80 90 100 110 120 130 140 150 160 170 180 190 200 250)
CLASSES=(bugfix bugfix ci-infra ci-infra routing routing bugfix bugfix ci-infra routing bugfix bugfix ci-infra ci-infra routing routing bugfix bugfix ci-infra ci-infra routing bugfix)
i=0
{
  printf '# fixture scorecard for EVAL-DERIVED-BUDGETS test\n'
  printf '# 21 good coding rows (p95=200, budget=300) + 1 BLOCK tail (excluded)\n'
  for t in "${TIMES[@]}"; do
    c="${CLASSES[$i]}"
    # tokens_out set to t*4 for the first 11 rows, '-' for the rest (exercises
    # the wall*ref_tok_s fallback in derive_token_budget for the no-token case)
    if [ "$i" -lt 11 ]; then tok=$((t * 4)); else tok="-"; fi
    printf '2026-01-%02d\tlive\tFIX-%03d\t%s\tT1\tglm-5.2\tMERGE\t-\t100\t%s\t-\t0\tfixture good %ss\t-\t%s\tactive\n' \
      "$((i+1))" "$i" "$c" "$t" "$t" "$tok"
    i=$((i+1))
  done
  # the too-slow tail — MUST be excluded from the good-time distribution
  printf '2026-01-22\tlive\tFIX-999\trouting\tT1\tglm-5.2\tBLOCK\t-\t0\t499\t-\t0\tfixture too-slow BLOCK excluded\t-\t-\tactive\n'
} > "$SC"

# ── fixture LEG-RANK: two legs, one at 40 tok/s, one at 80 tok/s (2x) ──
{
  printf 'model\tleg\treachable\tcanary_score\tlatency_s\ttok_s\tverdict\tdate\n'
  printf 'glm-5.2\tds\ttrue\t2/2\t3.0\t40.0\tHEALTHY\t2026-01-01\n'
  printf 'glm-5.2\tnvidia\ttrue\t2/2\t1.5\t80.0\tHEALTHY\t2026-01-01\n'
} > "$LR"

run_derive() {
  python3 "$TOOL" --scorecard "$SC" --results-dir "$EMPTY_DIR" \
    --leg-rank "$LR" --out "$OUT" --difficulty 2 "$@"
}
wall_for_leg() {
  python3 "$TOOL" --scorecard "$SC" --results-dir "$EMPTY_DIR" \
    --leg-rank "$LR" --wall-for-leg "$1" --token-budget "$2" \
    --work-class coding --difficulty 2
}

# ── (a) derived budget == p95+margin (p95=200, budget=300) ──────────────────
out="$(run_derive 2>&1)"
rc=$?
[ "$rc" -eq 0 ] && ok "(a) budget-derive.py exits 0 on a valid fixture" \
                 || bad "(a) budget-derive.py exited $rc"
# the coding row in budgets.tsv must show p95=200.0 and wall_budget=300.0
cod_line="$(awk -F'\t' '$1=="coding"' "$OUT")"
[ -n "$cod_line" ] && ok "(a) coding budget row present in budgets.tsv" \
                   || bad "(a) coding budget row present in budgets.tsv"
has "$cod_line" "$(printf 'coding\t2\t')" "(a) coding row keyed on (coding, difficulty=2)"
# n_good must be 21 (the BLOCK tail excluded)
has "$cod_line" "$(printf 'coding\t2\t21\t')" "(a) n_good=21 (BLOCK tail excluded from good count)"
# p95_time_s must be 200.0 (exact — no interpolation ambiguity at n=21, idx 19)
has "$cod_line" "$(printf '^coding\t2\t21\t200.0\t' )" "(a) p95_time_s == 200.0 (exact p95 of the 21 good times)"
# wall_budget_s must be 300.0 (200.0 * 1.5)
has "$cod_line" "$(printf '^coding\t2\t21\t200.0\t300.0\t')" "(a) wall_budget_s == 300.0 (= p95 * 1.5 = p95 + 0.5*p95)"
# status must be 'derived' (we have data)
has "$cod_line" 'derived$' "(a) status=derived (data present)"

# CRITICAL FAIL-ON-REVERT: if the derivation is reverted to return the hardcoded
# 480, the wall_budget_s would be 480, NOT 300. This assertion catches that.
not_has "$cod_line" "$(printf '^coding\t2\t21\t200.0\t480.0\t')" \
  "(a) wall_budget_s is NOT the hardcoded 480 (derivation is live — revert -> 480 -> this fails)"

# ── (b) 2x tok_s -> ~half wall-clock for the same token budget ──────────────
# token_budget=800, overhead=20.
# leg at 40 tok/s:   wall = 800/40 + 20 = 40.0
# leg at 80 tok/s:   wall = 800/80 + 20 = 30.0
# streaming component: 20 vs 10 -> 2x tok_s = ~half the streaming wall.
w40="$(wall_for_leg "glm-5.2/40.0" 800)"
w80="$(wall_for_leg "glm-5.2/80.0" 800)"
rc=$?
[ "$rc" -eq 0 ] && ok "(b) --wall-for-leg exits 0" || bad "(b) --wall-for-leg exited $rc"
has "$w40" '"wall_budget_s": 40.0' "(b) leg@40 tok/s -> wall=40.0 (800/40+20)"
has "$w80" '"wall_budget_s": 30.0' "(b) leg@80 tok/s -> wall=30.0 (800/80+20)"

# the normalization proof: the 2x-tok_s leg gets ~half the STREAMING wall.
# streaming only = wall - overhead: (40-20)=20 vs (30-20)=10 -> ratio 10/20 = 0.5
# We assert wall80_streaming / wall40_streaming is within [0.45, 0.55]
# (~half, not exact, because the assertion tolerates float noise but is tight
# enough that a flat-number revert — which gives ratio 1.0 — fails hard).
sw40=$(python3 -c "print($(printf '%s' "$w40" | sed -n 's/.*\"wall_budget_s\": \([0-9.]*\).*/\1/p') - 20.0)")
sw80=$(python3 -c "print($(printf '%s' "$w80" | sed -n 's/.*\"wall_budget_s\": \([0-9.]*\).*/\1/p') - 20.0)")
ratio=$(python3 -c "print(round(${sw80}/${sw40}, 3))")
if python3 -c "import sys; sys.exit(0 if 0.45 <= float('$ratio') <= 0.55 else 1)"; then
  ok "(b) 2x tok/s -> ~half streaming wall (ratio=$ratio, expected ~0.5)"
else
  bad "(b) 2x tok/s -> ~half streaming wall (ratio=$ratio, expected ~0.5; a flat-number revert gives 1.0)"
fi

# CRITICAL FAIL-ON-REVERT: if the normalization is reverted to ignore tok_s and
# return the flat wall_budget_s, BOTH legs get the SAME wall -> ratio = 1.0.
# The [0.45,0.55] window catches that.
if python3 -c "import sys; sys.exit(0 if abs(float('$ratio') - 1.0) < 0.05 else 1)"; then
  bad "(b) normalization appears REVERTED (ratio ~1.0 -> flat number, not per-leg)"
fi

# ── (c) KNOWN-GOOD filter: BLOCK tail excluded ───────────────────────────────
# n_good must be 21, NOT 22 (the BLOCK row at 499s is excluded).
has "$cod_line" "$(printf 'coding\t2\t21\t')" "(c) n_good=21 (the 499s BLOCK tail is excluded from the good-time distribution)"
# and the p95 is 200 (NOT ~499, which it would be if BLOCK leaked in)
has "$cod_line" "$(printf '^coding\t2\t21\t200.0\t')" "(c) p95=200.0 (BLOCK 499s did NOT raise the p95 to ~499)"

# ── (d) legacy work_class -> canonical 'coding' mapping ─────────────────────
# the fixture rows are tagged bugfix/ci-infra/routing — ALL must fold into
# canonical 'coding'. If the mapping were reverted, those rows would land in
# empty buckets (or be skipped), and the 'coding' n_good would be 0.
has "$cod_line" "$(printf 'coding\t2\t21\t')" "(d) legacy bugfix/ci-infra/routing rows folded into canonical 'coding' (n_good=21)"
# the other canonical buckets should be insufficient-data (no rows tagged them)
gen_line="$(awk -F'\t' '$1=="general"' "$OUT")"
has "$gen_line" 'insufficient-data$' "(d) 'general' bucket is insufficient-data (no good rows tagged general/reasoning/translation/creative entered the coding bucket via the mapping)"

# ── (e) insufficient-data -> safe default (NOT 0) ───────────────────────────
# a bucket with zero good rows must fall back to DEFAULT_WALL_S (900.0), NOT 0.
has "$gen_line" "$(printf '^general\t2\t0\t0.0\t900.0\t')" "(e) zero-data bucket -> wall_budget_s=900.0 (safe default, not 0)"
has "$gen_line" 'insufficient-data$' "(e) zero-data bucket -> status=insufficient-data (labeled, not presented as derived)"

# ── (f) BUDGET-SOURCE-RECONCILE: synthetic rows must NEVER steer the budget ──
# Standing rule: synthetic S0-S6 benchmarks are a SMOKE TEST ONLY — they must
# never rank a model or steer spend. Real outcomes only (source=live).
#
# THE DEFECT THIS PINS: budget-derive.py used to define its OWN
# `_REAL_OUTCOME_SOURCES = {"live","bench","bench2"}` — the SAME NAME as
# capability/grades.py's `{"live"}`, a DIFFERENT value. Synthetic bench rows
# therefore counted as real outcomes for the p95 latency budget. (Severity:
# every live row in the ledger carries time_s="-", while run.sh DOES record
# time_s on its synthetic rows — so the first bench run would have made
# synthetic the ONLY timed rows, i.e. the WHOLE budget.)
#
# This is a BEHAVIOURAL pin, not an introspection of the constant: it proves
# synthetic rows cannot reach the budget no matter HOW the allow-list is
# expressed. Re-widen the set anywhere and (f2)/(f3) go RED.
SC2="$D/scorecard-synthetic.tsv"
OUT2="$D/budgets-synthetic.tsv"
i=0
{
  printf '# fixture: 21 good LIVE coding rows (p95=200) + 10 SYNTHETIC bench/bench2\n'
  printf '# rows at 9999s. The synthetic rows are MERGE + stage=active — exactly what\n'
  printf '# benchmark/run.sh:140 appends. They must contribute NOTHING.\n'
  for t in "${TIMES[@]}"; do
    c="${CLASSES[$i]}"
    printf '2026-01-%02d\tlive\tFIX-%03d\t%s\tT1\tglm-5.2\tMERGE\t-\t100\t%s\t-\t0\tfixture good %ss\t-\t-\tactive\n' \
      "$((i+1))" "$i" "$c" "$t" "$t"
    i=$((i+1))
  done
  # SYNTHETIC tail: MERGE + stage=active + a wildly slow 9999s time. If the
  # allow-list re-widens, these enter -> n_good 21->31 and p95 200 -> ~9999.
  for n in 1 2 3 4 5; do
    printf '2026-02-%02d\tbench\tS%d\tbugfix\tT1\tglm-5.2\tMERGE\t-\t100\t9999\t-\t0\tsynthetic S%d smoke\t-\t-\tactive\n' "$n" "$n" "$n"
    printf '2026-03-%02d\tbench2\tS%d\tci-infra\tT1\tglm-5.2\tMERGE\t-\t100\t9999\t-\t0\tsynthetic S%d smoke\t-\t-\tactive\n' "$n" "$n" "$n"
  done
} > "$SC2"

python3 "$TOOL" --scorecard "$SC2" --results-dir "$EMPTY_DIR" \
  --leg-rank "$LR" --out "$OUT2" --difficulty 2 >/dev/null 2>&1
syn_line="$(awk -F'\t' '$1=="coding"' "$OUT2")"

# (f1) the SSOT import is live: budget-derive must reuse grades.py's object.
#      A re-introduced local literal makes these two different objects -> RED.
ssot="$(cd "$SRC/benchmark" && python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('bd', 'budget-derive.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sys.path.insert(0, '../capability')
import grades
same = m._REAL_OUTCOME_SOURCES is grades.REAL_OUTCOME_SOURCES
print('SSOT_SHARED' if same else 'SSOT_DIVERGED')
print('SET=' + ','.join(sorted(grades.REAL_OUTCOME_SOURCES)))
" 2>&1)"
has "$ssot" 'SSOT_SHARED' "(f1) budget-derive imports grades.REAL_OUTCOME_SOURCES (same object — a local copy would read SSOT_DIVERGED)"
has "$ssot" 'SET=live' "(f2) the SSOT allow-list is exactly {live} (widening it to bench/bench2 -> RED)"

# (f3) BEHAVIOUR: 10 synthetic MERGE rows at 9999s contribute NOTHING.
has "$syn_line" "$(printf '^coding\t2\t21\t')" "(f3) n_good=21 — the 10 synthetic bench/bench2 rows are EXCLUDED (a re-widened set gives 31)"
has "$syn_line" "$(printf '^coding\t2\t21\t200.0\t300.0\t')" "(f3) p95=200.0 / budget=300.0 — synthetic 9999s rows did NOT steer the budget"
not_has "$syn_line" '9999' "(f3) no synthetic 9999s value reached the derived budget"

# (f4) the degrade is SAFE and HONEST: a ledger of ONLY synthetic rows must
#      yield insufficient-data + the 900s safe default — never a
#      synthetic-derived number wearing a 'derived' label.
SC3="$D/scorecard-synth-only.tsv"; OUT3="$D/budgets-synth-only.tsv"
{
  printf '# fixture: ONLY synthetic rows — the budget must refuse to derive.\n'
  for n in 1 2 3 4 5; do
    printf '2026-02-%02d\tbench\tS%d\tbugfix\tT1\tglm-5.2\tMERGE\t-\t100\t42\t-\t0\tsynthetic only\t-\t-\tactive\n' "$n" "$n"
  done
} > "$SC3"
python3 "$TOOL" --scorecard "$SC3" --results-dir "$EMPTY_DIR" \
  --leg-rank "$LR" --out "$OUT3" --difficulty 2 >/dev/null 2>&1
so_line="$(awk -F'\t' '$1=="coding"' "$OUT3")"
has "$so_line" "$(printf '^coding\t2\t0\t0.0\t900.0\t')" "(f4) synthetic-only ledger -> n_good=0 + 900s safe default (fails SAFE, not to a synthetic p95 of 63.0)"
has "$so_line" 'insufficient-data$' "(f4) synthetic-only ledger -> status=insufficient-data (honest label, never 'derived' off smoke data)"

echo "SELFTEST SUMMARY: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
