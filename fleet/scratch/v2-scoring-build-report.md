# benchmark-v2 SCORING build report

Built on top of the pre-existing uncommitted harness hardening + TOKEN-CAPTURE
work already in the tree (`lib/grade_state.py`'s stale-state guards/locking,
`lib/charon_cost.py::snapshot_usage()`, `model-scorecard.sh`'s tokens_in/out
cols 14/15). None of that was reverted or altered in behavior. No commit, no
push. Harness confirmed idle before starting
(`pgrep -fa 'bench.sh|grade_state|run.sh'` matched nothing but this shell's
own snapshot process) and again idle after finishing.

## Files changed

**New:**
- `benchmark/lib/efficiency.py` — §4.3-§4.5 pure scoring math (mid-rank
  percentile, weighted EFF_PCT, bounded modifier, anti-cheat-ordered
  `section_total`). No disk/TSV/wall-clock access — fully unit-testable.
- `benchmark/lib/close_season.py` — §4.2 season-freeze batch job + TSV
  adapter (`bench2_rows_from_tsv`), immutable closed-season JSON store under
  `benchmark/state/seasons/<season_id>.json` (directory does not exist in
  the repo yet — created only inside scratch temp dirs during this session,
  confirmed absent from the real tree afterward).
- `benchmark/selftest/efficiency_selftest.py` — new self-test proving all 5
  required properties (see Verification below).

**Modified:**
- `benchmark/lib/tier_chart.py` — added v2 support: `COMPOSITE_EFF_CAP`,
  `season_for_date`, `bench2_rows_for`, `composite_v2`, `tier_label`, the new
  partition-aware `rank_in_tier(models, source, season=None)`, and
  `render_v2()` + a minimal CLI extension (`tier_chart.py <model> --source
  bench2 --season <id>`). The **old** `rank_in_tier(rows, this_model,
  tier_name)` was renamed to `_rank_in_tier_v1_internal` (its one call site,
  inside `render()`, updated to match) — behavior byte-for-byte unchanged;
  it had to be renamed only because Python can't have two functions sharing
  one name, and the design calls for the new, stricter signature to own the
  `rank_in_tier` name. Nothing else in v1's code path (`load_rows`,
  `bench_rows_for`, `composite_overall`, `overall_tier`, `render`) was
  touched.
- `model-scorecard.sh` — `VALID_SOURCE="live bench"` → `"live bench bench2"`.
  One line. `cmd_append`'s arity/column logic, `cmd_render`'s awk, and every
  other check were left untouched — a `bench2` row uses the identical
  15-column shape a `bench` row already uses post-TOKEN-CAPTURE, so no other
  code needed to change to accept it. (`cmd_render`'s v1-specific "BENCH mean
  score" block still filters `src=="bench"` only — `bench2` rows are
  correctly invisible to it, which is the intended partition behavior, not a
  gap.)

**Explicitly NOT touched** (in scope per §8 Phase 2 but out of scope for
this "scoring" pass, or already covered elsewhere):
- `bench.sh do_grade` was NOT wired to append `source=bench2` rows from live
  runs. That requires deciding how bench.sh picks v1-vs-v2 mode (a flag? a
  harness-version constant?) and is an integration/UX decision, not scoring
  math — flagged here rather than silently done or silently skipped.
- The real `model-scorecard.tsv`/`benchmark/runs/` tree and
  `benchmark/state/` were never written to. All verification ran against
  scratch TSVs/dirs (temp dirs under `tempfile.TemporaryDirectory()` inside
  the selftest, plus `/tmp/claude-*/.../scratchpad/` for the manual dry run).

## Design-conformance mapping (§4.2-§4.8 → code)

| Design rule | Where implemented | Notes |
|---|---|---|
| §4.2 season-frozen field, computed once, immutable after close | `close_season.py::close_season()` | Refuses to recompute an existing `<season>.json` without `force=True`; atomic write (`.tmp` + `rename()`). Proven by `efficiency_selftest.py::part1_field_freeze_reproducibility` (reproduces worked example 4.7a: W28's 4th model never perturbs W27's already-closed numbers; re-close without force raises). |
| §4.2 wall-clock note ("scripts can't call wall-clock in some contexts") | `close_season.py` never calls `time.time()`/`date.today()` to pick a season; `season_id` is always an explicit argument. `closed_ts` is provenance metadata only. |
| §4.3a mid-rank percentile, ties centered at 50 | `efficiency.py::mid_rank_percentile()` | `100*(worse+0.5*tie)/(n-1)`. Proven by `efficiency_selftest.py::part2_mid_rank_ties` (3-way tie → 50; all-tied/flat-sub-$0 field → 50 for everyone, not 0). |
| §4.3b `MIN_FIELD_SIZE=4` gates the modifier | `efficiency.py::modifier_from_eff_pct()` | Cohort-level gate (checked once per section per §4.2, since a season shares one cohort size). Proven by `part3_min_field_size` (cohort=2 → modifier 0 despite real differentiation; cohort=4 → modifier allowed to move). |
| §4.4 weighted EFF_PCT, tokens:time:cost=3:2:1, renormalized over available metrics | `efficiency.py::weighted_eff_pct()` | "tokens" = `tokens_in+tokens_out` combined into one scalar — the design always refers to a single tokens axis; the in/out combination rule is documented explicitly in `efficiency.py`'s module docstring since the design text doesn't spell it out. |
| §4.5 modifier applied BEFORE anti-cheat `min(...,89)` cap | `efficiency.py::section_total()` | `adjusted=clamp(raw+modifier,0,100)`, then `min(adjusted,89)` iff `capped_while_failing`. Order preserved exactly as designed. |
| §4.6a `COMPOSITE_EFF_CAP=±2` on the aggregate delta, cannot invert a ≥4pt correctness gap | `tier_chart.py::composite_v2()` | `composite_raw` = mean(section_correctness) (pure v1 formula on v2 data); `composite_eff_delta` clamped to ±2 before adding. Proven by `part4_composite_eff_cap` — reproduces worked example 4.7c exactly: P(raw=87,+5-swing)=89, Q(raw=91,-5-swing)=89 (tie, never inverted); near-tie case (both raw=88.5) → 90.5 (Frontier) vs 87.5 (Strong), proving efficiency *is* allowed to decide genuine near-ties. |
| §4.6b hard source/season partition everywhere a ranking happens | `tier_chart.py::rank_in_tier(models, source, season=None)` | New function (old same-name v1-only helper renamed `_rank_in_tier_v1_internal`, unchanged behavior). Raises `ValueError` on any record whose `(source, season)` doesn't exactly match the call's partition, on `source="bench"` given a season, and on `source="bench2"` given no season. Proven by `part5_partition_isolation` (mixed-source list raises; mixed-season bench2 list raises; a clean single-partition list ranks correctly) plus `close_season.bench2_rows_from_tsv`/`close_season()` never admitting a `source=="bench"` row into a bench2 cohort (same test, TSV-level check). |
| §4.6b tier labeling ("Frontier · v1" vs "Frontier · v2 (season)") | `tier_chart.py::tier_label()` + `render_v2()` | `render_v2()` prints the v2 chart standalone (never merged with v1's `render()` output) via a new CLI form `tier_chart.py <model> --source bench2 --season <id>`; provisional (season not yet closed) renders raw-only with an explicit "still OPEN (provisional)" notice, never a guessed tier. |
| §8 Phase 2 "close_season.py never admits a bench row into a bench2 cohort" self-test | `efficiency_selftest.py::part5_partition_isolation` | Explicit TSV with a mixed `source=bench`/`source=bench2` row for the same model/section; asserts the `bench` row is excluded from both the raw row list and the closed cohort. |

## Known, documented approximation (not silently papered over)

`close_season.py::bench2_rows_from_tsv()`'s `raw` field is read from the TSV
`score` column, which `grade_state.py::cmd_record` already finalizes as
`min(true_raw, 89)` for a capped-while-failing section — the grader's true
pre-cap score is not persisted anywhere upstream today (that's the
`grade.json` work described in BENCHMARK-V2-DESIGN.md §5, out of scope for
this scoring-only pass). This is harmless for the anti-cheat invariant
specifically (§4.5's own `min(adjusted,89)` re-application still holds the
89 ceiling regardless of what value came in), but means a capped-while-
failing row's `section_total` is computed from an already-capped `raw`
rather than the true one. `capped_while_failing` itself is derived (no such
column exists) from `gate=="fail" and not note.startswith("timeout (")`,
which is exact given how `bench.sh::do_grade`/`grade_state.py::cmd_record`
populate those two columns today (verified by re-reading `bench.sh` lines
304-365 and `grade_state.py::cmd_record`'s three finalize branches).

## Verification

- `python3 -m py_compile` clean on all 5 touched/new Python files
  (`efficiency.py`, `close_season.py`, `tier_chart.py`, `grade_state.py`,
  `charon_cost.py`) plus the new selftest.
- `bash -n` clean on `model-scorecard.sh`, `bench.sh`, `run.sh`.
- All pre-existing selftests still pass, unmodified, no regression:
  `selftest/run_selftests.py` (grader goldens, 20/20),
  `selftest/run_isolation_selftest.py` (bench-run-collision hardening),
  `selftest/token_capture_selftest.py` (TOKEN-CAPTURE + tier_chart mixed-
  column tolerance), `selftest/session_cost_selftest.py`.
- New `selftest/efficiency_selftest.py` passes — all 5 required properties
  (field-freeze reproducibility, mid-rank tie, MIN_FIELD_SIZE gating,
  COMPOSITE_EFF_CAP inversion-proof, bench2/v1 partition isolation), plus
  the extra `rank_in_tier` argument-validation edge cases (`bench`+season,
  `bench2`+no season).
- Manual dry-run: copied the real (cleaned) `model-scorecard.tsv` to a
  scratchpad path, derived 24 synthetic `source=bench2` rows from real
  `gpt-5.4`/`glm-5.2`/`hy3-preview-or`/`kimi-k2.6` S1-S6 bench rows (real
  scores/time_s/cost_usd, synthetic-but-plausible token counts since the
  real ledger predates TOKEN-CAPTURE), closed a season, and rendered all 4
  models via `tier_chart.render_v2()`. Numbers landed sanely: modifiers
  stayed within ±5, `section_total` correctly stayed ≤89 whenever
  `capped_while_failing`, composites ranged 84.6-99.6, tiers ("Strong · v2",
  "Frontier · v2") matched the composite cuts. Real files untouched
  throughout (`git status --porcelain benchmark/runs model-scorecard.tsv`
  clean of any net change beyond the pre-existing uncommitted diff; no
  `benchmark/state/` directory was created in the real tree).

## Proposed commit message

```
feat(benchmark-v2): implement season-frozen efficiency scoring (§4.2-§4.8)

Adds lib/efficiency.py (mid-rank percentile, MIN_FIELD_SIZE=4 gate,
tokens:time:cost=3:2:1 weighted EFF_PCT, ±5 bounded per-section modifier,
cap-after-modifier anti-cheat ordering) and lib/close_season.py (season
cohort computed once at close, immutable after; TSV adapter deriving
bench2 rows/capped_while_failing). tier_chart.py gains composite_v2()
(±2 COMPOSITE_EFF_CAP on the aggregate delta - provably can't invert a
>=4pt correctness gap), the partition-aware rank_in_tier(models, source,
season) that refuses mixed-source/season lists, and a v2 render path
(tier_chart.py <model> --source bench2 --season <id>). model-scorecard.sh
gains the bench2 source tag (one line; reuses the existing 15-column
TOKEN-CAPTURE shape unchanged). New selftest/efficiency_selftest.py proves
field-freeze reproducibility, mid-rank ties, MIN_FIELD_SIZE gating, the
composite cap's inversion-proof, and bench2/v1 partition isolation - all
against scratch TSVs/dirs. v1 (source=bench) scoring is untouched;
existing selftests all still pass.

Built per BENCHMARK-V2-DESIGN.md §4 (amended) + §8 Phase 2. bench.sh's
live-run bench2 wiring (Phase 2's do_grade touch-point) is deliberately
NOT included here - a mode-selection/UX decision, not scoring math.
```
