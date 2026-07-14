from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

_DEFAULT_HALF_LIFE_DAYS: Final[float] = 30.0
_SECONDS_PER_DAY: Final[float] = 86_400.0


@dataclass(frozen=True, slots=True)
class BitemporalRecord:
    valid_from: datetime
    learned_at: datetime
    valid_until: datetime | None = None
    last_referenced: datetime | None = None

    def weight(
        self,
        *,
        as_of: datetime | None = None,
        known_at: datetime | None = None,
        half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
    ) -> float:
        return bitemporal_weight(
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            learned_at=self.learned_at,
            last_referenced=self.last_referenced,
            as_of=as_of,
            known_at=known_at,
            half_life_days=half_life_days,
        )


def bitemporal_weight(
    *,
    valid_from: datetime,
    learned_at: datetime,
    valid_until: datetime | None = None,
    last_referenced: datetime | None = None,
    as_of: datetime | None = None,
    known_at: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    if half_life_days <= 0 or not math.isfinite(half_life_days):
        raise ValueError("half_life_days must be finite and greater than zero")

    observed_at = _utc(as_of or datetime.now(timezone.utc), "as_of")
    knowledge_at = _utc(known_at or observed_at, "known_at")
    start = _utc(valid_from, "valid_from")
    learned = _utc(learned_at, "learned_at")
    end = _utc(valid_until, "valid_until") if valid_until is not None else None
    referenced = (
        _utc(last_referenced, "last_referenced")
        if last_referenced is not None
        else None
    )

    if end is not None and end <= start:
        raise ValueError("valid_until must be later than valid_from")
    if learned > knowledge_at or observed_at < start:
        return 0.0
    if start > knowledge_at:
        return 0.0
    if end is not None and observed_at >= end:
        return 0.0

    anchor = max(start, learned)
    if referenced is not None:
        anchor = max(anchor, min(referenced, observed_at, knowledge_at))
    age_days = max(0.0, (min(observed_at, knowledge_at) - anchor).total_seconds())
    return math.exp2(-(age_days / _SECONDS_PER_DAY) / half_life_days)


def memory_fact_weight(
    fact: BitemporalRecord,
    *,
    as_of: datetime | None = None,
    known_at: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    return fact.weight(
        as_of=as_of,
        known_at=known_at,
        half_life_days=half_life_days,
    )


def model_signal_weight(
    signal: BitemporalRecord,
    *,
    as_of: datetime | None = None,
    known_at: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    return signal.weight(
        as_of=as_of,
        known_at=known_at,
        half_life_days=half_life_days,
    )


def apply_memory_decay(
    score: float,
    fact: BitemporalRecord,
    *,
    as_of: datetime | None = None,
    known_at: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    return score * memory_fact_weight(
        fact,
        as_of=as_of,
        known_at=known_at,
        half_life_days=half_life_days,
    )


def apply_model_signal_decay(
    score: float,
    signal: BitemporalRecord,
    *,
    as_of: datetime | None = None,
    known_at: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    return score * model_signal_weight(
        signal,
        as_of=as_of,
        known_at=known_at,
        half_life_days=half_life_days,
    )


def should_curate(
    fact: BitemporalRecord,
    *,
    as_of: datetime | None = None,
    known_at: datetime | None = None,
    threshold: float = 0.25,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> bool:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between zero and one")
    return memory_fact_weight(
        fact,
        as_of=as_of,
        known_at=known_at,
        half_life_days=half_life_days,
    ) < threshold


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)
