"""Retry backoff — mirrors Charon's gateway/backoff.py shape.

clamp_delay() computes an exponential backoff delay and is supposed to clamp it
to MAX_DELAY_S so a request never waits longer than the ceiling.

BUG: it returns the raw exponential delay without clamping, so large attempt
counts blow past MAX_DELAY_S. tests/test_backoff.py pins the required ceiling.
"""

BASE_DELAY_S = 1
MAX_DELAY_S = 30


def clamp_delay(attempt):
    """Return the backoff delay (seconds) for a 0-based retry `attempt`.

    BUG: not clamped to MAX_DELAY_S.
    """
    return BASE_DELAY_S * (2 ** attempt)
