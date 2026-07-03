from __future__ import annotations

import concurrent.futures
import json

from charon.spend_limits import SpendLimiter


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


def test_monthly_reset(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim._spent_usd = 50.0
    lim._month_start = "2020-01"
    decision = lim.check(10.0)
    assert lim._spent_usd == 0.0
    assert decision.allowed is True
    assert decision.remaining == 90.0


def test_persistence_survives_reload(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim1 = SpendLimiter(monthly_limit_usd=100.0)
    lim1._month_start = "2026-07"
    lim1.record(42.0)

    lim2 = SpendLimiter(monthly_limit_usd=100.0)
    assert lim2._spent_usd == 42.0
    assert lim2._month_start == "2026-07"


def test_atomic_write(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
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
