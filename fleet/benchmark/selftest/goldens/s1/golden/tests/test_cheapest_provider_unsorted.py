from gateway.providers import Provider, cheapest_provider


def test_cheapest_is_min_rank_unsorted():
    providers = [
        Provider("mid", "https://mid.example", "strong", 5),
        Provider("cheapest", "https://cheapest.example", "cheap", 1),
        Provider("last", "https://last.example", "strong", 9),
    ]
    assert cheapest_provider(providers).name == "cheapest"
