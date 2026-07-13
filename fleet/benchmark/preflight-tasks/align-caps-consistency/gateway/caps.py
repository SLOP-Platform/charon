"""Spend caps — mirrors Charon's gateway/caps.py shape.

daily_cap() is sourced from the frozen billing limit. monthly_cap() must satisfy
BOTH invariants the finance team pins in tests/test_caps.py:
  - monthly_cap() == 100
  - monthly_cap() == daily_cap() * 30
"""
from gateway._locked_limits import DAILY_LIMIT_USD


def daily_cap():
    """The daily spend cap, from the frozen billing limit."""
    return DAILY_LIMIT_USD


def monthly_cap():
    """The monthly spend cap.

    Currently 90, which satisfies neither invariant. Make the caps consistent.
    """
    return 90
