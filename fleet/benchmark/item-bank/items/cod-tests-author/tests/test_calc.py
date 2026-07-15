"""test_calc.py — regression test for the percent(5, 0) bug.

The test asserts the post-fix contract: percent(part, 0) must raise
ZeroDivisionError (the model is also expected to add it; if the model
adds the test and fixes the implementation, both pass)."""
import pytest

from calc import percent


def test_percent_normal():
    """Sanity: non-zero whole returns the correct percentage."""
    assert percent(25, 100) == 25.0
    assert percent(1, 4) == 25.0


def test_percent_zero_whole_raises():
    """The fix: percent(5, 0) MUST raise ZeroDivisionError, NOT return 0."""
    with pytest.raises(ZeroDivisionError):
        percent(5, 0)
