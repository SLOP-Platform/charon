from unittest import mock
from gateway.routing import select_provider


def test_select_provider_ascending_cost_rank_mocked():
    with mock.patch("gateway.routing.load_models") as m:
        m.return_value = {"demo-model": {"providers": [
            {"name": "prov-a", "cost_rank": 1},
            {"name": "prov-b", "cost_rank": 2},
            {"name": "prov-c", "cost_rank": 3},
        ]}}
        providers = select_provider("demo-model")
        ranks = [p["cost_rank"] for p in providers]
        assert ranks == sorted(ranks)
