"""test_refactor.py — verifies the rename was complete and consistent."""
import config
import routing
import meter
import providers


def test_config_definition_renamed():
    assert not hasattr(config.ProviderConfig, "cost_rank"), (
        "ProviderConfig.cost_rank must be renamed to price_rank"
    )
    assert hasattr(config.ProviderConfig, "price_rank"), (
        "ProviderConfig.price_rank is missing"
    )


def test_resolve_uses_new_name():
    p1 = config.ProviderConfig("a", 2, "mid", "url1")
    p2 = config.ProviderConfig("b", 1, "cheap", "url2")
    ordered = config._resolve_cost_rank([p1, p2])  # helper name unchanged
    assert ordered[0].price_rank == 1
    assert ordered[1].price_rank == 2


def test_routing_uses_new_name():
    p1 = config.ProviderConfig("a", 5, "high", "url1")
    p2 = config.ProviderConfig("b", 1, "cheap", "url2")
    assert routing.pick_cheapest([p1, p2]).name == "b"
    chain = routing.fallback_chain([p1, p2])
    assert chain[0].price_rank == 1


def test_meter_uses_new_name():
    p1 = config.ProviderConfig("a", 3, "mid", "url1")
    p2 = config.ProviderConfig("b", 1, "cheap", "url2")
    assert meter.billable_cost([p1, p2]) == {"a": 3, "b": 1}


def test_providers_uses_new_name():
    p1 = config.ProviderConfig("a", 5, "high", "url1")
    p2 = config.ProviderConfig("b", 2, "mid", "url2")
    p3 = config.ProviderConfig("c", 1, "cheap", "url3")
    aff = providers.affordable([p1, p2, p3], max_rank=2)
    assert {p.name for p in aff} == {"b", "c"}


def test_cost_class_unchanged():
    """cost_class must NOT have been renamed (only cost_rank -> price_rank)."""
    p = config.ProviderConfig("a", 1, "cheap", "url")
    assert p.cost_class == "cheap"
