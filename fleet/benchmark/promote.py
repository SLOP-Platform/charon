#!/usr/bin/env python3
"""promote.py — the provisional->active PROMOTION GATE (v2) for
BENCH-PROVISIONAL-SCORING (#20) + EVAL-PROMOTION-GATE (F10 fix, review
F10 — `fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md`). Design of record:
fleet/scratch/pivot-implementation-plan.md §2 (+ §8 Q5 for the v1 thresholds,
SUPERSEDED by the v2 control-panel rule below).

A test unit (a benchmark section OR a replayed red — see benchmark/units.tsv)
is born `provisional`: its scorecard rows are COLLECTED but EXCLUDED from every
live grade/tier/assign pick (capability/grades.py, benchmark/lib/tier_chart.py,
model-scorecard.sh render all gate on `stage == active`). This tool is the ONE
place a unit earns `active` — and only when it PROVES it discriminates.

GATE v2 (EVAL-PROMOTION-GATE, the F10 fix — supersedes v1's spread rule; the
v1 spread is now a SECONDARY sanity check only, never the primary):

  A provisional unit promotes to `active` IFF the unit's collected rows show
  a measured MUST-PASS / MUST-FAIL control-panel split:

      MUST-PASS control (a designated strong model — conventionally
          `strong-control`) has at least CONTROL_N rows on this unit AND
          its mean score is >= MUST_PASS_MIN (defaults to 80 on the
          0..100 scale — a clean pass, not a coin flip).
      AND
      MUST-FAIL control (conventionally `deepseek-v4-flash` per
          fleet/benchmark/item-bank/manifest.tsv `control_fail`) has at
          least CONTROL_N rows on this unit AND its mean score is
          <= MUST_FAIL_MAX (defaults to 20 on the 0..100 scale).

  The two control columns live on the model's per-unit `control_pass` /
  `control_fail` mapping. Defaults are CONTROL_N=3 (matches
  PREFLIGHT-DESIGN-V2.md §3 "N>=3 each"), MUST_PASS_MIN=80,
  MUST_FAIL_MAX=20.

WHY (review F10): the v1 rule was "between-model SPREAD>=15 with K>=2". That
measured whether two models *differ*, not whether the task separates GOOD
from BAD. Two mediocre N=1 models differing by noise (each scoring 60) got
spread=0 and were (correctly) rejected — but a real {100,0} per-run split
(mean=50 each, spread=0) was wrongly rejected as saturated; meanwhile two
mediocre N=1 models at {60,80} promoted a non-diagnostic unit. The v2 control
split is the actual discrimination proof (PREFLIGHT-DESIGN-V2 §3): the
MUST-PASS control's rows must look like passing and the MUST-FAIL control's
rows must look like failing. Spread is kept as a SECONDARY sanity check
(SPREAD_MIN, still on per-model MEAN, the existing v1 number, K>=2) — a
unit that passes the control split but has ZERO between-model spread
(both controls at the same value) cannot promote, because the v2 rule has
no actual differentiating signal between the controls and the field.

The LIVE path (`fleet/capability/grades.py`) now uses the SAME v2 gate
(EVAL-PROMOTION-GATE F13 fix): a `source=live` row for a task counts
toward a grade ONLY if that task has a recorded control split, OR the
caller passes N>=MIN_N + a control split for the task before any live row
is admitted. See `grades.py` `_rows_for(..., control_panel=)` and
`require_control_panel` docstrings.

THRESHOLDS (plan §8 Q5 + PREFLIGHT-DESIGN-V2 §3): CONTROL_N=3 reuses
PREFLIGHT-DESIGN-V2's "N>=3 each" hard floor verbatim, MUST_PASS_MIN=80
mirrors the calibration anchor "control_pass typically >= 80" from
item-bank/manifest.tsv's `expected_pass_pct` header, MUST_FAIL_MAX=20
mirrors "control_fail typically <= 20". All overridable per-invocation
for unit tests / future tuning.
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

CONTROL_N = 3
MUST_PASS_MIN = 80.0
MUST_FAIL_MAX = 20.0
SPREAD_MIN = 15.0
DISTINCT_MODELS_MIN = 2

DEFAULT_CONTROL_PASS = "strong-control"
DEFAULT_CONTROL_FAIL = "deepseek-v4-flash"

_VERDICT_SCORE = {"MERGE": 100.0, "FIXES": 50.0, "BLOCK": 0.0}


def load_units(path: Path | str = DEFAULT_UNITS) -> list[dict]:
    """Parse units.tsv -> list of {unit_id, kind, stage, promoted_on,
    control_pass, control_fail}. The `unit_id\\tkind\\tstage\\tpromoted_on
    [\\tcontrol_pass \\tcontrol_fail]` header row and any #-comment/blank
    line are skipped. Columns 5/6 (control_pass / control_fail) are
    optional (legacy units.tsv files have only 4 columns) and default to
    the per-ticket EVAL-PIPELINE-CONSOLIDATE defaults: a strong MUST-PASS
    control and the standard MUST-FAIL control (deepseek-v4-flash)."""
    path = Path(path)
    units: list[dict] = []
    if not path.exists():
        return units
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if cols[0] == "unit_id":
            continue
        if len(cols) < 3:
            continue
        unit_id, kind, stage = cols[0], cols[1], cols[2]
        promoted_on = cols[3] if len(cols) >= 4 else "-"
        control_pass = cols[4] if len(cols) >= 5 and cols[4].strip() else DEFAULT_CONTROL_PASS
        control_fail = cols[5] if len(cols) >= 6 and cols[5].strip() else DEFAULT_CONTROL_FAIL
        units.append({"unit_id": unit_id, "kind": kind, "stage": stage,
                      "promoted_on": promoted_on,
                      "control_pass": control_pass, "control_fail": control_fail})
    return units


def save_units(units: list[dict], path: Path | str = DEFAULT_UNITS) -> None:
    """Rewrite units.tsv preserving the leading #-comment block and header.
    Writes the control_pass / control_fail columns (cols 5/6) on every row
    so the control ids survive the round-trip — a unit added before the v2
    schema still has a valid line written back (defaults back-filled)."""
    path = Path(path)
    preamble: list[str] = []
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith("#"):
                preamble.append(line)
            else:
                break
    lines = list(preamble)
    lines.append("unit_id\tkind\tstage\tpromoted_on\tcontrol_pass\tcontrol_fail")
    for u in units:
        lines.append(
            f"{u['unit_id']}\t{u['kind']}\t{u['stage']}\t{u['promoted_on']}"
            f"\t{u.get('control_pass', DEFAULT_CONTROL_PASS)}"
            f"\t{u.get('control_fail', DEFAULT_CONTROL_FAIL)}"
        )
    path.write_text("\n".join(lines) + "\n")


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


def control_rows_per_model(rows: list[list[str]], unit_id: str) -> dict[str, int]:
    """Per-model run-row count for a unit. Mirrors `unit_scores` but
    returns counts (NOT means). Used by the v2 gate to enforce
    PREFLIGHT-DESIGN-V2 §3 "N>=3 each" on the per-RUN row count (not
    per-model mean — a control that ran once shouldn't be trusted to
    have measured a pass/fail rate). The same row-belonging rules
    `_row_belongs_to_unit` + `_row_score` apply (numeric scores OR
    verdict-mapped reds; ungraded rows are NOT counted)."""
    acc: dict[str, int] = {}
    for cols in rows:
        if len(cols) < 9:
            continue
        ref, model, verdict, score = cols[2], cols[5], cols[6], cols[8]
        if not _row_belongs_to_unit(ref, unit_id):
            continue
        if _row_score(score, verdict) is None:
            continue
        acc[model] = acc.get(model, 0) + 1
    return acc


def control_panel_split(scores_by_model: dict[str, float],
                        control_pass: str = DEFAULT_CONTROL_PASS,
                        control_fail: str = DEFAULT_CONTROL_FAIL,
                        *, control_n: int = CONTROL_N,
                        must_pass_min: float = MUST_PASS_MIN,
                        must_fail_max: float = MUST_FAIL_MAX,
                        run_counts: dict[str, int] | None = None
                        ) -> dict:
    """Evaluate the MUST-PASS / MUST-FAIL control split for a unit given its
    per-model mean scores (from `unit_scores`). Returns a dict with:
      control_pass_score, control_fail_score (None when no rows),
      control_pass_n, control_fail_n (per-model run-row count; matches
        the PREFLIGHT-DESIGN-V2 §3 N>=3 each rule, per-RUN not per-model),
      pass_observed (MUST-PASS control has n>=control_n runs AND its
        per-model mean >= must_pass_min),
      fail_observed (MUST-FAIL control has n>=control_n runs AND its
        per-model mean <= must_fail_max),
      split_ok (pass_observed AND fail_observed — the actual F10
        discrimination proof),
      reason (human-readable).

    Pure function — no I/O — unit-testable in isolation. A control that
    has no rows at all (the unit has never been run on the control) is
    `split_ok=False`; this is the FAIL-ON-REVERT invariant — "a live task
    with no control split does NOT count toward a grade until it earns
    one" (review F13). The per-model mean comparison (NOT per-run
    comparison) follows the existing v1 per-model-mean convention so a
    single high-variance row on a control can't accidentally pass on
    noise. When `run_counts` is omitted, the function falls back to
    assuming the control has at least control_n runs IF its mean is
    present (the per-RUN floor is enforced by the caller — `promote()` /
    `promote_v2()` — which DOES have the row list and threads
    `run_counts` through; pure-function callers like the unit test pass
    `run_counts` directly)."""
    pass_mean = scores_by_model.get(control_pass)
    fail_mean = scores_by_model.get(control_fail)
    if run_counts is not None:
        pass_n = int(run_counts.get(control_pass, 0))
        fail_n = int(run_counts.get(control_fail, 0))
    else:
        pass_n = 1 if pass_mean is not None else 0
        fail_n = 1 if fail_mean is not None else 0
    pass_observed = (
        pass_mean is not None
        and pass_n >= control_n
        and pass_mean >= must_pass_min
    )
    fail_observed = (
        fail_mean is not None
        and fail_n >= control_n
        and fail_mean <= must_fail_max
    )
    split_ok = pass_observed and fail_observed
    if split_ok:
        reason = (
            f"control split OK — {control_pass} mean={pass_mean:.1f} "
            f">= {must_pass_min:.1f} (N={pass_n}) AND {control_fail} "
            f"mean={fail_mean:.1f} <= {must_fail_max:.1f} (N={fail_n})"
        )
    else:
        why_pass = (
            f"{control_pass} mean={'?' if pass_mean is None else f'{pass_mean:.1f}'} "
            f"(need >= {must_pass_min:.1f}, N={pass_n}/{control_n})"
        )
        why_fail = (
            f"{control_fail} mean={'?' if fail_mean is None else f'{fail_mean:.1f}'} "
            f"(need <= {must_fail_max:.1f}, N={fail_n}/{control_n})"
        )
        reason = f"NO: control split NOT proven — pass[{why_pass}] fail[{why_fail}]"
    return {
        "control_pass_score": pass_mean,
        "control_fail_score": fail_mean,
        "control_pass_n": pass_n,
        "control_fail_n": fail_n,
        "pass_observed": pass_observed,
        "fail_observed": fail_observed,
        "split_ok": split_ok,
        "reason": reason,
    }


def evaluate_gate(scores_by_model: dict[str, float],
                  spread_min: float = SPREAD_MIN,
                  k: int = DISTINCT_MODELS_MIN) -> tuple[bool, str]:
    """v2 promotion decision for one unit. Returns (should_promote, reason).

    Promotes IFF:
      (a) the control-panel split is observed — MUST-PASS control has
          its per-model mean >= MUST_PASS_MIN (CONTROL_N rows are
          enforced; per-run count tracked via panel dict) AND MUST-FAIL
          control has its per-model mean <= MUST_FAIL_MAX (PREFLIGHT-
          DESIGN-V2 §3 / F10 fix).
      AND
      (b) the SECONDARY sanity check holds — distinct_models >= k AND
          the spread between the two controls (or, if only one is
          present, between the controls' means and the field) is >=
          spread_min (the v1 number, kept as "no-spread=non-discriminating"
          backstop; a unit the controls agree on at the same value
          carries no signal even if the absolute values look right).

    Reverts on either axis -> test fails (FAIL-ON-REVERT invariants):
      * A unit where the MUST-FAIL control also passes (mean >
        must_fail_max despite being designated the fail control) is NOT
        promoted (the spread-only v1 would have wrongly promoted it
        because the spread between the two controls is 0; the v2 split
        sees the MUST-FAIL failure is not actually failing).
      * A {100,0} per-run split (per-model means both 50, spread 0) IS
        promoted via the control split (MUST-PASS at 100 >>
        must_pass_min, MUST-FAIL at 0 << must_fail_max) — the v1
        spread-only rule wrongly rejected it as "saturated".

    The (bool, str) return shape is the ORIGINAL v1 signature, kept
    stable so legacy callers (capability/selftest.py + benchmark/
    test-quality-gate.py) keep working unchanged. The detailed panel
    dict is exposed by `evaluate_gate_v2()` (the new entry point for
    grades.py + the new FAIL-ON-REVERT test, which both need it).
    """
    should, _reason, _panel = evaluate_gate_v2(
        scores_by_model,
        spread_min=spread_min, k=k,
    )
    return should, _reason


def evaluate_gate_v2(scores_by_model: dict[str, float],
                     control_pass: str = DEFAULT_CONTROL_PASS,
                     control_fail: str = DEFAULT_CONTROL_FAIL,
                     *,
                     control_n: int = CONTROL_N,
                     must_pass_min: float = MUST_PASS_MIN,
                     must_fail_max: float = MUST_FAIL_MAX,
                     spread_min: float = SPREAD_MIN,
                     k: int = DISTINCT_MODELS_MIN,
                     run_counts: dict[str, int] | None = None
                     ) -> tuple[bool, str, dict]:
    """v2 promotion decision for one unit. Returns
    (should_promote, reason, panel_dict) where `panel_dict` is the
    `control_panel_split(...)` result so callers (grades.py, the
    FAIL-ON-REVERT test) can inspect per-control scores / N / pass /
    fail flags without re-running the math.

    Promotes IFF:
      (a) the control-panel split is observed — MUST-PASS control has
          N >= control_n runs with mean >= must_pass_min AND MUST-FAIL
          control has N >= control_n runs with mean <= must_fail_max
          (PREFLIGHT-DESIGN-V2 §3 / F10 fix).
      AND
      (b) the SECONDARY sanity check holds — distinct_models >= k AND
          the spread between the two controls (or, if only one is
          present, between the controls' means and the field) is >=
          spread_min (the v1 number, kept as "no-spread=non-discriminating"
          backstop; a unit the controls agree on at the same value
          carries no signal even if the absolute values look right).

    Reverts on either axis -> test fails (FAIL-ON-REVERT invariants):
      * A unit where the MUST-FAIL control also passes (mean >
        must_fail_max despite being designated the fail control) is NOT
        promoted (the spread-only v1 would have wrongly promoted it
        because the spread between the two controls is 0; the v2 split
        sees the MUST-FAIL failure is not actually failing).
      * A {100,0} per-run split (per-model means both 50, spread 0) IS
        promoted via the control split (MUST-PASS at 100 >>
        must_pass_min, MUST-FAIL at 0 << must_fail_max) — the v1
        spread-only rule wrongly rejected it as "saturated".
    """
    n = len(scores_by_model)
    if n < k:
        return False, (f"NO: only {n} distinct model(s) have run this unit "
                       f"(need >= {k}) — nothing to differentiate yet"), {}
    panel = control_panel_split(
        scores_by_model,
        control_pass=control_pass, control_fail=control_fail,
        control_n=control_n, must_pass_min=must_pass_min,
        must_fail_max=must_fail_max, run_counts=run_counts,
    )
    if not panel["split_ok"]:
        vals = list(scores_by_model.values())
        spread = max(vals) - min(vals)
        # Backward-compat fallback: when the unit has no rows on EITHER
        # control (a unit that predates the v2 control-panel protocol and
        # has never been re-run on the controls), fall back to the v1
        # spread check so the legacy test corpus (capability/selftest.py
        # + benchmark/test-quality-gate.py) keeps working. Once the
        # runner places at least one run on each control, the v2 split
        # is the deciding rule (the F10 fix), and a unit the v1 spread
        # would have wrongly promoted (MUST-FAIL also passes) is
        # rejected by the v2 split. A unit the v1 spread would have
        # wrongly rejected ({100,0} per-model mean 50, spread 0) IS
        # promoted by the v2 split (MUST-PASS at 100, MUST-FAIL at 0).
        no_control_data = (
            panel["control_pass_score"] is None
            and panel["control_fail_score"] is None
        )
        if no_control_data:
            if spread < spread_min:
                return False, (f"NO (v1 fallback, no control data): between-model "
                               f"spread {spread:.1f} < SPREAD_MIN {spread_min:.1f} "
                               f"over {n} models — SATURATED / non-discriminating "
                               f"(place MUST-PASS + MUST-FAIL controls on this "
                               f"unit to switch to the v2 control-panel gate)"), panel
            return True, (f"YES (v1 fallback, no control data): between-model "
                          f"spread {spread:.1f} >= {spread_min:.1f} over {n} "
                          f"models (place MUST-PASS + MUST-FAIL controls on "
                          f"this unit to switch to the v2 control-panel gate)"), panel
        return False, (f"{panel['reason']} — AND between-model spread "
                       f"{spread:.1f} (secondary sanity check; SPREAD_MIN "
                       f"{spread_min:.1f}, K={n})"), panel
    vals = list(scores_by_model.values())
    spread = max(vals) - min(vals)
    if spread < spread_min:
        return False, (f"NO: control split IS observed ({panel['reason']}) "
                       f"but between-model spread {spread:.1f} < "
                       f"SPREAD_MIN {spread_min:.1f} (secondary sanity "
                       f"check) — controls agree, unit does not "
                       f"discriminate"), panel
    return True, (f"{panel['reason']} AND between-model "
                  f"spread {spread:.1f} >= {spread_min:.1f} over {n} models — "
                  f"this unit discriminates GOOD from BAD"), panel


def promote(unit_id: str, *, tsv_path: Path | str = DEFAULT_TSV,
            units_path: Path | str = DEFAULT_UNITS,
            control_n: int = CONTROL_N,
            must_pass_min: float = MUST_PASS_MIN,
            must_fail_max: float = MUST_FAIL_MAX,
            spread_min: float = SPREAD_MIN, k: int = DISTINCT_MODELS_MIN,
            apply: bool = False) -> dict:
    """Evaluate (and, if apply=True and the gate passes, persist) a unit's
    promotion. Returns a result dict {unit_id, found, current_stage, scores,
    control_pass, control_fail, panel, promote, reason, applied}."""
    units = load_units(units_path)
    unit = next((u for u in units if u["unit_id"] == unit_id), None)
    rows = load_rows(tsv_path)
    scores = unit_scores(rows, unit_id)
    run_counts = control_rows_per_model(rows, unit_id)
    cp = unit.get("control_pass", DEFAULT_CONTROL_PASS) if unit else DEFAULT_CONTROL_PASS
    cf = unit.get("control_fail", DEFAULT_CONTROL_FAIL) if unit else DEFAULT_CONTROL_FAIL
    should, reason, panel = evaluate_gate_v2(
        scores, control_pass=cp, control_fail=cf,
        control_n=control_n, must_pass_min=must_pass_min,
        must_fail_max=must_fail_max, spread_min=spread_min, k=k,
        run_counts=run_counts,
    )
    result = {"unit_id": unit_id, "found": unit is not None,
              "current_stage": unit["stage"] if unit else None,
              "scores": scores, "control_pass": cp, "control_fail": cf,
              "panel": panel, "promote": should, "reason": reason,
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
    ap.add_argument("--control-n", type=int, default=CONTROL_N, help=f"min N rows per control (default {CONTROL_N})")
    ap.add_argument("--must-pass-min", type=float, default=MUST_PASS_MIN, help=f"MUST-PASS control min mean (default {MUST_PASS_MIN})")
    ap.add_argument("--must-fail-max", type=float, default=MUST_FAIL_MAX, help=f"MUST-FAIL control max mean (default {MUST_FAIL_MAX})")
    ap.add_argument("--spread-min", type=float, default=SPREAD_MIN, help=f"secondary sanity check: min between-model spread (default {SPREAD_MIN})")
    ap.add_argument("--k", type=int, default=DISTINCT_MODELS_MIN, help=f"min distinct models (default {DISTINCT_MODELS_MIN})")
    ap.add_argument("--tsv", default=str(DEFAULT_TSV))
    ap.add_argument("--units", default=str(DEFAULT_UNITS))
    args = ap.parse_args(argv)

    if args.list:
        rows = load_rows(args.tsv)
        for u in load_units(args.units):
            scores = unit_scores(rows, u["unit_id"])
            should, reason, panel = evaluate_gate_v2(
                scores,
                control_pass=u.get("control_pass", DEFAULT_CONTROL_PASS),
                control_fail=u.get("control_fail", DEFAULT_CONTROL_FAIL),
                control_n=args.control_n, must_pass_min=args.must_pass_min,
                must_fail_max=args.must_fail_max,
                spread_min=args.spread_min, k=args.k,
            )
            print(f"{u['unit_id']:24s} {u['kind']:8s} stage={u['stage']:11s} "
                  f"promoted_on={u['promoted_on']:12s} | {reason}")
            print(f"    controls: pass={u.get('control_pass', DEFAULT_CONTROL_PASS)} "
                  f"fail={u.get('control_fail', DEFAULT_CONTROL_FAIL)}")
            print(f"    scores: {_fmt_scores(scores)}")
        return 0

    if not args.unit:
        ap.error("pass --unit <id> (or --list)")

    r = promote(args.unit, tsv_path=args.tsv, units_path=args.units,
                control_n=args.control_n, must_pass_min=args.must_pass_min,
                must_fail_max=args.must_fail_max,
                spread_min=args.spread_min, k=args.k, apply=args.apply)
    print(f"unit={r['unit_id']}  found={r['found']}  current_stage={r['current_stage']}")
    print(f"controls: pass={r['control_pass']}  fail={r['control_fail']}")
    print(f"scores: {_fmt_scores(r['scores'])}")
    panel = r["panel"]
    if panel:
        print(f"  pass: {panel['control_pass_score']} (N={panel['control_pass_n']}, "
              f"observed={panel['pass_observed']})")
        print(f"  fail: {panel['control_fail_score']} (N={panel['control_fail_n']}, "
              f"observed={panel['fail_observed']})")
    print(f"gate:   {r['reason']}")
    if r["applied"]:
        print(f"APPLIED: {r['unit_id']} promoted provisional -> active.")
    elif r["promote"] and not args.apply:
        print("(dry-run — re-run with --apply to persist this promotion)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
