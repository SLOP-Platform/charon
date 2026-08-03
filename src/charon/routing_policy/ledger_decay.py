"""Router-side model-signal ledger decay — exponential half-life weighting.

Provides pure-stdlib functions to decay model-signal ledger entries by their
age, so stale benchmark/outcome signals lose weight over time.  Designed to be
plugged into the ranking path that consumes the model-signal/actuals ledger.

Reference: retired fleet/memory/bitemporal.py (FN2) — same exp2 half-life math,
but relocated from fleet/memory/ into the router package.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

_DEFAULT_HALF_LIFE_DAYS: Final[float] = 30.0
_SECONDS_PER_DAY: Final[float] = 86_400.0


@dataclass(frozen=True)
class ModelSignalEntry:
    """A single model-signal or outcome-ledger entry for routing.

    Attributes:
        model_id:   Model identifier.
        score:      Raw signal score (higher = better).
        learned_at: When the signal was first observed/learned.
        last_referenced: When the signal was last confirmed relevant
                        (if *None*, falls back to *learned_at*).
    """
    model_id: str
    score: float
    learned_at: datetime
    last_referenced: datetime | None = None


def signal_decay_weight(
    *,
    learned_at: datetime,
    last_referenced: datetime | None = None,
    as_of: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """Compute the exponential half-life decay weight for a signal.

    ``decayed_weight = 2 ** (-age_days / half_life_days)``

    The age is computed from *last_referenced* when available (the most recent
    confirmation the signal was relevant), falling back to *learned_at*.

    A signal anchored in the future (age < 0) returns weight 1.0 — no decay.

    Raises ``ValueError`` for non-positive or non-finite *half_life_days*, or
    for naive (timezone-unaware) datetimes.
    """
    if half_life_days <= 0:
        raise ValueError(f"half_life_days must be positive, got {half_life_days}")
    if not math.isfinite(half_life_days):
        raise ValueError(f"half_life_days must be finite, got {half_life_days}")

    as_of = as_of or datetime.now(timezone.utc)
    anchor = last_referenced or learned_at

    if anchor.tzinfo is None:
        raise ValueError("naive datetime not supported for anchor; use timezone-aware")
    if as_of.tzinfo is None:
        raise ValueError("naive datetime not supported for as_of; use timezone-aware")

    age_seconds = (as_of - anchor).total_seconds()
    if age_seconds < 0:
        return 1.0

    age_days = age_seconds / _SECONDS_PER_DAY
    return math.pow(2.0, -age_days / half_life_days)


def apply_ledger_decay(
    entries: list[ModelSignalEntry],
    *,
    as_of: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> list[tuple[ModelSignalEntry, float]]:
    """Apply exponential decay to model-signal ledger entries.

    Each entry's raw ``score`` is multiplied by its decay weight to produce a
    ``decayed_score``.  Results are returned sorted by ``decayed_score``
    descending (highest first), ready to be consumed by the ranking path.

    Args:
        entries:        Model-signal ledger entries to decay.
        as_of:          Reference timestamp (defaults to UTC now).
        half_life_days: Half-life in days (default 30).

    Returns:
        List of ``(entry, decayed_score)`` pairs sorted descending by score.
    """
    scored: list[tuple[ModelSignalEntry, float]] = []
    for e in entries:
        w = signal_decay_weight(
            learned_at=e.learned_at,
            last_referenced=e.last_referenced,
            as_of=as_of,
            half_life_days=half_life_days,
        )
        scored.append((e, e.score * w))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
