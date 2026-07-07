#!/usr/bin/env python3
"""benchmark-v2 SCORING self-test (BENCHMARK-V2-DESIGN.md §4.2-§4.8, as
amended by BENCHMARK-V2-REVIEW.md's adversarial pass).

Proves, entirely against SCRATCH copies (a temp dir standing in for
`model-scorecard.tsv` and `benchmark/state/seasons/`) - NEVER the real
`model-scorecard.tsv` or `benchmark/runs/` tree:

  1. Field-freeze reproducibility (§4.2): closing a season computes every
     row in its cohort ONCE; a model added to a LATER season never
     mutates an EARLIER, already-closed season's numbers, and
     `close_season()` refuses to recompute an already-closed season
     without an explicit `force=True`.
  2. Tie mid-rank (§4.3a): an N-way tie centers at percentile 50 (not 0),
     and an all-tied ("flat-sub $0 cost") field is neutral (50) for
     everyone - not a drag toward the bottom.
  3. MIN_FIELD_SIZE=4 gating (§4.3b): a cohort smaller than 4 gets
     modifier=0 for every model in it, regardless of who's actually
     faster/cheaper (closes the "penalized for running first" bug).
  4. COMPOSITE_EFF_CAP=+/-2 cannot invert a >=4-point composite_raw gap
     (§4.6a) - reproduces worked example 4.7c exactly.
  5. bench2/v1 partition isolation (§4.6b): a `source=="bench"` row never
     enters a bench2 cohort computed from the TSV; `rank_in_tier` refuses
     a mixed-source or mixed-season list.

Usage: python3 selftest/efficiency_selftest.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH_DIR = HERE.parent
LIB_DIR = BENCH_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

import close_season  # noqa: E402
import efficiency  # noqa: E402
import tier_chart  # noqa: E402

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


# --------------------------------------------------------------------------
# Part 1: field-freeze reproducibility (§4.2, worked example 4.7a)
# --------------------------------------------------------------------------

def _write_tsv(path: Path, rows: list[str]) -> None:
    header = (
        "# scratch model-scorecard.tsv - efficiency_selftest.py, never the real ledger\n"
        "# date\tsource\tref\twork_class\ttier\tmodel\tverdict\tgate\tscore\ttime_s\tcost_usd\tcorrections\tnote\ttokens_in\ttokens_out\n"
    )
    path.write_text(header + "\n".join(rows) + ("\n" if rows else ""))


def _bench2_row(date, section, model, score, time_s, cost_usd, tokens_in, tokens_out,
                 gate="pass", verdict="MERGE", note="ok"):
    return (f"{date}\tbench2\t{section}\ttests\t1\t{model}\t{verdict}\t{gate}\t{score}\t"
            f"{time_s}\t{cost_usd}\t0\t{note}\t{tokens_in}\t{tokens_out}")


def part1_field_freeze_reproducibility() -> None:
    with tempfile.TemporaryDirectory(prefix="eff-selftest-freeze-") as td:
        tmp = Path(td)
        tsv = tmp / "model-scorecard.tsv"
        seasons_dir = tmp / "seasons"

        # W27 (2026-06-29 .. 2026-07-05): 3-model cohort on S4, matching
        # example 4.7a - deliberately BELOW MIN_FIELD_SIZE(4) so everyone's
        # modifier is 0 (a plain "not enough data" outcome, not an error).
        w27_date = "2026-07-01"
        w27_rows = [
            _bench2_row(w27_date, "S4", "glm-5.2", 85, 20.0, 0.001, 500, 100),
            _bench2_row(w27_date, "S4", "gpt-5.4", 90, 15.0, 0.002, 600, 150),
            _bench2_row(w27_date, "S4", "deepseek-v4-pro", 87, 18.0, 0.0015, 550, 120),
        ]
        _write_tsv(tsv, w27_rows)

        season_w27 = close_season.season_id_for_date(w27_date)
        payload1 = close_season.close_season(season_w27, tsv_path=tsv, seasons_dir=seasons_dir)
        s4_w27 = payload1["sections"]["S4"]
        check(s4_w27["cohort_size"] == 3, f"W27 S4 cohort should be 3, got {s4_w27['cohort_size']}")
        for m, info in s4_w27["models"].items():
            check(info["modifier"] == 0.0,
                  f"W27 (cohort=3 < MIN_FIELD_SIZE=4) should give modifier=0 for {m}, got {info['modifier']}")
            check(info["section_total"] == info["raw"],
                  f"W27 modifier=0 means section_total should equal raw for {m}: {info}")
        w27_scores_before = {m: info["section_total"] for m, info in s4_w27["models"].items()}

        # W28: a 4th, much faster/cheaper model runs S4 in a DIFFERENT
        # (later) season - must NOT touch W27's already-closed numbers at
        # all, even though it's the same section id.
        w28_date = "2026-07-08"
        _write_tsv(tsv, w27_rows + [
            _bench2_row(w28_date, "S4", "fast-cheap-model", 88, 5.0, 0.0002, 100, 20),
        ])
        # re-closing W27 without force must be refused (immutability).
        raised = False
        try:
            close_season.close_season(season_w27, tsv_path=tsv, seasons_dir=seasons_dir)
        except RuntimeError:
            raised = True
        check(raised, "close_season() must refuse to recompute an already-CLOSED season without force=True")

        reloaded = close_season.load_closed(season_w27, seasons_dir=seasons_dir)
        for m, before in w27_scores_before.items():
            after = reloaded["sections"]["S4"]["models"][m]["section_total"]
            check(after == before,
                  f"W27's closed section_total for {m} must be UNCHANGED after a later season's "
                  f"model appeared in the TSV (reproducibility, §4.2) - was {before}, now {after}")

        # W28 is a genuinely separate cohort (only the one model ran S4 in
        # W28) - closing it must not require or reference W27 at all.
        season_w28 = close_season.season_id_for_date(w28_date)
        payload2 = close_season.close_season(season_w28, tsv_path=tsv, seasons_dir=seasons_dir)
        check("S4" in payload2["sections"], "W28 close should see its own S4 cohort")
        check(payload2["sections"]["S4"]["cohort_size"] == 1,
              f"W28's S4 cohort should be exactly the 1 model that ran in W28, got "
              f"{payload2['sections']['S4']['cohort_size']}")


# --------------------------------------------------------------------------
# Part 2: mid-rank ties + flat-field neutrality (§4.3a, example 4.7b)
# --------------------------------------------------------------------------

def part2_mid_rank_ties() -> None:
    # 5-model cohort, cost_usd: A=0.02, B=C=D=0.05 (3-way tie), E=0.09.
    values = {"A": 0.02, "B": 0.05, "C": 0.05, "D": 0.05, "E": 0.09}
    pct = efficiency.mid_rank_percentile(values)
    check(pct["B"] == 50.0, f"3-way tie should land at percentile 50 (mid-rank), got {pct['B']}")
    check(pct["C"] == 50.0 and pct["D"] == 50.0, f"all three tied models should be 50: {pct}")
    check(pct["A"] == 100.0, f"uniquely-best (lowest cost) should be 100, got {pct['A']}")
    check(pct["E"] == 0.0, f"uniquely-worst should be 0, got {pct['E']}")

    # flat-sub $0 cost - every model identical -> neutral 50 for everyone,
    # NOT 0 (the pre-amendment defect BENCHMARK-V2-REVIEW.md §2b found).
    flat = {"m1": 0.0, "m2": 0.0, "m3": 0.0, "m4": 0.0}
    flat_pct = efficiency.mid_rank_percentile(flat)
    check(all(v == 50.0 for v in flat_pct.values()),
          f"an all-tied (flat-sub $0) field must be neutral (50) for every model, got {flat_pct}")


# --------------------------------------------------------------------------
# Part 3: MIN_FIELD_SIZE gating (§4.3b)
# --------------------------------------------------------------------------

def part3_min_field_size() -> None:
    # cohort of 2: one model strictly faster/cheaper/fewer-tokens than the
    # other - would be a full-swing 0/100 coin flip without the gate.
    rows = [
        {"model": "first", "raw": 87, "capped_while_failing": False,
         "tokens": 1000, "time_s": 30.0, "cost_usd": 0.01},
        {"model": "second", "raw": 87, "capped_while_failing": False,
         "tokens": 200, "time_s": 5.0, "cost_usd": 0.002},
    ]
    result = efficiency.compute_section_cohort(rows)
    check(len(result) == 2, f"expected 2 models in the cohort result, got {len(result)}")
    for m, info in result.items():
        check(info["modifier"] == 0.0,
              f"cohort size 2 < MIN_FIELD_SIZE={efficiency.MIN_FIELD_SIZE} must force modifier=0 for "
              f"{m} regardless of relative efficiency, got {info['modifier']}")
        check(info["section_total"] == info["raw"],
              f"with modifier=0, section_total must equal raw for {m}: {info}")

    # cohort of exactly MIN_FIELD_SIZE=4 - modifier IS allowed to move now.
    big_rows = [
        {"model": f"m{i}", "raw": 80, "capped_while_failing": False,
         "tokens": 1000 - i * 100, "time_s": 30.0, "cost_usd": 0.01}
        for i in range(4)
    ]
    big_result = efficiency.compute_section_cohort(big_rows)
    mods = {m: info["modifier"] for m, info in big_result.items()}
    check(any(v != 0.0 for v in mods.values()),
          f"cohort size == MIN_FIELD_SIZE=4 with real differentiation should allow a nonzero "
          f"modifier for at least one model, got all zero: {mods}")


# --------------------------------------------------------------------------
# Part 4: COMPOSITE_EFF_CAP cannot invert a >=4pt correctness gap (§4.6a,
# worked example 4.7c)
# --------------------------------------------------------------------------

def part4_composite_eff_cap() -> None:
    # P: composite_raw=87, every section modifier at the extreme +5.
    p_sections = {
        s: {"raw": 87, "capped_while_failing": False, "section_total": 92}
        for s in tier_chart.CAPABILITY_SECTIONS
    }
    # Q: composite_raw=91, every section modifier at the extreme -5.
    q_sections = {
        s: {"raw": 91, "capped_while_failing": False, "section_total": 86}
        for s in tier_chart.CAPABILITY_SECTIONS
    }
    p_raw, p_final = tier_chart.composite_v2(p_sections)
    q_raw, q_final = tier_chart.composite_v2(q_sections)
    check(p_raw == 87.0, f"P composite_raw should be 87, got {p_raw}")
    check(q_raw == 91.0, f"Q composite_raw should be 91, got {q_raw}")
    check(p_final == 89.0, f"P composite_final should clamp to 87+2=89, got {p_final}")
    check(q_final == 89.0, f"Q composite_final should clamp to 91-2=89, got {q_final}")
    check(q_final >= p_final,
          f"the MORE correct model (Q, raw={q_raw}) must never end up with a LOWER "
          f"composite_final than the less correct one (P, raw={p_raw}) for a >=4pt gap: "
          f"P_final={p_final} Q_final={q_final}")

    # Near-tie (gap=0): efficiency SHOULD be allowed to decide, per design.
    tie_a_sections = {s: {"raw": 88.5, "capped_while_failing": False, "section_total": 93.5}
                       for s in tier_chart.CAPABILITY_SECTIONS}
    tie_b_sections = {s: {"raw": 88.5, "capped_while_failing": False, "section_total": 87.5}
                       for s in tier_chart.CAPABILITY_SECTIONS}
    _a_raw, a_final = tier_chart.composite_v2(tie_a_sections)
    _b_raw, b_final = tier_chart.composite_v2(tie_b_sections)
    check(a_final == 90.5, f"near-tie model A (clamped +2) should reach 90.5 (Frontier), got {a_final}")
    check(b_final == 87.5, f"near-tie model B (unclamped -1) should reach 87.5 (Strong), got {b_final}")
    check(tier_chart.tier_name_for(a_final) == "Frontier", f"A should tier Frontier at {a_final}")
    check(tier_chart.tier_name_for(b_final) == "Strong", f"B should tier Strong at {b_final}")


# --------------------------------------------------------------------------
# Part 5: bench2/v1 partition isolation (§4.6b)
# --------------------------------------------------------------------------

def part5_partition_isolation() -> None:
    with tempfile.TemporaryDirectory(prefix="eff-selftest-partition-") as td:
        tmp = Path(td)
        tsv = tmp / "model-scorecard.tsv"
        # MIX real v1 (source=bench) and v2 (source=bench2) rows for the
        # SAME model/section - a v1 row must never leak into a bench2
        # cohort's percentile field.
        _write_tsv(tsv, [
            "2026-07-01\tbench\tS4\ttests\t3\tsneaky-v1-row\tMERGE\tpass\t100\t1.0\t0.0001\t0\tv1 row, must be excluded",
            _bench2_row("2026-07-01", "S4", "real-bench2-a", 80, 20.0, 0.01, 500, 100),
            _bench2_row("2026-07-01", "S4", "real-bench2-b", 82, 22.0, 0.011, 520, 110),
            _bench2_row("2026-07-01", "S4", "real-bench2-c", 84, 18.0, 0.009, 480, 90),
            _bench2_row("2026-07-01", "S4", "real-bench2-d", 86, 16.0, 0.008, 460, 80),
        ])
        rows = close_season.bench2_rows_from_tsv(tsv)
        models_seen = {r["model"] for r in rows}
        check("sneaky-v1-row" not in models_seen,
              f"bench2_rows_from_tsv must NEVER admit a source=='bench' row, got models: {models_seen}")
        check(models_seen == {"real-bench2-a", "real-bench2-b", "real-bench2-c", "real-bench2-d"},
              f"bench2_rows_from_tsv should see exactly the 4 real bench2 rows, got {models_seen}")

        season = close_season.season_id_for_date("2026-07-01")
        payload = close_season.close_season(season, tsv_path=tsv, seasons_dir=tmp / "seasons")
        cohort_models = payload["sections"]["S4"]["cohort_models"]
        check("sneaky-v1-row" not in cohort_models,
              f"close_season's computed cohort must never include a v1 row, got {cohort_models}")
        check(len(cohort_models) == 4, f"cohort should be exactly the 4 bench2 models, got {cohort_models}")

    # rank_in_tier must refuse a mixed-source list.
    mixed_source = [
        {"model": "a", "source": "bench", "season": None, "composite": 90},
        {"model": "b", "source": "bench2", "season": "2026-W28", "composite": 91},
    ]
    raised = False
    try:
        tier_chart.rank_in_tier(mixed_source, "bench", season=None)
    except ValueError:
        raised = True
    check(raised, "rank_in_tier must raise ValueError on a mixed-source list")

    # rank_in_tier must refuse a mixed-season (both bench2) list.
    mixed_season = [
        {"model": "a", "source": "bench2", "season": "2026-W27", "composite": 90},
        {"model": "b", "source": "bench2", "season": "2026-W28", "composite": 91},
    ]
    raised2 = False
    try:
        tier_chart.rank_in_tier(mixed_season, "bench2", season="2026-W28")
    except ValueError:
        raised2 = True
    check(raised2, "rank_in_tier must raise ValueError on a mixed-season (both bench2) list")

    # rank_in_tier must refuse source='bench' called with a season set, and
    # source='bench2' called with NO season.
    raised3 = False
    try:
        tier_chart.rank_in_tier([], "bench", season="2026-W28")
    except ValueError:
        raised3 = True
    check(raised3, "rank_in_tier must raise when source='bench' is given a season")

    raised4 = False
    try:
        tier_chart.rank_in_tier([], "bench2", season=None)
    except ValueError:
        raised4 = True
    check(raised4, "rank_in_tier must raise when source='bench2' is given no season")

    # A CLEAN, single-partition list ranks normally (no false positive).
    clean = [
        {"model": "x", "source": "bench2", "season": "2026-W28", "composite": 80},
        {"model": "y", "source": "bench2", "season": "2026-W28", "composite": 95},
        {"model": "z", "source": "bench2", "season": "2026-W28", "composite": 88},
    ]
    ranked = tier_chart.rank_in_tier(clean, "bench2", season="2026-W28")
    check(ranked[0][0] == "y" and ranked[0][2] == 1,
          f"highest composite (y=95) should rank #1, got {ranked}")
    check(ranked[-1][0] == "x", f"lowest composite (x=80) should rank last, got {ranked}")


def main() -> None:
    part1_field_freeze_reproducibility()
    part2_mid_rank_ties()
    part3_min_field_size()
    part4_composite_eff_cap()
    part5_partition_isolation()

    if failures:
        print(f"BENCHMARK-V2 SCORING SELF-TEST FAILURES ({len(failures)}):")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("BENCHMARK-V2 SCORING SELF-TEST PASS: season close is computed once and never "
          "mutates after close (field-freeze reproducibility); mid-rank percentile centers "
          "ties/flat fields at 50, not 0; MIN_FIELD_SIZE=4 gates the modifier to 0 for "
          "small cohorts; COMPOSITE_EFF_CAP=+/-2 cannot invert a >=4-point composite_raw "
          "gap while still letting efficiency decide a genuine near-tie; bench2/v1 (and "
          "cross-season bench2) partitions are never mixed in one cohort or one ranked "
          "list. All against scratch copies - the real model-scorecard.tsv/benchmark/runs/ "
          "tree was never touched.")


if __name__ == "__main__":
    main()
