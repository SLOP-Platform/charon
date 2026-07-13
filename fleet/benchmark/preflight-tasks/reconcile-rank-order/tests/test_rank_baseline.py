from gateway.rank import Provider, rank_providers


def test_orders_by_cost_rank():
    provs = [Provider("b", 2), Provider("a", 1), Provider("c", 3)]
    assert [p.name for p in rank_providers(provs)] == ["a", "b", "c"]
