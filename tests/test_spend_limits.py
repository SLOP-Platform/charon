from __future__ import annotations

import concurrent.futures
import json
from datetime import datetime

import pytest

from charon.spend_limits import SpendLimiter


class _FrozenDatetime(datetime):
    """A ``datetime`` subclass that always reports ``frozen_year_month`` as
    ``strftime('%Y-%m')`` regardless of the real wall clock.

    ``SpendLimiter._ensure_month_reset`` calls ``datetime.now().strftime('%Y-%m')``
    on the module-local ``datetime`` class. Replacing the module reference with
    this subclass lets each test pin the month the limiter sees without touching
    the real clock, so the assertions cannot fail simply because the calendar
    rolled forward (the AMBIENT-COUPLED-TESTS bug). ``__init__``/``now`` return
    a regular ``datetime`` instance — only the ``strftime`` shim is overridden —
    so arithmetic, comparison, and JSON serialization all keep working.
    """

    frozen_year_month: str = "2026-07"

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        year, month = (int(p) for p in cls.frozen_year_month.split("-"))
        return datetime(year, month, 15, 12, 0, 0)


@pytest.fixture
def frozen_month(monkeypatch):
    """Pin the clock ``SpendLimiter`` sees to a specific ``YYYY-MM`` for the
    duration of the test. The clock is held in UTC by freezing the day to the
    15th at noon — far enough from any month boundary that time-zone offset
    (-12, +14, etc.) cannot push it across a month boundary either.
    Use the optional ``request``-style capture via a module-level
    ``_freeze_to`` variable when the test wants a non-default month.
    """
    monkeypatch.setattr("charon.spend_limits.datetime", _FrozenDatetime)
    yield _FrozenDatetime


def test_check_allowed_within_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    decision = lim.check(50.0)
    assert decision.allowed is True
    assert decision.remaining == 50.0


def test_check_denied_over_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record(80.0)
    decision = lim.check(30.0)
    assert decision.allowed is False
    assert decision.remaining == 20.0


def test_check_denied_exact_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record(100.0)
    decision = lim.check(0.01)
    assert decision.allowed is False


def test_record_accumulates(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record(10.0)
    lim.record(20.0)
    assert lim._spent_usd == 30.0


def test_remaining_returns_available(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record(30.0)
    assert lim.remaining() == 70.0


def test_unlimited_when_limit_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=0.0)
    decision = lim.check(999999.0)
    assert decision.allowed is True
    assert decision.remaining == float("inf")
    assert lim.remaining() == float("inf")


def test_monthly_reset(monkeypatch, tmp_path, frozen_month):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # Pin the wall clock to a known month (2026-07) so the reset exercise is
    # independent of the calendar the test runs on. Then set _month_start to a
    # strictly earlier month so the reset on the next check() is guaranteed to
    # fire — without depending on the real clock being in some other month.
    frozen_month.frozen_year_month = "2026-07"
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim._spent_usd = 50.0
    lim._month_start = "2020-01"
    decision = lim.check(10.0)
    assert lim._spent_usd == 0.0
    assert lim._month_start == "2026-07"
    assert decision.allowed is True
    assert decision.remaining == 90.0


def test_persistence_survives_reload(monkeypatch, tmp_path, frozen_month):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    frozen_month.frozen_year_month = "2026-07"
    lim1 = SpendLimiter(monthly_limit_usd=100.0)
    lim1._month_start = "2026-07"
    lim1.record(42.0)

    lim2 = SpendLimiter(monthly_limit_usd=100.0)
    assert lim2._spent_usd == 42.0
    assert lim2._month_start == "2026-07"


def test_atomic_write(monkeypatch, tmp_path, frozen_month):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    frozen_month.frozen_year_month = "2026-07"
    lim = SpendLimiter(monthly_limit_usd=200.0)
    lim._month_start = "2026-07"
    lim.record(5.0)

    spend_path = tmp_path / "spend.json"
    assert spend_path.exists()
    data = json.loads(spend_path.read_text())
    assert data["spent_usd"] == 5.0
    assert data["monthly_limit_usd"] == 200.0
    assert data["month_start"] == "2026-07"


def test_reason_on_denial(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(50.0)
    decision = lim.check(1.0)
    assert decision.allowed is False
    assert "cap exceeded" in decision.reason


def test_thread_safety_concurrent_records(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=1000.0)

    def record_many(n: int):
        for _ in range(n):
            lim.record(1.0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(record_many, 100) for _ in range(4)]
        for f in futures:
            f.result()

    assert lim._spent_usd == 400.0


def test_no_config_file_uses_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    assert lim._spent_usd == 0.0
    assert lim.remaining() == 100.0
