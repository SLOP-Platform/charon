"""Seeded behavioral test — encodes the required clamp. Must pass UNMODIFIED
after the product fix. Do not edit/skip/xfail/delete this file."""
from gateway.backoff import MAX_DELAY_S, clamp_delay


def test_early_attempts_grow_exponentially():
    assert clamp_delay(0) == 1
    assert clamp_delay(1) == 2
    assert clamp_delay(2) == 4


def test_delay_never_exceeds_ceiling():
    # attempt 10 would be 1024s unclamped; must be clamped to the ceiling.
    for attempt in range(0, 12):
        assert clamp_delay(attempt) <= MAX_DELAY_S
    assert clamp_delay(11) == MAX_DELAY_S
