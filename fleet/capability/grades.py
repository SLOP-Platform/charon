"""Grades-provider: model x work_class capability signal (build #14, the
shared "capability brain" per fleet/POOLS-REDESIGN-ADR-v2.md's "Grades
table: two consumers" subsection).

Two callers share this module: fleet ticket-assignment (this build,
capability/assign.py) and, later, the gateway request-routing consumer
described in the ADR. Both must see the SAME work_class taxonomy and the
SAME grade math, so the taxonomy and scoring formula live here, once.

EVAL-TAXONOMY-ALIGN (fixes the adversarial review's F3 BLOCKER / MSOT-BLAST-
RADIUS-AUDIT.md row #2 — "the eval grades the WRONG taxonomy"): "the SAME
work_class taxonomy" above used to be FALSE — assign.py fed this module
fleet board-ticket-shape classes (money-path/ci-infra/bugfix/...) while the
gateway router's own vocabulary (src/charon/routing_policy/matrix.py
`WorkClass`) shares zero names with it, so a router query would have
returned ZERO rows. It is genuinely true now: `grade()`/`_rows_for()` always
resolve BOTH vocabularies into ONE canonical grading space
(CANONICAL_WORK_CLASSES below, == the router's own 6 classes) before
matching rows, so a router-native query ("coding") and a board-ticket-shape
query ("bugfix") that lands in the same bucket see the SAME underlying
evidence. See fleet/state/EVAL-TAXONOMY.md for the full decision + mapping
table (single source of truth for the taxonomy itself).

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


# ---------------------------------------------------------------------------
# AGGREGATE-N (BENCH-AGGREGATE-N, #16 — design of record:
# fleet/scratch/pivot-implementation-plan.md §5, §8 Q5). The ledger is
# append-only and multi-row-capable, so a (model, work_class) already has N
# rows — but the numeric `score` column was only ever surfaced as a bare
# `mean` with NO noise band (grade() below), so a single-run number was
# trusted the same as a 3-run average. The validity review (§4/§5) proved
# that is not test-retest reliable: glm-5.2 scored S3 100->75 and S5 100->60
# ACROSS repeat runs. `_score_stats` publishes the smoothing signal — mean,
# sample stddev, and a 95% CI half-width (the "noise band") over the N runs —
# so a consumer can treat a gap SMALLER than the band as a TIE, not a rank
# (see `scores_tie`). Reuses `_WILSON_Z` (the same 95% two-sided z the
# merge/block Wilson bounds use) rather than inventing a second z for this
# sibling aggregate. A band needs >=2 runs to estimate run-to-run noise at
# all; with <2 runs stddev/band are None (honestly "unmeasurable from one
# sample"), never a fabricated 0.
# ---------------------------------------------------------------------------
def _score_stats(values: list[int]) -> tuple[float | None, float | None, float | None]:
    """(mean, sample_stddev, ci_half_width) over the numeric scores of N
    repeat runs. Returns (None, None, None) for zero runs; for a single run
    returns (mean, None, None) — one sample carries no run-to-run noise
    estimate, so the band is left unmeasured rather than faked as 0."""
    n = len(values)
    if n == 0:
        return None, None, None
    m = sum(values) / n
    if n < 2:
        return m, None, None
    var = sum((v - m) ** 2 for v in values) / (n - 1)   # sample (Bessel) variance
    sd = math.sqrt(var)
    band = _WILSON_Z * sd / math.sqrt(n)                 # 95% CI half-width on the mean
    return m, sd, band


def scores_tie(score_a: float, band_a: float | None,
               score_b: float, band_b: float | None) -> bool:
    """#16: two aggregate scores are a TIE (not a rank) when the gap between
    them is within their COMBINED noise band — |a-b| <= band_a + band_b. A
    None band (fewer than 2 runs, so noise is unmeasurable) contributes 0: we
    never invent a band we could not measure, so an un-repeated score can only
    tie another via the OTHER model's measured band. tier_chart.py keeps a
    lockstep copy of this exact formula for the composite rank (it must not
    import across the capability<->benchmark package boundary, the same
    duplication discipline season_for_date() already documents there)."""
    ba = band_a or 0.0
    bb = band_b or 0.0
    return abs(score_a - score_b) <= (ba + bb)

# ---------------------------------------------------------------------------
# CANONICAL CAPABILITY-GRADING TAXONOMY (EVAL-TAXONOMY-ALIGN — review F3
# BLOCKER, MSOT-BLAST-RADIUS-AUDIT.md row #2). Single source of truth =
# fleet/state/EVAL-TAXONOMY.md, which mirrors the PRODUCT ROUTER's own
# semantic work_class vocabulary VERBATIM: src/charon/routing_policy/
# matrix.py:20-27 `WorkClass` Literal, identically mirrored in
# src/charon/capability/taxonomy.py `_SEED_CLASSES`. This — not WORK_CLASSES
# below — is the axis `grade()` actually keys the capability signal on.
# `_live_product_work_classes()` cross-checks this literal copy against the
# live product module when importable (same resilience pattern as
# `_load_catalog()`/get_tier_hint below: try live, tolerate unavailable).
CANONICAL_WORK_CLASSES: tuple[str, ...] = (
    "reasoning", "coding", "translation", "creative", "analysis", "general",
)

# WORK_CLASSES = the fleet BOARD-TICKET / assign.py-CLI INPUT vocabulary
# (ticket SHAPE, not model capability). This is a SEPARATE, disjoint axis
# from CANONICAL_WORK_CLASSES above — kept, unchanged in content, so
# assign.py's `--work-class` CLI and validate_board.sh's board-ticket
# `work_class:` meta-field check keep working exactly as before (neither is
# owned by EVAL-TAXONOMY-ALIGN; this ticket is taxonomy-only, not a re-tag
# of the board). Every one of these legacy strings is mapped into the
# canonical grading space by _LEGACY_TO_CANONICAL below, applied at READ
# time only (the TSV on disk keeps its original raw strings — nothing is
# lost or silently rewritten).
#
# Known, deliberately UNTOUCHED residual (out of this ticket's owns:): this
# 11-class list is already diverged from model-scorecard.sh's VALID_CLASS
# (9 — no rig-meta/design-review) and enqueue-capture.sh's hardcoded copy
# (same 9) — MSOT-BLAST-RADIUS-AUDIT.md row #2's OTHER divergence, on the
# fleet-ticket-shape axis itself, not the fleet<->router taxonomy split this
# ticket fixes. Reconciling that would touch model-scorecard.sh/
# enqueue-capture.sh (neither owned here) and does not block the fix below.
WORK_CLASSES: tuple[str, ...] = (
    "money-path", "routing", "ci-infra", "refactor", "bugfix",
    "tests", "greenfield-feature", "docs", "frontend",
    "rig-meta", "design-review",
)
GENERALIST = "generalist"

# Fleet ticket-shape -> canonical product-router class. Judgment calls are
# documented in fleet/state/EVAL-TAXONOMY.md (short version: the review's own
# F5 finding — "the honest battery is one skill wearing three labels" — means
# nearly every fleet ticket is the same underlying skill, a small local code
# change, so most legacy classes fold into "coding"; design-review folds into
# "analysis" (assessing a tradeoff); docs/rig-meta are non-code/meta prose
# work, folded into "general"). No fleet class maps to reasoning/translation/
# creative — the fleet ticket stream has never produced one of those; that is
# an honest gap this ticket surfaces, not one it manufactures coverage for.
_LEGACY_TO_CANONICAL: dict[str, str] = {
    "money-path": "coding", "routing": "coding", "ci-infra": "coding",
    "refactor": "coding", "bugfix": "coding", "tests": "coding",
    "greenfield-feature": "coding", "frontend": "coding",
    "design-review": "analysis",
    "docs": "general", "rig-meta": "general",
}

assert set(_LEGACY_TO_CANONICAL) == set(WORK_CLASSES), (
    "grades.py: WORK_CLASSES and _LEGACY_TO_CANONICAL have drifted apart — "
    "every legacy fleet class MUST have a canonical mapping (fail loud at "
    "import time, not a silent None at grade-time)."
)
assert set(_LEGACY_TO_CANONICAL.values()) <= set(CANONICAL_WORK_CLASSES), (
    "grades.py: _LEGACY_TO_CANONICAL maps to a class outside CANONICAL_WORK_CLASSES."
)


def _canonical_of(work_class: str) -> str | None:
    """Resolve a class string — either native CANONICAL_WORK_CLASSES or
    legacy WORK_CLASSES — to its canonical bucket. Returns None for a string
    that is neither (callers must treat None as "cannot be graded in
    canonical space", never a silent fallback bucket)."""
    if work_class in CANONICAL_WORK_CLASSES:
        return work_class
    return _LEGACY_TO_CANONICAL.get(work_class)


def _live_product_work_classes() -> tuple[str, ...] | None:
    """Best-effort LIVE cross-check against the product's own `WorkClass`
    Literal (src/charon/routing_policy/matrix.py) — same
    try-live-then-tolerate-unavailable resilience pattern as
    `_load_catalog()` below. Returns None (never raises) if the product repo
    isn't importable in this environment; callers must treat that as
    "unverifiable here", not "drifted"."""
    try:
        if str(_CHARON_SRC) not in sys.path:
            sys.path.insert(0, str(_CHARON_SRC))
        import typing as _typing
        from charon.routing_policy.matrix import WorkClass as _ProductWorkClass
        return _typing.get_args(_ProductWorkClass)
    except Exception:
        return None

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

# ---------------------------------------------------------------------------
# PROVISIONAL-vs-ACTIVE staging (BENCH-PROVISIONAL-SCORING, #20 — design of
# record: fleet/scratch/pivot-implementation-plan.md §2, §8 Q4). A test unit
# (a benchmark section OR a replayed red) is `provisional` while it collects
# data but has NOT yet proven it discriminates, and `active` once
# benchmark/promote.py's gate flips it. Its stage rides on each ledger row as
# a NEW 16th trailing column (`stage`), following the exact backward-compat
# pattern tokens_in/out (cols 14/15) use — a row with FEWER than 16 columns
# (every legacy 13- or 15-column row already in the ledger) defaults to
# `active`, so no historical grade shifts.
#
# `stage` is ORTHOGONAL to `source`: `source` = provenance (is this a real
# outcome?), `stage` = trust (has this unit proven it discriminates?). A row
# counts toward a capability grade ONLY when BOTH hold — `source` in
# `_REAL_OUTCOME_SOURCES` AND `stage == active`. This preserves the
# fail-closed property #20 exists to protect: a provisional row is COLLECTED
# in the ledger but EXCLUDED from every active grade/tier/assign pick until
# promoted, so adding reds-replay (#25) or harder sections (#17) can never
# silently move the live ranking before the promotion gate says they earned
# it. Analysis/promotion tooling opts back in via `include_provisional=True`.
_ACTIVE_STAGE = "active"
_PROVISIONAL_STAGE = "provisional"


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
    # AGGREGATE-N (#16): the noise band on the numeric bench-score aggregate,
    # over `bench_score_n` repeat runs. stddev/band are None when <2 runs
    # carry a numeric score (unmeasurable from one sample — see _score_stats).
    # For real-outcome `source=live` rows whose `score` column is '-' these
    # stay None/0, which is correct: the pivot demoted the synthetic bench
    # score, so the band is only populated when a real-outcome source ever
    # carries a numeric score. Exposed so a consumer can call scores_tie().
    bench_score_stddev: float | None = None
    bench_score_band: float | None = None
    bench_score_n: int = 0

    def summary(self) -> str:
        base = (f"{self.model}: n={self.n} merge={self.merge_pct:.0f}% "
                f"block={self.block_pct:.0f}% score={self.score:.0f}")
        if self.low_confidence:
            base += f" [LOW-CONFIDENCE: n<{MIN_N}]"
        if self.mean_bench_score is not None and self.bench_score_band is not None:
            # AGGREGATE-N (#16): show the mean WITH its noise band so a single
            # lucky run is never read as if it were a stable multi-run average.
            base += (f" bench={self.mean_bench_score:.0f}±{self.bench_score_band:.0f}"
                     f" (N={self.bench_score_n} runs)")
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

    PROVISIONAL-vs-ACTIVE (#20): admission is ALSO gated on the row's `stage`
    (16th column) — only `stage == active` rows count; a provisional row (an
    unpromoted unit's data) is collected but excluded, orthogonally to the
    source allow-list. See `_ACTIVE_STAGE` / `_rows_for(include_provisional=)`
    and benchmark/promote.py (the gate that flips a unit provisional->active).

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
            # PROVISIONAL-vs-ACTIVE (#20): `stage` is the 16th trailing column
            # (_rest = cols[13:] == [tokens_in, tokens_out, stage, ...]). Any
            # row with < 16 columns — every legacy 13/15-col row — defaults to
            # `active` so no historical grade shifts. An empty stage cell also
            # defaults to active (fail-open ONLY on the legacy axis; the trust
            # gate itself stays fail-closed — an explicit `provisional` value is
            # the only thing that excludes a row here).
            stage = _rest[2].strip() if len(_rest) >= 3 and _rest[2].strip() else _ACTIVE_STAGE
            self._rows.append({
                "date": date, "source": source, "ref": ref, "work_class": wclass,
                "tier": tier, "model": model, "verdict": verdict, "gate": gate,
                "score": score, "time_s": time_s, "cost_usd": cost_usd,
                "corrections": corrections, "note": note, "stage": stage,
            })

    def all_models(self) -> list[str]:
        return sorted({r["model"] for r in self._rows})

    def _rows_for(self, model: str, work_class: str | None,
                  real_only: bool = True,
                  include_provisional: bool = False) -> list[dict]:
        """Rows for a (model, work_class) — REAL-OUTCOME actuals ONLY by
        default (ALLOW-LIST: source in _REAL_OUTCOME_SOURCES). Synthetic
        S0–S6 bench/bench2 rows AND any provisional/unknown source are excluded
        from the grade per the real-outcomes pivot (see _REAL_OUTCOME_SOURCES
        above — fail-closed); pass real_only=False only for smoke/diagnostic
        tooling that explicitly wants every row. work_class is None to
        aggregate across every class (the generalist bucket).

        PROVISIONAL-vs-ACTIVE (#20): by default only `stage == active` rows
        count — a provisional row (a not-yet-promoted unit's data) is collected
        in the ledger but EXCLUDED here, orthogonally to the source allow-list
        (BOTH gates must pass). Promotion tooling / analysis pass
        include_provisional=True to see provisional rows too; the live grade
        path never does, so an unpromoted unit provably cannot move a grade.

        EVAL-TAXONOMY-ALIGN: `work_class` may be either a native
        CANONICAL_WORK_CLASSES string (the product router's own vocabulary —
        e.g. "coding") or a legacy WORK_CLASSES string (the fleet
        board-ticket-shape vocabulary assign.py feeds in today — e.g.
        "bugfix"). A CANONICAL query matches every row whose CANONICAL
        bucket agrees (folding in every mapped legacy row — this is the new
        capability that lets the router see real, non-zero historical data,
        per fleet/state/EVAL-TAXONOMY.md). A legacy query matches by EXACT
        raw string, unchanged from before this ticket — zero behavior change
        for assign.py / the existing fixture-driven selftest proofs.
        `_canonical_of()` is resolved PER ROW HERE (query time), not cached
        at `_load()` time — so `_LEGACY_TO_CANONICAL` is a genuinely live
        mapping (a revert takes effect immediately, no reload needed; see
        the selftest's fail-on-revert check)."""
        canonical_query = work_class is not None and work_class in CANONICAL_WORK_CLASSES
        out = []
        for r in self._rows:
            if r["model"] != model:
                continue
            if real_only and r["source"] not in _REAL_OUTCOME_SOURCES:
                continue
            if not include_provisional and r["stage"] != _ACTIVE_STAGE:
                continue
            if work_class is not None:
                if canonical_query:
                    if _canonical_of(r["work_class"]) != work_class:
                        continue
                elif r["work_class"] != work_class:
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

        # AGGREGATE-N (#16): smooth the numeric bench-score aggregate over its N
        # repeat runs and publish the noise band, instead of a bare mean that
        # trusted a single run like a multi-run average.
        mean_bench, bench_sd, bench_band = _score_stats(bench_scores)

        return Grade(
            model=model, requested_work_class=requested, used_work_class=used,
            fallback_used=fallback, n=n, merge=merge, block=block, fixes=fixes,
            merge_pct=merge_pct, block_pct=block_pct, score=score,
            low_confidence=low_confidence,
            mean_bench_score=mean_bench,
            mean_cost_usd=mean(costs) if costs else None,
            mean_time_s=mean(times) if times else None,
            corrections_total=corr_total,
            bench_score_stddev=bench_sd,
            bench_score_band=bench_band,
            bench_score_n=len(bench_scores),
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
