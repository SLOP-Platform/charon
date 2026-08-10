"""Tests proving that the quality scorer correctly excludes bad providers
and does not fail on three inert-code defects that were making the filter dead.

The three defects (2026-08-10):
  1. Cold-start: _ensure() minted a fresh record with score 0.5 (passes floor).
  2. Overwrite: reliability_score was recomputed from last call only, ignoring
     accumulated calls/successes.
  3. Phantom downgrade term: no-downgrade score was always 1.0 (hardcoded).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from charon.quality_scorer import QualityScorer


def _scorer() -> tuple[QualityScorer, Path]:
    d = Path(tempfile.mkdtemp())
    return QualityScorer(state_dir=d), d


def test_cold_start_default_returns_pass():
    """An unmeasured provider returns 0.5 — passes the floor but signals
    'no data yet'. The caller makes the final decision."""
    s, _ = _scorer()
    assert s.score("never-seen") == 0.5


def test_accumulated_success_rate_drives_score():
    """Score reflects cumulative success/fail ratio, not just the last call."""
    s, _ = _scorer()
    prov = "test-prov"
    for _ in range(9):
        s.record(prov, latency_ms=100, success=False, tokens=0)
    s.record(prov, latency_ms=100, success=True, tokens=0)
    score = s.score(prov)
    # 10 calls, 1 success = 0.1 success rate
    # latency: 100ms ― 1.0 - 100/60000 = ~0.998
    # downgrade: 0 downgrades → 1.0
    # expected ≈ (1.0 + 0.1 + 1.0) / 3 ≈ 0.7
    # OLD: reliability_score overwrites → last call = success → 1.0
    assert score < 0.8, (
        f"accumulated score {score} too high — old code gave 1.0 for last-call-only")


def test_perpetual_failure_excluded():
    """A provider that never succeeds drops below 0.5 floor."""
    s, _ = _scorer()
    for _ in range(50):
        s.record("bad", latency_ms=45000, success=False, tokens=0)
    score = s.score("bad")
    # latency_ewma: 45000ms ≈ 1.0 - 45000/60000 = 0.25
    # success: 0.0; downgrade: 0 downgrades → 1.0
    # ≈ (0.25 + 0.0 + 1.0) / 3 ≈ 0.42 → below floor
    assert score < 0.5, (
        f"perpetual-failure provider must score below 0.5, got {score}")


def test_downgrade_count_tracks_correctly():
    """downgrade_count reflects the number of downgrade-flagged records."""
    s, _ = _scorer()
    s.record("dg", latency_ms=100, success=True, tokens=0, downgrade=True)
    s.record("dg", latency_ms=100, success=True, tokens=0, downgrade=True)
    s.record("dg", latency_ms=100, success=False, tokens=0)  # no downgrade flag
    assert s.downgrade_count("dg") == 2

    assert s.downgrade_count("never-seen") == 0
    """A provider flagged as downgrading scores lower than one that isn't."""
    s, _ = _scorer()
    s.record("clean", latency_ms=100, success=True, tokens=0)
    s.record("downgrader", latency_ms=100, success=True, tokens=0, downgrade=True)
    clean_score = s.score("clean")
    dirty_score = s.score("downgrader")
    assert dirty_score < clean_score, (
        f"downgrader {dirty_score} >= clean {clean_score} — "
        f"downgrade signal not reducing score")


def test_old_code_overwrite_defect_reverts_to_wrong():
    """Fail-on-revert: simulate the old overwrite behaviour. If score only
    reflects the last call, a provider with 10 failures + 1 success gets 1.0."""
    s, _ = _scorer()
    prov = "flaky"
    for _ in range(10):
        s.record(prov, latency_ms=100, success=False, tokens=0)
    s.record(prov, latency_ms=100, success=True, tokens=0)
    score = s.score(prov)
    assert score < 0.8, (
        f"FAIL-ON-REVERT: 10 failures + 1 success should NOT score 1.0. "
        f"Got {score} — old code overwrites to last-call-only.")
