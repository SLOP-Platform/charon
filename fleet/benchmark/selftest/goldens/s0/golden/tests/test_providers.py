from gateway.providers import VALID_COST_CLASSES


def test_cheap_class_spelled_correctly():
    assert "cheap" in VALID_COST_CLASSES
    assert "chearp" not in VALID_COST_CLASSES
