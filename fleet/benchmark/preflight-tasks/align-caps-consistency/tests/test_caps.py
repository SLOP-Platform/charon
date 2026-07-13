from gateway.caps import daily_cap, monthly_cap


def test_monthly_equals_plan_ceiling():
    assert monthly_cap() == 100


def test_monthly_equals_thirty_days():
    assert monthly_cap() == daily_cap() * 30
