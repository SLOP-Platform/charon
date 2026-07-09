#!/usr/bin/env python3
"""Final tier chart for a benchmarked model: section->grade table, ONE overall
tier placement across ALL 7 sections (S0-S6), and this model's RANK within
that tier against every other model already scored in model-scorecard.tsv.

No fleet/tiers.json exists in this repo (checked before building this) -
the composite/ladder below is this chart's own definition, documented here
so it's never silent:

COMPOSITE FORMULA
  S0 stays a pass/fail SANITY GATE, not a capability input (it only proves
  the harness/model-plumbing works at all - scoring it into a capability
  average would reward "the tool didn't crash" as if it were a skill). It
  must score exactly 100 or the whole run is flagged INVALID rather than
  tiered.
  Once S0=100, the OVERALL COMPOSITE = the unweighted mean of every graded
  section's score in S1..S6 (equal weight; S6 counts alongside the backend
  sections instead of sitting on a separate axis - this is the one change
  from the prior two-tier chart, replacing "backend tier reach" + a parallel
  "frontend tier" with a single number). Ungraded sections are simply
  excluded from the mean (a partial run still gets a running composite).

TIER LADDER (simple, plain-word, no compound/parenthetical jargon):
  Frontier   composite >= 90
  Strong     composite >= 75 and < 90
  Capable    composite >= 60 and < 75
  Basic      composite >= 50 and < 60
  No Tier    composite <  50  -- "too weak to place"
These cuts mirror the existing MERGE(>=90)/FIXES(50-89)/BLOCK(<50) verdict
bands used per-section (MODEL-BENCHMARK-SPEC.md), just split FIXES into two
human-readable notches (Strong/Capable) instead of leaving one wide band.

RANK = this model's composite versus every OTHER model in
model-scorecard.tsv that lands in the SAME tier, sorted descending by
composite, ties broken by lower mean time_s across all graded sections
(faster is the better tiering candidate at equal score, per the
efficiency-triple rationale in MODEL-BENCHMARK-SPEC.md #5a). Models with no
tier (INVALID or "No Tier") are never ranked - the chart says so plainly
instead of printing a rank among the unplaceable.

--------------------------------------------------------------------------
BENCHMARK-V2 (source=bench2) - BENCHMARK-V2-DESIGN.md §4.6a/§4.6b

Everything above this line is the ORIGINAL v1 formula (source=="bench")
and is UNCHANGED by v2 - same functions, same behavior, same output for
any v1 model. v2 adds a SEPARATE, PARALLEL formula that never mixes with
v1 in one ranked list:

  composite_raw(M)   = mean(section_correctness) over S1..S6, where
                        section_correctness = min(raw,89) if the section
                        hit CORRECTIONS_CAP while still failing, else raw
                        - i.e. the EXACT v1 formula, applied to v2 data
                        (§4.6a). This is what `composite_v2()` below
                        returns as its first element.
  composite_eff_delta = mean(section_total - section_correctness) over
                        the same sections, CLAMPED to +/-COMPOSITE_EFF_CAP
                        (2 points) before being added to composite_raw -
                        a composite-level cap independent of (and smaller
                        than) the per-section +/-5 modifier bound (§4.5),
                        so efficiency can never invert a >=4-point
                        composite_raw gap between two models (§4.6a,
                        worked example 4.7c).
  composite_final(M)  = composite_raw(M) + composite_eff_delta_clamped(M)
                        - this is what a v2 tier decision is read off,
                        using the SAME TIER_LADDER cuts as v1 (90/75/60/50
                        - "Frontier" is the same bar everywhere).

`section_total`/`modifier` are only ever available for a season's models
AFTER that season has been CLOSED (`lib/close_season.py`, §4.2) - a
provisional (still-open-season) bench2 row has no section_total yet and
must render raw-only, never tiered on a guessed/partial modifier.

`rank_in_tier(models, source, season=None)` (§4.6b) is the load-bearing
partition guard: it takes an explicit, pre-tagged list of per-model
composite records and refuses (raises ValueError) the instant one of them
doesn't match the requested `(source, season)` partition exactly - v1 and
v2 (and different v2 seasons) are NEVER ranked in one merged, sorted list.
This is a NEW function, distinct from the pre-existing per-tier ranking
helper used internally by v1's own `render()` (renamed
`_rank_in_tier_v1_internal` below, behavior byte-for-byte unchanged, so
existing v1 output is unaffected) - two different signatures can't share
one name in this module, and the v1 internal helper's exact prior
behavior (used only by `render()`) is preserved deliberately rather than
folded into the new, stricter API.
"""
import sys
from datetime import date as _date
from pathlib import Path

TSV = Path(__file__).resolve().parent.parent.parent / "model-scorecard.tsv"

ALL_SECTIONS = ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
CAPABILITY_SECTIONS = ["S1", "S2", "S3", "S4", "S5", "S6"]

TIER_LADDER = [
    (90, "Frontier"),
    (75, "Strong"),
    (60, "Capable"),
    (50, "Basic"),
]

# BENCHMARK-V2-DESIGN.md §4.6a - the composite-level cap on the AGGREGATE
# efficiency contribution (independent of, and smaller than, the
# per-section +/-MODIFIER_MAX=5 bound in lib/efficiency.py). Provably
# cannot invert a >=4-composite-point correctness gap between two models
# (2 * COMPOSITE_EFF_CAP = 4) - see composite_v2()'s docstring and worked
# example 4.7c.
COMPOSITE_EFF_CAP = 2.0

# AGGREGATE-N (BENCH-AGGREGATE-N, #16 — design of record:
# fleet/scratch/pivot-implementation-plan.md §5). The synthetic S0–S6
# bench score is not test-retest reliable at N=1 (validity review §4/§5:
# glm-5.2 scored S3 100->75, S5 100->60 ACROSS repeat runs), yet
# bench_rows_for() previously kept only the LAST row per section
# (dict last-wins) and tiered off that single number. It now AGGREGATES all
# active bench rows sharing a section ref into mean ± noise band over N runs
# (see `_score_stats`), and a composite gap SMALLER than the combined band
# renders as a TIE, not a rank (`_composites_tie`). Reuses the same 95%
# two-sided z capability/grades.py's Wilson bounds use.
_AGG_Z = 1.959963985


def _score_stats(values):
    """(mean, sample_stddev, ci_half_width) over N repeat-run scores — LOCKSTEP
    with capability/grades.py::_score_stats (kept a local copy so this module
    keeps no import across the benchmark<->capability package boundary, the
    same duplication discipline season_for_date() documents above). Returns
    (None,None,None) for 0 runs; (mean,None,None) for 1 run (one sample carries
    no run-to-run noise estimate — band left unmeasured, never faked as 0)."""
    n = len(values)
    if n == 0:
        return None, None, None
    m = sum(values) / n
    if n < 2:
        return m, None, None
    var = sum((v - m) ** 2 for v in values) / (n - 1)
    sd = var ** 0.5
    return m, sd, _AGG_Z * sd / (n ** 0.5)


def _composites_tie(score_a, band_a, score_b, band_b):
    """#16: TIE (not a rank) when the gap is within the combined noise band —
    LOCKSTEP with capability/grades.py::scores_tie. A None band (<2 runs,
    unmeasurable) contributes 0."""
    return abs(score_a - score_b) <= ((band_a or 0.0) + (band_b or 0.0))


def composite_band(section_scores):
    """#16: propagate each section's per-mean CI half-width to the OVERALL
    composite (which is the unweighted mean of the section means). With the
    composite = (1/k)·Σ mean_i, its standard error² = (1/k²)·Σ stderr_i²
    (stderr_i = band_i / z), so the composite band = z·√(that). A section with
    <2 runs has no measurable band and contributes 0. Returns None if no
    capability section is graded yet."""
    stderr_sq = []
    k = 0
    for s in CAPABILITY_SECTIONS:
        info = section_scores.get(s)
        if info is None:
            continue
        k += 1
        band = info.get("score_band")
        if band:
            stderr_sq.append((band / _AGG_Z) ** 2)
    if k == 0:
        return None
    return _AGG_Z * ((sum(stderr_sq) / (k * k)) ** 0.5)

# REAL-OUTCOMES PIVOT (BENCH-REGROUND-LIVE, pivot A2 — design of record:
# fleet/scratch/pivot-implementation-plan.md §0/§1/§7; driving verdict:
# fleet/BENCHMARK-VALIDITY-REVIEW.md). The synthetic S0–S6 composite/tier this
# module computes is DEMOTED to a smoke-test: it no longer sets a capability
# tier position and must not be read as a ranking signal. Real capability
# grades now come from `source=live` real-outcome actuals via
# capability/grades.py (which excludes source in {bench,bench2}). S0 is kept
# ONLY as the harness sanity gate (S0 != 100 => INVALID run). This banner is
# printed on every human-facing render so the demotion can never be silent;
# the composite math below is UNCHANGED (efficiency_selftest / token_capture
# selftests + the v2 partition guard still depend on it verbatim) — only its
# STATUS changed from "capability tier" to "smoke-only diagnostic".
_SMOKE_BANNER = (
    "SMOKE-ONLY (synthetic S0–S6) — DEMOTED per the real-outcomes pivot\n"
    "(fleet/BENCHMARK-VALIDITY-REVIEW.md): this composite/tier is NOT a\n"
    "capability signal and no longer feeds ranking or the grades brain.\n"
    "Real grades come from source=live actuals via capability/grades.py.\n"
    "S0 below remains ONLY a harness sanity gate."
)


def load_rows(tsv_path=TSV):
    rows = []
    if not tsv_path.exists():
        return rows
    for line in tsv_path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 13:
            continue
        rows.append(cols)
    return rows


def _stage(cols):
    """PROVISIONAL-vs-ACTIVE (#20): a row's stage is its 16th column; any row
    with < 16 columns (every legacy 13/15-col row) is `active`. An empty cell
    also reads active — only an explicit `provisional` value excludes a row."""
    if len(cols) >= 16 and cols[15].strip():
        return cols[15].strip()
    return "active"


def bench_rows_for(rows, model):
    """AGGREGATE-N (#16): all ACTIVE source=bench rows sharing a section ref are
    now aggregated (mean ± noise band over N runs), NOT collapsed to the last
    row (the old dict last-wins, which trusted one run like a stable average —
    the exact N=1 unreliability the validity review flagged). `score` carries
    the aggregate MEAN (so composite_overall/render read it unchanged), plus
    new keys `score_n`/`score_mean`/`score_stddev`/`score_band`/`score_values`
    publish the smoothing signal. The non-score display fields (time/cost/
    corrections/verdict/gate/note) keep the LAST run's value — same shape older
    readers (token_capture_selftest part3) assert on; only the score gained a
    band."""
    buckets = {}
    for cols in rows:
        # PROVISIONAL-vs-ACTIVE (#20): a provisional unit's rows are COLLECTED
        # but excluded from the (smoke) composite/tier — same trust gate the
        # capability grade uses in capability/grades.py, applied here too so a
        # provisional section can never move even the demoted smoke chart.
        if _stage(cols) != "active":
            continue
        _date, source, ref, wclass, _tier, m, verdict, gate, score, time_s, cost, corr, note = cols[:13]
        if source != "bench" or m != model:
            continue
        if score == "-":
            continue
        b = buckets.setdefault(ref, {"scores": []})
        b["scores"].append(int(score))
        # last-run wins for the display/efficiency fields (unchanged behavior)
        b.update({"skill": wclass, "verdict": verdict, "gate": gate,
                  "time_s": time_s, "cost_usd": cost, "corrections": corr, "note": note})
    out = {}
    for ref, b in buckets.items():
        scores = b["scores"]
        mean_s, sd, band = _score_stats(scores)
        out[ref] = {
            "score": mean_s,          # AGGREGATE MEAN over N runs (was single last row)
            "score_mean": mean_s, "score_stddev": sd, "score_band": band,
            "score_n": len(scores), "score_values": list(scores),
            "verdict": b["verdict"], "gate": b["gate"], "skill": b["skill"],
            "time_s": b["time_s"], "cost_usd": b["cost_usd"],
            "corrections": b["corrections"], "note": b["note"],
        }
    return out


def composite_overall(section_scores):
    scores = [section_scores[s]["score"] for s in CAPABILITY_SECTIONS if s in section_scores]
    return sum(scores) / len(scores) if scores else None


def tier_name_for(composite):
    for floor, name in TIER_LADDER:
        if composite >= floor:
            return name
    return "No Tier"


def overall_tier(section_scores):
    """Returns (tier_name_or_None, composite_or_reason).
    tier_name is one of: None (nothing graded yet), "INVALID", "No Tier",
    or a TIER_LADDER name. When it's a real tier, the second element is the
    numeric composite; otherwise it's a human-readable reason string."""
    s0 = section_scores.get("S0")
    if s0 is None:
        if not section_scores:
            return None, "not yet determined (no sections graded)"
        return "INVALID", "S0 sanity gate not yet run - investigate harness/model-plumbing before trusting any other section"
    if s0["score"] != 100:
        return "INVALID", "S0 sanity gate not clean (100 required); investigate harness/model-plumbing before trusting any other section"
    comp = composite_overall(section_scores)
    if comp is None:
        return None, "not yet determined (no capability sections graded)"
    name = tier_name_for(comp)
    if name == "No Tier":
        return "No Tier", f"too weak to place (composite {comp:.1f} < 50)"
    return name, comp


def mean_time(section_scores, keys=ALL_SECTIONS):
    times = []
    for k in keys:
        info = section_scores.get(k)
        if info and info["time_s"] not in ("-", ""):
            try:
                times.append(float(info["time_s"]))
            except ValueError:
                pass
    return sum(times) / len(times) if times else float("inf")


def _rank_in_tier_v1_internal(rows, this_model, tier_name):
    """v1-only (source=="bench") per-tier rank, used internally by render().
    Rank among every OTHER model in the tsv landing in the same named tier
    (this_model included), sorted by composite desc, tie-broken by mean time_s
    asc.

    AGGREGATE-N (#16): ranking now uses COMPETITION ranks with statistical
    ties — two adjacent models whose composite gap is within their COMBINED
    noise band (`_composites_tie`) share a rank instead of being ordered on
    noise (a sub-band gap is a tie, not a rank). Returns (rank, total, tied)
    where `tied` is True iff this_model shares its rank with >=1 other model."""
    all_models = sorted({cols[5] for cols in rows if cols[1] == "bench"})
    candidates = []
    for m in all_models:
        sc = bench_rows_for(rows, m)
        t, comp = overall_tier(sc)
        if t != tier_name or comp is None or isinstance(comp, str):
            continue
        candidates.append({"model": m, "composite": comp,
                           "band": composite_band(sc) or 0.0, "tie_break": mean_time(sc)})
    candidates.sort(key=lambda c: (-c["composite"], c["tie_break"]))
    total = len(candidates)
    # competition ranking ("1,2,2,4") with a #16 tie = within the combined band
    # of the current tie-GROUP LEADER (not the immediate neighbour). Statistical
    # ties are non-transitive, so anchoring to the neighbour would CHAIN A~B~C
    # into one rank even when A-C exceeds the combined band; anchoring to the
    # group leader keeps a tie group from drifting past its own noise band.
    ranks = []
    leader = None
    for i, c in enumerate(candidates):
        if i == 0:
            ranks.append(1)
            leader = c
        elif _composites_tie(c["composite"], c["band"],
                             leader["composite"], leader["band"]):
            ranks.append(ranks[-1])   # tie stays anchored to the group leader
        else:
            ranks.append(i + 1)       # new group starts
            leader = c
    rank = None
    tied = False
    for i, c in enumerate(candidates):
        if c["model"] == this_model:
            rank = ranks[i]
            tied = ranks.count(ranks[i]) > 1
            break
    return rank, total, tied


# --------------------------------------------------------------------------
# BENCHMARK-V2 (source=bench2) - §4.6a composite, §4.6b partition guard.
# --------------------------------------------------------------------------

def season_for_date(date_str):
    """ISO calendar week id (e.g. "2026-W28") for a `date` column value -
    identical rule to lib/close_season.py::season_id_for_date, duplicated
    here (rather than imported) so tier_chart.py has no import-time
    dependency on close_season.py; both are tiny, stdlib-only, and must
    never drift apart (single-line rule, easy to keep in lockstep)."""
    y, w, _weekday = _date.fromisoformat(date_str).isocalendar()
    return f"{y}-W{w:02d}"


def bench2_rows_for(rows, model, season):
    """Like `bench_rows_for`, but for source=="bench2" rows belonging to
    ONE model AND ONE season (§4.6b: a bench2 row from a different season
    - or any source=="bench" row - can never enter this model's section
    map). `score` here is `section_correctness` as recorded in the ledger
    (see lib/close_season.py's TSV-adapter docstring for the one known
    raw-vs-recorded approximation on capped-while-failing rows)."""
    out = {}
    for cols in rows:
        if len(cols) < 13:
            continue
        if _stage(cols) != "active":  # PROVISIONAL-vs-ACTIVE (#20): exclude provisional (see bench_rows_for)
            continue
        date, source = cols[0], cols[1]
        _ref, wclass, _tier, m, verdict, gate, score, time_s, cost, corr, note = cols[2:13]
        if source != "bench2" or m != model:
            continue
        if season_for_date(date) != season:
            continue
        if score == "-":
            continue
        out[_ref] = {
            "score": int(score), "verdict": verdict, "gate": gate,
            "skill": wclass, "time_s": time_s, "cost_usd": cost,
            "corrections": corr, "note": note,
        }
    return out


def composite_v2(section_data):
    """§4.6a - composite for ONE model in a CLOSED season.

    `section_data`: dict[section] -> {"raw": float, "capped_while_failing":
    bool, "section_total": float} for CAPABILITY_SECTIONS this model has a
    CLOSED (lib/close_season.py) result for - i.e. one model's slice of
    `close_season.close_season(...)["sections"][section]["models"][model]`
    across every section, keyed by section id.

    Returns (composite_raw, composite_final) or (None, None) if no
    section is present. `composite_raw` is the pure-correctness v1 formula
    applied to v2 data (mean of section_correctness); `composite_final`
    adds the mean per-section efficiency delta, CLAMPED to
    +/-COMPOSITE_EFF_CAP, so efficiency alone can never invert a
    >=2*COMPOSITE_EFF_CAP=4-point composite_raw gap (worked example 4.7c).
    """
    correctness_vals = []
    deltas = []
    for section in CAPABILITY_SECTIONS:
        info = section_data.get(section)
        if info is None:
            continue
        raw = info["raw"]
        correctness = min(raw, 89) if info["capped_while_failing"] else raw
        correctness_vals.append(correctness)
        deltas.append(info["section_total"] - correctness)
    if not correctness_vals:
        return None, None
    composite_raw = sum(correctness_vals) / len(correctness_vals)
    composite_eff_delta = sum(deltas) / len(deltas)
    clamped = max(-COMPOSITE_EFF_CAP, min(COMPOSITE_EFF_CAP, composite_eff_delta))
    return composite_raw, composite_raw + clamped


def tier_label(tier_name, source, season=None):
    """Human-readable, formula-labeled tier name for display - §4.6b:
    "Frontier" alone is never printed for a v1/v2 result; every render is
    labeled by formula and, for bench2, by season, so an operator can
    never mistake a v2 (correctness +/- efficiency) row for a v1 (pure
    correctness) one at a glance."""
    if source == "bench2":
        return f"{tier_name} · v2 ({season})" if season else f"{tier_name} · v2"
    return f"{tier_name} · v1"


def rank_in_tier(models, source, season=None):
    """§4.6b - PARTITION-AWARE rank, the new, stricter public API (distinct
    from `_rank_in_tier_v1_internal` above, which `render()` still uses
    unchanged for its own v1 CLI output).

    `models`: list of dicts, each describing ONE model's already-computed
    composite in ONE partition: {"model": id, "source": "bench"|"bench2",
    "season": str|None, "composite": float, "tie_break": float
    (optional, default 0.0 - lower is better, e.g. mean time_s)}.

    `source`/`season` name the partition this call is FOR. Every record in
    `models` must match EXACTLY - this function refuses (raises
    ValueError) the instant one doesn't, rather than silently ranking a
    mixed-source or mixed-season list (the exact defect
    BENCHMARK-V2-REVIEW.md §6 flagged as "specified but untested"):
      - source=="bench" requires season is None (v1 has no season axis -
        passing one, or a record tagged with one, is itself a caller bug).
      - source=="bench2" requires an explicit season (v2 rows are only
        ever ranked within ONE season's closed cohort, never pooled across
        seasons - see BENCHMARK-V2-DESIGN.md §4.2/§4.6b).

    Returns a list of (model, composite, rank) sorted best-first (desc
    composite, asc tie_break), rank 1-based.
    """
    if source not in ("bench", "bench2"):
        raise ValueError(f"rank_in_tier: unknown source {source!r} (must be 'bench' or 'bench2')")
    if source == "bench" and season is not None:
        raise ValueError("rank_in_tier: source='bench' (v1) has no season axis - pass season=None")
    if source == "bench2" and season is None:
        raise ValueError(
            "rank_in_tier: source='bench2' requires an explicit season - v2 rows are "
            "only ever ranked within one CLOSED season's cohort, never pooled across "
            "seasons (BENCHMARK-V2-DESIGN.md §4.2/§4.6b)")
    for rec in models:
        rec_source = rec.get("source")
        rec_season = rec.get("season")
        if rec_source != source or rec_season != season:
            raise ValueError(
                f"rank_in_tier: refusing a MIXED-PARTITION list - expected every record "
                f"to be source={source!r} season={season!r}, but model={rec.get('model')!r} "
                f"is tagged source={rec_source!r} season={rec_season!r}. bench/bench2 "
                f"rows, and different bench2 seasons, must NEVER share one ranked list "
                f"(BENCHMARK-V2-DESIGN.md §4.6b, closes BENCHMARK-V2-REVIEW.md §6).")
    ordered = sorted(models, key=lambda r: (-r["composite"], r.get("tie_break", 0.0)))
    return [(r["model"], r["composite"], i) for i, r in enumerate(ordered, start=1)]


def _sum_numeric(section_scores, key):
    """Sum a numeric column across graded sections. Returns (total, n_with_data)."""
    total = 0.0
    n = 0
    for info in section_scores.values():
        v = info.get(key)
        if v in (None, "-", ""):
            continue
        try:
            total += float(v)
            n += 1
        except ValueError:
            pass
    return total, n


def _fmt_total(total, n, fmt=".1f"):
    if n == 0:
        return "-"
    if fmt == "d":
        return format(int(round(total)), "d")
    return format(total, fmt)


def render(model, tsv_path=TSV):
    rows = load_rows(tsv_path)
    sc = bench_rows_for(rows, model)

    print("=" * 78)
    print(f"MODEL-BENCHMARK SMOKE CHART -- {model}")
    print(_SMOKE_BANNER)
    print("=" * 78)
    # section | skill | grade | time_s | cost_usd | corrections (all read
    # straight from the model's appended bench rows, never recomputed).
    # AGGREGATE-N (#16): `grade` is now the MEAN over N runs; the added `runs`
    # and `±band` columns publish the smoothing signal per section so a
    # single-run number is never read as a stable multi-run average.
    hdr = f"{'section':8} {'skill':18} {'grade':6} {'runs':5} {'±band':7} {'time_s':8} {'cost_usd':9} {'corr':5}"
    print(hdr)
    print(f"{'-------':8} {'-----':18} {'-----':6} {'----':5} {'-----':7} {'------':8} {'--------':9} {'----':5}")
    for sec in ALL_SECTIONS:
        info = sc.get(sec)
        if info is None:
            print(f"{sec:8} {'-':18} {'-':6} {'-':5} {'-':7} {'-':8} {'-':9} {'-':5}")
        else:
            skill = info["skill"][:18]
            grade_str = f"{info['score']:.0f}" if info["score"] is not None else "-"
            band = info.get("score_band")
            band_str = f"±{band:.0f}" if band is not None else "n<2"
            print(f"{sec:8} {skill:18} {grade_str:<6} {info['score_n']:<5} {band_str:<7} "
                  f"{info['time_s']:<8} {info['cost_usd']:<9} {info['corrections']:<5}")
    print("-" * 78)

    # TOTALS across all graded sections (summed from the bench rows above).
    corr_total, corr_n = _sum_numeric(sc, "corrections")
    time_total, time_n = _sum_numeric(sc, "time_s")
    cost_total, cost_n = _sum_numeric(sc, "cost_usd")
    print(f"{'TOTALS':8} {'':18} {'':6} "
          f"{_fmt_total(time_total, time_n):<8} "
          f"{_fmt_total(cost_total, cost_n, fmt='.4f'):<9} "
          f"{_fmt_total(corr_total, corr_n, fmt='d'):<5}")
    print("-" * 78)

    tier, comp_or_reason = overall_tier(sc)
    # DEMOTED: labeled "SMOKE COMPOSITE", never "OVERALL TIER" — this is a
    # synthetic diagnostic, not a capability tier position (real-outcomes pivot).
    if tier is None:
        print(f"SMOKE COMPOSITE (synthetic; NOT a capability tier): {comp_or_reason}")
    elif tier in ("INVALID", "No Tier"):
        label = "INVALID" if tier == "INVALID" else "NO TIER"
        print(f"SMOKE COMPOSITE (synthetic; NOT a capability tier): {label} -- {comp_or_reason}")
    else:
        rank, total, tied = _rank_in_tier_v1_internal(rows, model, tier)
        rank_str = f"#{rank} of {total}" if rank else "unranked (composite unavailable)"
        if tied:
            # AGGREGATE-N (#16): a sub-band composite gap is a TIE, not a rank.
            rank_str += " (TIE — composite gap within the noise band; not a rank)"
        cband = composite_band(sc)
        band_str = f" ±{cband:.1f}" if cband is not None else ""
        print(f"SMOKE COMPOSITE (synthetic; NOT a capability tier): {tier} "
              f"(composite {comp_or_reason:.1f}{band_str}) -- smoke-rank {rank_str} among smoke-charted models")
    print("(capability grade/tier: see capability/grades.py — source=live actuals)")
    print("=" * 78)


def render_v2(model, season, tsv_path=TSV, seasons_dir=None):
    """bench2 (v2) tier chart for one model in one season - §4.2/§4.6a/§4.6b.

    A season that hasn't been CLOSED yet (`lib/close_season.py`) renders
    `raw`-only, clearly labeled "provisional" - never a guessed/partial
    modifier or tier (§4.2 mechanic 1). Once closed, prints the same
    section table shape as v1's `render()` plus the section_total/
    modifier columns, the composite_raw/composite_final split (§4.6a), and
    this model's rank strictly within the SAME source+season partition
    (§4.6b) - never mixed with v1 or another season's bench2 cohort.
    """
    import close_season  # local import: keeps v1's render() free of any
    # dependency on the v2 subsystem/files, mirroring "v1 unchanged".
    if seasons_dir is None:
        seasons_dir = close_season.DEFAULT_SEASONS_DIR

    rows = load_rows(tsv_path)
    sc = bench2_rows_for(rows, model, season)

    print("=" * 78)
    print(f"MODEL-BENCHMARK-V2 SMOKE CHART -- {model} -- season {season}")
    print(_SMOKE_BANNER)
    print("=" * 78)

    if not close_season.is_closed(season, seasons_dir=seasons_dir):
        print(f"season {season} is still OPEN (provisional) - no efficiency modifier "
              f"or tier yet (BENCHMARK-V2-DESIGN.md §4.2). Recorded so far (raw only):")
        hdr = f"{'section':8} {'skill':18} {'raw':6} {'time_s':8} {'cost_usd':9} {'corr':5}"
        print(hdr)
        for sec in CAPABILITY_SECTIONS:
            info = sc.get(sec)
            if info is None:
                print(f"{sec:8} {'-':18} {'-':6} {'-':8} {'-':9} {'-':5}")
            else:
                skill = info["skill"][:18]
                print(f"{sec:8} {skill:18} {info['score']:<6} {info['time_s']:<8} {info['cost_usd']:<9} {info['corrections']:<5}")
        print("=" * 78)
        return

    closed = close_season.load_closed(season, seasons_dir=seasons_dir)
    section_data = {}
    hdr = f"{'section':8} {'raw':5} {'corr.':6} {'eff%':6} {'mod':6} {'total':6}"
    print(hdr)
    for sec in CAPABILITY_SECTIONS:
        sec_payload = closed["sections"].get(sec, {}).get("models", {}).get(model)
        if sec_payload is None:
            print(f"{sec:8} {'-':5} {'-':6} {'-':6} {'-':6} {'-':6}")
            continue
        section_data[sec] = sec_payload
        eff_pct = sec_payload["eff_pct"]
        eff_str = f"{eff_pct:.0f}" if eff_pct is not None else "-"
        print(f"{sec:8} {sec_payload['raw']:<5} "
              f"{('Y' if sec_payload['capped_while_failing'] else 'n'):6} "
              f"{eff_str:6} {sec_payload['modifier']:<6.1f} {sec_payload['section_total']:<6.1f}")
    print("-" * 78)

    composite_raw, composite_final = composite_v2(section_data)
    if composite_raw is None:
        print("OVERALL TIER: not yet determined (no capability sections closed for this model/season)")
        print("=" * 78)
        return

    tier_name = tier_name_for(composite_final)
    label = tier_label(tier_name, "bench2", season)

    # Partition-aware rank among every OTHER model closed in this SAME
    # season (§4.6b) - built here (not delegated) since it needs each
    # model's own composite_v2, which in turn needs this season's closed
    # payload; never includes a v1 row or a different season's bench2 row.
    cohort_models = set()
    for sec_result in closed["sections"].values():
        cohort_models.update(sec_result.get("cohort_models", []))
    records = []
    for m in cohort_models:
        m_section_data = {}
        for sec in CAPABILITY_SECTIONS:
            payload = closed["sections"].get(sec, {}).get("models", {}).get(m)
            if payload is not None:
                m_section_data[sec] = payload
        m_raw, m_final = composite_v2(m_section_data)
        if m_final is None:
            continue
        records.append({"model": m, "source": "bench2", "season": season, "composite": m_final})
    ranked = rank_in_tier(records, "bench2", season)
    rank = next((r for _m, _c, r in ranked if _m == model), None)
    rank_str = f"#{rank} of {len(ranked)}" if rank else "unranked"

    print(f"composite_raw (pure correctness): {composite_raw:.1f}")
    print(f"composite_final (+/-{COMPOSITE_EFF_CAP:.0f} capped efficiency delta): {composite_final:.1f}")
    # DEMOTED: smoke composite, not a capability tier position (real-outcomes pivot).
    print(f"SMOKE COMPOSITE (synthetic; NOT a capability tier): {label} -- "
          f"smoke-rank {rank_str} among this season's bench2 smoke cohort")
    print("(capability grade/tier: see capability/grades.py — source=live actuals)")
    print("=" * 78)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 3 and args[1] == "--season":
        # legacy-shell-friendly alt form: tier_chart.py <model> --season <id>
        render_v2(args[0], args[2])
    elif len(args) >= 2 and "--source" in args:
        idx = args.index("--source")
        source = args[idx + 1]
        model = args[0]
        if source == "bench2":
            if "--season" not in args:
                print("usage: tier_chart.py <model> --source bench2 --season <season_id>", file=sys.stderr)
                sys.exit(2)
            season = args[args.index("--season") + 1]
            render_v2(model, season)
        else:
            render(model)
    elif len(args) == 1:
        render(args[0])
    else:
        print("usage: tier_chart.py <model>                              (v1)\n"
              "       tier_chart.py <model> --source bench2 --season <id> (v2)", file=sys.stderr)
        sys.exit(2)
