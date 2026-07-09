"""Grades-provider: model x work_class capability signal (build #14, the
shared "capability brain" per fleet/POOLS-REDESIGN-ADR-v2.md's "Grades
table: two consumers" subsection).

Two callers share this module: fleet ticket-assignment (this build,
capability/assign.py) and, later, the gateway request-routing consumer
described in the ADR. Both must see the SAME work_class taxonomy and the
SAME grade math, so the taxonomy and scoring formula live here, once.

TODAY's data source is fleet/model-scorecard.tsv (per POOLS-REDESIGN-ADR-v2.md
§"two consumers": assignment's bar for usefulness is lower than gateway
routing's, so it can consume real signal now, ahead of the Phase 2a grades
table). The `GradesProvider` interface below is the swap point: when the
pools-redesign grades table lands, a new provider class implements the same
interface and every caller (assign.py today, gateway routing later) keeps
working unchanged.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

FLEET_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TSV = FLEET_DIR / "model-scorecard.tsv"

# ---------------------------------------------------------------------------
# Confidence-aware scoring (fixes the #14 review's "small-N over-trust"
# must-fix: fleet/scratch/ticket-assign-review.md Q1 — raw
# `score = merge% - block%` collapses to +-100/0 at n=1, so a single lucky
# MERGE outranks a model with real multi-sample evidence that includes a
# genuine BLOCK. Demonstrated inversion: glm-5.2/routing n=3 (2 MERGE + 1
# real BLOCK, old score 33.3) lost to any n=1-lucky-MERGE model (old score
# 100). See capability/testdata/scorecard-fixture.tsv and selftest.py's
# test_confidence_fixes_smalln_inversion() for the frozen-fixture proof.
#
# MIN_N=4: reuses benchmark-v2's efficiency.py MIN_FIELD_SIZE threshold and
# rationale verbatim ("cohorts smaller than this get modifier=0 ... below 4,
# percentile is either undefined or a full-swing coin flip; not stable
# enough to move a tier decision" — fleet/benchmark/lib/efficiency.py L27-30)
# rather than inventing a new number for this sibling scoring module. A
# Grade with n < MIN_N is flagged LOW_CONFIDENCE (surfaced on the Grade
# object and in summary()/rationale) — this is a DISCLOSURE flag, not a
# ranking gate: the Wilson bounds below already do the actual discounting,
# continuously, so a LOW_CONFIDENCE grade still ranks correctly relative to
# a high-confidence one instead of being all-or-nothing zeroed like
# efficiency.py's per-section modifier.
# ---------------------------------------------------------------------------
MIN_N = 4

# Wilson score interval (E.B. Wilson, "Probable Inference, the Law of
# Succession, and Statistical Inference," JASA 22, 1927), 95% two-sided
# confidence -> z_0.975.
_WILSON_Z = 1.959963985


def _wilson_bound(successes: int, n: int, upper: bool, z: float = _WILSON_Z) -> float:
    """One side of the Wilson score interval for a binomial proportion,
    scaled to a 0..100 percentage. `upper=False` returns the conservative
    LOWER bound (don't over-trust a good rate seen on a small sample: n=1
    all-MERGE lands around 20.6, not 100). `upper=True` returns the
    conservative UPPER bound (don't under-trust the *risk* implied by a
    small sample: n=1 with zero observed BLOCKs still carries a wide
    "could-be-bad" upper bound around 79.3, not 0).

    Used asymmetrically by `grade()`: merge uses the lower bound (discount
    good news), block uses the upper bound (don't discount bad news' hidden
    risk). This asymmetry is what lets a model with more total evidence AND
    a real observed block still outrank a lucky single sample — see the
    module docstring above and the fixture-driven proof in selftest.py.
    """
    if n <= 0:
        return 0.0
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = p + z2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)
    bound = (center + margin) if upper else (center - margin)
    return 100.0 * max(0.0, min(1.0, bound / denom))

# Single source of truth = model-scorecard.sh's VALID_CLASS (line ~21). Duplicated
# here (stdlib TSV reader, no shared JSON schema between bash and this module) —
# MUST be kept in lockstep, same discipline tier_chart.py documents for its own
# duplicated season_for_date() rule. "generalist" is NOT a scorecard work_class;
# it is this module's aggregate-across-everything fallback bucket (see grade()).
WORK_CLASSES: tuple[str, ...] = (
    "money-path", "routing", "ci-infra", "refactor", "bugfix",
    "tests", "greenfield-feature", "docs", "frontend",
)
GENERALIST = "generalist"

_MERGE, _BLOCK = "MERGE", "BLOCK"

# ---------------------------------------------------------------------------
# REAL-OUTCOMES PIVOT (BENCH-REGROUND-LIVE, pivot A2 — design of record:
# fleet/scratch/pivot-implementation-plan.md §0/§1/§2/§7; driving verdict:
# fleet/BENCHMARK-VALIDITY-REVIEW.md). The synthetic S0–S6 benchmark is
# "theater, not measure" for RANKING (graders world-readable + self-driven +
# self-reported; 5/7 sections saturate), so it is DEMOTED to a smoke-test:
# ONLY rows whose `source` is an explicitly REAL-OUTCOME provenance feed the
# capability grade or its rank key `score`.
#
# This is an ALLOW-LIST (fail-CLOSED), NOT a deny-list, and that is deliberate
# (BENCH-REGROUND-LIVE review Q2): a real signal is admitted only when its
# provenance is on this list; every other source — synthetic (`bench`/
# `bench2`), and any future PROVISIONAL/unknown value (plan §2 line ~136
# floats `bench-prov`/`reds-prov` as a candidate encoding for #20 provisional
# rows) — is treated as NOT-yet-trusted and excluded. A deny-list would let
# such a future provisional row silently count as trusted live evidence — the
# exact leak #20 exists to prevent.
#
# `live` is the ONLY genuinely-real production-outcome source today: per plan
# §0 (VALID_SOURCE="live bench bench2") `source=live` rows are real routed
# tickets/PRs whose MERGE/BLOCK verdict a human/gate produced out-of-band by
# construction. `ticket` is NOT a production source — it is test-only (never
# in model-scorecard.sh's VALID_SOURCE; it only ever appeared in the frozen
# selftest fixture as the test-time analog of live), so the fixture's real
# rows now use `source=live` too and the allow-list is exactly {"live"}.
# Extend this set DELIBERATELY as new real sources land (e.g. promoted
# reds-replay rows per §7/#25), never implicitly. `tier_chart.py` keeps S0
# alone as the harness sanity/smoke gate and nothing synthetic sets a
# capability tier position anymore.
_REAL_OUTCOME_SOURCES = frozenset({"live"})


@dataclass
class Grade:
    """One model's grade at one work_class (or the generalist aggregate)."""

    model: str
    requested_work_class: str
    used_work_class: str          # == requested, or GENERALIST if no direct data
    fallback_used: bool
    n: int
    merge: int
    block: int
    fixes: int
    merge_pct: float
    block_pct: float
    score: float                  # confidence-aware; the primary rank key (see MIN_N/_wilson_bound above)
    low_confidence: bool          # n < MIN_N — disclosure flag; does NOT gate ranking, only surfaces it
    mean_bench_score: float | None
    mean_cost_usd: float | None
    mean_time_s: float | None
    corrections_total: int

    def summary(self) -> str:
        base = (f"{self.model}: n={self.n} merge={self.merge_pct:.0f}% "
                f"block={self.block_pct:.0f}% score={self.score:.0f}")
        if self.low_confidence:
            base += f" [LOW-CONFIDENCE: n<{MIN_N}]"
        if self.fallback_used:
            base += f" (no {self.requested_work_class} data — generalist fallback)"
        if self.mean_cost_usd is not None:
            base += f" cost=${self.mean_cost_usd:.4f}"
        if self.mean_time_s is not None:
            base += f" time={self.mean_time_s:.1f}s"
        return base


class GradesProvider:
    """Abstract interface. Swap implementations without touching callers."""

    def grade(self, model: str, work_class: str) -> Grade | None:
        raise NotImplementedError

    def all_models(self) -> list[str]:
        raise NotImplementedError


class ScorecardGradesProvider(GradesProvider):
    """TODAY's implementation: reads fleet/model-scorecard.tsv directly (not
    via model-scorecard.sh's `render` text table — that's for human eyes;
    this parses the TSV structurally, same 15-column shape cmd_append writes,
    same tolerance for legacy 13-column rows tier_chart.py already relies on).

    REAL-OUTCOMES PIVOT (A2): the grade is grounded ONLY in real-outcome
    actuals rows — `source=live` real routed tickets/PRs (out-of-band-valid by
    construction). Admission is an ALLOW-LIST (fail-closed): only sources in
    `_REAL_OUTCOME_SOURCES` count; synthetic S0–S6 bench/bench2 rows AND any
    provisional/unknown source are DEMOTED and no longer counted into
    merge/block/score or the tier — see `_REAL_OUTCOME_SOURCES` and
    `_rows_for(..., real_only=True)`. A model with only non-real evidence
    therefore has no capability grade (grade() returns None), which is the
    intended demotion, not a regression.

    Score formula: a confidence-aware, Wilson-bound spread (see module-level
    `_wilson_bound`/MIN_N docs) — merge's lower bound minus block's upper
    bound, NOT the raw `merge_pct - block_pct` this replaced. A verdict of
    FIXES counts toward neither numerator, so it still drags the merge bound
    down without inflating the block bound — deliberately: FIXES is "partial
    credit, not a clean win," and should rank below a clean MERGE ledger even
    without an explicit BLOCK. `merge_pct`/`block_pct` (raw percentages) are
    still carried on Grade for human-readable display; only `score` (the
    rank key) changed.
    """

    def __init__(self, tsv_path: Path | str = DEFAULT_TSV):
        self.tsv_path = Path(tsv_path)
        self._rows: list[dict] = []
        self._load()

    def _load(self) -> None:
        if not self.tsv_path.exists():
            return
        for line in self.tsv_path.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 13:
                continue
            (date, source, ref, wclass, tier, model, verdict, gate, score,
             time_s, cost_usd, corrections, note, *_rest) = cols
            self._rows.append({
                "date": date, "source": source, "ref": ref, "work_class": wclass,
                "tier": tier, "model": model, "verdict": verdict, "gate": gate,
                "score": score, "time_s": time_s, "cost_usd": cost_usd,
                "corrections": corrections, "note": note,
            })

    def all_models(self) -> list[str]:
        return sorted({r["model"] for r in self._rows})

    def _rows_for(self, model: str, work_class: str | None,
                  real_only: bool = True) -> list[dict]:
        """Rows for a (model, work_class) — REAL-OUTCOME actuals ONLY by
        default (ALLOW-LIST: source in _REAL_OUTCOME_SOURCES). Synthetic
        S0–S6 bench/bench2 rows AND any provisional/unknown source are excluded
        from the grade per the real-outcomes pivot (see _REAL_OUTCOME_SOURCES
        above — fail-closed); pass real_only=False only for smoke/diagnostic
        tooling that explicitly wants every row. work_class is None to
        aggregate across every class (the generalist bucket)."""
        out = []
        for r in self._rows:
            if r["model"] != model:
                continue
            if real_only and r["source"] not in _REAL_OUTCOME_SOURCES:
                continue
            if work_class is not None and r["work_class"] != work_class:
                continue
            out.append(r)
        return out

    def grade(self, model: str, work_class: str) -> Grade | None:
        requested = work_class
        if work_class == GENERALIST:
            rows = self._rows_for(model, None)
            used, fallback = GENERALIST, False
        else:
            rows = self._rows_for(model, work_class)
            used, fallback = work_class, False
            if not rows:
                rows = self._rows_for(model, None)  # generalist fallback
                used, fallback = GENERALIST, True
        if not rows:
            return None

        n = len(rows)
        merge = sum(1 for r in rows if r["verdict"] == _MERGE)
        block = sum(1 for r in rows if r["verdict"] == _BLOCK)
        fixes = n - merge - block
        merge_pct = 100.0 * merge / n
        block_pct = 100.0 * block / n
        # Confidence-aware score, NOT merge_pct - block_pct — see module
        # docstring above _wilson_bound. Asymmetric bounds: merge's
        # conservative LOWER bound minus block's conservative UPPER bound.
        score = _wilson_bound(merge, n, upper=False) - _wilson_bound(block, n, upper=True)
        low_confidence = n < MIN_N

        # DEMOTED (real-outcomes pivot): `rows` are real-outcome actuals only
        # (see _rows_for / _REAL_OUTCOME_SOURCES allow-list), so no synthetic
        # bench/bench2 row is present here and mean_bench_score resolves to None
        # for real data whose score column is '-' — the synthetic S0–S6
        # composite no longer feeds the grade OR the assign rank/tiebreak. Kept
        # defined so the field still populates if a future real-outcome source
        # ever carries a numeric score.
        bench_scores = [int(r["score"]) for r in rows if r["score"].isdigit()]
        costs = [float(r["cost_usd"]) for r in rows if _is_float(r["cost_usd"])]
        times = [float(r["time_s"]) for r in rows if _is_float(r["time_s"])]
        corr_total = sum(int(r["corrections"]) for r in rows if r["corrections"].isdigit())

        return Grade(
            model=model, requested_work_class=requested, used_work_class=used,
            fallback_used=fallback, n=n, merge=merge, block=block, fixes=fixes,
            merge_pct=merge_pct, block_pct=block_pct, score=score,
            low_confidence=low_confidence,
            mean_bench_score=mean(bench_scores) if bench_scores else None,
            mean_cost_usd=mean(costs) if costs else None,
            mean_time_s=mean(times) if times else None,
            corrections_total=corr_total,
        )


def _is_float(s: str) -> bool:
    if s in ("-", ""):
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Cost-tier lookup (frontier/strong/economy, i.e. high/med/low) — a SEPARATE
# axis from the benchmark difficulty "tier" column in model-scorecard.tsv.
# Two-path resolution, same resilience pattern fleet/claim.sh already uses for
# `charon tier resolve`: try the product's own tier-alias data live; if the
# `charon` CLI isn't importable in this environment, fall back to a local
# copy of the tiny alias table (documented below, must stay in lockstep with
# src/charon/config.py's TIER_ALIASES, lines ~316-330).
# ---------------------------------------------------------------------------
_ALIASES = {
    "frontier": "high", "strong": "med", "economy": "low",
    "opus": "high", "sonnet": "med", "haiku": "low",
    "low": "low", "med": "med", "high": "high",
}

_CHARON_SRC = Path("/home/stack/code/charon/src")
_catalog_by_id: dict[str, str] | None = None


def _load_catalog() -> dict[str, str]:
    global _catalog_by_id
    if _catalog_by_id is not None:
        return _catalog_by_id
    _catalog_by_id = {}
    try:
        if str(_CHARON_SRC) not in sys.path:
            sys.path.insert(0, str(_CHARON_SRC))
        from charon import model_catalog as _mc  # read-only import; never edits src/
        _catalog_by_id = {e.id: e.tier_hint for e in _mc.catalog()}
    except Exception:
        _catalog_by_id = {}
    return _catalog_by_id


def resolve_tier_alias(name: str) -> str | None:
    """Fold a ticket/CLI tier string to canonical low/med/high, or None if unrecognized."""
    return _ALIASES.get(name.strip().lower()) if name else None


def get_tier_hint(model: str) -> str | None:
    """This model's cost tier (low/med/high) from the curated catalog, or None
    if the model isn't in the curated catalog (e.g. a benchmark-only id like
    `hy3-preview-or` or `gpt-5.4` that hasn't been added to model_catalog.py
    yet) — callers must treat None as "unknown", not "excluded"."""
    return _load_catalog().get(model)
