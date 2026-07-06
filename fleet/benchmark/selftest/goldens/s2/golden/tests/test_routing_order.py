from gateway.routing import select_provider


def test_select_provider_ascending_cost_rank():
    providers = select_provider("demo-model")
    names = [p["name"] for p in providers]
    # Hardcoded against the REAL models.json content (prov-a=1, prov-b=2,
    # prov-c=3) - a mutation of the file must break this expectation.
    assert names == ["prov-a", "prov-b", "prov-c"]
