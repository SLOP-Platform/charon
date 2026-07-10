# benchmark-v2 SCORING — adversarial review

Scope: deep on the scoring math (`efficiency.py`, `close_season.py`,
`tier_chart.py` v2 additions), coherence pass over the uncommitted diff.
Read-only, no edits. Selftest RUN: `python3 selftest/efficiency_selftest.py`
→ **exit 0, PASS** (all 5 parts). v1 `tier_chart.py gpt-5.4` renders
correctly (Frontier, composite 95.8, rank #2 of 3) → exit 0.

## VERDICT: SHIP-WITH-FIXES

The core math is correct and faithfully implements §4.2–§4.6 as amended.
One genuine latent defect (cheap, 1-line) plus two design-level notes.
Nothing blocks runtime *today* (the bench2 append path is deliberately
unbuilt, so no bench2 rows exist yet), but F1 is in core scoring code
being committed now and will silently mis-score once Phase-2 wiring lands.

---

## Deep math verification (CODE vs §4)

**Mid-rank percentile `100*(worse+0.5·tie)/(n-1)`** — CORRECT.
- All-tie / single-distinct-value field → worse=0, tie=n-1 → **50** for
  everyone (verified: `part2` flat-$0 field, and my own 4-model run). ✓
- Uniquely-best → 100, uniquely-worst → 0. ✓
- N=1 → `{}` (n<2 guard); no div-by-zero, no NaN. ✓
- Direction: `worse` counts strictly-higher (worse-efficiency) values, so
  **lower time/tokens/cost → higher percentile → +modifier**. Correct. ✓
- MIN_FIELD_SIZE gate is a SEPARATE guard in `modifier_from_eff_pct`
  (cohort<4 → 0); mid_rank itself is safe for any n≥2. ✓

**Weight renormalization (3:2:1) with a missing metric** — CORRECT.
`weighted_eff_pct` renormalizes over only the metrics the model has a
percentile for; `total_weight==0 → None`. A token-less model is simply
absent from the tokens field (`metric_values` excludes None), so a
with-token model is **never ranked against a without-token one in the
same field**. ✓

**±5 modifier + cap-after-modifier** — CORRECT & spec-ordered.
`adjusted=clamp(raw+mod,0,100)`, then `min(adjusted,89)` iff
`capped_while_failing`. The 89 cap applies strictly AFTER the modifier, so
efficiency cannot rescue a capped-failing section above 89; a passing
section keeps full 0–100 range. ✓

**COMPOSITE_EFF_CAP=±2 inversion-proof** — PROVEN independently.
`composite_final ∈ [raw−2, raw+2]`. For raw_Q−raw_P ≥ 4:
`Q_final ≥ raw_Q−2 ≥ raw_P+2 ≥ P_final`. Cannot invert a ≥4-pt gap; ties
exactly at gap=4 (89=89). Tried to build a counterexample — impossible,
the clamp is the binding constraint and the per-section delta is itself
bounded ±5 so the mean is ±5 pre-clamp. ✓ (Anti-cheat scope note: the 89
cap is *per-section*; a Strong-band model at composite_raw 88–89.99 CAN
reach Frontier via +2 — this is design-intended (worked ex. 4.7c) and
identical in spirit to v1's mean-of-min(score,89). Not a new defect.)

**Season freeze / immutability** — SOLID.
`close_season` refuses recompute if file exists & not `force`; atomic
write (`.tmp` + `replace()`, POSIX-atomic; crash leaves old/absent file
intact, never half-written). `efficiency.py` is disk-free; only writer is
`close_season`; `render_v2` only reads. A closed season cannot be mutated
by any path. Score fields reproduce identically (pure functions of rows);
only `closed_ts` provenance differs on a forced re-close. Provisional
(no file) → `render_v2` shows raw-only. ✓

**Partition** — SOLID. `bench2_rows_from_tsv` filters `source=="bench2"`
at the read boundary (v1 row can never enter a cohort); `close_season`
filters `r["season"]==season_id`; `rank_in_tier` raises on any
mixed-source/season record and on bench+season / bench2+no-season.
v1 `_rank_in_tier_v1_internal` rename is **byte-for-byte** (diff shows
name+docstring only; sole call site in `render()` updated). No v1
regression. ✓

**Flagged approximation (capped raw)** — BENIGN for the percentile (the
actual question): percentiles read tokens/time/cost only, never `raw`, so
they're fully correct regardless. It touches `section_total` only for a
capped-while-failing row whose true pre-cap raw >89 AND modifier<0 (then
84 vs 89) — bounded ≤5pt, always in the *harsher* direction on an
already-failing section, and further diluted by the ±2 composite clamp.
Not a ranking-correctness problem.

---

## Findings (ranked)

**F1 (SHOULD-FIX before commit — core, cheap, latent) —
`cohort_size = len(rows)` in `efficiency.compute_section_cohort`.**
Duplicate model rows (same model re-benched in one season/section) inflate
the count past DISTINCT models and OPEN the MIN_FIELD_SIZE gate on an
unstable field. Confirmed: 2 distinct models × 2 rows each → cohort_size=4
→ gate opens → each metric field has 2 entries → full-swing ±5 modifiers
— the exact run-order coin-flip MIN_FIELD_SIZE exists to prevent. Also
inconsistent with `close_season`'s own payload `cohort_size`, which
correctly uses `len(sorted(set(models)))`. Fix: count distinct models (or
dedupe rows) for the gate. Not live today (no bench2 append path yet) but
ships as a silent trap the moment Phase-2 wiring lands.

**F2 (NOTE — design-level, low) — per-metric sub-field not gated.**
§4.3b gates on |C| (cohort), not per-metric field size. A cohort of 4
where a weight-3 metric (tokens) is present for only 2 models yields a
n=2 coin-flip (0/100) on the heaviest axis (confirmed: B=+3.33, D=−5.00).
Code CONFORMS to the design; the design's own MIN_FIELD_SIZE rationale
just doesn't extend to sub-fields. Low risk in practice (tokens present
for all post-TOKEN-CAPTURE rows). Worth a design footnote, not a code fix.

**F3 (COHERENCE NOTE — low) — `efficiency_selftest.py` not wired into
`run_selftests.py`.** It's a standalone script like its siblings
(isolation/token_capture/session_cost), consistent with the existing
pattern, and no fleet gate auto-runs it — so committing won't fail a gate,
but there's no single command that sweeps it. Consider adding it to a
runner later.

## Coherence pass — PASS
- v1 back-compat: real tsv is 28 bench + 4 live rows, all 13-col; v1
  `render` works; `load_rows`/`bench_rows_for` unpack `cols[:13]`;
  bench2 adapter guards `len(cols)>13` → no IndexError on legacy rows.
- No `/home/stack`, IPs, tokens, or keys in any new/changed benchmark
  file (grepped; the one grep hit was a prose false-positive).
- `model-scorecard.sh`: one-line `VALID_SOURCE` add; bench2 reuses the
  15-col shape; v1 render awk still filters `src=="bench"` (bench2
  correctly invisible to v1 aggregates).
- No fleet-gate (validate_board.sh is board-only) or CI runs this Python,
  so the commit can't fail a gate.

## Must-fix-before-commit (ranked)
1. **F1** — `cohort_size` = distinct models, not `len(rows)` (1-line;
   prevents future silent scoring corruption). Only real fix.
2. (optional) **F2/F3** — footnote the sub-field gap; wire the selftest.
