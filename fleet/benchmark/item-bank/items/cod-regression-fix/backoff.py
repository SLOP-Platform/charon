"""backoff.py — backoff-clamp primitive to be fixed."""


def clamp(delay: float, max_delay: float, *, jitter: float = 0.0) -> float:
    """Cap `delay` to `max_delay`. If `jitter` > 0, the jitter offset
    is applied AFTER the cap (current behavior — the bug). The fix
    should apply the cap AFTER the jitter offset.

    CURRENT BUG: the cap is applied to the un-jittered delay, then
    jitter is added on top — so a jittered value can exceed `max_delay`.
    The seeded test in tests/test_backoff.py catches this."""
    capped = min(delay, max_delay)
    return capped + capped * jitter
