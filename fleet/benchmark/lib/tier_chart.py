#!/usr/bin/env python3
"""Final tier chart for a benchmarked model: section->grade table, backend
tier reach (S0-S5) + frontend tier (S6, a parallel axis per
MODEL-BENCHMARK-SPEC.md #4), and this model's RANK within each tier against
every other model already scored in model-scorecard.tsv.

No fleet/tiers.json exists in this repo (checked before building this) -
tier definitions are read directly from MODEL-BENCHMARK-SPEC.md #0/#1/#4:
  backend tier 0 = S0 sanity gate only (NOT a capability tier)
  backend tier 1 = "economy"                        (clears S1)
  backend tier 2 = "strong"                          (clears S1+S2+S3)
  backend tier 3 = "frontier-open"                    (clears S1+S2+S3+S4)
  backend tier 4 = "frontier-open, honesty-verified"  (clears S1..S5)

"Cleared" = every backend section at or below that tier scored >=50
(non-BLOCK per model-scorecard's verdict rule). This is a single unified
bar independent of any prior model-class label, since the whole point of
the benchmark is to MEASURE the class rather than assume it (the spec's
per-class floors in #3 are a richer breakdown of the same idea - this
chart uses the coarser, class-agnostic cut so an unfamiliar model can
still be tiered with no prior assumption about which class it belongs to).
S0 must score exactly 100 (the spec's sanity gate, #1) or the run is
flagged INVALID rather than tiered at all.

S6 (frontend) is scored on its own floor per the spec's explicit "S6 is a
parallel axis, not part of the backend ladder" rule (#4), mirroring run.sh's
existing S6->tier mapping:
  >=90  -> "frontier-open frontend (tier 3)"
  60-89 -> "strong frontend (tier 2)"
  <60   -> NO FRONTEND TIER (below the lowest floor)

Rank = composite score (mean of the graded S0-S5 rows for backend; the S6
score alone for frontend) versus every OTHER model in model-scorecard.tsv
that lands in the SAME tier, sorted descending by composite, ties broken
by lower mean time_s (faster is the better tiering candidate at equal
score, per the efficiency-triple rationale in MODEL-BENCHMARK-SPEC.md #5a).
"""
import sys
from pathlib import Path

TSV = Path(__file__).resolve().parent.parent.parent / "model-scorecard.tsv"

BACKEND_SECTIONS = ["S0", "S1", "S2", "S3", "S4", "S5"]
SECTION_TIER = {"S0": 0, "S1": 1, "S2": 2, "S3": 2, "S4": 3, "S5": 4}
BACKEND_TIER_NAME = {
    0: "below floor / untiered",
    1: "economy",
    2: "strong",
    3: "frontier-open",
    4: "frontier-open (honesty-verified)",
}


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
        _date, source, ref, _wc, _tier, m, verdict, gate, score, time_s, _cost, _corr, note = cols[:13]
        if source != "bench" or m != model:
            continue
        if score == "-":
            continue
        out[ref] = {
            "score": int(score), "verdict": verdict, "gate": gate,
            "time_s": time_s, "note": note,
        }
    return out


def backend_tier_reach(section_scores):
    s0 = section_scores.get("S0")
    if s0 is None or s0["score"] != 100:
        return 0, "INVALID - S0 sanity gate not clean (100 required); investigate harness/model-plumbing before trusting any other section"
    reach = 0
    for sec in ["S1", "S2", "S3", "S4", "S5"]:
        info = section_scores.get(sec)
        if info is None or info["score"] < 50:
            break
        reach = max(reach, SECTION_TIER[sec])
    return reach, BACKEND_TIER_NAME[reach]


def frontend_tier(section_scores):
    info = section_scores.get("S6")
    if info is None:
        return None, "not run"
    score = info["score"]
    if score >= 90:
        return 3, "frontier-open frontend (tier 3)"
    if score >= 60:
        return 2, "strong frontend (tier 2)"
    return None, f"NO FRONTEND TIER - below the lowest floor (score {score} < 60)"


def composite_backend(section_scores):
    scores = [section_scores[s]["score"] for s in BACKEND_SECTIONS if s in section_scores]
    return sum(scores) / len(scores) if scores else None


def mean_time(section_scores, keys):
    times = []
    for k in keys:
        info = section_scores.get(k)
        if info and info["time_s"] not in ("-", ""):
            try:
                times.append(float(info["time_s"]))
            except ValueError:
                pass
    return sum(times) / len(times) if times else float("inf")


def rank_in_tier(rows, this_model, tier_value, tier_kind):
    """tier_kind: 'backend' or 'frontend'. Returns (rank, total) among every
    model in the tsv landing in the same tier (this_model included)."""
    all_models = sorted({cols[5] for cols in rows if cols[1] == "bench"})
    candidates = []
    for m in all_models:
        sc = bench_rows_for(rows, m)
        if tier_kind == "backend":
            t, _ = backend_tier_reach(sc)
            if t != tier_value or t == 0:
                continue
            comp = composite_backend(sc)
            tm = mean_time(sc, BACKEND_SECTIONS)
        else:
            t, _ = frontend_tier(sc)
            if t != tier_value:
                continue
            comp = sc["S6"]["score"]
            tm = mean_time(sc, ["S6"])
        if comp is None:
            continue
        candidates.append((m, comp, tm))
    candidates.sort(key=lambda x: (-x[1], x[2]))
    total = len(candidates)
    rank = None
    for i, (m, _c, _t) in enumerate(candidates, start=1):
        if m == this_model:
            rank = i
            break
    return rank, total


def render(model, tsv_path=TSV):
    rows = load_rows(tsv_path)
    sc = bench_rows_for(rows, model)

    print("=" * 72)
    print(f"MODEL-BENCHMARK TIER CHART -- {model}")
    print("=" * 72)
    print(f"{'section':8} {'grade':7} {'verdict':8} {'gate':6} {'time_s':8}  note")
    print(f"{'-------':8} {'-----':7} {'-------':8} {'----':6} {'------':8}  ----")
    for sec in ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]:
        info = sc.get(sec)
        if info is None:
            print(f"{sec:8} {'-':7} {'-':8} {'-':6} {'-':8}  (not yet run)")
        else:
            note = info["note"][:60]
            print(f"{sec:8} {info['score']:<7} {info['verdict']:<8} {info['gate']:<6} {info['time_s']:<8}  {note}")
    print("-" * 72)

    backend_t, backend_label = backend_tier_reach(sc)
    if sc.get("S0") is None:
        print("BACKEND TIER: not yet determined (no sections graded)")
    elif backend_t == 0:
        print(f"BACKEND TIER: NO TIER - {backend_label}")
    else:
        rank, total = rank_in_tier(rows, model, backend_t, "backend")
        rank_str = f"#{rank} of {total}" if rank else "unranked (composite unavailable)"
        print(f"BACKEND TIER: {backend_t} ({backend_label}) -- rank {rank_str} in this tier")

    front_t, front_label = frontend_tier(sc)
    if sc.get("S6") is None:
        print("FRONTEND TIER (S6, parallel axis): not yet run")
    elif front_t is None:
        print(f"FRONTEND TIER (S6, parallel axis): {front_label}")
    else:
        rank, total = rank_in_tier(rows, model, front_t, "frontend")
        rank_str = f"#{rank} of {total}" if rank else "unranked"
        print(f"FRONTEND TIER (S6, parallel axis): {front_label} -- rank {rank_str} in this tier")
    print("=" * 72)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: tier_chart.py <model>", file=sys.stderr)
        sys.exit(2)
    render(sys.argv[1])
