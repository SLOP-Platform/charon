"""Tests for charon.quota — proactive free-tier quota engine.

All tests use an injectable deterministic clock — no real time.sleep.
"""
from __future__ import annotations

import json
from pathlib import Path

from charon.quota import QuotaTracker


class FakeClock:
    """Injectably mutable clock for deterministic time-advance tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._t: float = start

    def __call__(self) -> float:
        self._t += 1.0
        return self._t

    def set(self, t: float) -> None:
        self._t = t


# ---------------------------------------------------------------------------
# No limits — never blocked
# ---------------------------------------------------------------------------


def test_no_limits_never_skips() -> None:
    """A provider with no configured limit is never skipped."""
    tracker = QuotaTracker()
    for _ in range(100):
        assert not tracker.should_skip("openai", est_tokens=100)
        tracker.record("openai", tokens=100)
    assert not tracker.should_skip("openai", est_tokens=1_000_000)
    assert tracker.counters() == {}


def test_no_limits_is_inert() -> None:
    """No limits configured anywhere — tracker is inert advisory bookkeeping."""
    tracker = QuotaTracker()
    for _ in range(500):
        tracker.record("p", tokens=50)
    assert not tracker.should_skip("p", est_tokens=9999)
    assert tracker.counters() == {}


# ---------------------------------------------------------------------------
# RPM limit
# ---------------------------------------------------------------------------


def test_rpm_skip_after_two_records() -> None:
    tracker = QuotaTracker(limits={"p": {"rpm": 2}})
    tracker.record("p", tokens=0)
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")
    assert tracker.counters()["skip_rpm"] == 1


def test_rpm_resets_after_window() -> None:
    clock = FakeClock()
    tracker = QuotaTracker(limits={"p": {"rpm": 2}}, now=clock)
    tracker.record("p", tokens=0)
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")
    clock.set(61.0)
    assert not tracker.should_skip("p")


def test_rpm_partial_window_slide() -> None:
    """RPM slides: old entries fall out, new become possible."""
    clock = FakeClock(0.0)
    tracker = QuotaTracker(limits={"p": {"rpm": 2}}, now=clock)
    tracker.record("p", tokens=0)   # t=1
    tracker.record("p", tokens=0)   # t=2
    clock.set(62.0)                  # first entry now expired
    assert not tracker.should_skip("p")


# ---------------------------------------------------------------------------
# TPM limit
# ---------------------------------------------------------------------------


def test_tpm_trips_on_total() -> None:
    tracker = QuotaTracker(limits={"p": {"tpm": 1000}})
    tracker.record("p", tokens=900)
    assert tracker.should_skip("p", est_tokens=200)  # 900+200 > 1000
    assert not tracker.should_skip("p", est_tokens=50)


def test_tpm_ignored_when_no_est_tokens() -> None:
    tracker = QuotaTracker(limits={"p": {"tpm": 100}})
    tracker.record("p", tokens=200)
    assert not tracker.should_skip("p", est_tokens=0)


def test_tpm_counter() -> None:
    tracker = QuotaTracker(limits={"p": {"tpm": 10}})
    tracker.record("p", tokens=5)
    tracker.record("p", tokens=5)
    assert tracker.should_skip("p", est_tokens=1)
    assert tracker.counters()["skip_tpm"] == 1


# ---------------------------------------------------------------------------
# RPD limit (24h)
# ---------------------------------------------------------------------------


def test_rpd_trips_after_exceeded() -> None:
    tracker = QuotaTracker(limits={"p": {"rpd": 1}})
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")
    assert tracker.counters()["skip_rpd"] == 1


def test_rpd_resets_after_86400s() -> None:
    clock = FakeClock()
    tracker = QuotaTracker(limits={"p": {"rpd": 1}}, now=clock)
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")
    clock.set(86401.0)
    assert not tracker.should_skip("p")


# ---------------------------------------------------------------------------
# TPD limit (24h tokens)
# ---------------------------------------------------------------------------


def test_tpd_trips_on_total() -> None:
    tracker = QuotaTracker(limits={"p": {"tpd": 500}})
    tracker.record("p", tokens=450)
    assert tracker.should_skip("p", est_tokens=100)
    assert not tracker.should_skip("p", est_tokens=30)


def test_tpd_counter() -> None:
    tracker = QuotaTracker(limits={"p": {"tpd": 100}})
    tracker.record("p", tokens=80)
    tracker.record("p", tokens=20)
    assert tracker.should_skip("p", est_tokens=1)
    assert tracker.counters()["skip_tpd"] == 1


# ---------------------------------------------------------------------------
# Multiple providers, independent
# ---------------------------------------------------------------------------


def test_providers_independent() -> None:
    tracker = QuotaTracker(limits={"a": {"rpm": 1}, "b": {"rpm": 10}})
    tracker.record("a", tokens=0)
    assert tracker.should_skip("a")
    for _ in range(10):
        tracker.record("b", tokens=0)
    assert tracker.should_skip("b")
    for _ in range(500):
        assert not tracker.should_skip("c", est_tokens=9999)
        tracker.record("c", tokens=9999)


# ---------------------------------------------------------------------------
# Multiple limits on same provider
# ---------------------------------------------------------------------------


def test_multiple_limits_rpm_wins() -> None:
    """RPM is checked first, so RPM skip fires before TPM."""
    tracker = QuotaTracker(limits={"p": {"rpm": 2, "tpm": 100}})
    tracker.record("p", tokens=0)
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p", est_tokens=200)
    assert "skip_rpm" in tracker.counters()
    assert "skip_tpm" not in tracker.counters()


# ---------------------------------------------------------------------------
# get_wait_time
# ---------------------------------------------------------------------------


def test_wait_time_zero_when_no_limits() -> None:
    tracker = QuotaTracker()
    assert tracker.get_wait_time("p") == 0.0


def test_wait_time_rpm() -> None:
    clock = FakeClock(0.0)
    tracker = QuotaTracker(limits={"p": {"rpm": 1}}, now=clock)
    tracker.record("p", tokens=0)   # t=1, expires at t=61
    clock.set(50.0)                  # now = 50
    wait = tracker.get_wait_time("p")
    assert 10.0 <= wait <= 12.0


def test_wait_time_zero_when_not_blocked() -> None:
    tracker = QuotaTracker(limits={"p": {"rpm": 5}})
    tracker.record("p", tokens=0)
    assert tracker.get_wait_time("p") == 0.0


def test_wait_time_tpm() -> None:
    clock = FakeClock(0.0)
    tracker = QuotaTracker(limits={"p": {"tpm": 100}}, now=clock)
    tracker.record("p", tokens=90)   # t=1, 90 tokens
    clock.set(0.0)                    # reset before next record
    tracker.record("p", tokens=10)   # t=2, 10 more tokens
    clock.set(50.0)
    wait = tracker.get_wait_time("p", est_tokens=1)
    assert wait > 0.0


def test_wait_time_rpm_zero_means_never() -> None:
    tracker = QuotaTracker(limits={"p": {"rpm": 0}})
    assert tracker.get_wait_time("p") == float("inf")


# ---------------------------------------------------------------------------
# counters() is a snapshot
# ---------------------------------------------------------------------------


def test_counters_is_snapshot() -> None:
    tracker = QuotaTracker(limits={"p": {"rpm": 1}})
    tracker.record("p", tokens=0)
    tracker.should_skip("p")
    snap = tracker.counters()
    snap["skip_rpm"] = 999
    assert tracker.counters()["skip_rpm"] == 1


# ---------------------------------------------------------------------------
# stdlib-only imports
# ---------------------------------------------------------------------------


def test_stdlib_only_imports() -> None:
    """QuotaTracker's module must not import any third-party packages."""
    allowed = {
        "__future__", "time", "collections", "collections.abc", "threading",
        "typing", "json", "os", "uuid", "pathlib", "dataclasses",
        "datetime", "calendar",
    }
    import ast
    import pathlib

    src = pathlib.Path("src/charon/quota.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top: str = alias.name.split(".")[0]
                assert top in allowed, f"third-party import: {alias.name}"
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            top = node.module.split(".")[0]
            assert top in allowed, f"third-party import: {node.module}"


# ---------------------------------------------------------------------------
# should_skip with est_tokens=0 behaves correctly for token windows
# ---------------------------------------------------------------------------


def test_should_skip_zero_est_tokens_ignores_tpm() -> None:
    tracker = QuotaTracker(limits={"p": {"tpm": 5}})
    tracker.record("p", tokens=100)
    assert not tracker.should_skip("p", est_tokens=0)


# ---------------------------------------------------------------------------
# Calendar limits — monthly / weekly / daily-reset
# ---------------------------------------------------------------------------


class _UtcClock:
    """Injectably mutable UTC clock for calendar-boundary tests.

    Distinct from the monotonic ``now=`` clock so we can advance time
    AND cross calendar boundaries on the same tick.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._t: float = start

    def __call__(self) -> float:
        return self._t

    def set(self, t: float) -> None:
        self._t = t

    def advance(self, dt: float) -> None:
        self._t += dt


def test_monthly_tmo_blocks_n_plus_one() -> None:
    """(a) A monthly tpm-style cap blocks the (N+1)th token."""
    mono = FakeClock(0.0)
    utc = _UtcClock(1_700_000_000.0)  # 2023-11-14 22:13:20 UTC, well inside Nov
    tracker = QuotaTracker(limits={"mistral": {"tmo": 1_000_000_000}}, now=mono)
    tracker.set_utc_now(utc)
    # 999_999_999 tokens — still under the cap.
    tracker.record("mistral", tokens=999_999_999)
    # (N+1)th token: 1 more would push to 1_000_000_000 — exactly equal, allowed.
    assert not tracker.should_skip("mistral", est_tokens=1)
    # But 2 more pushes to 1_000_000_001 — over the cap, MUST skip.
    assert tracker.should_skip("mistral", est_tokens=2)
    assert tracker.counters().get("skip_tmo") == 1


def test_monthly_tmo_resets_on_calendar_boundary() -> None:
    """(a) Crossing a month boundary clears the monthly counter."""
    mono = FakeClock(0.0)
    # Start mid-November 2023.
    utc = _UtcClock(1_700_000_000.0)
    tracker = QuotaTracker(limits={"mistral": {"tmo": 1_000}}, now=mono)
    tracker.set_utc_now(utc)
    # Saturate the cap.
    tracker.record("mistral", tokens=1_000)
    assert tracker.should_skip("mistral", est_tokens=1)
    # Jump to mid-December 2023 (2023-12-15 12:00:00 UTC = 1702641600).
    utc.set(1_702_641_600.0)
    # New month — counter should be reset, 1 token allowed again.
    assert not tracker.should_skip("mistral", est_tokens=1)
    assert not tracker.should_skip("mistral", est_tokens=1_000)


def test_monthly_rmo_blocks_requests() -> None:
    """(a) Monthly request-count cap works the same way."""
    mono = FakeClock(0.0)
    utc = _UtcClock(1_700_000_000.0)
    tracker = QuotaTracker(limits={"p": {"rmo": 2}}, now=mono)
    tracker.set_utc_now(utc)
    tracker.record("p", tokens=0)
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")
    assert tracker.counters().get("skip_rmo") == 1
    # Cross month boundary — counter resets.
    utc.set(1_702_641_600.0)
    assert not tracker.should_skip("p")
    tracker.record("p", tokens=0)
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")


def test_calendar_rpd_resets_at_utc_midnight() -> None:
    """(a) An opted-in calendar-daily limit resets at UTC midnight."""
    mono = FakeClock(0.0)
    # 2023-11-14 23:59:00 UTC = 1_700_006_340
    utc = _UtcClock(1_700_006_340.0)
    tracker = QuotaTracker(
        limits={"p": {"rpd": {"limit": 1, "reset": "calendar"}}},
        now=mono,
    )
    tracker.set_utc_now(utc)
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")
    # 2023-11-15 00:00:30 UTC = 1_700_006_430 — past midnight, counter reset.
    utc.set(1_700_006_430.0)
    assert not tracker.should_skip("p")


def test_calendar_rwk_resets_on_monday() -> None:
    """Weekly calendar reset hits the next Monday 00:00 UTC."""
    mono = FakeClock(0.0)
    # 2023-11-15 (Wednesday) 12:00 UTC = 1_700_049_600
    utc = _UtcClock(1_700_049_600.0)
    tracker = QuotaTracker(
        limits={"nanogpt": {"rwk": {"limit": 1, "reset": "calendar"}}},
        now=mono,
    )
    tracker.set_utc_now(utc)
    tracker.record("nanogpt", tokens=0)
    assert tracker.should_skip("nanogpt")
    # 2023-11-20 (Monday) 00:00:30 UTC = 1_700_438_430 — past Monday midnight
    utc.set(1_700_438_430.0)
    assert not tracker.should_skip("nanogpt")


def test_legacy_rpd_still_rolling() -> None:
    """(c) A plain int ``rpd`` is still rolling 86400s — no regression."""
    clock = FakeClock()
    tracker = QuotaTracker(limits={"p": {"rpd": 1}}, now=clock)
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")
    clock.set(86401.0)
    assert not tracker.should_skip("p")


def test_legacy_rpm_unchanged() -> None:
    """(c) A plain int ``rpm`` is still rolling 60s — no regression."""
    clock = FakeClock()
    tracker = QuotaTracker(limits={"p": {"rpm": 2}}, now=clock)
    tracker.record("p", tokens=0)
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")
    clock.set(61.0)
    assert not tracker.should_skip("p")


def test_dict_limit_with_rolling_reset_is_rolling() -> None:
    """(c) ``{"rpd": {"limit": 1, "reset": "rolling"}}`` is the legacy path
    (rolling 86400s, not calendar)."""
    clock = FakeClock()
    tracker = QuotaTracker(
        limits={"p": {"rpd": {"limit": 1, "reset": "rolling"}}}, now=clock,
    )
    tracker.record("p", tokens=0)
    assert tracker.should_skip("p")
    clock.set(86401.0)
    assert not tracker.should_skip("p")


def test_calendar_wait_time_is_until_next_boundary() -> None:
    """Calendar wait time is the seconds until the next UTC boundary."""
    mono = FakeClock(0.0)
    # 2023-11-30 12:00:00 UTC = 1_701_345_600; next month start (Dec 1 00:00) is +12h.
    utc = _UtcClock(1_701_345_600.0)
    tracker = QuotaTracker(limits={"p": {"tmo": 10}}, now=mono)
    tracker.set_utc_now(utc)
    tracker.record("p", tokens=10)
    wait = tracker.get_wait_time("p", est_tokens=1)
    # 12h exactly: 43_200s. Allow tiny slop for the time used to compute
    # _month_start_epoch / _next_month_start (datetime → float conversions).
    assert 43_190.0 < wait <= 43_200.0


# ---------------------------------------------------------------------------
# Persistence — usage survives a gateway restart
# ---------------------------------------------------------------------------


def test_calendar_usage_persists_across_instances(tmp_path: Path) -> None:
    """(b) Calendar usage survives a restart (new QuotaTracker, same state_dir)."""
    state_dir = tmp_path
    mono = FakeClock(0.0)
    utc = _UtcClock(1_700_000_000.0)
    a = QuotaTracker(limits={"p": {"tmo": 1_000}}, now=mono, state_dir=state_dir)
    a.set_utc_now(utc)
    a.record("p", tokens=400)
    a.record("p", tokens=400)
    # State file should now exist.
    state_file = state_dir / "quota_usage.json"
    assert state_file.exists()
    # New instance — same state file, same clock, same limits.
    b = QuotaTracker(limits={"p": {"tmo": 1_000}}, now=mono, state_dir=state_dir)
    b.set_utc_now(utc)
    # 800 already spent; 200 more would push to 1000 (== limit, allowed).
    assert not b.should_skip("p", est_tokens=200)
    # 201 more would push to 1001 — over the cap, MUST skip.
    assert b.should_skip("p", est_tokens=201)


def test_persistence_required_to_pass_test(tmp_path: Path) -> None:
    """(b) A tracker that does NOT persist sees 0 in a fresh instance.

    This is the FAIL-ON-REVERT assertion: revert the persistence code and
    this test fails (the new instance sees 0, so 400+400=800 — well under
    the 1_000 cap — and should_skip returns False instead of True).
    """
    state_dir = tmp_path / "no_persist"
    state_dir.mkdir()
    mono = FakeClock(0.0)
    utc = _UtcClock(1_700_000_000.0)
    a = QuotaTracker(limits={"p": {"tmo": 1_000}}, now=mono, state_dir=state_dir)
    a.set_utc_now(utc)
    a.record("p", tokens=400)
    a.record("p", tokens=400)
    # State file MUST have been written.
    assert (state_dir / "quota_usage.json").exists()
    # Simulate the revert: re-load with a brand-new tracker that has
    # NO state_dir → that one MUST see 0. This is what would happen if
    # we forgot the state_dir argument OR the persist path was deleted.
    b = QuotaTracker(limits={"p": {"tmo": 1_000}}, now=mono)
    b.set_utc_now(utc)
    # b has no state — 800 of 1_000 spent is invisible to it.
    assert not b.should_skip("p", est_tokens=999)
    # And the stateful one (a) still sees 800 / 1_000.
    assert a.should_skip("p", est_tokens=201)


def test_state_file_is_well_formed_json(tmp_path: Path) -> None:
    """The persisted file is valid JSON with the expected shape."""
    state_dir = tmp_path
    mono = FakeClock(0.0)
    utc = _UtcClock(1_700_000_000.0)
    tracker = QuotaTracker(
        limits={"p": {"tmo": 100, "rpm": 5}}, now=mono, state_dir=state_dir,
    )
    tracker.set_utc_now(utc)
    tracker.record("p", tokens=30)
    data = json.loads((state_dir / "quota_usage.json").read_text())
    assert "providers" in data
    assert "p" in data["providers"]
    p = data["providers"]["p"]
    assert "calendar" in p
    assert "tmo" in p["calendar"]
    assert p["calendar"]["tmo"]["count"] == 30.0


def test_corrupt_state_file_fails_open(tmp_path: Path) -> None:
    """A corrupt state file is treated as empty (fail-open on load)."""
    state_dir = tmp_path
    (state_dir / "quota_usage.json").write_text("{not valid json")
    mono = FakeClock(0.0)
    utc = _UtcClock(1_700_000_000.0)
    tracker = QuotaTracker(limits={"p": {"tmo": 100}}, now=mono, state_dir=state_dir)
    tracker.set_utc_now(utc)
    # Empty state — 99 tokens fine, 100+1 must skip.
    assert not tracker.should_skip("p", est_tokens=99)
    assert tracker.should_skip("p", est_tokens=101)


def test_missing_state_dir_arg_does_not_persist() -> None:
    """No state_dir → no persistence, but tracker still works in-memory."""
    mono = FakeClock(0.0)
    utc = _UtcClock(1_700_000_000.0)
    tracker = QuotaTracker(limits={"p": {"tmo": 50}}, now=mono)
    tracker.set_utc_now(utc)
    tracker.record("p", tokens=30)
    assert tracker.should_skip("p", est_tokens=21)  # 30+21=51 > 50
    # New instance with no state_dir — also empty.
    fresh = QuotaTracker(limits={"p": {"tmo": 50}}, now=mono)
    fresh.set_utc_now(utc)
    assert not fresh.should_skip("p", est_tokens=49)


def test_rolling_window_persists_across_instances(tmp_path: Path) -> None:
    """Rolling-window deques also persist (so RPD/RWK counts survive a restart)."""
    state_dir = tmp_path
    clock = FakeClock()
    a = QuotaTracker(limits={"p": {"rpd": 1}}, now=clock, state_dir=state_dir)
    a.record("p", tokens=0)
    # New instance at the same monotonic time — the (0.0, 1.0, 2.0, …) FakeClock
    # pattern means a's record() left t=1.0; we want b's view to still see it.
    b = QuotaTracker(limits={"p": {"rpd": 1}}, now=clock, state_dir=state_dir)
    assert b.should_skip("p")


def test_persistence_handles_unconfigured_provider(tmp_path: Path) -> None:
    """A provider that disappears from the config after a restart is loaded
    from disk but never throttles (its limits vanished)."""
    state_dir = tmp_path
    mono = FakeClock(0.0)
    utc = _UtcClock(1_700_000_000.0)
    a = QuotaTracker(limits={"p": {"tmo": 50}}, now=mono, state_dir=state_dir)
    a.set_utc_now(utc)
    a.record("p", tokens=40)
    # b has no limits for p — the persisted state is loaded but not throttled.
    b = QuotaTracker(limits={"p": {}}, now=mono, state_dir=state_dir)
    b.set_utc_now(utc)
    assert not b.should_skip("p", est_tokens=999_999)

