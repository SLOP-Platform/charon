"""Tests for per-provider SpendLimiter — tracking, caps, backfill."""
from __future__ import annotations

import tempfile
from pathlib import Path

from charon.spend_limits import SpendLimiter


def _limiter(**kw) -> SpendLimiter:
    d = Path(tempfile.mkdtemp())
    return SpendLimiter(state_dir=d, **kw)


def test_per_provider_cap_blocks_when_exceeded():
    lim = _limiter(provider_limits={"deepseek": 1.0})
    lim.record(0.9, provider="deepseek")
    dec = lim.check(0.2, provider="deepseek")
    assert not dec.allowed
    assert "deepseek" in dec.reason


def test_per_provider_cap_allows_when_under():
    lim = _limiter(provider_limits={"deepseek": 1.0})
    lim.record(0.5, provider="deepseek")
    dec = lim.check(0.3, provider="deepseek")
    assert dec.allowed


def test_global_cap_unaffected_by_provider_tracking():
    lim = _limiter(monthly_limit_usd=5.0)
    lim.record(4.0, provider="deepseek")
    dec = lim.check(2.0, provider="openrouter")
    assert not dec.allowed
    assert "monthly spend cap exceeded" in dec.reason


def test_provider_spent_and_remaining():
    lim = _limiter(provider_limits={"deepseek": 10.0})
    lim.record(3.0, provider="deepseek")
    assert lim.provider_spent("deepseek") == 3.0
    assert lim.remaining(provider="deepseek") == 7.0


def test_spent_summary_contains_per_provider():
    lim = _limiter(provider_limits={"a": 5.0, "b": 10.0})
    lim.record(1.0, provider="a")
    lim.record(2.0, provider="b")
    s = lim.spent_summary()
    assert s["provider_spent"] == {"a": 1.0, "b": 2.0}
    assert s["provider_limits"] == {"a": 5.0, "b": 10.0}


def test_persistence_roundtrips_provider_spent():
    d = Path(tempfile.mkdtemp())
    lim1 = SpendLimiter(provider_limits={"x": 10.0}, state_dir=d)
    lim1.record(7.5, provider="x")
    lim2 = SpendLimiter(state_dir=d)
    assert lim2.provider_spent("x") == 7.5


def test_month_reset_clears_provider_spent():
    lim = _limiter(provider_limits={"a": 10.0})
    lim.record(5.0, provider="a")
    lim._month_start = "2026-07"  # force reset
    lim.record(1.0, provider="a")
    assert lim.provider_spent("a") == 1.0


def test_no_provider_tracking_when_provider_is_none():
    lim = _limiter(monthly_limit_usd=1.0)
    lim.record(0.5)
    assert lim.provider_spent("any") == 0.0
    assert lim.spent_summary()["provider_spent"] == {}
    assert lim.spent_summary()["total"] == 0.5


def test_provider_limits_config_rejects_non_positive():
    lim = _limiter(provider_limits={"valid": 5.0, "zero": 0.0})
    lim.record(10.0, provider="zero")
    dec = lim.check(1.0, provider="zero")
    assert dec.allowed  # 0.0 limit is treated as no limit


def test_check_without_provider_uses_global_only():
    lim = _limiter(monthly_limit_usd=2.0, provider_limits={"x": 100.0})
    lim.record(1.9)
    dec = lim.check(1.0)  # no provider passed
    assert not dec.allowed
    assert "monthly spend cap exceeded" in dec.reason


def test_provider_limits_returns_configured_limits():
    lim = _limiter(provider_limits={"a": 5.0, "b": 10.0})
    assert lim.provider_limits() == {"a": 5.0, "b": 10.0}
    # None provider → use global
    assert lim.remaining() == float("inf")


def test_parse_provider_limits():
    from charon.gateway import _parse_provider_limits
    assert _parse_provider_limits(None) == {}
    assert _parse_provider_limits([]) == {}
    assert _parse_provider_limits({"good": 5.0, "zero": 0.0, "bad": "nope"}) == {"good": 5.0}
