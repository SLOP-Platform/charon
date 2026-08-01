from __future__ import annotations

import json
from datetime import datetime

import pytest

from charon.spend_limits import SpendLimiter


class _FrozenDatetime(datetime):
    frozen_year_month: str = "2026-07"

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        year, month = (int(p) for p in cls.frozen_year_month.split("-"))
        return datetime(year, month, 15, 12, 0, 0)


@pytest.fixture
def frozen_month(monkeypatch):
    monkeypatch.setattr("charon.spend_limits.datetime", _FrozenDatetime)
    yield _FrozenDatetime


# ── Contract (a): unpriced does NOT increase spent_usd ────────────────
# Revert → RED: the old code has no ``record_unpriced`` method at all,
# so the test fails with AttributeError on revert.

def test_unpriced_does_not_increment_spent_usd(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record_unpriced()
    assert lim.spent_usd == 0.0
    lim.record_unpriced()
    lim.record_unpriced()
    assert lim.spent_usd == 0.0


def test_unpriced_increments_count(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    assert lim.unpriced_count == 0
    lim.record_unpriced()
    assert lim.unpriced_count == 1
    lim.record_unpriced()
    lim.record_unpriced()
    assert lim.unpriced_count == 3


def test_unpriced_count_starts_at_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    assert lim.unpriced_count == 0


# ── Contract (b): free $0 records 0.0 (guard regression) ─────────────

def test_free_zero_cost_does_not_inflate_spent_usd(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record(0.0)
    lim.record(0.0)
    assert lim.spent_usd == 0.0


# ── Contract (c): real provider cost recorded verbatim ────────────────

def test_real_cost_recorded_verbatim(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record(0.05)
    lim.record(0.10)
    assert lim.spent_usd == pytest.approx(0.15)


# ── Contract (d): monthly_limit_usd re-read from disk, not clobbered ──
# Revert → RED: the old code never calls _reload_limit() inside check(),
# so the limit stays at the constructor value and is clobbered on save.

def test_cap_reloaded_from_disk_on_check(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record(10.0)

    spend_path = tmp_path / "spend.json"
    data = json.loads(spend_path.read_text())
    assert data["monthly_limit_usd"] == 100.0

    data["monthly_limit_usd"] = 200.0
    spend_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    dec = lim.check(30.0)
    assert dec.allowed is True
    assert dec.remaining == 160.0


def test_cap_not_clobbered_by_persist(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record(10.0)

    spend_path = tmp_path / "spend.json"
    data = json.loads(spend_path.read_text())
    data["monthly_limit_usd"] = 200.0
    spend_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    lim.check(5.0)
    lim.record(5.0)

    on_disk = json.loads(spend_path.read_text())
    assert on_disk["monthly_limit_usd"] == 200.0
    assert on_disk["spent_usd"] == 15.0


def test_zero_limit_still_reloaded_to_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=0.0)
    lim.record(5.0)

    spend_path = tmp_path / "spend.json"
    data = json.loads(spend_path.read_text())
    data["monthly_limit_usd"] = 50.0
    spend_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    dec = lim.check(10.0)
    assert dec.allowed is True
    assert dec.remaining == 35.0

    lim.record(10.0)
    dec2 = lim.check(40.0)
    assert dec2.allowed is False
    assert "cap exceeded" in dec2.reason


# ── Contract (e): ANTI-OVER-BLOCK ─────────────────────────────────────

def test_requests_flow_when_below_real_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(20.0)
    dec = lim.check(10.0)
    assert dec.allowed is True
    assert dec.remaining == 20.0


def test_requests_blocked_when_above_real_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(45.0)
    dec = lim.check(10.0)
    assert dec.allowed is False
    assert dec.remaining == 5.0


# ── Mixed: unpriced + real cost coexist ───────────────────────────────

def test_unpriced_and_real_cost_independent(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim.record_unpriced()
    lim.record(0.05)
    lim.record_unpriced()
    lim.record(0.10)
    assert lim.spent_usd == pytest.approx(0.15)
    assert lim.unpriced_count == 2


# ── Month reset resets unpriced count ─────────────────────────────────

def test_monthly_reset_resets_unpriced_count(monkeypatch, tmp_path, frozen_month):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    frozen_month.frozen_year_month = "2026-07"
    lim = SpendLimiter(monthly_limit_usd=100.0)
    lim._month_start = "2020-01"
    lim._unpriced_count = 7
    lim.record_unpriced()
    assert lim.unpriced_count == 1
    assert lim._month_start == "2026-07"


# ── Persistence round-trips unpriced_count ────────────────────────────

def test_unpriced_count_survives_reload(monkeypatch, tmp_path, frozen_month):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    frozen_month.frozen_year_month = "2026-07"
    lim1 = SpendLimiter(monthly_limit_usd=100.0)
    lim1._month_start = "2026-07"
    lim1.record_unpriced()
    lim1.record_unpriced()
    lim1.record(1.0)

    lim2 = SpendLimiter(monthly_limit_usd=100.0)
    assert lim2.unpriced_count == 2
    assert lim2.spent_usd == 1.0


def test_unpriced_count_persisted_to_file(monkeypatch, tmp_path, frozen_month):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    frozen_month.frozen_year_month = "2026-07"
    lim = SpendLimiter(monthly_limit_usd=200.0)
    lim._month_start = "2026-07"
    lim.record_unpriced()

    spend_path = tmp_path / "spend.json"
    data = json.loads(spend_path.read_text())
    assert data["unpriced_count"] == 1
    assert data["spent_usd"] == 0.0
