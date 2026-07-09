#!/usr/bin/env python3
"""promote.py — the provisional->active PROMOTION GATE (v1) for
BENCH-PROVISIONAL-SCORING (#20). Design of record:
fleet/scratch/pivot-implementation-plan.md §2 (+ §8 Q5 for the thresholds).

A test unit (a benchmark section OR a replayed red — see benchmark/units.tsv)
is born `provisional`: its scorecard rows are COLLECTED but EXCLUDED from every
live grade/tier/assign pick (capability/grades.py, benchmark/lib/tier_chart.py,
model-scorecard.sh render all gate on `stage == active`). This tool is the ONE
place a unit earns `active` — and only when it PROVES it discriminates.

GATE v1 (deliberately simple; #16/#17 replace it with a CI-aware discrimination
test later — plan §5, "do not block #20 on #17"):

  a provisional unit promotes to `active` IFF, over the models that have run it,
      score_spread = max(per-model score) - min(per-model score)  >=  SPREAD_MIN
    AND
      distinct_models  >=  DISTINCT_MODELS_MIN (K)

The score_spread test is the local analog of the pools ADR's
decision-differentiation gate and capability/selftest.py's proof-of-effect: a
SATURATED unit (every model ~100, spread ~0) carries no ranking signal and
provably CANNOT promote — which is the whole point of the pivot (5/7 synthetic
sections saturate). A unit only one model has run also cannot promote (nothing
to differentiate between yet).

THRESHOLDS (plan §8 Q5: "start deliberately low — mirror the pools gate's
10-15% 'prove non-zero effect' stance — tighten as coverage grows; operator to
set the first X"). Started low here and overridable per-invocation via
--spread-min / --k:
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
FLEET_DIR = BENCH_DIR.parent
DEFAULT_UNITS = BENCH_DIR / "units.tsv"
DEFAULT_TSV = FLEET_DIR / "model-scorecard.tsv"

# plan §8 Q5 — start low, tighten as coverage grows.
SPREAD_MIN = 15.0            # points on the 0..100 scale (mirrors pools gate's 10-15%)
DISTINCT_MODELS_MIN = 2      # K: need >= 2 distinct models to have anything to differentiate

# Verdict -> score for units whose rows carry no numeric section score (e.g.
# replayed reds, #25: check_cmd exit 0 => MERGE, non-zero => BLOCK).
_VERDICT_SCORE = {"MERGE": 100.0, "FIXES": 50.0, "BLOCK": 0.0}


# ---------------------------------------------------------------------------
# units.tsv registry I/O
# ---------------------------------------------------------------------------
def load_units(path: Path | str = DEFAULT_UNITS) -> list[dict]:
    """Parse units.tsv -> list of {unit_id, kind, stage, promoted_on}. The
    `unit_id\\tkind\\tstage\\tpromoted_on` header row and any #-comment/blank
    line are skipped."""
    path = Path(path)
    units: list[dict] = []
    if not path.exists():
        return units
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if cols[0] == "unit_id":            # header
            continue
        if len(cols) < 3:
            continue
        unit_id, kind, stage = cols[0], cols[1], cols[2]
        promoted_on = cols[3] if len(cols) >= 4 else "-"
        units.append({"unit_id": unit_id, "kind": kind, "stage": stage,
                      "promoted_on": promoted_on})
    return units


def save_units(units: list[dict], path: Path | str = DEFAULT_UNITS) -> None:
    """Rewrite units.tsv preserving the leading #-comment block and header."""
    path = Path(path)
    preamble: list[str] = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith("#"):
                preamble.append(line)
            else:
                break
    lines = list(preamble)
    lines.append("unit_id\tkind\tstage\tpromoted_on")
    for u in units:
        lines.append(f"{u['unit_id']}\t{u['kind']}\t{u['stage']}\t{u['promoted_on']}")
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# ledger -> per-model score for a unit
# ---------------------------------------------------------------------------
def _row_belongs_to_unit(ref: str, unit_id: str) -> bool:
    """A ledger row belongs to a unit if its `ref` IS the unit id (live bench
    rows and replayed reds both write ref==unit_id, e.g. "S3" / a red's id) or
    is a `<unit_id>-<n>` sub-ref (the synthetic fixtures use "S3-01" etc.)."""
    return ref == unit_id or ref.startswith(unit_id + "-")


def _row_score(score: str, verdict: str) -> float | None:
    """Numeric section score if present, else the verdict mapping (reds), else
    None (an ungraded/`-`-both row contributes nothing)."""
    if score.isdigit():
        return float(score)
    return _VERDICT_SCORE.get(verdict)


def unit_scores(rows: list[list[str]], unit_id: str) -> dict[str, float]:
    """Per-model representative score for `unit_id` = the MEAN of that model's
    graded scores on the unit. `rows` are raw split-on-tab column lists (any
    stage — promotion looks at the unit's COLLECTED provisional data). Columns
    follow model-scorecard.tsv: ref=col3, model=col6, verdict=col7, score=col9."""
    acc: dict[str, list[float]] = {}
    for cols in rows:
        if len(cols) < 9:
            continue
        ref, model, verdict, score = cols[2], cols[5], cols[6], cols[8]
        if not _row_belongs_to_unit(ref, unit_id):
            continue
        s = _row_score(score, verdict)
        if s is None:
            continue
        acc.setdefault(model, []).append(s)
    return {m: sum(v) / len(v) for m, v in acc.items()}


def load_rows(tsv_path: Path | str = DEFAULT_TSV) -> list[list[str]]:
    tsv_path = Path(tsv_path)
    if not tsv_path.exists():
        return []
    return [ln.split("\t") for ln in tsv_path.read_text().splitlines()
            if ln and not ln.startswith("#")]


# ---------------------------------------------------------------------------
# THE GATE (pure function — unit-testable, no I/O)
# ---------------------------------------------------------------------------
def evaluate_gate(scores_by_model: dict[str, float],
                  spread_min: float = SPREAD_MIN,
                  k: int = DISTINCT_MODELS_MIN) -> tuple[bool, str]:
    """v1 promotion decision for one unit. Returns (should_promote, reason).

    Promotes IFF distinct_models >= k AND score_spread >= spread_min. A
    saturated unit (spread ~0) or a single-model unit CANNOT promote — this is
    the regression-guard for the whole pivot (plan §2 acceptance)."""
    n = len(scores_by_model)
    if n < k:
        return False, (f"NO: only {n} distinct model(s) have run this unit "
                       f"(need >= {k}) — nothing to differentiate yet")
    vals = list(scores_by_model.values())
    spread = max(vals) - min(vals)
    if spread < spread_min:
        return False, (f"NO: score_spread {spread:.1f} < SPREAD_MIN {spread_min:.1f} "
                       f"across {n} models — SATURATED / non-discriminating "
                       f"(the exact case #20 must not promote)")
    return True, (f"YES: score_spread {spread:.1f} >= {spread_min:.1f} over {n} "
                  f"models — this unit discriminates")


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
def promote(unit_id: str, *, tsv_path: Path | str = DEFAULT_TSV,
            units_path: Path | str = DEFAULT_UNITS,
            spread_min: float = SPREAD_MIN, k: int = DISTINCT_MODELS_MIN,
            apply: bool = False) -> dict:
    """Evaluate (and, if apply=True and the gate passes, persist) a unit's
    promotion. Returns a result dict {unit_id, found, current_stage, scores,
    promote, reason, applied}."""
    units = load_units(units_path)
    unit = next((u for u in units if u["unit_id"] == unit_id), None)
    scores = unit_scores(load_rows(tsv_path), unit_id)
    should, reason = evaluate_gate(scores, spread_min, k)
    result = {"unit_id": unit_id, "found": unit is not None,
              "current_stage": unit["stage"] if unit else None,
              "scores": scores, "promote": should, "reason": reason,
              "applied": False}
    if unit is None:
        result["reason"] = f"NO: unit {unit_id!r} not in {Path(units_path).name}"
        result["promote"] = False
        return result
    if unit["stage"] == "active":
        result["reason"] = f"already active (promoted_on={unit['promoted_on']}) — no-op"
        result["promote"] = False
        return result
    if should and apply:
        unit["stage"] = "active"
        unit["promoted_on"] = _date.today().isoformat()
        save_units(units, units_path)
        result["applied"] = True
    return result


def _fmt_scores(scores: dict[str, float]) -> str:
    if not scores:
        return "(no graded rows yet)"
    return ", ".join(f"{m}={s:.0f}" for m, s in sorted(scores.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", help="unit_id to evaluate/promote (see benchmark/units.tsv)")
    ap.add_argument("--list", action="store_true", help="list all units + their current discrimination")
    ap.add_argument("--apply", action="store_true",
                    help="actually flip the unit to active when the gate passes (default: dry-run report only)")
    ap.add_argument("--spread-min", type=float, default=SPREAD_MIN, help=f"min score spread (default {SPREAD_MIN})")
    ap.add_argument("--k", type=int, default=DISTINCT_MODELS_MIN, help=f"min distinct models (default {DISTINCT_MODELS_MIN})")
    ap.add_argument("--tsv", default=str(DEFAULT_TSV))
    ap.add_argument("--units", default=str(DEFAULT_UNITS))
    args = ap.parse_args(argv)

    if args.list:
        rows = load_rows(args.tsv)
        for u in load_units(args.units):
            scores = unit_scores(rows, u["unit_id"])
            should, reason = evaluate_gate(scores, args.spread_min, args.k)
            print(f"{u['unit_id']:24s} {u['kind']:8s} stage={u['stage']:11s} "
                  f"promoted_on={u['promoted_on']:12s} | {reason}")
            print(f"    scores: {_fmt_scores(scores)}")
        return 0

    if not args.unit:
        ap.error("pass --unit <id> (or --list)")

    r = promote(args.unit, tsv_path=args.tsv, units_path=args.units,
                spread_min=args.spread_min, k=args.k, apply=args.apply)
    print(f"unit={r['unit_id']}  found={r['found']}  current_stage={r['current_stage']}")
    print(f"scores: {_fmt_scores(r['scores'])}")
    print(f"gate:   {r['reason']}")
    if r["applied"]:
        print(f"APPLIED: {r['unit_id']} promoted provisional -> active.")
    elif r["promote"] and not args.apply:
        print("(dry-run — re-run with --apply to persist this promotion)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
