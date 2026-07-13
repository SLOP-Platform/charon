"""EFFORT-ESTIMATOR — the scoring brain for the decompose gate's EFFORT axis.

DECOMPOSE-DEFAULT-GATE decomposes on change SURFACE (owns split into >1
provably-independent module group, ``decompose_surface.change_surface``). That
axis is BLIND to "single-file / coupled but LARGE-and-slow" work — one file
touched by a hard, many-behavior ticket never trips the surface gate at all.

This module is that missing EFFORT axis, built as an isolated, pure,
deterministic scoring brain (no network, no clock, no RNG, stdlib-only —
mirrors the rest of ``src/charon``). It does NOT wire into ``intake.py`` — a
separate thin "wire" ticket hooks ``estimate_effort``/``effort_verdict`` into
the gate later (DECOMPOSE-EFFORT-AXIS ds-note).

Effort combines three signals, all read off the ticket + (optional) change
surface — never invented:

  * ``difficulty`` — the ticket's own 1-5 difficulty field (board convention;
    see e.g. DECOMPOSE-EFFORT-AXIS.md's own frontmatter).
  * change SIZE — blast-radius file count / call-site count, from a
    ``decompose_surface.change_surface`` facts dict when the caller has one;
    otherwise a compute-free fallback (the ticket's own declared ``owns``
    count) so this module never has to parse source itself.
  * BEHAVIOR count — the number of distinct required behaviors, parsed from
    the ticket's ``accept`` field (a list of fail-on-revert bullets, or a
    prose/bulleted block — board tickets write ``accept`` either way).

``effort_verdict`` turns a score into one of three bands. The SOFT band is
advisory (warn, still admit — some work is irreducibly one-file-but-big, and
forcing artificial seams there is worse); only the HARD band is a clear
over-scope call. Both bands are calibrated PER EXECUTOR TIER via
``tier_threshold`` — a 21-minute Opus-tier task is not the same effort as a
21-minute weak-tier task, so the same raw score can land in different bands
depending on which tier would execute it.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------- weights
# Fixed, documented combination weights. Tunable, but a constant revert of the
# whole computation (e.g. always returning a fixed EffortScore) is caught by
# the fail-on-revert test — these weights are not the load-bearing guarantee,
# the *combination itself* is.
DIFFICULTY_WEIGHT = 2.0
SIZE_WEIGHT = 0.15
BEHAVIOR_WEIGHT = 1.0

MIN_DIFFICULTY = 1
MAX_DIFFICULTY = 5
DEFAULT_DIFFICULTY = 3  # sane mid-point when the ticket omits it

# --------------------------------------------------------------------- bands
# Soft = advisory ("advise-split", still admitted). Hard = clear over-scope.
DEFAULT_SOFT_THRESHOLD = 10.0
DEFAULT_HARD_THRESHOLD = 16.0

# Sane per-tier defaults used when no scorecard actuals are available. A
# stronger tier can absorb more raw effort before the same band trips; a
# weaker one trips sooner. Unknown tier names fall back to 1.0 (no scaling).
DEFAULT_TIER_MULTIPLIER: dict[str, float] = {
    "strong": 1.4,
    "high": 1.4,
    "opus": 1.6,
    "mid": 1.0,
    "default": 1.0,
    "med": 1.0,
    "weak": 0.65,
    "cheap": 0.65,
    "low": 0.65,
}

# Reference tier used to turn absolute per-tier actuals into a relative
# multiplier (actual-for-tier / actual-for-reference-tier).
REFERENCE_TIER = "strong"

# Multiplier is clamped so one wildly-off actual sample can't blow the
# threshold out to somewhere nonsensical.
MIN_MULTIPLIER = 0.25
MAX_MULTIPLIER = 4.0

Verdict = str  # "ok" | "advise-split" | "over-scope"


# --------------------------------------------------------------------- score

@dataclass(frozen=True)
class EffortScore:
    """The three raw signals plus the combined, tier-agnostic total.

    ``total`` is deliberately NOT tier-scaled — ``effort_verdict``/
    ``tier_threshold`` apply the tier scaling at verdict time, so the same
    score can be compared across tiers (that is the whole point of the axis).
    """

    difficulty: int
    size: float
    behaviors: int
    total: float
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EffortThreshold:
    """A tier-calibrated pair of bands: ``soft`` (advisory) and ``hard``
    (over-scope). ``hard`` is always >= ``soft``."""

    soft: float
    hard: float


def estimate_effort(ticket: Any, surface: Mapping[str, object] | None = None) -> EffortScore:
    """Combine ``ticket``'s difficulty + behavior count with a change-size
    estimate into one :class:`EffortScore`.

    ``ticket`` is duck-typed: either a mapping (board frontmatter shape, e.g.
    ``{"difficulty": 3, "owns": [...], "accept": "..."}``) or an object with
    matching attributes (e.g. ``intake.PlanUnit``). ``surface`` is, when
    given, a ``decompose_surface.change_surface(...)`` facts dict — the SIZE
    signal then reads its blast-radius/call-edge counts. Without a surface,
    SIZE compute-free-falls-back to the ticket's own declared owned-file
    count (never parses source itself).
    """
    difficulty = _difficulty(ticket)
    size, size_note = _size(ticket, surface)
    behaviors, behavior_note = _behaviors(ticket)

    total = (
        difficulty * DIFFICULTY_WEIGHT
        + size * SIZE_WEIGHT
        + behaviors * BEHAVIOR_WEIGHT
    )
    notes = (
        f"difficulty={difficulty} (weight {DIFFICULTY_WEIGHT})",
        size_note,
        behavior_note,
    )
    return EffortScore(
        difficulty=difficulty, size=size, behaviors=behaviors, total=round(total, 3),
        notes=notes,
    )


def effort_verdict(
    score: EffortScore,
    tier: str | None = None,
    *,
    actuals: TierActuals = None,
) -> Verdict:
    """Classify ``score`` against the (tier-calibrated) bands.

    Returns ``"ok"`` below the soft band, ``"advise-split"`` at/above soft but
    below hard (ADVISORY — the caller should warn and record, but still
    admit the ticket), and ``"over-scope"`` at/above hard (the only HARD
    verdict — the caller should split further or flag for a human).
    """
    threshold = tier_threshold(tier, actuals)
    if score.total >= threshold.hard:
        return "over-scope"
    if score.total >= threshold.soft:
        return "advise-split"
    return "ok"


# ----------------------------------------------------------- tier calibration

# What ``tier_threshold`` accepts as "actuals": a ready-made tier->avg-effort
# map, an iterable of row-like objects/mappings each exposing a tier + an
# actual-effort value, or a filesystem path to a ``ScorecardStore`` root (the
# latest GOOD artifact's rows are read; per-row ``metadata`` is consulted for
# ``tier``/``avg_minutes``). ``None`` degrades to the sane per-tier defaults.
TierActuals = Mapping[str, float] | Iterable[object] | str | Path | None

_ACTUAL_VALUE_KEYS = ("avg_minutes", "avg_build_minutes", "minutes", "actual", "value")


def tier_threshold(tier: str | None, actuals: TierActuals = None) -> EffortThreshold:
    """Derive the (soft, hard) bands for ``tier``.

    Self-calibrating: when ``actuals`` carries a per-tier average build-time
    (or other effort-actual), the bands scale by
    ``actual[REFERENCE_TIER] / actual[tier]`` (clamped) instead of the fixed
    default table — a tier that takes LONGER for the same ticket is the
    weaker one, so it gets a LOWER threshold (trips sooner). This tracks how
    THIS fleet's tiers actually perform, not a guess. Degrades to
    :data:`DEFAULT_TIER_MULTIPLIER` (a sane
    per-tier default that still varies by tier) when no usable actuals are
    supplied, and to no scaling at all (multiplier 1.0) for an unknown or
    absent tier name.
    """
    multiplier = _tier_multiplier(tier, actuals)
    return EffortThreshold(
        soft=round(DEFAULT_SOFT_THRESHOLD * multiplier, 3),
        hard=round(DEFAULT_HARD_THRESHOLD * multiplier, 3),
    )


def _tier_multiplier(tier: str | None, actuals: TierActuals) -> float:
    if not tier:
        return 1.0
    table = _resolve_actuals_table(actuals)
    if table:
        reference = table.get(REFERENCE_TIER)
        if reference is None:
            reference = statistics.mean(table.values())
        value = table.get(tier)
        if value is not None and value and reference:
            # Actuals are a build-TIME (e.g. avg minutes): a tier that takes
            # LONGER for the same ticket is the weaker one, so it must get a
            # LOWER threshold (trips sooner) — hence reference / value, not
            # value / reference.
            return _clamp(reference / value, MIN_MULTIPLIER, MAX_MULTIPLIER)
    return DEFAULT_TIER_MULTIPLIER.get(tier, 1.0)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _resolve_actuals_table(actuals: TierActuals) -> dict[str, float] | None:
    """Normalize any accepted ``actuals`` shape into a plain tier->float map."""
    if actuals is None:
        return None
    if isinstance(actuals, (str, Path)):
        return _load_scorecard_actuals(Path(actuals))
    if isinstance(actuals, Mapping):
        try:
            return {str(k): float(v) for k, v in actuals.items()}  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
    if isinstance(actuals, Iterable):
        grouped: dict[str, list[float]] = defaultdict(list)
        for row in actuals:
            t = _field(row, "tier", None)
            v = None
            for key in _ACTUAL_VALUE_KEYS:
                v = _field(row, key, None)
                if v is not None:
                    break
            if t and v is not None:
                try:
                    grouped[str(t)].append(float(v))
                except (TypeError, ValueError):
                    continue
        if not grouped:
            return None
        return {t: statistics.mean(vs) for t, vs in grouped.items()}
    return None


def _load_scorecard_actuals(root: Path) -> dict[str, float] | None:
    """Read per-tier actuals out of a ``ScorecardStore`` root's latest GOOD
    artifact. Never creates the directory (unlike ``ScorecardStore.__init__``,
    which mkdirs unconditionally) — a missing/bad path just degrades to the
    sane default, it never has a filesystem side effect."""
    if not root.is_dir():
        return None
    try:
        from .capability.scorecard import ScorecardStore
    except ImportError:
        return None
    try:
        artifact = ScorecardStore(root).read_latest()
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if artifact is None:
        return None
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in artifact.rows:
        t = row.metadata.get("tier")
        v = None
        for key in _ACTUAL_VALUE_KEYS:
            v = row.metadata.get(key)
            if v is not None:
                break
        if t and v is not None:
            try:
                grouped[str(t)].append(float(v))
            except (TypeError, ValueError):
                continue
    if not grouped:
        return None
    return {t: statistics.mean(vs) for t, vs in grouped.items()}


# ------------------------------------------------------------------ signals

def _difficulty(ticket: Any) -> int:
    raw = _field(ticket, "difficulty", DEFAULT_DIFFICULTY)
    try:
        value = int(round(float(raw)))
    except (TypeError, ValueError):
        value = DEFAULT_DIFFICULTY
    return int(_clamp(value, MIN_DIFFICULTY, MAX_DIFFICULTY))


def _size(ticket: Any, surface: Mapping[str, object] | None) -> tuple[float, str]:
    if surface is not None:
        files = _as_list(surface.get("files"))
        call_edges = _as_list(surface.get("call_edges"))
        blast_radius = surface.get("blast_radius")
        blast_total = 0
        if isinstance(blast_radius, Mapping):
            blast_total = sum(len(_as_list(v)) for v in blast_radius.values())
        size = float(len(files) + len(call_edges) + blast_total)
        note = (
            f"size={size:g} (surface: {len(files)} files, {len(call_edges)} call "
            f"edges, {blast_total} blast-radius entries; weight {SIZE_WEIGHT})"
        )
        return size, note

    # Compute-free fallback: no source parsing, just what the ticket declares.
    owns = _field(ticket, "owns", None)
    if owns is None:
        owns = _field(ticket, "owned_paths", None)
    owned = _as_list(owns)
    size = float(max(1, len(owned)))
    note = f"size={size:g} (compute-free fallback: {len(owned)} declared owned path(s))"
    return size, note


_BULLET_RE = re.compile(r"^(?:[-*]\s+|\d+[.)]\s+)")


def _behaviors(ticket: Any) -> tuple[int, str]:
    raw = _field(ticket, "accept", None)
    source = "accept"
    if raw is None:
        raw = _field(ticket, "accept_criteria", None)
        source = "accept_criteria"
    items = _split_behavior_items(raw)
    return len(items), f"behaviors={len(items)} (parsed from {source!r})"


def _split_behavior_items(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    bullets = [ln for ln in lines if _BULLET_RE.match(ln)]
    if bullets:
        return bullets
    # No bullet markup (a prose accept block, e.g. board "accept: |" text) —
    # fall back to splitting on sentence boundaries as a distinct-behavior proxy.
    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]
    return sentences or [text]


# ------------------------------------------------------------------ ticket access

def _field(obj: Any, name: str, default: Any = None) -> Any:
    """Duck-typed field access: mapping ``.get`` first, else ``getattr``."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]
