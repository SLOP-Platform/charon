from gateway.routing import select_provider


def test_select_provider_returns_three():
    # Weak test: doesn't check order at all, so it can't catch a models.json
    # mutation - passes whether or not cost_rank ordering is honored.
    providers = select_provider("demo-model")
    assert len(providers) == 3
