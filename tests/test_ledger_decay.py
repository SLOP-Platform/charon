"""Tests for router-side model-signal ledger decay.

FAIL-ON-REVERT: if decay weighting is removed from the routing path or the
old-vs-fresh down-weight check is removed, these tests go RED.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

# Load ledger_decay from our source tree and inject it into the charon
# package namespace.  This is necessary because the charon-product source
# lives in a separate checkout (/home/stack/code/charon) while our module
# adds a new file to the routing_policy package.
_ledger_module_name = "charon.routing_policy.ledger_decay"
_src_dir = Path(__file__).resolve().parent.parent / "src"
_spec = importlib.util.spec_from_file_location(
    _ledger_module_name,
    str(_src_dir / "charon" / "routing_policy" / "ledger_decay.py"),
)
_ledger_mod = importlib.util.module_from_spec(_spec)
sys.modules[_ledger_module_name] = _ledger_mod
_spec.loader.exec_module(_ledger_mod)

from charon.routing_policy.ledger_decay import (  # noqa: E402
    ModelSignalEntry,
    apply_ledger_decay,
    signal_decay_weight,
)

_T30 = timedelta(days=30)
_T60 = timedelta(days=60)
_T300 = timedelta(days=300)


class TestSignalDecayWeight:
    """Unit tests for the raw decay-weight function."""

    def test_fresh_signal_has_full_weight(self):
        now = datetime.now(timezone.utc)
        w = signal_decay_weight(learned_at=now, as_of=now)
        assert w == pytest.approx(1.0)

    def test_stale_signal_at_one_half_life(self):
        now = datetime.now(timezone.utc)
        half_life_ago = now - _T30
        w = signal_decay_weight(learned_at=half_life_ago, as_of=now)
        assert w == pytest.approx(0.5)

    def test_very_stale_signal_near_zero(self):
        now = datetime.now(timezone.utc)
        very_old = now - _T300
        w = signal_decay_weight(learned_at=very_old, as_of=now)
        assert w == pytest.approx(2.0 ** -10)

    def test_old_downweighted_vs_fresh(self):
        now = datetime.now(timezone.utc)
        old = now - _T60
        fresh = now - timedelta(hours=1)
        w_old = signal_decay_weight(learned_at=old, as_of=now)
        w_fresh = signal_decay_weight(learned_at=fresh, as_of=now)
        assert w_old < w_fresh

    def test_naive_datetime_raises(self):
        with pytest.raises(ValueError, match="naive"):
            signal_decay_weight(
                learned_at=datetime(2024, 1, 1),
                as_of=datetime.now(timezone.utc),
            )

    def test_non_positive_half_life_raises(self):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValueError, match="positive"):
            signal_decay_weight(learned_at=now, as_of=now, half_life_days=0)
        with pytest.raises(ValueError, match="positive"):
            signal_decay_weight(learned_at=now, as_of=now, half_life_days=-1)

    def test_non_finite_half_life_raises(self):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValueError, match="finite"):
            signal_decay_weight(learned_at=now, as_of=now, half_life_days=float("nan"))
        with pytest.raises(ValueError, match="finite"):
            signal_decay_weight(learned_at=now, as_of=now, half_life_days=float("inf"))

    def test_last_referenced_overrides_learned_at(self):
        now = datetime.now(timezone.utc)
        very_old = now - _T300
        recent = now - timedelta(days=5)
        w = signal_decay_weight(
            learned_at=very_old, last_referenced=recent, as_of=now,
        )
        assert w == pytest.approx(2.0 ** (-5 / 30))

    def test_future_anchor_returns_full_weight(self):
        now = datetime.now(timezone.utc)
        future = now + _T30
        w = signal_decay_weight(learned_at=future, as_of=now)
        assert w == pytest.approx(1.0)

    def test_custom_half_life(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=10)
        w = signal_decay_weight(learned_at=old, as_of=now, half_life_days=10.0)
        assert w == pytest.approx(0.5)

    def test_default_as_of_is_utc_now(self):
        old = datetime.now(timezone.utc) - _T30
        w = signal_decay_weight(learned_at=old)
        assert 0.0 < w < 1.0


class TestApplyLedgerDecay:
    """Tests for the ranking-level decay application."""

    def test_old_signal_downweighted_vs_fresh_equal_raw_score(self):
        """FAIL-ON-REVERT: an old signal is down-weighted vs a fresh one
        of equal raw score — decay is actually applied in the ranking path,
        not just defined."""
        now = datetime.now(timezone.utc)
        entries = [
            ModelSignalEntry(
                model_id="old", score=100.0,
                learned_at=now - _T60,
            ),
            ModelSignalEntry(
                model_id="fresh", score=100.0,
                learned_at=now - timedelta(hours=1),
            ),
        ]
        result = apply_ledger_decay(entries, as_of=now)
        assert result[0][0].model_id == "fresh"
        assert result[0][1] > result[1][1]

    def test_ranking_flips_because_of_decay(self):
        """GREEN-IS-NOT-PROOF: a routing decision flips because a stale
        model signal decayed — not merely that the math function returns
        a smaller number.

        Without decay: old-but-high (score=80) > fresh-but-lower (score=70),
        so the old signal wins.  With decay the old signal decays below the
        fresh one, changing the rank order.  This demonstrates a real routing
        consequence, not just a smaller number.
        """
        now = datetime.now(timezone.utc)
        entries = [
            ModelSignalEntry(
                model_id="old-but-high", score=80.0,
                learned_at=now - _T60,
            ),
            ModelSignalEntry(
                model_id="fresh-but-lower", score=70.0,
                learned_at=now - timedelta(hours=1),
            ),
        ]
        result = apply_ledger_decay(entries, as_of=now)
        assert result[0][0].model_id == "fresh-but-lower", (
            "Without decay the old signal (80) outranks the fresh one (70); "
            "with decay the old signal decays to ~20 and the fresh stays ~70, "
            "so the ranking flips."
        )

    def test_decay_disabled_giant_half_life(self):
        """With a giant half-life, decay is negligible and raw order holds."""
        now = datetime.now(timezone.utc)
        entries = [
            ModelSignalEntry(
                model_id="old", score=80.0,
                learned_at=now - _T60,
            ),
            ModelSignalEntry(
                model_id="fresh", score=70.0,
                learned_at=now - timedelta(hours=1),
            ),
        ]
        result = apply_ledger_decay(entries, as_of=now, half_life_days=1e6)
        assert result[0][0].model_id == "old"

    def test_empty_entries(self):
        result = apply_ledger_decay([])
        assert result == []

    def test_single_entry_unchanged(self):
        now = datetime.now(timezone.utc)
        entry = ModelSignalEntry(model_id="m1", score=50.0, learned_at=now)
        result = apply_ledger_decay([entry], as_of=now)
        assert len(result) == 1
        assert result[0][0].model_id == "m1"
        assert result[0][1] == pytest.approx(50.0)

    def test_last_referenced_anchors_decay(self):
        """A signal with recent last_referenced decays less than one without."""
        now = datetime.now(timezone.utc)
        entries = [
            ModelSignalEntry(
                model_id="referenced-recently", score=100.0,
                learned_at=now - _T60,
                last_referenced=now - timedelta(days=5),
            ),
            ModelSignalEntry(
                model_id="not-referenced", score=100.0,
                learned_at=now - _T60,
                last_referenced=None,
            ),
        ]
        result = apply_ledger_decay(entries, as_of=now)
        assert result[0][0].model_id == "referenced-recently"
