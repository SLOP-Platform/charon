from gateway.providers import Provider, dedupe_providers


def test_no_duplicates_passthrough():
    provs = [Provider("a", 1), Provider("b", 2)]
    assert [p.name for p in dedupe_providers(provs)] == ["a", "b"]
