from gateway.providers import Provider, cheapest


def test_cheapest():
    assert cheapest([Provider("b", 2), Provider("a", 1)]).name == "a"
