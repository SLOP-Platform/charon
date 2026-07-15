"""test_app.py — verifies the cost-class enum has the corrected value."""
from app import CostClass, classify


def test_cost_class_cheap_value():
    """The misspelled 'chearp' must be fixed to 'cheap'."""
    assert CostClass.CHEAP.value == "cheap", (
        f"CHEAP.value should be 'cheap' but is {CostClass.CHEAP.value!r}"
    )


def test_classify_cheap_returns_low_cost():
    """`classify(CostClass.CHEAP)` must return 'low-cost'."""
    assert classify(CostClass.CHEAP) == "low-cost"


def test_mid_and_high_unchanged():
    """Mid and High enum values should not be touched."""
    assert CostClass.MID.value == "mid"
    assert CostClass.HIGH.value == "high"
