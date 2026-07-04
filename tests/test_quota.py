"""Tests for charon.quota — proactive sliding-window quota tracker.

All tests use an injectable deterministic clock — no real time.sleep.
"""
from __future__ import annotations

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
        "typing",
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
