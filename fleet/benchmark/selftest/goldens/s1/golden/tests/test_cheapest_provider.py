"""Baseline test. NOTE: the fixture list below is pre-sorted DESCENDING by
cost_rank, so providers[-1] (the buggy implementation) happens to equal the
true minimum for THIS specific input. This is the trap: a lazy fix that
doesn't add a test on an unsorted input leaves the bug uncaught.
"""
from gateway.providers import Provider, cheapest_provider


def test_cheapest_is_min_rank_presorted():
    providers = [
        Provider("gamma", "https://gamma.example", "strong", 3),
        Provider("beta", "https://beta.example", "strong", 2),
        Provider("alpha", "https://alpha.example", "cheap", 1),
    ]
    assert cheapest_provider(providers).name == "alpha"
