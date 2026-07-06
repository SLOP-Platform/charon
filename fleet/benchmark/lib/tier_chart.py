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
"""
import sys
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


def bench_rows_for(rows, model):
    out = {}
    for cols in rows:
        _date, source, ref, wclass, _tier, m, verdict, gate, score, time_s, cost, corr, note = cols[:13]
        if source != "bench" or m != model:
            continue
        if score == "-":
            continue
        out[ref] = {
            "score": int(score), "verdict": verdict, "gate": gate,
            "skill": wclass, "time_s": time_s, "cost_usd": cost,
            "corrections": corr, "note": note,
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


def rank_in_tier(rows, this_model, tier_name):
    """Rank among every OTHER model in the tsv landing in the same named
    tier (this_model included), sorted by composite desc, tie-broken by
    mean time_s asc. Returns (rank, total)."""
    all_models = sorted({cols[5] for cols in rows if cols[1] == "bench"})
    candidates = []
    for m in all_models:
        sc = bench_rows_for(rows, m)
        t, comp = overall_tier(sc)
        if t != tier_name or comp is None or isinstance(comp, str):
            continue
        tm = mean_time(sc)
        candidates.append((m, comp, tm))
    candidates.sort(key=lambda x: (-x[1], x[2]))
    total = len(candidates)
    rank = None
    for i, (m, _c, _t) in enumerate(candidates, start=1):
        if m == this_model:
            rank = i
            break
    return rank, total


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
    print(f"MODEL-BENCHMARK TIER CHART -- {model}")
    print("=" * 78)
    # section | skill | grade | time_s | cost_usd | corrections (all read
    # straight from the model's appended bench rows, never recomputed).
    hdr = f"{'section':8} {'skill':18} {'grade':6} {'time_s':8} {'cost_usd':9} {'corr':5}"
    print(hdr)
    print(f"{'-------':8} {'-----':18} {'-----':6} {'------':8} {'--------':9} {'----':5}")
    for sec in ALL_SECTIONS:
        info = sc.get(sec)
        if info is None:
            print(f"{sec:8} {'-':18} {'-':6} {'-':8} {'-':9} {'-':5}")
        else:
            skill = info["skill"][:18]
            print(f"{sec:8} {skill:18} {info['score']:<6} {info['time_s']:<8} {info['cost_usd']:<9} {info['corrections']:<5}")
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
    if tier is None:
        print(f"OVERALL TIER: {comp_or_reason}")
    elif tier in ("INVALID", "No Tier"):
        label = "INVALID" if tier == "INVALID" else "NO TIER"
        print(f"OVERALL TIER: {label} -- {comp_or_reason}")
    else:
        rank, total = rank_in_tier(rows, model, tier)
        rank_str = f"#{rank} of {total}" if rank else "unranked (composite unavailable)"
        print(f"OVERALL TIER: {tier} (composite {comp_or_reason:.1f}) -- rank {rank_str} of models in this tier")
    print("=" * 78)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: tier_chart.py <model>", file=sys.stderr)
        sys.exit(2)
    render(sys.argv[1])
