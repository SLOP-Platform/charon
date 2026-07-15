"""FT-CONFIG-SURFACE — provider config must DECLARE a leg's free-tier limits
so QuotaTracker can be fed from config.

Acceptance contract (mirrors the ticket):

* A provider config with a ``free_tier`` block round-trips to the
  normalized limits dict QuotaTracker consumes — shape must match
  ``QuotaTracker(limits={provider: {rpm/tpm/rpd/tpd}})`` exactly.
* A bad limit (negative, non-int) is rejected at ``add_provider`` time.
* A config with NO ``free_tier`` block still loads (back-compat unlimited).
* FAIL-ON-REVERT: if the schema field is removed, the round-trip test fails
  because the config is dropped/errors and ``_load_free_tier_limits``
  returns no entry for the provider.

Note: the new free-tier accessors are underscore-prefixed because the
``charon.config`` package facade (``__init__.py``) is owned by a separate
ticket. They are still importable from the submodule directly:
    ``from charon.config.providers import _load_free_tier_limits``
"""
from __future__ import annotations

import pytest

from charon.config import providers as providers_mod
from charon.config.providers import (
    _free_tier_to_quota_limits,
    _load_free_tier_limits,
    add_provider,
)

# ── round-trip: config → QuotaTracker-shaped limits dict ─────────────


def test_free_tier_round_trip_full_block(monkeypatch, tmp_path):
    """All four rate keys + extras + reset/anchor survive a write+read cycle
    and ``_load_free_tier_limits`` projects to the QuotaTracker shape."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    block = {
        "rpm": 60,
        "rpd": 200,
        "tpm": 100_000,
        "tpd": 5_000_000,
        "weekly_tokens": 1_000_000,
        "monthly_tokens": 4_000_000,
        "reset": "calendar",
        "reset_anchor": "00:00",
    }
    add_provider("free-leg", base_url="https://api.example.com/v1",
                 free_tier=block)

    # persisted entry contains the full block (with extras + reset)
    persisted = providers_mod.load_providers()["free-leg"]
    assert persisted["free_tier"]["rpm"] == 60
    assert persisted["free_tier"]["rpd"] == 200
    assert persisted["free_tier"]["tpm"] == 100_000
    assert persisted["free_tier"]["tpd"] == 5_000_000
    assert persisted["free_tier"]["weekly_tokens"] == 1_000_000
    assert persisted["free_tier"]["monthly_tokens"] == 4_000_000
    assert persisted["free_tier"]["reset"] == "calendar"
    assert persisted["free_tier"]["reset_anchor"] == {"time": "00:00"}

    # _load_free_tier_limits projects to QuotaTracker shape: ONLY rate keys,
    # NOT weekly_tokens/monthly_tokens/reset/reset_anchor.
    limits = _load_free_tier_limits()
    assert "free-leg" in limits
    qt = limits["free-leg"]
    assert set(qt) == {"rpm", "rpd", "tpm", "tpd"}
    assert qt == {"rpm": 60, "rpd": 200, "tpm": 100_000, "tpd": 5_000_000}


def test_free_tier_round_trip_only_rpm(monkeypatch, tmp_path):
    """A minimal free_tier block with a single rate key still round-trips."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("rpm-only", base_url="https://rpm.example/v1",
                 free_tier={"rpm": 5})
    limits = _load_free_tier_limits()
    assert limits == {"rpm-only": {"rpm": 5}}


def test_free_tier_merges_with_existing_entry(monkeypatch, tmp_path):
    """An existing provider with base_url retains it when free_tier is added."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("dup", base_url="https://dup.example/v1", key_env="DUP_KEY")
    add_provider("dup", free_tier={"rpd": 10})
    entry = providers_mod.load_providers()["dup"]
    assert entry["base_url"] == "https://dup.example/v1"
    assert entry["key_env"] == "DUP_KEY"
    assert entry["free_tier"] == {"rpd": 10}
    assert _load_free_tier_limits() == {"dup": {"rpd": 10}}


def test_free_tier_zero_limit_is_valid(monkeypatch, tmp_path):
    """0 means "no requests" (hard block); still a valid int limit."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("blocked", free_tier={"rpm": 0})
    assert _load_free_tier_limits() == {"blocked": {"rpm": 0}}


# ── back-compat: no free_tier block → unlimited ──────────────────────


def test_provider_without_free_tier_loads_unlimited(monkeypatch, tmp_path):
    """A pre-existing provider with no free_tier block (back-compat case)
    loads cleanly and does NOT appear in the QuotaTracker limits dict."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("legacy", base_url="https://legacy.example/v1")
    assert providers_mod.load_providers()["legacy"] == {
        "base_url": "https://legacy.example/v1"
    }
    assert _load_free_tier_limits() == {}


def test_add_provider_without_free_tier_kwarg_keeps_existing(monkeypatch, tmp_path):
    """Calling add_provider with no free_tier kwarg (the old signature) is
    a no-op on the free_tier field — pre-existing free_tier is preserved."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("keep", free_tier={"rpm": 10})
    add_provider("keep", base_url="https://keep.example/v1")  # no free_tier kwarg
    entry = providers_mod.load_providers()["keep"]
    assert entry["free_tier"] == {"rpm": 10}
    assert entry["base_url"] == "https://keep.example/v1"


def test_empty_providers_file_loads_as_empty(monkeypatch, tmp_path):
    """A fresh config dir (no providers.json) returns {} from the loader."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    assert _load_free_tier_limits() == {}


# ── validation: bad limits are rejected ──────────────────────────────


def test_negative_limit_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="non-negative int"):
        add_provider("bad", free_tier={"rpm": -1})


def test_non_int_limit_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="non-negative int"):
        add_provider("bad", free_tier={"rpm": 1.5})
    with pytest.raises(ValueError, match="non-negative int"):
        add_provider("bad", free_tier={"rpd": "100"})


def test_bool_limit_rejected(monkeypatch, tmp_path):
    """``True`` / ``False`` are int subclasses in Python but never a
    meaningful rate limit — must be rejected explicitly."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="non-negative int"):
        add_provider("bad", free_tier={"rpm": True})


def test_unknown_free_tier_key_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="unknown keys"):
        add_provider("bad", free_tier={"bogus": 10, "rpm": 1})


def test_reset_must_be_rolling_or_calendar(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="reset must be one of"):
        add_provider("bad", free_tier={"rpm": 1, "reset": "hourly"})


def test_calendar_reset_no_anchor_defaults_to_utc_midnight(monkeypatch, tmp_path):
    """A ``calendar`` reset with no anchor is valid and resolves to UTC
    midnight — documented default. The anchor field is simply absent."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("cal", free_tier={"rpd": 1, "reset": "calendar"})
    entry = providers_mod.load_providers()["cal"]["free_tier"]
    assert entry["reset"] == "calendar"
    assert "reset_anchor" not in entry  # default = UTC midnight (no field)


def test_anchor_without_reset_rejected(monkeypatch, tmp_path):
    """An anchor with no reset kind is meaningless — must error."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="reset_anchor requires"):
        add_provider("bad", free_tier={"reset_anchor": "00:00"})


def test_calendar_anchor_accepts_hhmm(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("cal", free_tier={"rpd": 1, "reset": "calendar",
                                    "reset_anchor": "17:30"})
    assert providers_mod.load_providers()["cal"]["free_tier"]["reset_anchor"] == {
        "time": "17:30"
    }


def test_calendar_anchor_accepts_weekday_name(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("cal", free_tier={"rpd": 1, "reset": "calendar",
                                    "reset_anchor": "Monday"})
    assert providers_mod.load_providers()["cal"]["free_tier"]["reset_anchor"] == {
        "weekday": 0
    }


def test_calendar_anchor_accepts_day_of_month(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("cal", free_tier={"rpd": 1, "reset": "calendar",
                                    "reset_anchor": 1})
    assert providers_mod.load_providers()["cal"]["free_tier"]["reset_anchor"] == {
        "day_of_month": 1
    }


def test_calendar_anchor_rejects_garbage(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="reset_anchor"):
        add_provider("bad", free_tier={"rpd": 1, "reset": "calendar",
                                       "reset_anchor": "nope"})


def test_rolling_anchor_ignored(monkeypatch, tmp_path):
    """An anchor on a rolling reset is silently ignored — rolling windows
    don't have a calendar boundary."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("roll", free_tier={"rpm": 1, "reset": "rolling",
                                    "reset_anchor": "ignored"})
    entry = providers_mod.load_providers()["roll"]["free_tier"]
    assert entry["reset"] == "rolling"
    assert "reset_anchor" not in entry


def test_free_tier_must_be_dict(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="must be a dict"):
        add_provider("bad", free_tier=[1, 2, 3])  # type: ignore[arg-type]


# ── QuotaTracker-shape projection: direct unit test ─────────────────


def test_free_tier_to_quota_limits_strips_extras():
    """The projection strips weekly_tokens/monthly_tokens/reset/anchor —
    QuotaTracker's sliding-window model does not consume them."""
    block = {
        "rpm": 10,
        "tpm": 1000,
        "weekly_tokens": 999_999,
        "reset": "rolling",
    }
    assert _free_tier_to_quota_limits(block) == {"rpm": 10, "tpm": 1000}


def test_free_tier_to_quota_limits_empty_block():
    assert _free_tier_to_quota_limits({}) == {}


# ── FAIL-ON-REVERT guard ─────────────────────────────────────────────
#
# This test pins the contract: if the schema field is removed (revert),
# ``_load_free_tier_limits`` returns no entry for the provider, so the
# round-trip assertion fails.  The test depends on the persisted key
# "free_tier" — if the field is renamed/removed, persisted["free_tier"]
# would not exist and the test would fail.


def test_fail_on_revert_free_tier_field_removed(monkeypatch, tmp_path):
    """REVERT GUARD: if a future revert drops the ``free_tier`` field from
    providers.json, this test fails because the projected limits dict is
    empty for the configured provider."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    add_provider("pinned", base_url="https://pinned.example/v1",
                 free_tier={"rpm": 3, "rpd": 100})
    entry = providers_mod.load_providers()["pinned"]
    assert "free_tier" in entry, (
        "FAIL-ON-REVERT: the free_tier schema field was removed from "
        "add_provider persistence — re-add it or this contract is broken")
    assert _load_free_tier_limits() == {"pinned": {"rpm": 3, "rpd": 100}}
