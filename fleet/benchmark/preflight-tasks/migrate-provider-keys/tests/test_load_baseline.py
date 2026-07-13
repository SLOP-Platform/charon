from gateway.config_load import load_providers


def test_loads_two_providers():
    provs = load_providers()
    assert [p["name"] for p in provs] == ["prov-a", "prov-b"]
    assert all(p["base_url"].startswith("https://") for p in provs)
