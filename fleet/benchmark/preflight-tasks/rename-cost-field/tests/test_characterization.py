"""Golden characterization test — pins observable behavior across the rename.

Written against the PUBLIC functions (not the field name), so it must pass
unchanged before and after the rename. If any call site is missed, one of these
functions raises AttributeError and this suite goes red.
"""
from gateway.providers import Provider, cheapest
from gateway.routing import order_by_cost
from gateway.meter import rank_summary


def _fixture():
    return [Provider("b", 2), Provider("a", 1), Provider("c", 3)]


def test_cheapest():
    assert cheapest(_fixture()).name == "a"


def test_order():
    assert [p.name for p in order_by_cost(_fixture())] == ["a", "b", "c"]


def test_summary():
    assert rank_summary(_fixture()) == {"a": 1, "b": 2, "c": 3}
