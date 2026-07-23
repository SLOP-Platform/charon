from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

_DEFAULT_HALF_LIFE_DAYS: Final[float] = 30.0
_SECONDS_PER_DAY: Final[float] = 86_400.0


@dataclass(frozen=True)
class ModelSignalEntry:
    model_id: str
    raw_score: float
    learned_at: datetime
    last_referenced: datetime | None = None


def model_signal_weight(
    *,
    learned_at: datetime,
    last_referenced: datetime | None = None,
    as_of: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    if half_life_days <= 0 or not math.isfinite(half_life_days):
        raise ValueError("half_life_days must be finite and greater than zero")

    now = _utc(as_of or datetime.now(UTC))
    learned = _utc(learned_at, "learned_at")

    if learned > now:
        return 0.0

    anchor = learned
    if last_referenced is not None:
        ref = _utc(last_referenced, "last_referenced")
        if ref < now:
            anchor = max(learned, ref)

    age_days = max(0.0, (now - anchor).total_seconds() / _SECONDS_PER_DAY)
    return math.exp2(-age_days / half_life_days)


def apply_decay(
    entry: ModelSignalEntry,
    *,
    as_of: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    w = model_signal_weight(
        learned_at=entry.learned_at,
        last_referenced=entry.last_referenced,
        as_of=as_of,
        half_life_days=half_life_days,
    )
    return entry.raw_score * w


def rank_by_decayed_score(
    entries: list[ModelSignalEntry],
    *,
    as_of: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> list[ModelSignalEntry]:
    if not entries:
        return []
    return sorted(
        entries,
        key=lambda e: apply_decay(e, as_of=as_of, half_life_days=half_life_days),
        reverse=True,
    )


def _utc(value: datetime, field: str = "datetime") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)
