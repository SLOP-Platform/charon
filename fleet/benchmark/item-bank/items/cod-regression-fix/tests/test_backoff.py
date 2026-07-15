"""test_backoff.py — SEEDED RED spec test. Do NOT modify.

The test asserts the contract the FIX must satisfy: the cap is applied
AFTER the jitter offset (not before). The current `backoff.clamp` does
the opposite, so the test reds today. The model fixes backoff.py to
make this test green — without modifying the test itself.
"""
from backoff import clamp


def test_no_jitter_default_unchanged():
    """The no-jitter path must keep its prior contract."""
    assert clamp(10.0, 100.0) == 10.0
    assert clamp(150.0, 100.0) == 100.0


def test_jitter_under_cap():
    """delay=10, jitter=0.5 -> jittered=15 -> below cap -> returns 15."""
    assert clamp(10.0, 100.0, jitter=0.5) == 15.0


def test_jitter_above_cap():
    """delay=80, jitter=0.5 -> jittered=120 -> exceeds cap=100 -> returns 100.
    This is the regression: previously the cap was applied to the
    un-jittered delay, returning 80, and 80 + 80*0.5 = 120 was returned
    unconstrained. The fix enforces the cap on the jittered value."""
    assert clamp(80.0, 100.0, jitter=0.5) == 100.0


def test_jitter_at_cap_boundary():
    """delay=66.66, jitter=0.5 -> jittered=100.0 (approx) -> at cap -> 100.
    Tolerant of float noise: anything in [99.99, 100.0] is acceptable."""
    out = clamp(66.66, 100.0, jitter=0.5)
    assert 99.99 <= out <= 100.0 + 1e-9, f"got {out}, expected ~100"
