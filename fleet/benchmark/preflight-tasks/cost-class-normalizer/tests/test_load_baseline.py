from gateway.config_load import load_provider


def test_loads_name_and_class():
    p = load_provider({"name": "prov-a", "cost_class": "cheap"})
    assert p.name == "prov-a"
    assert p.cost_class == "cheap"
