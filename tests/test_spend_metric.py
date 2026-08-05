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


# ═══════════════════════════════════════════════════════════════════════
# FAIL-CLOSED: an unreadable counter must REFUSE, never serve
# ═══════════════════════════════════════════════════════════════════════
# A spend file that exists but cannot be trusted used to be swallowed by a
# bare ``return`` in _load(), leaving spent_usd at 0.0 — an uncapped gateway
# wearing a cap's clothes. Absent file is NOT this case: that is a fresh
# install and legitimately starts at zero.


def _write_state(tmp_path, **fields):
    (tmp_path / "spend.json").write_text(json.dumps(fields), encoding="utf-8")


def test_corrupt_json_refuses_to_serve(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    (tmp_path / "spend.json").write_text("{not json at all", encoding="utf-8")
    lim = SpendLimiter(monthly_limit_usd=50.0)
    assert lim.state_unreadable is True
    dec = lim.check(0.01)
    assert dec.allowed is False
    assert "fail-closed" in dec.reason
    assert lim.remaining() == 0.0


def test_non_object_state_refuses_to_serve(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    (tmp_path / "spend.json").write_text("[1, 2, 3]", encoding="utf-8")
    lim = SpendLimiter(monthly_limit_usd=50.0)
    dec = lim.check(0.01)
    assert dec.allowed is False
    assert "fail-closed" in dec.reason


def test_nan_spent_on_disk_refuses_to_serve(monkeypatch, tmp_path):
    """``json.loads`` accepts a bare ``NaN`` literal. A NaN ``spent_usd``
    makes every ``projected > limit`` comparison False — the cap silently
    stops existing. Fail closed instead."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    (tmp_path / "spend.json").write_text(
        '{"spent_usd": NaN, "month_start": "2026-08", "monthly_limit_usd": 50.0}',
        encoding="utf-8",
    )
    lim = SpendLimiter(monthly_limit_usd=50.0)
    dec = lim.check(1.0)
    assert dec.allowed is False
    assert "finite" in dec.reason


def test_negative_spent_on_disk_refuses_to_serve(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    _write_state(tmp_path, spent_usd=-1000.0, month_start="2026-08",
                 monthly_limit_usd=50.0)
    lim = SpendLimiter(monthly_limit_usd=50.0)
    dec = lim.check(1.0)
    assert dec.allowed is False
    assert "non-negative" in dec.reason


def test_unreadable_state_refuses_even_with_no_cap_set(monkeypatch, tmp_path):
    """limit 0.0 means "no cap" — but an unreadable counter is a fault, and a
    fault must not be answered with unlimited spend."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    (tmp_path / "spend.json").write_text("}}}", encoding="utf-8")
    lim = SpendLimiter(monthly_limit_usd=0.0)
    dec = lim.check(999999.0)
    assert dec.allowed is False


def test_absent_state_is_not_a_fault(monkeypatch, tmp_path):
    """ANTI-OVER-BLOCK for the fail-closed latch: a fresh install has no file
    and must still serve."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    assert lim.state_unreadable is False
    assert lim.check(1.0).allowed is True


def test_unreadable_state_recovers_when_file_is_repaired(monkeypatch, tmp_path):
    """The latch must not stick: repair the file and traffic flows again."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    (tmp_path / "spend.json").write_text("garbage", encoding="utf-8")
    lim = SpendLimiter(monthly_limit_usd=50.0)
    assert lim.check(1.0).allowed is False
    _write_state(tmp_path, spent_usd=1.0, month_start="2026-08",
                 monthly_limit_usd=50.0)
    assert lim.check(1.0).allowed is True


# ═══════════════════════════════════════════════════════════════════════
# NaN / negative COST at record() time is an UNKNOWN, never a dollar total
# ═══════════════════════════════════════════════════════════════════════


def test_nan_cost_does_not_poison_the_counter(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(49.0)
    lim.record(float("nan"))
    assert lim.spent_usd == pytest.approx(49.0)
    # the cap still trips — it would not if NaN had been added
    assert lim.check(5.0).allowed is False


def test_nan_cost_counted_as_unpriced(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(float("inf"))
    assert lim.unpriced_count == 1
    assert lim.snapshot()["invalid_cost_count"] == 1


def test_negative_cost_never_lowers_spend(monkeypatch, tmp_path):
    """Under-reporting is a runaway with extra steps: a negative 'cost' must
    not buy back headroom under the cap."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(49.0)
    lim.record(-40.0)
    assert lim.spent_usd == pytest.approx(49.0)
    assert lim.check(5.0).allowed is False


# ═══════════════════════════════════════════════════════════════════════
# RESET: the corrupted August counter (arming step 2)
# ═══════════════════════════════════════════════════════════════════════


def test_reset_month_zeroes_the_counter(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    _write_state(tmp_path, spent_usd=1185.4428735774175, month_start="2026-08",
                 monthly_limit_usd=50.0)
    lim.check(0.01)
    assert lim.spent_usd == pytest.approx(1185.4428735774175)
    lim.reset_month(reason="corrupt August counter")
    assert lim.spent_usd == 0.0
    assert lim.unpriced_count == 0


def test_reset_preserves_the_discarded_value_for_audit(monkeypatch, tmp_path):
    """The corrupt total is not recoverable, but it is not memory-holed
    either — otherwise a reset is indistinguishable from a coverup."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    _write_state(tmp_path, spent_usd=1185.4428735774175, month_start="2026-08",
                 monthly_limit_usd=50.0)
    lim = SpendLimiter(monthly_limit_usd=50.0)
    rec = lim.reset_month(reason="corrupt August counter")
    assert rec["previous_spent_usd"] == pytest.approx(1185.4428735774175)
    assert rec["reason"] == "corrupt August counter"
    on_disk = json.loads((tmp_path / "spend.json").read_text())
    assert on_disk["spent_usd"] == 0.0
    assert on_disk["last_reset"]["previous_spent_usd"] == pytest.approx(
        1185.4428735774175
    )


def test_reset_survives_process_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    _write_state(tmp_path, spent_usd=1185.44, month_start="2026-08",
                 monthly_limit_usd=50.0)
    SpendLimiter(monthly_limit_usd=50.0).reset_month(reason="corrupt counter")
    lim2 = SpendLimiter(monthly_limit_usd=50.0)
    assert lim2.spent_usd == 0.0
    assert lim2.limit_usd == 50.0


def test_disk_triggered_reset_on_a_running_limiter(monkeypatch, tmp_path):
    """Arming step 2 with NO restart: the operator drops reset_requested into
    spend.json and the running limiter clears the corrupt counter."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    _write_state(tmp_path, spent_usd=1185.4428735774175, month_start="2026-08",
                 monthly_limit_usd=50.0)
    assert lim.check(1.0).allowed is False  # cap tripped by the corrupt number

    _write_state(tmp_path, spent_usd=1185.4428735774175, month_start="2026-08",
                 monthly_limit_usd=50.0, reset_requested=True,
                 reset_reason="corrupt August counter")
    dec = lim.check(1.0)
    assert dec.allowed is True          # counter cleared in-process
    assert lim.spent_usd == 0.0


def test_disk_triggered_reset_is_one_shot(monkeypatch, tmp_path):
    """The flag must clear, or every subsequent request would reset the
    counter and the cap could never accrue toward its limit."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    _write_state(tmp_path, spent_usd=100.0, month_start="2026-08",
                 monthly_limit_usd=50.0, reset_requested=True)
    lim.check(1.0)
    assert lim.spent_usd == 0.0
    on_disk = json.loads((tmp_path / "spend.json").read_text())
    assert on_disk.get("reset_requested") in (None, False)

    lim.record(40.0)
    lim.record(5.0)
    assert lim.spent_usd == pytest.approx(45.0)   # not re-zeroed
    assert lim.check(10.0).allowed is False       # cap accrues normally again


# ═══════════════════════════════════════════════════════════════════════
# ARMING SEQUENCE, END TO END: $50 cap against a reset counter
# ═══════════════════════════════════════════════════════════════════════


def test_arming_sequence_50_dollar_cap(monkeypatch, tmp_path):
    """Operator decision 2026-08-02: monthly_limit_usd = 50.00. Against the
    corrupt 1185.44 the cap refuses everything (an outage); after the reset it
    enforces at the boundary and NOT before it."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    _write_state(tmp_path, spent_usd=1185.4428735774175, month_start="2026-08",
                 monthly_limit_usd=50.0)
    lim = SpendLimiter(monthly_limit_usd=50.0)
    assert lim.check(0.01).allowed is False       # the outage this ticket avoids

    lim.reset_month(reason="corrupt August counter, not recoverable")

    lim.record(49.99)                              # just under
    assert lim.check(0.005).allowed is True        # still flows
    lim.record(0.02)                               # just over
    over = lim.check(0.01)
    assert over.allowed is False
    assert "monthly cap $50.00 reached" in over.reason
    assert "$50.01 spent" in over.reason


def test_cap_denial_is_loud_and_named(monkeypatch, tmp_path):
    """A silent refusal is indistinguishable from a dead provider. The reason
    string is what the client sees in the 402 body."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(50.0)
    dec = lim.check(1.0)
    assert dec.allowed is False
    assert "monthly cap $50.00 reached" in dec.reason
    assert "$50.00 spent" in dec.reason
    assert "cap exceeded" in dec.reason  # keeps the pre-existing contract


# ═══════════════════════════════════════════════════════════════════════
# PER-PROVIDER ATTRIBUTION ("which provider did we spend that on")
# ═══════════════════════════════════════════════════════════════════════


def test_spend_attributed_per_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(1.25, provider="openrouter")
    lim.record(0.75, provider="openrouter")
    lim.record(2.00, provider="groq")
    assert lim.per_provider == {"openrouter": pytest.approx(2.0),
                                "groq": pytest.approx(2.0)}
    assert lim.spent_usd == pytest.approx(4.0)


def test_per_provider_survives_reload(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(1.25, provider="openrouter")
    lim.record_unpriced(provider="cerebras")
    lim2 = SpendLimiter(monthly_limit_usd=50.0)
    assert lim2.per_provider["openrouter"] == pytest.approx(1.25)
    assert lim2.snapshot()["unpriced_by_provider"] == {"cerebras": 1}


def test_snapshot_surfaces_unpriced_beside_the_number(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=50.0)
    lim.record(1.0, provider="openrouter")
    lim.record_unpriced(provider="openrouter")
    lim.record_unpriced(provider="groq")
    snap = lim.snapshot()
    assert snap["spent_usd"] == pytest.approx(1.0)
    assert snap["unpriced_count"] == 2
    assert snap["monthly_limit_usd"] == 50.0
    assert snap["state_unreadable"] is False


# ═══════════════════════════════════════════════════════════════════════
# CLOBBER: record() must not write a stale cap back over an operator edit
# ═══════════════════════════════════════════════════════════════════════


def test_record_does_not_clobber_cap_without_a_prior_check(monkeypatch, tmp_path):
    """The original clobber bug: _save() persisted the constructor's limit.
    Reloading only inside check() leaves the hole open whenever a record()
    lands first — which is exactly what reverted a 50.0 edit to 0.0."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    lim = SpendLimiter(monthly_limit_usd=0.0)
    lim.record(1.0)
    data = json.loads((tmp_path / "spend.json").read_text())
    data["monthly_limit_usd"] = 50.0
    (tmp_path / "spend.json").write_text(json.dumps(data), encoding="utf-8")

    lim.record(1.0)   # no check() in between
    on_disk = json.loads((tmp_path / "spend.json").read_text())
    assert on_disk["monthly_limit_usd"] == 50.0
    assert lim.limit_usd == 50.0


def test_unusable_constructor_limit_raises(monkeypatch, tmp_path):
    """Coercing an unusable cap to 0.0 would silently mean 'no cap'."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        SpendLimiter(monthly_limit_usd=float("nan"))
    with pytest.raises(ValueError):
        SpendLimiter(monthly_limit_usd=-10.0)
