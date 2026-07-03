"""Tests for QualityScorer — latency EWMA, reliability scoring, persistence,
thread safety."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from charon.quality_scorer import QualityScorer


def _make(tmp_path: Path) -> QualityScorer:
    return QualityScorer(state_dir=tmp_path)


def test_new_provider_default_score(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    assert qs.score("openai") == 0.5


def test_record_updates_latency_ewma(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    qs.record("p1", latency_ms=1000, success=True, tokens=10)
    expected = 0.34 * 1000.0 + 0.66 * 0.0
    assert qs._ensure("p1").latency_ewma_ms == pytest.approx(expected)

    qs.record("p1", latency_ms=2000, success=True, tokens=10)
    expected2 = 0.34 * 2000.0 + 0.66 * expected
    assert qs._ensure("p1").latency_ewma_ms == pytest.approx(expected2)


def test_record_increments_calls_and_successes(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    qs.record("p1", latency_ms=500, success=True, tokens=5)
    rec = qs._ensure("p1")
    assert rec.calls == 1
    assert rec.successes == 1


def test_record_failure_no_success_increment(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    qs.record("p1", latency_ms=500, success=False, tokens=5)
    rec = qs._ensure("p1")
    assert rec.calls == 1
    assert rec.successes == 0


def test_reliability_score_after_success(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    qs.record("p1", latency_ms=100, success=True, tokens=10)
    assert qs.score("p1") > 0.5


def test_reliability_score_after_failure(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    qs.record("p1", latency_ms=50_000, success=False, tokens=1)
    assert qs.score("p1") < 0.5


def test_score_clamped_to_zero(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    for _ in range(10):
        qs.record("p1", latency_ms=90_000, success=False, tokens=1)
    assert qs.score("p1") >= 0.0


def test_multiple_providers_independent(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    qs.record("alice", latency_ms=100, success=True, tokens=5)
    qs.record("bob", latency_ms=80_000, success=False, tokens=5)

    rec_a = qs._ensure("alice")
    rec_b = qs._ensure("bob")
    assert rec_a.calls == 1
    assert rec_a.successes == 1
    assert rec_b.calls == 1
    assert rec_b.successes == 0
    assert rec_a.latency_ewma_ms == pytest.approx(0.34 * 100)
    assert rec_b.latency_ewma_ms == pytest.approx(0.34 * 80_000)
    assert qs.score("alice") > 0.5
    assert qs.score("bob") < 0.5


def test_persistence_survives_reload(tmp_path: Path) -> None:
    qs1 = _make(tmp_path)
    qs1.record("p1", latency_ms=500, success=True, tokens=5)

    qs2 = QualityScorer(state_dir=tmp_path)
    assert qs2.score("p1") == pytest.approx(qs1.score("p1"))
    rec = qs2._ensure("p1")
    assert rec.calls == 1
    assert rec.successes == 1
    assert rec.latency_ewma_ms == pytest.approx(0.34 * 500)


def test_thread_safety_concurrent_records(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    errors: list[Exception] = []

    def do_record() -> None:
        for i in range(100):
            try:
                qs.record("ts", latency_ms=i % 1000, success=i % 3 != 0, tokens=1)
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=do_record) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    rec = qs._ensure("ts")
    assert rec.calls == 400


def test_ewma_converges_to_observed(tmp_path: Path) -> None:
    qs = _make(tmp_path)
    for _ in range(1000):
        qs.record("p1", latency_ms=500, success=True, tokens=1)
    assert qs._ensure("p1").latency_ewma_ms == pytest.approx(500.0, rel=0.1)
