from __future__ import annotations

import importlib.util
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent
_MODULE_PATH = _ROOT.parent / "memory" / "bitemporal.py"
_SPEC = importlib.util.spec_from_file_location(
    "fleet_memory_bitemporal",
    _MODULE_PATH,
)
assert _SPEC and _SPEC.loader, "could not load bitemporal module spec"
bitemporal = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = bitemporal
_SPEC.loader.exec_module(bitemporal)

BitemporalRecord = bitemporal.BitemporalRecord
bitemporal_weight = bitemporal.bitemporal_weight
memory_fact_weight = bitemporal.memory_fact_weight
model_signal_weight = bitemporal.model_signal_weight
apply_memory_decay = bitemporal.apply_memory_decay
apply_model_signal_decay = bitemporal.apply_model_signal_decay
should_curate = bitemporal.should_curate


def _at(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


NOW = _at(2026, 7, 14)


def test_bitemporal_weight_fresh_one_stale_decays():
    fresh_learned = _at(2026, 7, 13)
    stale_learned = _at(2025, 1, 1)

    fresh = BitemporalRecord(
        valid_from=_at(2026, 7, 1),
        learned_at=fresh_learned,
        last_referenced=fresh_learned,
    )
    stale = BitemporalRecord(
        valid_from=_at(2025, 1, 1),
        learned_at=stale_learned,
        last_referenced=stale_learned,
    )

    w_fresh = memory_fact_weight(fresh, as_of=NOW, half_life_days=30.0)
    w_stale = memory_fact_weight(stale, as_of=NOW, half_life_days=30.0)

    assert w_fresh == pytest.approx(math.exp2(-1 / 30), rel=1e-9)
    assert 0.0 < w_stale < w_fresh
    assert w_stale < 0.5
    assert w_fresh > w_stale * 10


def test_apply_memory_decay_downweights_stale_facts():
    base_score = 1.0
    fresh = BitemporalRecord(
        valid_from=_at(2026, 7, 1),
        learned_at=_at(2026, 7, 13),
        last_referenced=_at(2026, 7, 13),
    )
    stale = BitemporalRecord(
        valid_from=_at(2025, 1, 1),
        learned_at=_at(2025, 1, 1),
        last_referenced=_at(2025, 1, 1),
    )

    fresh_score = apply_memory_decay(base_score, fresh, as_of=NOW)
    stale_score = apply_memory_decay(base_score, stale, as_of=NOW)

    assert fresh_score > stale_score
    assert fresh_score == pytest.approx(math.exp2(-1 / 30), rel=1e-9)
    assert stale_score < 0.1


def test_model_signal_decay_stale_vs_fresh_downweights():
    bad_score = -1.0
    stale_signal = BitemporalRecord(
        valid_from=_at(2024, 6, 1),
        learned_at=_at(2024, 6, 1),
    )
    fresh_signal = BitemporalRecord(
        valid_from=_at(2026, 7, 1),
        learned_at=_at(2026, 7, 12),
    )

    stale_eff = apply_model_signal_decay(bad_score, stale_signal, as_of=NOW)
    fresh_eff = apply_model_signal_decay(bad_score, fresh_signal, as_of=NOW)

    assert abs(stale_eff) < abs(fresh_eff)
    assert abs(stale_eff) < 1e-6
    assert fresh_eff == pytest.approx(-math.exp2(-2 / 30), rel=1e-9)
    assert abs(fresh_eff) > abs(stale_eff) * 1_000_000


def test_decay_disabled_weights_equal():
    fresh_signal = BitemporalRecord(
        valid_from=_at(2026, 7, 1),
        learned_at=_at(2026, 7, 12),
    )
    stale_signal = BitemporalRecord(
        valid_from=_at(2024, 6, 1),
        learned_at=_at(2024, 6, 1),
    )

    fresh_w = model_signal_weight(fresh_signal, as_of=NOW, half_life_days=30.0)
    stale_w = model_signal_weight(stale_signal, as_of=NOW, half_life_days=30.0)

    weight_delta = abs(fresh_w - stale_w)
    assert weight_delta > 0.3

    broken_fresh = model_signal_weight(
        fresh_signal, as_of=NOW, half_life_days=10_000_000.0
    )
    broken_stale = model_signal_weight(
        stale_signal, as_of=NOW, half_life_days=10_000_000.0
    )

    assert math.isclose(broken_fresh, broken_stale, rel_tol=1e-3)


def test_should_curate_triggers_for_stale_facts():
    stale = BitemporalRecord(
        valid_from=_at(2024, 1, 1),
        learned_at=_at(2024, 1, 1),
        last_referenced=_at(2024, 1, 1),
    )
    fresh = BitemporalRecord(
        valid_from=_at(2026, 7, 1),
        learned_at=_at(2026, 7, 13),
        last_referenced=_at(2026, 7, 13),
    )

    assert should_curate(stale, as_of=NOW, threshold=0.5)
    assert not should_curate(fresh, as_of=NOW, threshold=0.5)


def test_expired_record_zero_weight():
    expired = BitemporalRecord(
        valid_from=_at(2025, 1, 1),
        valid_until=_at(2025, 6, 1),
        learned_at=_at(2025, 1, 1),
    )

    w = memory_fact_weight(expired, as_of=NOW)
    assert w == 0.0


def test_invalid_window_rejected():
    bad = BitemporalRecord(
        valid_from=_at(2025, 6, 1),
        valid_until=_at(2025, 1, 1),
        learned_at=_at(2025, 1, 1),
    )
    with pytest.raises(ValueError):
        memory_fact_weight(bad, as_of=NOW)


def test_naive_datetime_rejected():
    record = BitemporalRecord(
        valid_from=datetime(2026, 7, 1),
        learned_at=datetime(2026, 7, 1),
    )
    with pytest.raises(ValueError):
        memory_fact_weight(record)


def test_half_life_must_be_positive_finite():
    record = BitemporalRecord(
        valid_from=_at(2026, 7, 1),
        learned_at=_at(2026, 7, 1),
    )
    with pytest.raises(ValueError):
        memory_fact_weight(record, half_life_days=0)
    with pytest.raises(ValueError):
        memory_fact_weight(record, half_life_days=math.inf)


def test_known_at_caps_future_knowledge():
    record = BitemporalRecord(
        valid_from=_at(2026, 7, 1),
        learned_at=_at(2026, 7, 13),
    )

    w_no_cap = model_signal_weight(record, as_of=NOW)
    assert w_no_cap == pytest.approx(math.exp2(-1 / 30), rel=1e-9)

    w_cap = model_signal_weight(
        record,
        as_of=NOW,
        known_at=NOW - timedelta(days=400),
    )
    assert w_cap == pytest.approx(0.0)