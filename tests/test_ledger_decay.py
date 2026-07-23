from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from charon.routing_policy import (
    ModelSignalEntry,
    apply_decay,
    model_signal_weight,
    rank_by_decayed_score,
)

_NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=UTC)
_DAY = timedelta(days=1)


# --------------------------------------------------------------------------- failure tests


def test_naive_datetime_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        model_signal_weight(learned_at=datetime(2026, 1, 1))


def test_negative_half_life_raises():
    with pytest.raises(ValueError, match="half_life_days"):
        model_signal_weight(
            learned_at=_NOW - _DAY * 10,
            as_of=_NOW,
            half_life_days=-1,
        )


def test_zero_half_life_raises():
    with pytest.raises(ValueError, match="half_life_days"):
        model_signal_weight(
            learned_at=_NOW - _DAY * 10,
            as_of=_NOW,
            half_life_days=0,
        )


def test_future_learned_at_returns_zero():
    w = model_signal_weight(learned_at=_NOW + _DAY * 7, as_of=_NOW)
    assert w == 0.0


def test_empty_list_returns_empty():
    assert rank_by_decayed_score([], as_of=_NOW) == []


# --------------------------------------------------------------------------- decay math


def test_fresh_signal_weighs_nearly_one():
    w = model_signal_weight(
        learned_at=_NOW - timedelta(hours=1),
        as_of=_NOW,
    )
    # 1 hour is negligible vs 30d half-life → weight ≈ 1.0
    assert w == pytest.approx(1.0, abs=1e-3)


def test_one_half_life_weighs_half():
    w = model_signal_weight(
        learned_at=_NOW - _DAY * 30,
        as_of=_NOW,
        half_life_days=30.0,
    )
    assert w == pytest.approx(0.5, abs=1e-4)


def test_two_half_lives_weighs_quarter():
    w = model_signal_weight(
        learned_at=_NOW - _DAY * 60,
        as_of=_NOW,
        half_life_days=30.0,
    )
    assert w == pytest.approx(0.25, abs=1e-4)


def test_custom_half_life():
    w = model_signal_weight(
        learned_at=_NOW - _DAY * 7,
        as_of=_NOW,
        half_life_days=7.0,
    )
    assert w == pytest.approx(0.5, abs=1e-4)


def test_last_referenced_extends_anchor():
    w = model_signal_weight(
        learned_at=_NOW - _DAY * 60,
        last_referenced=_NOW - _DAY * 15,
        as_of=_NOW,
        half_life_days=30.0,
    )
    # anchor is max(learned, min(referenced, observed)) = max(-60, -15) = -15 days
    # 15 days / 30 day half-life = 0.5 → exp2(-0.5) = 0.7071
    assert w == pytest.approx(math.exp2(-15.0 / 30.0), abs=1e-4)


# --- fail-on-revert: old signal down-weighted vs fresh


def test_old_signal_down_weighted_vs_fresh():
    fresh = ModelSignalEntry(
        model_id="model-a",
        raw_score=100.0,
        learned_at=_NOW - _DAY * 5,
    )
    stale = ModelSignalEntry(
        model_id="model-b",
        raw_score=100.0,
        learned_at=_NOW - _DAY * 60,
    )
    fresh_w = apply_decay(fresh, as_of=_NOW)
    stale_w = apply_decay(stale, as_of=_NOW)
    assert fresh_w > stale_w, "old signal must be down-weighted vs fresh"
    assert stale_w < fresh_w * 0.75, "stale should be notably smaller"


# --- green-is-not-proof: ranking flips due to decay


def test_ranking_flips_because_of_decay():
    entries = [
        ModelSignalEntry("model-old", raw_score=60.0, learned_at=_NOW - _DAY * 20),
        ModelSignalEntry("model-young", raw_score=50.0, learned_at=_NOW - _DAY * 5),
    ]
    ranked_raw = sorted(entries, key=lambda e: e.raw_score, reverse=True)
    assert ranked_raw[0].model_id == "model-old"
    assert ranked_raw[1].model_id == "model-young"

    ranked_decayed = rank_by_decayed_score(entries, as_of=_NOW, half_life_days=30.0)
    assert ranked_decayed[0].model_id == "model-young"
    assert ranked_decayed[1].model_id == "model-old"


def test_ranking_flips_stale_high_score_loses_to_fresh_lower_score():
    entries = [
        ModelSignalEntry("model-stale", raw_score=90.0, learned_at=_NOW - _DAY * 90),
        ModelSignalEntry("model-fresh", raw_score=50.0, learned_at=_NOW - _DAY * 2),
    ]
    ranked_raw = sorted(entries, key=lambda e: e.raw_score, reverse=True)
    assert ranked_raw[0].model_id == "model-stale"
    assert ranked_raw[1].model_id == "model-fresh"

    ranked_decayed = rank_by_decayed_score(entries, as_of=_NOW, half_life_days=30.0)
    assert ranked_decayed[0].model_id == "model-fresh"
    assert ranked_decayed[1].model_id == "model-stale"


# --- routing-path integration


def test_decay_is_exported_via_routing_policy():
    from charon import routing_policy
    assert hasattr(routing_policy, "ModelSignalEntry")
    assert hasattr(routing_policy, "model_signal_weight")
    assert hasattr(routing_policy, "apply_decay")
    assert hasattr(routing_policy, "rank_by_decayed_score")


def test_apply_decay_is_wired_as_routing_utility():
    from charon.routing_policy import apply_decay as routed_decay
    from charon.routing_policy.ledger_decay import apply_decay as direct_decay
    assert routed_decay is direct_decay


def test_ranking_path_changes_order_when_decay_applied():
    entries = [
        ModelSignalEntry("model-a", raw_score=90.0, learned_at=_NOW - _DAY * 90),
        ModelSignalEntry("model-b", raw_score=85.0, learned_at=_NOW - _DAY * 2),
        ModelSignalEntry("model-c", raw_score=80.0, learned_at=_NOW - _DAY * 1),
    ]
    raw_order = [e.model_id for e in sorted(entries, key=lambda e: e.raw_score, reverse=True)]
    decayed_order = [e.model_id for e in rank_by_decayed_score(entries, as_of=_NOW)]

    assert raw_order == ["model-a", "model-b", "model-c"]
    assert decayed_order != raw_order
    assert decayed_order[0] == "model-b"
    assert decayed_order[1] == "model-c"
    assert decayed_order[2] == "model-a"
