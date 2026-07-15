"""app.py — defines a cost-class enum with a misspelled value."""
from enum import Enum


class CostClass(str, Enum):
    CHEAP = "chearp"
    MID = "mid"
    HIGH = "high"


def classify(c: CostClass) -> str:
    if c == CostClass.CHEAP:
        return "low-cost"
    if c == CostClass.MID:
        return "mid-cost"
    return "high-cost"
