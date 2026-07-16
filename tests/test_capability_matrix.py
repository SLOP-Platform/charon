"""CapabilityMatrix data + query API tests.

Covers the static provider-quirk rules (reasoning-incapable providers) and the
grade query API. This module is **not yet wired** into the gateway / forwarder —
that is out of scope (later ticket / R4 work).
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from charon.capability.scorecard import ScorecardArtifact, ScorecardRow, ScorecardStore
from charon.routing_policy.matrix import (
    _DEFAULT_PROVIDER_DENIES,
    CapabilityMatrix,
)


class TestQueryAPI:
    """Grade lookup + provider capability queries."""

    def test_get_grade_missing_returns_unknown(self):
        m = CapabilityMatrix()
        assert m.get_grade("gpt-4", "reasoning") == "unknown"

    def test_set_and_get_grade(self):
        m = CapabilityMatrix()
        m.set_grade("gpt-4", "reasoning", grade="A", confidence=0.9)
        assert m.get_grade("gpt-4", "reasoning") == "A"

    def test_set_grade_overwrites_prior(self):
        m = CapabilityMatrix()
        m.set_grade("gpt-4", "coding", grade="B")
        m.set_grade("gpt-4", "coding", grade="A")
        assert m.get_grade("gpt-4", "coding") == "A"

    def test_supports_unknown_provider_defaults_true(self):
        """Providers not listed in the quirk table should default to True
        (safe assumption — no data means not known-bad)."""
        m = CapabilityMatrix()
        assert m.supports("some-new-provider", "reasoning") is True
        assert m.supports("deepseek", "coding") is True

    def test_supports_openrouter_reasoning_is_false(self):
        m = CapabilityMatrix()
        assert m.supports("openrouter", "reasoning") is False

    def test_supports_openrouter_other_classes_still_true(self):
        m = CapabilityMatrix()
        assert m.supports("openrouter", "coding") is True
        assert m.supports("openrouter", "general") is True
        assert m.supports("openrouter", "analysis") is True

    def test_supports_novita_reasoning_is_false(self):
        m = CapabilityMatrix()
        assert m.supports("novita", "reasoning") is False

    def test_supports_novita_other_classes_still_true(self):
        m = CapabilityMatrix()
        assert m.supports("novita", "creative") is True
        assert m.supports("novita", "translation") is True


class TestProviderDenyAllow:
    """Mutation of provider-level denials."""

    def test_deny_adds_restriction(self):
        m = CapabilityMatrix()
        m.deny("deepseek", "reasoning")
        assert m.supports("deepseek", "reasoning") is False

    def test_allow_removes_restriction(self):
        m = CapabilityMatrix()
        # openrouter is denied reasoning by default
        assert m.supports("openrouter", "reasoning") is False
        m.allow("openrouter", "reasoning")
        assert m.supports("openrouter", "reasoning") is True

    def test_allow_on_unknown_provider_is_noop(self):
        m = CapabilityMatrix()
        m.allow("brand-new", "reasoning")
        assert m.supports("brand-new", "reasoning") is True


class TestDefaultProviderDenies:
    """The built-in static quirk table matches ROUTER-DESIGN.md."""

    def test_defaults_include_openrouter_and_novita(self):
        assert "openrouter" in _DEFAULT_PROVIDER_DENIES
        assert "novita" in _DEFAULT_PROVIDER_DENIES
        assert _DEFAULT_PROVIDER_DENIES["openrouter"] == {"reasoning"}
        assert _DEFAULT_PROVIDER_DENIES["novita"] == {"reasoning"}

    def test_defaults_are_seeded_on_init(self):
        m = CapabilityMatrix()
        # not relying on _DEFAULT_PROVIDER_DENIES directly — exercise the instance
        assert m.supports("openrouter", "reasoning") is False
        assert m.supports("novita", "reasoning") is False

    def test_defaults_overrideable(self):
        """Caller can pass an explicit provider_denies to override defaults."""
        m = CapabilityMatrix(provider_denies={"openrouter": set()})
        assert m.supports("openrouter", "reasoning") is True
        assert m.supports("novita", "reasoning") is False  # still present via default

    @pytest.mark.parametrize(
        "wc", ["reasoning", "coding", "translation", "creative", "analysis", "general"]
    )
    def test_all_work_classes_are_valid_literals(self, wc: str):
        """Smoke: every WorkClass literal can round-trip through the API."""
        m = CapabilityMatrix()
        m.set_grade("m1", wc, "A")  # type: ignore[arg-type]
        assert m.get_grade("m1", wc) == "A"  # type: ignore[arg-type]


class TestScorecardStore:
    """ScorecardStore freeze/read/LKG fallback tests (ported from deleted test_actuals_ledger.py)."""

    def test_freeze_and_read(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")
        art = ScorecardArtifact(
            seq=1,
            timestamp=time.time(),
            rows=[
                ScorecardRow(model="gpt-4", work_class="codegen", score=0.92, samples=10),
            ],
        )
        store.freeze(art)
        loaded = store.read_latest()
        assert loaded is not None
        assert loaded.seq == 1
        assert len(loaded.rows) == 1
        assert loaded.rows[0].model == "gpt-4"
        assert loaded.rows[0].score == 0.92

    def test_latest_seq_is_incrementing(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")
        for seq in (1, 2, 3):
            store.freeze(ScorecardArtifact(seq=seq, timestamp=float(seq), rows=[]))
        assert store.latest_seq() == 3
        assert store.lkg_seq() == 3

        store.freeze(ScorecardArtifact(
            seq=4, timestamp=4.0, rows=[],
            gate_pass=False, fail_on_revert_pass=False,
        ))
        assert store.latest_seq() == 4
        assert store.lkg_seq() == 3, "LKG must stay at the last GOOD seq (3), not 4"

        loaded = store.read_latest()
        assert loaded is not None
        assert loaded.seq == 3

    def test_lkg_fallback_bad_scorecard(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")

        art1 = ScorecardArtifact(
            seq=1, timestamp=100.0,
            rows=[ScorecardRow(model="m1", work_class="wg", score=0.5, samples=1)],
            gate_pass=True, fail_on_revert_pass=True,
        )
        store.freeze(art1)

        art2 = ScorecardArtifact(
            seq=2, timestamp=200.0,
            rows=[ScorecardRow(model="m2", work_class="wg", score=0.9, samples=2)],
            gate_pass=False, fail_on_revert_pass=False,
        )
        store.freeze(art2)

        assert store.latest_seq() == 2
        assert store.lkg_seq() == 1, "LKG must be the last GOOD seq (1), not latest (2)"

        loaded = store.read_latest()
        assert loaded is not None
        assert loaded.seq == 1
        assert loaded.rows[0].model == "m1"

    def test_corrupt_latest_falls_back_to_lkg(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")

        art1 = ScorecardArtifact(
            seq=1, timestamp=100.0,
            rows=[ScorecardRow(model="m1", work_class="wg", score=0.5, samples=1)],
        )
        store.freeze(art1)

        art2 = ScorecardArtifact(
            seq=2, timestamp=200.0,
            rows=[ScorecardRow(model="m2", work_class="wg", score=0.9, samples=2)],
        )
        store.freeze(art2)

        loaded_before = store.read_latest()
        assert loaded_before is not None
        assert loaded_before.seq == 2

        art2_path = store._artifact_path("0000002")
        art2_path.write_text("{corrupt json!!!")
        assert art2_path.exists()

        now_loaded = store.read_latest()
        assert now_loaded is not None
        assert now_loaded.seq == 1
        assert now_loaded.rows[0].model == "m1"

    def test_corrupt_lkg_both_dead_returns_none(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")

        store.freeze(ScorecardArtifact(
            seq=1, timestamp=100.0,
            rows=[ScorecardRow(model="m1", work_class="wg", score=0.5, samples=1)],
        ))
        store.freeze(ScorecardArtifact(
            seq=2, timestamp=200.0,
            rows=[ScorecardRow(model="m2", work_class="wg", score=0.9, samples=2)],
        ))

        store._artifact_path("0000001").write_text("{bad")
        store._artifact_path("0000002").write_text("{bad")

        result = store.read_latest()
        assert result is None

    def test_read_at_seq(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")
        art = ScorecardArtifact(
            seq=5, timestamp=500.0,
            rows=[ScorecardRow(model="m1", work_class="wg", score=0.7, samples=3)],
        )
        store.freeze(art)
        loaded = store.read_at_seq(5)
        assert loaded is not None
        assert loaded.seq == 5
        assert loaded.rows[0].score == 0.7

        assert store.read_at_seq(99) is None

    def test_missing_pointer_returns_none(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "empty")
        assert store.read_latest() is None
        assert store.latest_seq() is None
        assert store.lkg_seq() is None

    def test_corrupt_pointer_file(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")
        store.freeze(ScorecardArtifact(seq=1, timestamp=1.0, rows=[]))
        (tmp_path / "scorecards" / "latest").write_text("not-a-number\n")
        loaded = store.read_latest()
        assert loaded is not None
        assert loaded.seq == 1

    def test_non_numeric_lkg_pointer_does_not_crash(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")
        store.freeze(ScorecardArtifact(
            seq=1, timestamp=1.0, rows=[],
            gate_pass=True, fail_on_revert_pass=True,
        ))
        (tmp_path / "scorecards" / "lkg").write_text("GARBAGE-NOT-A-NUMBER\n")

        loaded = store.read_latest()
        assert loaded is not None
        assert loaded.seq == 1

        assert store.lkg_seq() is None

    def test_garbage_lkg_pointer_and_bad_latest_returns_none(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")
        store.freeze(ScorecardArtifact(
            seq=1, timestamp=1.0, rows=[],
            gate_pass=False, fail_on_revert_pass=False,
        ))
        (tmp_path / "scorecards" / "lkg").write_text("xx-not-int\n")
        result = store.read_latest()
        assert result is None

    def test_non_numeric_latest_pointer_does_not_crash(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")
        store.freeze(ScorecardArtifact(
            seq=1, timestamp=1.0, rows=[],
            gate_pass=True, fail_on_revert_pass=True,
        ))
        store.freeze(ScorecardArtifact(
            seq=2, timestamp=2.0, rows=[],
            gate_pass=True, fail_on_revert_pass=True,
        ))
        (tmp_path / "scorecards" / "latest").write_text("ZZZ\n")
        loaded = store.read_latest()
        assert loaded is not None
        assert loaded.seq == 2
        assert store.latest_seq() is None

    def test_cold_start_no_good_returns_none(self, tmp_path: Path) -> None:
        store = ScorecardStore(tmp_path / "scorecards")
        store.freeze(ScorecardArtifact(
            seq=1, timestamp=1.0, rows=[],
            gate_pass=False, fail_on_revert_pass=False,
        ))
        assert store.lkg_seq() is None
        assert store.read_latest() is None
