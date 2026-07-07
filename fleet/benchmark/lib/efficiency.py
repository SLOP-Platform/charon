#!/usr/bin/env python3
"""benchmark-v2 efficiency scoring math (BENCHMARK-V2-DESIGN.md §4.3-§4.5,
as amended by BENCHMARK-V2-REVIEW.md's adversarial pass - the amended
numbers are what's implemented here, NOT the original pre-review draft).

Pure functions only - this module never touches disk, the TSV, or wall
clock. It operates on an already-assembled, already-frozen SEASON COHORT
(one call = one section's worth of one season's models) handed to it by
`lib/close_season.py`, which is the ONLY caller that may invoke this
against real data - never live/partial, per §4.2's reproducibility
requirement. Keeping this module TSV-agnostic and disk-free makes every
rule below directly unit-testable with synthetic rows (see
`selftest/efficiency_selftest.py`), independent of harness plumbing.

SCOPE (what this module is, and is not):
  - IS: the per-section, per-metric percentile -> weighted EFF_PCT ->
    bounded modifier -> section_total pipeline (§4.3-§4.5).
  - IS NOT: season framing/freezing/immutability (`lib/close_season.py`,
    §4.2), composite-level aggregation or the COMPOSITE_EFF_CAP clamp
    (`lib/tier_chart.py`, §4.6a), or source/season partitioning
    (`lib/tier_chart.py::rank_in_tier`, §4.6b).

CONSTANTS (§4.3b, §4.4, §4.5 - values are the AMENDED ones, unchanged by
the review from the original draft per BENCHMARK-V2-REVIEW.md's verdict:
"the tokens:time:cost = 3:2:1 weighting is unchanged", "Per-section
MODIFIER_MAX stays ±5 ... the review found no defect in it *per section*"):
  MIN_FIELD_SIZE = 4     - cohorts smaller than this get modifier=0 for
                            everyone (§4.3b - below 4, percentile is either
                            undefined or a full-swing coin flip; not stable
                            enough to move a tier decision).
  MODIFIER_MAX   = 5     - per-section modifier is bounded to +/-5 points
                            out of a 0-100 section score (§4.5).
  METRIC_WEIGHTS         - tokens:time:cost = 3:2:1 (§4.4), renormalized
                            over whichever metrics are actually available
                            for a given model.

"tokens" here means tokens_in + tokens_out combined into one scalar
(fewer total tokens = more efficient) - the design (§4, worked examples)
always refers to a single "tokens" axis and never distinguishes in vs.
out for scoring purposes; `lib/close_season.py`'s TSV adapter is what
performs this combination before handing rows to `compute_section_cohort`
below. Documented explicitly here since the design text doesn't spell out
the in+out combination rule itself.
"""
from __future__ import annotations

MIN_FIELD_SIZE = 4
MODIFIER_MAX = 5.0
METRIC_WEIGHTS = {"tokens": 3, "time_s": 2, "cost_usd": 1}
METRICS = tuple(METRIC_WEIGHTS)


def mid_rank_percentile(values: dict) -> dict:
    """§4.3a - mid-rank (average-rank/Hazen-style) percentile, lower-is-
    better, computed over exactly the models present in `values` (a dict
    model -> numeric value; callers must have ALREADY excluded any model
    missing this metric - that exclusion is a metric-availability decision,
    not this function's job).

        worse(M) = #{m != M : value(m) > value(M)}
        tie(M)   = #{m != M : value(m) == value(M)}
        pct(M)   = 100 * (worse(M) + 0.5*tie(M)) / (|values| - 1)

    Centers an all-tied (or 2-way-tied, etc.) field at exactly 50, not 0 -
    the defect BENCHMARK-V2-REVIEW.md §2b found in the pre-amendment
    formula ("count strictly-worse only" floors ties at the bottom instead
    of the middle). A uniquely-best value lands at 100, a uniquely-worst
    value at 0 (worked example 4.7b).

    Returns {} (percentile undefined for everyone) when there are fewer
    than 2 models to compare - a lone model has no field to be ranked
    against; callers (weighted_eff_pct) must treat a model's absence from
    this dict as "no percentile for this metric", not as 0.
    """
    n = len(values)
    if n < 2:
        return {}
    items = list(values.items())
    out = {}
    for model, value in items:
        worse = sum(1 for m2, v2 in items if m2 != model and v2 > value)
        tie = sum(1 for m2, v2 in items if m2 != model and v2 == value)
        out[model] = 100.0 * (worse + 0.5 * tie) / (n - 1)
    return out


def weighted_eff_pct(percentiles_by_metric: dict, model: str) -> float | None:
    """§4.4 - weighted combine of per-metric percentiles for one model,
    renormalized over whichever metrics that model actually has a
    percentile for (`available = {X : percentile(M,S,X) is defined}`).

    `percentiles_by_metric`: {metric_name -> {model -> percentile}}, as
    produced by calling `mid_rank_percentile` once per metric (each metric
    may have a different, smaller sub-cohort - a model missing `cost_usd`
    simply isn't a key in that metric's dict).

    Returns None (EFF_PCT undefined) if `model` has no percentile for ANY
    metric - the caller (modifier_from_eff_pct) must then floor the
    modifier at 0, never guess.
    """
    total = 0.0
    total_weight = 0.0
    for metric, weight in METRIC_WEIGHTS.items():
        pct = percentiles_by_metric.get(metric, {}).get(model)
        if pct is not None:
            total += weight * pct
            total_weight += weight
    if total_weight == 0:
        return None
    return total / total_weight


def modifier_from_eff_pct(eff_pct: float | None, cohort_size: int) -> float:
    """§4.3b + §4.5: modifier=0 if EFF_PCT is undefined OR the section's
    cohort is below MIN_FIELD_SIZE (a single cohort-level gate - §4.2
    guarantees every section in a season shares one cohort size, so this
    is checked once per section, not per model/metric). Otherwise linear,
    centered at the field median (modifier 0 at the 50th percentile),
    bounded to +/-MODIFIER_MAX at the 0th/100th percentile.
    """
    if eff_pct is None or cohort_size < MIN_FIELD_SIZE:
        return 0.0
    return (eff_pct - 50.0) / 50.0 * MODIFIER_MAX


def section_total(raw: float, modifier: float, capped_while_failing: bool) -> float:
    """§4.5 - anti-cheat ordering, confirmed sound and UNCHANGED by the
    review: the modifier is applied to `raw` BEFORE the correction-round
    cap, never after.

        adjusted      = clamp(raw + modifier, 0, 100)
        section_total = min(adjusted, 89)  if capped_while_failing
                       = adjusted           otherwise

    A timed-out section (raw=0) naturally also gets the field's worst
    time_s (percentile ~0, modifier ~-5) -> clamp(0-5, 0, 100) = 0, no
    special case needed (matches §4.5's own worked note).
    """
    adjusted = max(0.0, min(100.0, raw + modifier))
    if capped_while_failing:
        return min(adjusted, 89.0)
    return adjusted


def compute_section_cohort(rows: list[dict]) -> dict:
    """Full §4.3-§4.5 pipeline for ONE section's ONE season cohort.

    `rows`: list of dicts, one per model in the cohort, each with:
      "model"                 str, unique within `rows`
      "raw"                   float/int - grader score (0-100) for this
                               model/section, AS RECORDED (see
                               lib/close_season.py's TSV adapter docstring
                               for the one known approximation: a
                               capped-while-failing row's true PRE-cap raw
                               score isn't persisted anywhere upstream
                               today, so the adapter passes the already
                               min(...,89)-capped value through as `raw`
                               too - harmless here since §4.5's own
                               min(adjusted,89) re-application produces
                               the same ceiling regardless).
      "capped_while_failing"  bool - this section hit CORRECTIONS_CAP
                               while still failing (grade_state.py's
                               `min(score, 89)` branch).
      "tokens"                int|None  (tokens_in + tokens_out combined)
      "time_s"                float|None
      "cost_usd"              float|None
      Missing/None values are metric-unavailable for that model (excluded
      from that metric's percentile field, never guessed as 0).

    Returns {model -> {"eff_pct": float|None, "modifier": float,
                        "section_total": float, "raw": ...,
                        "capped_while_failing": ...}}
    """
    cohort_size = len({row["model"] for row in rows})
    metric_values: dict = {m: {} for m in METRICS}
    for row in rows:
        for metric in METRICS:
            value = row.get(metric)
            if value is not None:
                metric_values[metric][row["model"]] = value

    percentiles_by_metric = {
        metric: mid_rank_percentile(values) for metric, values in metric_values.items()
    }

    out = {}
    for row in rows:
        model = row["model"]
        eff_pct = weighted_eff_pct(percentiles_by_metric, model)
        modifier = modifier_from_eff_pct(eff_pct, cohort_size)
        total = section_total(row["raw"], modifier, row["capped_while_failing"])
        out[model] = {
            "eff_pct": eff_pct,
            "modifier": modifier,
            "section_total": total,
            "raw": row["raw"],
            "capped_while_failing": row["capped_while_failing"],
        }
    return out
