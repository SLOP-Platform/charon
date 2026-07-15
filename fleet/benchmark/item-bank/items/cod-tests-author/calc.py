"""calc.py — the buggy implementation the model must fix."""


def percent(part: float, whole: float) -> float:
    """Return `part / whole * 100` as a percentage. The current
    implementation swallows ZeroDivisionError and returns 0 — a
    footgun, since a missing-data case becomes indistinguishable from
    a genuine 0% result. The fix must let ZeroDivisionError propagate
    so the caller can handle it explicitly."""
    try:
        return (part / whole) * 100
    except ZeroDivisionError:
        return 0
